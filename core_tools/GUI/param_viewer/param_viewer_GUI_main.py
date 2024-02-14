# -*- coding: utf-8 -*-
from typing import Optional
from core_tools.GUI.param_viewer.param_viewer_GUI_window import Ui_MainWindow
from PyQt5 import QtCore, QtWidgets
import qcodes as qc
from dataclasses import dataclass
from ..qt_util import qt_log_exception

import logging

logger = logging.getLogger(__name__)


@dataclass
class param_data_obj:
    param_parameter: any
    gui_input_param: any
    division: any


class param_viewer(QtWidgets.QMainWindow, Ui_MainWindow):

    def __init__(self, gates_object: Optional[object] = None,
                 max_diff: float = 1000,
                 keysight_rf: Optional[object] = None,
                 locked=False):
        self.real_gates = list()
        self.virtual_gates = list()
        self.rf_settings = list()
        self.station = qc.Station.default
        self.max_diff = max_diff
        self.keysight_rf = keysight_rf
        self.locked = locked
        self.real_gates_qt_voltage_input = dict()

        if gates_object:
            self.gates_object = gates_object
        else:
            try:
                self.gates_object = self.station.gates
            except AttributeError:
                raise ValueError('`gates` must be set in qcodes.station or supplied as argument')
        self._step_size = 1  # [mV]
        instance_ready = True

        # set graphical user interface
        self.app = QtCore.QCoreApplication.instance()
        if self.app is None:
            instance_ready = False
            self.app = QtWidgets.QApplication([])

        super(QtWidgets.QMainWindow, self).__init__()
        self.setupUi(self)

        # add RF parameters
        if hasattr(self.gates_object.hardware, 'RF_source_names'):
            for src_name in self.gates_object.hardware.RF_source_names:
                inst = getattr(self.station, src_name)
                for RFpar in self.gates_object.hardware.RF_params:
                    param = getattr(inst, RFpar)
                    self._add_RFset(param)
        if self.keysight_rf is not None:
            try:
                for ks_param in self.keysight_rf.all_params:
                    self._add_RFset(ks_param)
            except Exception as e:
                logger.error(f'Failed to add keysight RF {e}')

        # add real gates
        for gate_name in self.gates_object.hardware.dac_gate_map.keys():
            param = getattr(self.gates_object, gate_name)
            self._add_gate(param, False)

        # add virtual gates
        for gate_name in self.gates_object.v_gates:
            param = getattr(self.gates_object, gate_name)
            self._add_gate(param, True)

        self.step_size.clear()
        items = [100, 50, 20, 10, 5, 2, 1, 0.5, 0.2, 0.1]
        self.step_size.addItems(str(item) for item in items)
        self.step_size.setCurrentText("1")

        self.lock.setChecked(self.locked)
        self.lock.stateChanged.connect(lambda: self._update_lock(self.lock.isChecked()))
        self.step_size.currentIndexChanged.connect(lambda: self.update_step(float(self.step_size.currentText())))
        self._finish_gates_GUI()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(lambda: self._update_parameters())
        self.timer.start(500)

        self.show()
        if not instance_ready:
            self.app.exec()

    @qt_log_exception
    def closeEvent(self, event):
        self.timer.stop()

    @qt_log_exception
    def update_step(self, value: float):
        """ Update step size of the parameter GUI elements with the specified value """
        self._step_size = value
        for gate in self.real_gates:
            gate.gui_input_param.setSingleStep(value)
        for gate in self.virtual_gates:
            gate.gui_input_param.setSingleStep(value)

    @qt_log_exception
    def _update_lock(self, locked):
        print('Locked:', locked)
        self.locked = locked

    @qt_log_exception
    def _add_RFset(self, parameter: qc.Parameter):
        ''' Add a new RF.

        Args:
            parameter (QCoDeS parameter object) : parameter to add.
        '''

        i = len(self.rf_settings)
        layout = self.layout_RF

        name = parameter.full_name
        unit = parameter.unit
        step_size = 0.5
        division = 1

        name = name.replace('keysight_rfgen_', '')

        if 'freq' in parameter.name:
            division = 1e6
            step_size = 0.1
            unit = f'M{unit}'

        _translate = QtCore.QCoreApplication.translate

        set_name = QtWidgets.QLabel(self.RFsettings)
        set_name.setObjectName(name)
        set_name.setMinimumSize(QtCore.QSize(100, 0))
        set_name.setText(_translate("MainWindow", name))
        layout.addWidget(set_name, i, 0, 1, 1)

        if 'enable' in name:
            set_input = QtWidgets.QCheckBox(self.RFsettings)
            set_input.setObjectName(name + "_input")
            set_input.stateChanged.connect(lambda: self._set_bool(parameter, set_input.isChecked))
        else:
            set_input = QtWidgets.QDoubleSpinBox(self.RFsettings)
            set_input.setObjectName(name + "_input")
            set_input.setMinimumSize(QtCore.QSize(100, 0))
            set_input.setRange(-1e9, 1e9)
            set_input.setValue(parameter()/division)
            set_input.valueChanged.connect(lambda: self._set_set(parameter, set_input.value, division))
            set_input.setKeyboardTracking(False)
            set_input.setSingleStep(step_size)

        layout.addWidget(set_input, i, 1, 1, 1)

        set_unit = QtWidgets.QLabel(self.RFsettings)
        set_unit.setObjectName(name + "_unit")
        set_unit.setText(_translate("MainWindow", unit))
        layout.addWidget(set_unit, i, 2, 1, 1)
        self.rf_settings.append(param_data_obj(parameter,  set_input, division))

    @qt_log_exception
    def _add_gate(self, parameter: qc.Parameter, virtual: bool):
        '''
        add a new gate.

        Args:
            parameter (QCoDeS parameter object) : parameter to add.
            virtual (bool) : True in case this is a virtual gate.
        '''

        i = len(self.real_gates)
        layout = self.layout_real

        if virtual:
            i = len(self.virtual_gates)
            layout = self.layout_virtual

        name = parameter.name
        unit = parameter.unit

        _translate = QtCore.QCoreApplication.translate

        gate_name = QtWidgets.QLabel(self.virtualgates)
        gate_name.setObjectName(name)
        gate_name.setMinimumSize(QtCore.QSize(100, 0))
        gate_name.setText(_translate("MainWindow", name))
        layout.addWidget(gate_name, i, 0, 1, 1)

        voltage_input = QtWidgets.QDoubleSpinBox(self.virtualgates)
        voltage_input.setObjectName(name + "_input")
        voltage_input.setMinimumSize(QtCore.QSize(100, 0))

        if not virtual:
            #voltage_input.setRange(-4000.0, 4000.0)
            voltage_input.setRange(-10000.0, 10000.0)
        else:
            # QDoubleSpinBox needs a limit. Set it high for virtual voltage
            voltage_input.setRange(-9999.99, 9999.99)
        voltage_input.setValue(parameter())
        voltage_input.valueChanged.connect(lambda: self._set_gate(parameter, voltage_input.value, voltage_input))
        voltage_input.setKeyboardTracking(False)
        layout.addWidget(voltage_input, i, 1, 1, 1)

        gate_unit = QtWidgets.QLabel(self.virtualgates)
        gate_unit.setObjectName(name + "_unit")
        gate_unit.setText(_translate("MainWindow", unit))
        layout.addWidget(gate_unit, i, 2, 1, 1)
        if not virtual:
            self.real_gates.append(param_data_obj(parameter,  voltage_input, 1))
        else:
            self.virtual_gates.append(param_data_obj(parameter,  voltage_input, 1))

        # Need to save away the handle to the voltage_input QDoubleSpinBox 
        # so that we can update the different gates from the self.dependant_gate_map
        self.real_gates_qt_voltage_input[name] = voltage_input

    @qt_log_exception
    def _set_gate(self, gate, value, voltage_input, alt_value=None):
        if self.locked:
            logger.warning('Not changing voltage, ParameterViewer is locked!')
            # Note value will be restored by _update_parameters
            return

        # The original function takes arg 'value' in the form of a Qt type which
        # makes it a little awkward to reuse this function when running the 
        # update_dependant_gates function, therefore the alt_val was added 
        # so that a simple numeric value can be used instead  (ma)
        if alt_value:
            val = alt_value
        else:
            val = value()

        delta = abs(val - gate())

        #print( f'(_set_gate) {value=} {val=}  {type(value)=}')
        if self.max_diff is not None and delta > self.max_diff:
            logger.warning(f'Not setting {gate} to {val:.1f}mV. '
                           f'Difference {delta:.0f} mV > {self.max_diff:.0f} mV')
            return

        # If the alt_value was used we must update the gui input
        if alt_value:
            voltage_input.setValue(val)

        try:
            last_value = gate.get()
            new_text = voltage_input.text()
            current_text = voltage_input.textFromValue(last_value)
            if new_text != current_text:
                logger.info(f'GUI value changed: set gate {gate.name} {current_text} -> {new_text}')
                gate.set(val)
                # Look for any dependant gates to change (ma)
                # if there are then change each one of them according to the gate_dependancy_map
                #self.update_dependant_gates(gate, val)
        except Exception as ex:
            logger.error(f'Failed to set gate {gate} to {val}: {ex}')
            raise

    @qt_log_exception
    def update_dependant_gates(self, gate, value):
        '''
        Function that looks at self.gate_object.dependant_gate_map which defines a list of
        gates which are dependant on each other. Then will change the value of each dependant
        gate based on the map (ma)
        # TODO Peters LikedParameter could be used to do this
        '''
        if hasattr(self.gates_object, 'dependant_gate_map'):
            dpgmap = self.gates_object.dependant_gate_map
            if gate.name in dpgmap:
                # Found one or more gates that are dependant on this gate
                # now update those gates based on the dependant_gate_map
                # which looks like this:
                # gates.dependant_gate_map = {
                # #    gate              mult    gate1     mult1   ofs    gate2
                # #     V                  V      V         V       V       V
                #     'Vds'         :  [[+0.5,  'Vcm',    +1.0 ,   0.0,   'HG07b'],  # changing Vds will update HG07b
                #                       [-0.5,  'Vcm',     1.0 ,   0.0,   'HG12b']], # changing Vds will update HG12b
                # where the following operation is performed
                # gate2 =  gate*mult + gate1*mult1 + ofs 
                # HG07b =   Vds*0.5  +   Vcm*1.0   + ofs
                #print( f'(update_dependant_gates) {gate.name=} {value=} {dpgmap[gate.name]=}  ')
                for dep in dpgmap[gate.name]:
                    mult   = dep[0]
                    gate1  = dep[1]
                    mult1  = dep[2]
                    ofs    = dep[3]
                    gate2  = dep[4]
                    #print( '(update_dependant_gates)' , gate1, mult, ofs, gate2 )
                    gate1_current_voltage = self.gates_object[gate1]()
                    qt_voltage_input = self.real_gates_qt_voltage_input[gate2]
                    gate2_new_voltage =  (value * mult) + (gate1_current_voltage * mult1) + ofs
                    gate2_obj = self.gates_object[gate2]
                    print( f'(update_dependant_gates) {gate.name=}={value} {gate1=}={gate1_current_voltage} {mult=} {ofs=} {gate2=}={gate2_new_voltage}' )
                    self._set_gate(  gate2_obj, None, qt_voltage_input, alt_value=gate2_new_voltage )

    @qt_log_exception
    def _set_set(self, setting, value, division):
        logger.info(f'setting {setting} to {value():.1f} times {division:.1f}')
        setting.set(value()*division)
        self.gates_object.hardware.RF_settings[setting.full_name] = value()*division
        self.gates_object.hardware.sync_data()

    @qt_log_exception
    def _set_bool(self, setting, value):
        setting.set(value())
        self.gates_object.hardware.RF_settings[setting.full_name] = value()
        self.gates_object.hardware.sync_data()

    @qt_log_exception
    def _finish_gates_GUI(self):

        for items, layout_widget in [
                (self.real_gates, self.layout_real),
                (self.virtual_gates, self.layout_virtual),
                (self.rf_settings, self.layout_RF)]:
            i = len(items) + 1

            spacerItem = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
            layout_widget.addItem(spacerItem, i, 0, 1, 1)

            spacerItem1 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
            layout_widget.addItem(spacerItem1, 0, 3, 1, 1)

        self.setWindowTitle(f'Parameter Viewer for {self.gates_object}')

    @qt_log_exception
    def _update_parameters(self):
        '''
        updates the values of all the gates in the parameter viewer periodically
        '''
        idx = self.tab_menu.currentIndex()

        if idx == 0:
            params = self.real_gates
        elif idx == 1:
            params = self.virtual_gates
        elif idx == 2:
            params = self.rf_settings
        else:
            return

        for param in params:
            try:
                # do not update when a user clicks on it.
                gui_input = param.gui_input_param
                if not gui_input.hasFocus():
                    if isinstance(param.gui_input_param, QtWidgets.QDoubleSpinBox):
                        new_value = param.param_parameter()/param.division
                        current_text = gui_input.text()
                        new_text = gui_input.textFromValue(new_value)
                        if current_text != new_text:
                            logger.info(f'Update GUI {param.param_parameter.name} {current_text} -> {new_text}')
                            gui_input.setValue(new_value)
                            if gui_input.text() != new_text:
                                print(f'WARNING: {param.param_parameter.name} corrected from '
                                      f'{new_text} to {gui_input.text()}')
                elif isinstance(param.gui_input_param, QtWidgets.QCheckBox):
                    param.gui_input_param.setChecked(param.param_parameter())
            except Exception:
                logger.error(f'Error updating {param}', exc_info=True)
