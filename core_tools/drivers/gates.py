import copy
import json
import logging
import os
from functools import partial

import numpy as np
import qcodes as qc

from core_tools import __version__ as ct_version
from core_tools.drivers.hardware.hardware import hardware as hw_parent

logger = logging.getLogger(__name__)


class gates(qc.Instrument):
    """
    gates class, generate qcodes parameters for the real gates and the virtual gates
    It also manages the virtual gate matrix.
    """

    def __init__(self, name, hardware, dac_sources, dc_gain={}):
        """
        gates object
        args:
            name (str) : name of the instrument
            hardware (class) : class describing the instrument
            dac_sources (list<virtual_dac>) : list with the dacs
            dc_gain (Dict[str,float]) : DC gain factors to compensate for.

        Notes:
            DC gain is the value of the external amplification factor.
            dc_gain = {'P1': 4.0} means P1 has an external amplification of 4.0.
            The DAC output will be set to v_gate/4.0.

            To avoid accidents, DC gain cannot be changed at run-time.
        """
        super(gates, self).__init__(name)

        if not isinstance(hardware, hw_parent):
            logger.info("Detected old hardware class")

        self.hardware = hardware
        self.dc_gain = dc_gain.copy()

        # keep a reference to the raw dac instrument per gate. Needed when
        # the instrument has no `dacN` parameter (e.g. OPX channels).
        self._dac_instruments = {}
        self._dac_params = {}
        self._cached_gate_voltages: dict[str, float] = {}
        self._gv = dict()
        self._real_gates = list()
        self._virtual_gates = list()
        self._virt_gate_convertors = list()
        self._all_gate_names = list()

        # add gates:
        for gate_name, dac_location in self.hardware.dac_gate_map.items():
            source_index, ch_num = dac_location[0], dac_location[1]
            instrument = dac_sources[source_index]

            # Some instruments (e.g. OPX) do not expose a `dacN` parameter that
            # can be read from. In that case store `None` and keep the raw
            # instrument so we can still call its `set` method later on.
            param_name = f"dac{int(ch_num)}"
            if (
                hasattr(instrument, "parameters")
                and param_name in instrument.parameters
            ):
                self._dac_params[gate_name] = instrument.parameters[param_name]
            else:
                self._dac_params[gate_name] = None
            self._dac_instruments[gate_name] = instrument

            self._all_gate_names.append(gate_name)
            self._real_gates.append(gate_name)
            self.add_parameter(
                gate_name,
                set_cmd=partial(self._set_voltage, gate_name),
                get_cmd=partial(self._get_voltage, gate_name),
                unit="mV",
            )

        # make virtual gates:
        for virt_gate_set in self.hardware.virtual_gates:
            virt_gate_convertor = virt_gate_set.get_view(available_gates=self._all_gate_names)
            self._virt_gate_convertors.append(virt_gate_convertor)
            virtual_gates = virt_gate_convertor.virtual_gates
            unknown_gates = [name for name in virt_gate_set.virtual_gate_names if name not in virtual_gates]
            self._all_gate_names += virtual_gates
            self._virtual_gates += virtual_gates
            for name in unknown_gates:
                print(f"WARNING: unknown gate '{name}' defined in matrix '{virt_gate_set.name}'")
            for v_gate_name in virtual_gates:
                self.add_parameter(v_gate_name,
                                   set_cmd=partial(self._set_voltage_virt, v_gate_name, virt_gate_convertor),
                                   get_cmd=partial(self._get_voltage_virt, v_gate_name, virt_gate_convertor),
                                   unit="mV")

        self._projection_cache_matrices = []
        self._projection_cache_projection = None

    def get_idn(self):
        return dict(vendor='CoreTools',
                    model='gates',
                    serial='',
                    firmware=ct_version)

    @property
    def gates(self):
        return list(self._real_gates)

    @property
    def v_gates(self):
        return list(self._virtual_gates)

    def _set_voltage(self, gate_name, voltage):
        """
        set a voltage to the dac
        Args:
            voltage (double) : voltage to set
            gate_name (str) : name of the gate to set
        """
        if gate_name in self.hardware.boundaries.keys():
            min_voltage, max_voltage = self.hardware.boundaries[gate_name]
            if voltage < min_voltage or voltage > max_voltage:
                raise ValueError(f"Voltage boundaries violated, trying to set gate {gate_name} to {voltage:.1f} mV.\n"
                                 f"The limit is set to {min_voltage} to {max_voltage} mV.")

        if gate_name in self.dc_gain:
            dac_voltage = voltage / self.dc_gain[gate_name]
            logger.info(f"set {gate_name} {voltage:.1f} mV (DAC:{dac_voltage:.1f} mV)")
        else:
            dac_voltage = voltage
            logger.info(f"set {gate_name} {voltage:.1f} mV")

        dac_location = self.hardware.dac_gate_map[gate_name]
        instrument = self._dac_instruments.get(gate_name)

        param = self._dac_params[gate_name]
        if param is None:
            if instrument is None or not hasattr(instrument, "set"):
                raise AttributeError(
                    f"Instrument for gate {gate_name} does not expose a parameter or set method"
                )
            channel = int(dac_location[1])
            instrument.set(f"dac{channel}", dac_voltage)
            if len(dac_location) >= 3:
                instrument.set(f"dac{int(dac_location[2])}", dac_voltage)
        else:
            param(dac_voltage)
            if len(dac_location) >= 3:
                ch2 = int(dac_location[2])
                param_name2 = f"dac{ch2}"
                if (
                    instrument is not None
                    and hasattr(instrument, "parameters")
                    and param_name2 in instrument.parameters
                ):
                    instrument.parameters[param_name2](dac_voltage)
                elif instrument is not None and hasattr(instrument, "set"):
                    instrument.set(param_name2, dac_voltage)

        self._cached_gate_voltages[gate_name] = voltage

    def _get_voltage(self, gate_name):
        """
        get a voltage to the dac
        Args:
            gate_name (str) : name of the gate to get
        """
        param = self._dac_params[gate_name]
        if param is None:
            return self._cached_gate_voltages.get(gate_name, 0.0)

        voltage = param.cache()
        if gate_name in self.dc_gain:
            voltage = voltage * self.dc_gain[gate_name]

        self._cached_gate_voltages[gate_name] = voltage
        return voltage

    def _set_voltage_virt(self, gate_name, virt_gate_convertor, voltage):
        """
        set a voltage to the virtual dac
        Args:
            voltage (double) : voltage to set
            gate_name : name of the virtual gate
        """
        old_voltages = self.get_all_gate_voltages()
        projection = self.get_virtual_gate_projection()
        delta = voltage - old_voltages[gate_name]
        logger.info(f"set {gate_name} {old_voltages[gate_name]:.1f} -> {voltage:.1f} mV")

        try:
            for real_gate, ratio in projection[gate_name].items():
                self.parameters[real_gate].set(old_voltages[real_gate] + ratio * delta)
        except Exception as ex:
            logger.warning(
                f"Failed to set virtual gate voltage to {voltage:.1f} mV; Reverting all voltages. "
                f"Exception: {ex}"
            )
            for real_gate, ratio in projection[gate_name].items():
                self.parameters[real_gate].set(old_voltages[real_gate])
            raise

    def _get_voltage_virt(self, gate_name, virt_gate_convertor):
        '''
        get a voltage to the virtual dac
        Args:
            gate_name : name of the virtual gate
        '''
        return self.get_all_gate_voltages()[gate_name]

    def _get_voltages(self, gates):
        return [self.get(gate_name) for gate_name in gates]

    def set_all_zero(self):
        '''
        set all dacs in the gate set to 0. Is ramped down 1 per 1
        '''
        print("In progress ..")
        for gate_name, dac_location in self.hardware.dac_gate_map.items():
            self.parameters[gate_name].set(0)
        print("All gates set to 0!")

    @property
    def gv(self) -> dict[str, float]:
        '''Returns voltages of all real gates.
        '''
        for gate_name, my_dac_location in self.hardware.dac_gate_map.items():
            self._gv[gate_name] = self._get_voltage(gate_name)

        return copy.copy(self._gv)

    @gv.setter
    def gv(self, gate_voltages: dict[str, float]):
        '''
        Set gate voltages
        '''
        for name, voltage in gate_voltages.items():
            self._set_voltage(name, voltage)

    def get_gate_voltages(self) -> dict[str, str]:
        res = {}
        for gate_name in self._all_gate_names:
            v = self.get(gate_name)
            res[gate_name] = f'{v:.2f}'
        return res

    def get_all_gate_voltages(self) -> dict[str, float]:
        """ Returns voltages of real and virtual gates.

        NOTE:
            Also sets all cached values for virtual gates used in snapshot!
        """
        v = {}
        for name in self._real_gates:
            v_real = self._get_voltage(name)
            v[name] = v_real
            self.parameters[name].cache.set(v_real)

        for virt_gate_convertor in self._virt_gate_convertors:
            real_voltages = [v[name] for name in virt_gate_convertor.real_gates]
            virtual_voltages = np.matmul(virt_gate_convertor.r2v_matrix, real_voltages)
            for vg_name, vg_voltage in zip(virt_gate_convertor.virtual_gates, virtual_voltages):
                v[vg_name] = vg_voltage
                self.parameters[vg_name].cache.set(vg_voltage)

        return v

    def get_virtual_gate_projection(self):
        '''
        Returns a dictionary with per virtual gate name a dictionary
        with real gate names and multipliers.
        Example:
             'vP1': {'P1': 1.0, 'P2': -0.12},
             'vP2': {'P1': -0.10, 'P2': 1.0},
        '''
        # cache physical channels and matrices. Do not recompute if nothing changed.
        if (len(self._virt_gate_convertors) == len(self._projection_cache_matrices)):
            for i, vm in enumerate(self._virt_gate_convertors):
                if not np.array_equal(vm.r2v_matrix, self._projection_cache_matrices[i]):
                    break
            else:
                # nothing has changed.
                return self._projection_cache_projection

        gates = list(self._real_gates)
        projection_matrix = np.eye(len(gates))

        for vm in self._virt_gate_convertors:

            real_gates = vm.real_gates
            v2r = np.linalg.inv(vm.r2v_matrix)
            # select real gate columns from projection matrix
            col_indices = [gates.index(gate) for gate in real_gates]
            m = projection_matrix[:, col_indices]
            # multiply and concatenate
            p_new = m @ v2r

            projection_matrix = np.concatenate([projection_matrix, p_new], axis=-1)
            # add virtual gates to gate list
            gates += vm.virtual_gates

        # return map
        result = {}
        for i, gate in enumerate(gates):
            if gate in self._real_gates:
                # Only project virtual gates to physical gates. Skip real gates.
                continue
            gate_values = {}
            result[gate] = gate_values
            for j, real_gate in enumerate(self._real_gates):
                value = projection_matrix[j, i]
                if np.abs(value) > 1e-5:
                    gate_values[real_gate] = value

        self._projection_cache_matrices = []
        for vm in self._virt_gate_convertors:
            self._projection_cache_matrices.append(vm.r2v_matrix.copy())
        self._projection_cache_projection = result

        return result

    def snapshot_base(self, update=False, params_to_skip_update=None):
        # update real and virtual gates cached values by getting them.
        self.get_all_gate_voltages()

        return super().snapshot_base(update, params_to_skip_update)

    def save(self, filename: str, mode: str = "real"):
        """Saves gate voltages to file in json format.
        Args:
            filename: file to write to.
            mode: "real", "virtual" or "real and virtual" for gates to save.
        """
        if mode not in ["real", "virtual", "real and virtual"]:
            raise ValueError(f"Unknown mode '{mode}'")
        gate_voltages = self.get_all_gate_voltages()
        if mode == "real":
            for gate in self._virtual_gates:
                del gate_voltages[gate]
        if mode == "virtual":
            for gate in self._real_gates:
                del gate_voltages[gate]

        dir_name = os.path.dirname(filename)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(filename, "w") as fp:
            json.dump(gate_voltages, fp, indent=2)

    def load(
            self,
            filename: str,
            mode: str = "real",
            gate_names: list[str] | None = None,
            max_delta: float = 100,
            min_delta: float = 0.01,
            force: bool = False,
    ):
        """Loads gate voltages from file (json format).

        A confirmation will be asked before applying the voltages, unless `force` is True.

        Args:
            filename: file to read from.
            mode: "real" or "virtual" for gates to set.
            gate_names: specific gates to set. Ignores `mode`.
            max_delta:
                maximum allowed voltage difference in mV when setting gates.
                No gate will be set if any gate exceeds the specified maximum delta.
            min_delta:
                minimum difference in mV to apply voltage. This is a threshold to avoid
                changing voltage with less than DAC resolution.
            force: If True applies voltages without asking confirmation.

        Notes:
            If a gate voltage is not specified in the file it will be ignored.
        """
        if mode not in ["real", "virtual"]:
            raise ValueError(f"Unsuported mode '{mode}'")

        if gate_names is None:
            if mode == "real":
                gate_names = self._real_gates
            else:
                gate_names = self._virtual_gates

        current_voltages = self.get_all_gate_voltages()
        with open(filename, "r") as fp:
            new_voltages = json.load(fp)

        changed_gates: list[str] = []
        for name in gate_names:
            if name not in new_voltages:
                print(f"gate {name} not specified in file")
                continue
            abs_delta = abs(current_voltages[name] - new_voltages[name])
            if abs_delta > max_delta:
                raise Exception(f"Voltage change for gate {name} from {current_voltages[name]:.2f} mV to "
                                f"{new_voltages[name]:.2f} exceeds delta of {max_delta:.2f} mV")
            if abs_delta > min_delta:
                changed_gates.append(name)
        for name in changed_gates:
            print(f"gate {name}: {current_voltages[name]:7.2f} mV -> {new_voltages[name]:7.2f}")
        if len(changed_gates) == 0:
            print("No differences with current voltages")
        else:
            if force or confirm("Apply these voltages?"):
                for name in changed_gates:
                    self.parameters[name].set(new_voltages[name])


def confirm(prompt_text):
    """
    Ask user to enter Y or N (case-insensitive).
    :return: True if the answer is Y.
    :rtype: bool
    """
    answer = "_"
    while answer not in ["", "y", "n"]:
        answer = input(prompt_text + ' [y]/n').lower()
    return answer == "y" or answer == ''
