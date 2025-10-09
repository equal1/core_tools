import logging
import os
from collections import defaultdict
from typing import Any
from dataclasses import dataclass

import qcodes as qc
from qtpy import QtCore, QtWidgets
from ruamel.yaml import YAML

from core_tools.GUI.qt_util import qt_log_exception
from core_tools.GUI.resources.icons import add_icons_to_checkbox


logger = logging.getLogger(__name__)


@dataclass
class param_data_obj:
    param_parameter: Any
    gui_input_param: Any
    name: str
    cb_star: QtWidgets.QCheckBox


class param_viewer(QtWidgets.QMainWindow):

    def __init__(self, gates_object: object | None = None,
                 max_diff: float = 1000,
                 locked=False):
        self.tab_gates: dict[str, list] = defaultdict(list)
        self.station = qc.Station.default
        self.max_diff = max_diff
        self.locked = locked
        self.favorite_gates: list[str] = []
        self._last_gui_values: dict[str, dict[str, float]] = defaultdict(dict)

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
        self.setup_ui()

        self.load_favorites()

        self.layout_favorites = self.add_tab("Favorites")
        self.add_tab("Real")
        self.add_tab("All virtual")

        # add real gates
        self._add_gates("Real", gates_object.hardware.dac_gate_map.keys())

        # add virtual gates
        self._add_gates("All virtual", gates_object.v_gates)

        # add virtual gates per matrix
        for virt_gate_set in gates_object.hardware.virtual_gates:
            vgm_name = virt_gate_set.name
            self.add_tab(vgm_name)
            self._add_gates(vgm_name, virt_gate_set.virtual_gate_names)

        self.refill_favorite_gates_tab()
        self.tab_menu.setCurrentIndex(1)

        self.step_size.clear()
        items = [100, 50, 20, 10, 5, 2, 1, 0.5, 0.2, 0.1]
        self.step_size.addItems(str(item) for item in items)
        self.step_size.setCurrentText("1")

        self.lock.setChecked(self.locked)
        self.lock.stateChanged.connect(lambda: self._update_lock(self.lock.isChecked()))
        self.step_size.currentIndexChanged.connect(lambda: self.update_step(float(self.step_size.currentText())))

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(lambda: self._update_parameters())
        self.timer.start(500)

        self.show()
        if not instance_ready:
            self.app.exec()

    def setup_ui(self):
        self.tabs = {}
        self.tab_layout = {}
        self.resize(650, 1200)
        self.centralwidget = QtWidgets.QWidget(self)
        self.gridLayout = QtWidgets.QGridLayout(self.centralwidget)
        self.gridLayout.setContentsMargins(-1, -1, -1, 0)
        self.tab_menu = QtWidgets.QTabWidget(self.centralwidget)
        self.gridLayout.addWidget(self.tab_menu, 0, 0, 1, 1)
        self.tab_menu.currentChanged.connect(lambda: self._tab_changed())

        horizontalLayout_2 = QtWidgets.QHBoxLayout()
        horizontalLayout_2.setContentsMargins(-1, -1, -1, 0)
        horizontalLayout_2.setSpacing(4)
        self.lock = QtWidgets.QCheckBox(self.centralwidget)
        self.lock.setText("Lock parameter viewer")
        horizontalLayout_2.addWidget(self.lock)
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        horizontalLayout_2.addItem(spacerItem)
        label = QtWidgets.QLabel(self.centralwidget)
        label.setText("Voltage step")
        horizontalLayout_2.addWidget(label)
        self.step_size = QtWidgets.QComboBox(self.centralwidget)
        self.step_size.setEnabled(True)
        horizontalLayout_2.addWidget(self.step_size)
        label_2 = QtWidgets.QLabel(self.centralwidget)
        label_2.setText("mV")
        horizontalLayout_2.addWidget(label_2)
        self.gridLayout.addLayout(horizontalLayout_2, 1, 0, 1, 1)
        self.setCentralWidget(self.centralwidget)
        statusbar = QtWidgets.QStatusBar()
        self.setStatusBar(statusbar)
        self.setWindowTitle("Parameter Viewer")

    def _tab_changed(self):
        self._update_parameters()

    def add_tab(self, name):
        tab = QtWidgets.QWidget()
        gridLayout = QtWidgets.QGridLayout(tab)
        scrollArea = QtWidgets.QScrollArea(tab)
        scrollArea.setWidgetResizable(True)
        scrollAreaWidgetContents = QtWidgets.QWidget()
        # scrollAreaWidgetContents.setGeometry(QtCore.QRect(0, 0, 756, 495))
        scroll_layout = QtWidgets.QGridLayout(scrollAreaWidgetContents)
        layout = QtWidgets.QGridLayout()
        layout.setSpacing(2)
        scroll_layout.addLayout(layout, 0, 0, 1, 1)
        scrollArea.setWidget(scrollAreaWidgetContents)
        gridLayout.addWidget(scrollArea, 0, 0, 1, 1)
        self.tabs[name] = tab
        self.tab_layout[name] = layout
        self.tab_menu.addTab(tab, name)
        return layout

    def refill_favorite_gates_tab(self):
        layout = self.tab_layout["Favorites"]
        parameters = self.tab_gates["Favorites"]
        n_rows = len(parameters)
        parameters.clear()
        for row in range(n_rows+1):
            for col in range(5):
                item = layout.itemAtPosition(row, col)
                if item is None:
                    continue
                widget = item.widget()
                if widget is not None:
                    layout.removeWidget(widget)
                    widget.deleteLater()
                else:
                    layout.removeItem(item)
        self._add_gates("Favorites", self.favorite_gates)

    @qt_log_exception
    def closeEvent(self, event):
        self.timer.stop()

    @qt_log_exception
    def update_step(self, value: float):
        """ Update step size of the parameter GUI elements with the specified value """
        self._step_size = value
        for gates in self.tab_gates.values():
            for gate in gates:
                gate.gui_input_param.setSingleStep(value)

    @qt_log_exception
    def _update_lock(self, locked):
        print('Locked:', locked)
        self.locked = locked

    @qt_log_exception
    def _add_gates(self, tab_name: str, gate_names: list[str]):
        for gate_name in gate_names:
            try:
                param = self.gates_object.parameters[gate_name]
            except KeyError:
                print(f"Ignoring gate '{gate_name}'. It does not exist.")
                continue
            self._add_gate(param, tab_name)
        self._add_spacers(tab_name)

    @qt_log_exception
    def _add_gate(self, parameter: qc.Parameter, tab_name: str):
        '''
        add a new gate.

        Args:
            parameter (QCoDeS parameter object) : parameter to add.
            virtual (bool) : True in case this is a virtual gate.
        '''

        layout = self.tab_layout[tab_name]
        row = len(self.tab_gates[tab_name])

        name = parameter.name
        unit = parameter.unit

        _translate = QtCore.QCoreApplication.translate

        gate_name = QtWidgets.QLabel()
        gate_name.setObjectName(name)
        gate_name.setMinimumSize(QtCore.QSize(100, 0))
        gate_name.setText(_translate("MainWindow", name))
        layout.addWidget(gate_name, row, 0, 1, 1)

        voltage_input = QtWidgets.QDoubleSpinBox()
        voltage_input.setObjectName(name + "_input")
        voltage_input.setMinimumSize(QtCore.QSize(100, 0))

        virtual = parameter.name in self.gates_object.v_gates

        if not virtual:
            voltage_input.setRange(-4000.0, 4000.0)
        else:
            # QDoubleSpinBox needs a limit. Set it high for virtual voltage
            voltage_input.setRange(-99999.99, 99999.99)
        voltage_input.setValue(parameter())
        voltage_input.valueChanged.connect(lambda: self._set_gate(parameter, voltage_input))
        voltage_input.setKeyboardTracking(False)
        voltage_input.setSingleStep(self._step_size)
        layout.addWidget(voltage_input, row, 1, 1, 1)

        gate_unit = QtWidgets.QLabel()
        gate_unit.setObjectName(name + "_unit")
        gate_unit.setText(_translate("MainWindow", unit))
        layout.addWidget(gate_unit, row, 2, 1, 1)

        cb_star = QtWidgets.QCheckBox("  ")
        cb_star.setCheckState(QtCore.Qt.Checked if name in self.favorite_gates else QtCore.Qt.Unchecked)
        add_icons_to_checkbox(cb_star, "Starred.png", "StarWhite.png", 18)
        cb_star.stateChanged.connect(lambda state: self._star_changed(name, state))
        layout.addWidget(cb_star, row, 3, 1, 1)

        param_data = param_data_obj(parameter,  voltage_input, name, cb_star)
        self.tab_gates[tab_name].append(param_data)

    @qt_log_exception
    def _star_changed(self, gate_name: str, state: QtCore.Qt.CheckState):
        update = False
        if state == QtCore.Qt.Checked:
            if gate_name not in self.favorite_gates:
                self.favorite_gates.append(gate_name)
            update = True
        else:
            if gate_name in self.favorite_gates:
                self.favorite_gates.remove(gate_name)
            update = True
        if update:
            self.save_favorites()
            self.refill_favorite_gates_tab()

    def _get_favorites_filename(self):
        path = "~/.core_tools/parameter_viewer"
        name = "favorites.yaml"
        path = os.path.expanduser(path)
        os.makedirs(path, exist_ok=True)
        return os.path.join(path, name)

    def load_favorites(self):
        filename = self._get_favorites_filename()
        if not os.path.exists(filename):
            return
        yaml = YAML()
        with open(filename) as fp:
            gates = yaml.load(fp)
        # Only keep known gates.
        self.favorite_gates = [name for name in gates if name in self.gates_object.parameters]

    def save_favorites(self):
        filename = self._get_favorites_filename()
        yaml = YAML()
        with open(filename, "w") as fp:
            yaml.dump(self.favorite_gates, fp)

    @qt_log_exception
    def _set_gate(self, gate, voltage_input):
        current_voltage = gate()
        new_value = voltage_input.value()
        new_text = voltage_input.text()
        old_text = voltage_input.textFromValue(current_voltage)
        if new_text == old_text:
            return
        if self.locked:
            logger.warning(f"ParameterViewer is locked! Voltage of {gate.name} not changed.")
            voltage_input.setValue(current_voltage)
            return
        if not voltage_input.isEnabled():
            logger.info(f"Ignoring out of range value {gate.name}: {new_value}")
            return
        delta = abs(new_value - current_voltage)
        if self.max_diff is not None and delta > self.max_diff:
            logger.warning(f"Not setting {gate} to {new_value:.1f}mV. "
                           f"Difference {delta:.0f} mV > {self.max_diff:.0f} mV")
            return
        try:
            logger.info(f"GUI value changed: set gate {gate.name} {old_text} -> {new_text}")
            gate.set(new_value)
        except Exception as ex:
            logger.error(f"Failed to set gate {gate.name} to {new_value}: {ex}")

    def _add_spacers(self, tab_name: str):
        layout = self.tab_layout[tab_name]
        row = len(self.tab_gates[tab_name])

        spacerItem = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        layout.addItem(spacerItem, row, 0, 1, 1)

        spacerItem1 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        layout.addItem(spacerItem1, 0, 4, 1, 1)

    @qt_log_exception
    def _update_parameters(self):
        '''
        updates the values of all the gates in the parameter viewer periodically
        '''
        idx = self.tab_menu.currentIndex()
        tab_name = self.tab_menu.tabText(idx)
        all_gate_voltages = {}
        params = self.tab_gates[tab_name]
        # if supported retrieve all voltages in 1 call. That's a lot faster.
        if hasattr(self.gates_object, "get_all_gate_voltages"):
            all_gate_voltages = self.gates_object.get_all_gate_voltages()

        for param in params:
            try:
                name = param.name
                if name in all_gate_voltages:
                    new_value = all_gate_voltages[name]
                else:
                    new_value = param.param_parameter()

                old_value = self._last_gui_values[tab_name].get(name, None)
                param.cb_star.setCheckState(QtCore.Qt.Checked if name in self.favorite_gates else QtCore.Qt.Unchecked)

                if old_value == new_value:
                    continue

                # do not update when a user clicks on it.
                gui_input = param.gui_input_param
                if not gui_input.hasFocus():
                    if isinstance(gui_input, QtWidgets.QDoubleSpinBox):
                        if idx == 1 and (new_value < gui_input.minimum() or new_value > gui_input.maximum()):
                            gui_input.setEnabled(False)
                            gui_input.setStyleSheet("color : red;")
                            new_text = gui_input.textFromValue(new_value)
                            current_text = gui_input.text()
                            if current_text != new_text:
                                gui_input.setValue(new_value)
                        else:
                            if not gui_input.isEnabled():
                                gui_input.setEnabled(True)
                                gui_input.setStyleSheet("")

                            current_text = gui_input.text()
                            new_text = gui_input.textFromValue(new_value)
                            if current_text != new_text:
                                logger.info(f'Update GUI {param.param_parameter.name} {current_text} -> {new_text}')
                                gui_input.setValue(new_value)
                                # Note: additional check on 0.0, because "-0.00 " and "0.00" are numerically equal.
                                if gui_input.text() != new_text and gui_input.valueFromText(new_text) != 0.0:
                                    print(f'WARNING: {param.param_parameter.name} corrected from '
                                          f'{new_text} to {gui_input.text()}')
                    elif isinstance(gui_input, QtWidgets.QCheckBox):
                        gui_input.setChecked(bool(new_value))
                    self._last_gui_values[tab_name][name] = new_value
            except Exception:
                logger.error(f'Error updating {param}', exc_info=True)
