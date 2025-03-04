import logging
import inspect
import os
from enum import Enum
from typing import Any

from PyQt5 import QtCore, QtWidgets

from core_tools.GUI.keysight_videomaps.liveplotting import liveplotting
from core_tools.GUI.script_runner.script_runner_gui import Ui_MainWindow
from core_tools.GUI.script_runner.commands import Function, Cell
from core_tools.GUI.script_runner.web_server import run_web_server
from core_tools.GUI.qt_util import qt_log_exception


logger = logging.getLogger(__name__)


class ScriptRunner(QtWidgets.QMainWindow, Ui_MainWindow):
    '''
    User interface to execute functions and IPython cells.

    Example:
        def sayHi(name:str, times:int=1):
            for _ in range(times):
                print(f'Hi {name}')

        script_gui = ScriptRunner()

        script_gui.add_function(sayHi, name='Bob', times=3)
        script_gui.add_function(sayHi, 'Greet all', name='all')
        script_gui.add_cell('Say Hi', path+'/test_script.py')
        script_gui.add_cell(2, path+'/test_script.py'),
    '''

    def __init__(self):
        # set graphical user interface
        self.app = QtCore.QCoreApplication.instance()
        if self.app is None:
            instance_ready = False
            self.app = QtWidgets.QApplication([])
        else:
            instance_ready = True

        super(QtWidgets.QMainWindow, self).__init__()
        self.setupUi(self)

        self.video_mode_running = False
        self.video_mode_label = QtWidgets.QLabel("VideoMode: <unknown")
        self.video_mode_label.setMargin(2)
        self.statusbar.setContentsMargins(8, 0, 4, 4)
        self.statusbar.addWidget(self.video_mode_label)
        self.video_mode_paused = False
        self._update_video_mode_status()

        self.latest_result = None
        self.commands = []

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(lambda: self._update_video_mode_status())
        self.timer.start(500)

        self.show()
        if not instance_ready:
            self.app.exec()

    def add_function(self, func: Any, command_name: str | None = None, **kwargs):
        '''
        Adds a function to be run as command in ScriptRunner.

        The argument types of the function are displayed in the GUI. The entered
        data is converted to the specified type. Currently the types `str`, `int`, `float` and `bool`
        are supported.
        If the type of the argument is not specified, then a string will be passed to the function.

        If command_name is not specified, then the name of func is used as
        command name.

        The additional keyword arguments will be entered as default values in the GUI.

        Args:
            func: function to execute.
            command_name: Optional name to show for the command in ScriptRunner.
            kwargs: default arguments to pass with function.
        '''
        self._add_command(Function(func, command_name, **kwargs))

    def add_cell(self, cell: str | int, python_file: str, command_name: str | None = None):
        '''
        Add an IPython cell with Python code to be run as command in ScriptRunner.

        If command_name is not specified then cell+filename with be used as command name.

        Args:
            cell: name or number of cell to run.
            python_file: filename of Python file.
            command_name: Optional name to show for the command in ScriptRunner.
        '''
        self._add_command(Cell(cell, python_file, command_name))

    def run_server(self):
        run_web_server(self.commands)

    @qt_log_exception
    def closeEvent(self, event):
        self.timer.stop()
        self.timer = None

    @qt_log_exception
    def _run_command(self, command, arg_inputs):
        try:
            self._update_video_mode_status()
            running = self.video_mode_running
            if running:
                self.video_mode_paused = True
                self._video_mode_start_stop(running)
                self._show_video_mode_status('PAUSED', '#FF8')
                self.app.processEvents()

            kwargs = {
                name: (inp.currentText() if isinstance(inp, QtWidgets.QComboBox) else inp.text())
                for name, inp in arg_inputs.items()
            }
            command_result = command(**kwargs)
        except Exception as ex:
            command_result = ex
            logger.error('Failure running command', exc_info=True)
        finally:
            self.latest_result = command_result
            if running:
                self.video_mode_paused = False
                self._video_mode_start_stop(running)

    def _add_command(self, command):
        i = len(self.commands)
        self.commands.append(command)

        layout = self.commands_layout
        cmd_btn = QtWidgets.QPushButton(command.name, self.commands_widget)
        cmd_btn.setObjectName(f'command_{i}')
        cmd_btn.setMinimumSize(QtCore.QSize(100, 0))
        layout.addWidget(cmd_btn, i, 0, 1, 1)

        arg_inputs = {}
        for j, (name, parameter) in enumerate(command.parameters.items()):
            _label = QtWidgets.QLabel(self.commands_widget)
            _label.setObjectName(f"{command.name}_label_{j}")
            _label.setMinimumSize(QtCore.QSize(20, 0))
            _label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            text = name
            annotation = parameter.annotation
            if annotation is not inspect._empty:
                if isinstance(annotation, str):
                    raise Exception(f"Type of argument {parameter.name} ('{annotation}') cannot be converted.")
                text = f'{name} ({annotation.__name__})'
            _label.setText(text)
            layout.addWidget(_label, i, 2*j+1, 1, 1)

            if issubclass(annotation, Enum):
                _input = QtWidgets.QComboBox(self.commands_widget)
                for e in annotation:
                    _input.addItem(e.name, e)
                if name in command.defaults:
                    default = command.defaults[name]
                    if isinstance(default, str):
                        try:
                            # try match on value
                            default = annotation(default)
                        except Exception:
                            # try match on name
                            default = annotation[default]
                    _input.setCurrentText(default.name)
            else:
                _input = QtWidgets.QLineEdit(self.commands_widget)
                if name in command.defaults:
                    _input.setText(str(command.defaults[name]))
            _input.setObjectName(f"{command.name}_input_{j}")
            _input.setMinimumSize(QtCore.QSize(80, 0))
            layout.addWidget(_input, i, 2*j+2, 1, 1)
            arg_inputs[name] = _input

        cmd_btn.clicked.connect(lambda: self._run_command(command, arg_inputs))

    def add_commands(self, commands):
        for i, command in enumerate(commands):
            self._add_command(i, command)

    def _update_video_mode_status(self):
        if self.video_mode_paused:
            return
        if liveplotting.last_instance is None:
            self._show_video_mode_status('<unknown>', '')
            self.video_mode_running = False
            return
        running = liveplotting.last_instance.is_running
        if not running:
            self._show_video_mode_status('stopped', '')
        elif running == '1D':
            self._show_video_mode_status('1D running', '#4D6')
        elif running == '2D':
            self._show_video_mode_status('2D running', '#4D6')
        else:
            self._show_video_mode_status('???', '#AA4')
        self.video_mode_running = running

    def _show_video_mode_status(self, text, color):
        self.video_mode_label.setText(f'VideoMode: {text}')
        self.video_mode_label.setStyleSheet(f'QLabel {{ background-color : {color} }}')

    def _video_mode_start_stop(self, mode):
        if mode == '1D':
            liveplotting.last_instance._1D_start_stop()
        if mode == '2D':
            liveplotting.last_instance._2D_start_stop()


if __name__ == "__main__":

    def sayHi(name: str, times: int = 1):
        for _ in range(times):
            print(f'Hi {name}')
        return name

    class Mode(str, Enum):
        LEFT = 'left'
        CENTER = 'center'
        RIGHT = 'right'

    def fit(x: float, mode: Mode):
        print(f'fit {x}, {mode}')

    path = os.path.dirname(__file__).replace('\\', '/')

    ui = ScriptRunner()
    ui.add_function(sayHi)
    ui.add_function(sayHi, name='Bob', times=3)
    ui.add_function(sayHi, 'Greet all', name='all')
    ui.add_function(fit, 'Fit it', mode=Mode.CENTER, x=1.0)
    ui.add_function(fit, 'Fit it', mode='center', x=1.0)
    ui.add_function(fit, 'Fit it', mode='CENTER', x=1.0)
    ui.add_cell('Say Hi', path+'/test_script.py')
    ui.add_cell(2, path+'/test_script.py', 'Magic Button')
    ui.add_cell('Oops', path+'/test_script.py')
    ui.add_cell('Syntax Error', path+'/test_script.py')

    # NOTE:
    # To start servicing http requests run:
    # ui.run_server()
