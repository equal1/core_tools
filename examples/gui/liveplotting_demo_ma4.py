
from functools import partial
import numpy as np
import PyQt5
import qcodes
from qcodes.data.io import DiskIO
from qcodes.data.data_set import DataSet
from qcodes.parameters import DelegateParameter

from core_tools.GUI.keysight_videomaps.liveplotting import liveplotting, set_data_saver
from core_tools.GUI.keysight_videomaps.data_saver.qcodes import QCodesDataSaver
from core_tools.GUI.keysight_videomaps.data_getter.scan_generator_OPX import fake_digitizer
from core_tools.GUI.qt_util import qt_init

from pulse_lib.base_pulse import pulselib

from core_tools.drivers.gates import gates as Gates
from core_tools.drivers.hardware.hardware import hardware as Hardware

from core_tools.GUI.virt_gate_matrix_qml.gui_controller import (
    virt_gate_matrix_GUI as VirtGateMatrixGUI,
)
from core_tools.GUI.param_viewer.param_viewer_GUI_main import (
    param_viewer as ParamViewerGUI,
)


# %%

#start_all_logging()
#logger.get_file_handler().setLevel(logging.DEBUG)

try:
    qcodes.Instrument.close_all()
except: pass

class DummyGates(qcodes.Instrument):
    def __init__(self, name, gates, v_gates):
        super().__init__(name)
        self.gates = gates
        self.v_gates = v_gates
        self._voltages = {}

        for gate_name in gates + v_gates:
            self.add_parameter(gate_name,
                               set_cmd=partial(self._set, gate_name),
                               get_cmd=partial(self._get, gate_name),
                               unit="mV")
            self._voltages[gate_name] = 0.0

    def get_idn(self):
        return {}

    def _set(self, gate_name, value):
        print(f'{gate_name}: {value:5.2f} mV')
        self._voltages[gate_name] = value

    def _get(self, gate_name):
        return self._voltages[gate_name]

    def get_gate_voltages(self):
        res = {}
        for gate_name in self.gates + self.v_gates:
            res[gate_name] = f'{self.get(gate_name):.2f}'
        return res


class DummyAwg(qcodes.Instrument):
    def __init__(self, name):
        super().__init__(name)

    def get_idn(self):
        return {}

    def awg_flush(self, ch):
        pass

    def release_waveform_memory(self):
        pass


def create_pulse_lib(awgs):
    pulse = pulselib()

    for awg in awgs:

        pulse.add_awg(awg)

        # define channels
        #chs = ['HG13b', 'HG11b', 'HG09b', 'Vds', 'Vcm'] #['Vgs13', 'Vgs11', 'Vgs09', 'vVds', 'vVcm']
        #chs = [] #['Vgs13', 'Vgs11', 'Vgs09', 'vVds', 'vVcm']
        chs =  ["HG13b", "HG11b", "HG09b", "HG07b", "HG12b"]
        for ch in chs:
            pulse.define_channel(ch, awg.name, ch)

    pulse.finish_init()
    return pulse





station = qcodes.Station()


# QDACII driver
from qcodes_contrib_drivers.drivers.QDevil import QDAC2
# OPX driver
from qualang_tools.external_frameworks.qcodes.opx_driver import OPX

# host: router IP address, port: 11+ last 3 dig of OPX
#opx = OPX(config, name="OPX_alice", host="opx-sc-001", port='11253', close_other_machines=False)
# opx = OPX(config, name="OPX_alice", host="opx-sc-001", port='11253', close_other_machines=True)
# #Add the OPX instrument to the QCoDeS station
# station.add_component(opx)





qdac2_addr = 'qdac-sc-001'
qdac2 = QDAC2.QDac2('QDAC', visalib='@py', address=f'TCPIP::{qdac2_addr}::5025::SOCKET')
# Create duplicates of the QDAC2 parameters from qdac2.ch<N>.dc_constant_V  to  qdac2.dac<N>
# this is needed because the Gate function assumes that the SPIRACK is being used 
# which uses parameters with a name 'dac<N>' with values in mV
for i in range(1,1+24):
    qdac2.add_parameter(    
        name=f'dac{i}',
        parameter_class=qcodes.DelegateParameter,
        source=qdac2.channel(i).dc_constant_V,
        label=f'dac{i}',
        unit='mV',
        scale=0.001,
    )
    
# Add the QDAC2 instrument to the QCoDeS station
station.add_component(qdac2)


class FakeDac(qcodes.Instrument):
    """ nonexisting dac instrument for holding virtual parameters Vcm Vds etc"""
    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)
        for i in range(1,1+24):
            self.add_parameter(    
                name=f'dac{i}',
                parameter_class=qcodes.ManualParameter,
                initial_value=0.0,
                unit='mV',
            )
    def get_idn(self):
        return { "vendor": "FakeWare",  "model": "DAC24", "serial": None, "firmware": None,  }

fdac1 = FakeDac('fdac1')
station.add_component(fdac1)

#qt_init()

########## Static Gate Stuff  ################################################################
hw = Hardware("hardware")
# hw.dac_gate_map = {
#     "B5": (0, 1),
#     "B6": (0, 2),
#     "SD2P": (0, 3),
#     # "A4": (0, 4),
#     # "S3EDSR": (0, 5),
#     # "A1": (0, 6),
#     "SD1P": (0, 7),
#     # "O2": (0, 8),
#     # "A2": (0, 9),
#     # "O1b": (0, 10),
#     # "O1": (0, 11),
#     "B0": (1, 10),
#     "B1": (0, 13),
#     "P1": (0, 12),
#     "P2": (1, 9),
#     # "L1": (0, 14),
#     "SD1B2": (0, 15),
#     "SD1B1": (0, 16),
#     "P3": (1, 2),
#     "B3": (1, 3),
#     "P4": (1, 4),
#     "B4": (1, 5),
#     "P5": (1, 6),
#     # "L4": (1, 7),
#     "B2": (1, 8),  # , range: 4v bi
#     "P6": (1, 11),
#     # "O3": (1, 12),
#     # "O4": (1, 13),
#     # "A3": (1, 14),
#     "SD2B1": (1, 1),
#     "SD2B2": (1, 15),
#     # "S1": (2, 1),
#     # "S2": (2, 2),
#     # "S4": (2, 3),
# }  # connect the appropriate dac ports via the matrix module to your device


hw.dac_gate_map = {
    'Varactor_ctl': (0,10),  
    # 'Vcm'         : (0,20),
    # 'Vds'         : (0,21),
    # 'Vgs09'       : (0,22),
    # 'Vgs11'       : (0,23),
    # 'Vgs13'       : (0,24),
    'HG13b'       : (0,13),
    'HG11b'       : (0,11),
    'HG09b'       : (0,12),
    'HG07b'       : (0,14),
    'HG12b'       : (0,15),
}

# The signals Vcm, Vds, Vgs09, Vgs11, Vgs13, are really 'virtual'
# signals. But they have been implemented here as real signals. 
# These signals  are mapped to unused dac channels on the QDAC2. 
# This means that along with the other signals they retain their 
# last voltage values when the software terminates, and when a 
# new session is started the signals do not need to be initialized.

# Currently the virtual gate mapping functions require that an
# SQL database is operational such that the virtual gate values 
# are remembered from one session to the next. We don't have SQL
# running so mapping all signals to real hardware channels

# But they are mapped to real channels on the QDAC2 



# mV limits
hw.boundaries = {name: (-10000, +10000) for name in hw.dac_gate_map}

v_gate_names = ["Vgs13", "Vgs11", "Vgs09", "Vds", "Vcm"]
gate_names = ["HG13b", "HG11b", "HG09b", "HG07b", "HG12b"]
#assert all(name in hw.dac_gate_map for name in v_gate_names)  # not sure this is needed or why it was required (ma)
# P1, P2 = M * (P1, P2)

# In the case of the Alpha3 Vcm and Vds offset voltages the 
# Matrix to go from virtual voltages to real voltages is simple
# but we need to use the inverse matrix for the pulse_lib functions
# (note pulse.add_virtual_matrix( real2virtual=False) does not seem to work)
v2r_VirtGateMatrix = [
    # Vgs13    Vgs11    Vgs09    Vds     Vcm
    [  1,        0,       0,      0,      1  ],   # HG13b
    [  0,        1,       0,      0,      1  ],   # HG11b
    [  0,        0,       1,      0,      1  ],   # HG09b
    [  0,        0,       0,    +0.5,     1  ],   # HG07b
    [  0,        0,       0,    -0.5,     1  ],   # HG12b
] 
r2v_VirtGateMatrix = np.linalg.inv(v2r_VirtGateMatrix)

hw.virtual_gates.add(
    "v_gates",
    gates=gate_names,
    virtual_gates=v_gate_names,
    matrix = r2v_VirtGateMatrix,
)
#gates = Gates("gates", hardware=hw, dac_sources=[d5a_1, d5a_2, d5a_3], dc_gain={})
gates = Gates("gates", hardware=hw, dac_sources=[qdac2,fdac1], dc_gain={})

# Define how the Vcm updates the other gates
# gate2 =  gate*mult + gate1*mult1 + ofs
# HG07b =  Vds * 0.5 + Vcm   + ofs

# TODO Peters LikedParameter could be used to do this
gates.dependant_gate_map = {
#    gate              mult    gate1     mult1     ofs    gate2
#     V                  V         V       V        V      V
    'Vcm'         :  [[ 1.0,  'Vgs09',   1.0 ,   0.0,   'HG09b'],  # changing Vcm will update HG09b
                      [ 1.0,  'Vgs11',   1.0 ,   0.0,   'HG11b'],  # changing Vcm will update HG11b
                      [ 1.0,  'Vgs13',   1.0 ,   0.0,   'HG13b'], # changing Vcm will update HG13b
                      [ 1.0,  'Vds',    +0.5 ,   0.0,   'HG07b'], # changing Vcm will update HG07b
                      [ 1.0,  'Vds',    -0.5 ,   0.0,   'HG12b']], # changing Vcm will update HG12b

    'Vds'         :  [[+0.5,  'Vcm',     1.0 ,   0.0,   'HG07b'],  # changing Vds will update HG07b
                      [-0.5,  'Vcm',     1.0 ,   0.0,   'HG12b']], # changing Vds will update HG12b

    'Vgs09'       :  [[ 1.0,  'Vcm',     1.0 ,    0.0,   'HG09b']], # changing Vgs09 will update HG09b
    'Vgs11'       :  [[ 1.0,  'Vcm',     1.0 ,    0.0,   'HG11b']], # changing Vgs11 will update HG11b
    'Vgs13'       :  [[ 1.0,  'Vcm',     1.0 ,    0.0,   'HG13b']], # changing Vgs13 will update HG13b
} 




# gates['Varactor_ctl'](7070)
# gates.Varactor_ctl(9800)
# print(f"{gates['Varactor_ctl']()=}")

######################################################################################

# setup QCODES data storage
path = 'C:/Projects/test_data'
io = DiskIO(path)
DataSet.default_io = io
set_data_saver(QCodesDataSaver())

#station = qcodes.Station()

# Create a dummy OPXQDAC AWG for performing the OPX sweeps
awg = DummyAwg(f'SWPQDAC')
awgs = [awg]
station.add_component(awg)


dig = fake_digitizer("fake_digitizer")  # creates a Multiparamter containing parameters chan_1, chan_2 of shape tuple([(20,20)]*2)
station.add_component(dig)


# use AWG2 for real and AWG3 for virtual gates. (It's all fake)
# gates = DummyGates('gates',
#                    [f'AWG2_{ch}' for ch in range(1,5)],
#                    [f'AWG3_{ch}' for ch in range(1,5)])
station.add_component(gates)

pulse = create_pulse_lib(awgs)

pulse.add_virtual_matrix(
    name="AWG_VirtGateMatrix",
    #real_gate_names= ["Vgs13", "Vgs11", "Vgs09", "vVds", "vVcm"],  
    #virtual_gate_names=["HG13b", "HG11b", "HG09b", "Vds", "Vcm"],
    real_gate_names=    ["HG13b", "HG11b", "HG09b", "HG07b", "HG12b"],
    virtual_gate_names= ["Vgs13", "Vgs11", "Vgs09", "Vds", "Vcm"],  
    #as a temporary solution we define the matrix manually, ideally we should take the input from the one defined in the GUI
    #should be smthg like VirtGateMatrixGUI()
    matrix=r2v_VirtGateMatrix,
    real2virtual=False,  # If True v_real = M^-1 @ v_virtual else v_real = M @ v_virtual ## not sure this is doing anything the way i'm using it!
    filter_undefined=False,
    keep_squared=True,
)

settings = {
    'gen':{
        '2D_colorbar':True,
        '2D_cross':True,
        'max_V_swing': 500,
        },
    '1D':{
        'offsets':{'AWG3_1': 10.0},
        },
    '2D':{

        "gate1_name": "Vgs13",
        "V1_swing": 100.0,  # mV
        "gate2_name": "Vgs11",
        "V2_swing": 330.0,  # mV


        'offsets':{
            'Vgs13': 500,
            'Vgs11': 800,
            },
        },
    }

# By starting the Qt app before running the liveplotting function
# we cause the liveplotting function to exit and defer the running
# the app.exec() mainloop. This allows the running of the ParamViewerGui
app = PyQt5.QtWidgets.QApplication([])
plotting = liveplotting(pulse, dig, "OPX", settings, iq_mode='I+Q', gates=gates)
param_viewer = ParamViewerGUI(gates_object=gates, max_diff=10000)
app.exec()



# ALL SETTIMGS:
#settings = {
#    '1D': {
#        'gate_name': 'vP1',
#        'V_swing': 20.0,
#        'npt': 100,
#        't_meas': 25.0,
#        'average': 200,
#        'offsets':{'AWG3_1': 10.0},
#        },
#    '2D': {
#        'gate1_name': 'vP1',
#        'V1_swing': 20.0,
#        'gate2_name': 'vP2',
#        'V2_swing': 10.0,
#        'npt': 100,
#        't_meas': 25.0,
#        'average': 200,
#        'offsets':{'AWG3_1': 10.0},
#        },
#    'gen': {
#        'n_columns': 2,
#        '2D_colorbar':True,
#        '2D_cross':True,
#        'max_V_swing': 250,
#        }
#    }




plotting._2D_gate2_name.setCurrentIndex(1)
plotting._2D_t_meas.setValue(1)
plotting._2D_V1_swing.setValue(100)
plotting._2D_npt.setValue(80)


# %%
