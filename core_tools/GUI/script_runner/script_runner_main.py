import ast
import inspect
import json
import logging
import os
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Union, get_args, get_origin

from PyQt5 import QtCore, QtWidgets

from core_tools.GUI.keysight_videomaps.liveplotting import liveplotting
from core_tools.GUI.qt_util import qt_log_exception
from core_tools.GUI.script_runner.script_runner_gui import Ui_MainWindow

try:
    from spyder_kernels.customize.spydercustomize import runcell
except:
    runcell = None

logger = logging.getLogger(__name__)


def pretty_type_str(anno) -> str:
    try:
        origin = get_origin(anno)
        args = get_args(anno)

        if origin is None:
            # Plain types or Enums
            return getattr(anno, "__name__", str(anno).replace("typing.", ""))

        if origin in (list, tuple, set, frozenset):
            inner = ", ".join(pretty_type_str(a) for a in args) or "Any"
            return f"{origin.__name__}[{inner}]"

        if origin is dict:
            k, v = (args + ("Any", "Any"))[:2]
            return f"dict[{pretty_type_str(k)}, {pretty_type_str(v)}]"

        if origin is Union:
            # Optional[T] shows as "T | None"
            return " | ".join(pretty_type_str(a) for a in args)

        # Fallback
        return str(anno).replace("typing.", "")
    except Exception:
        return str(anno).replace("typing.", "")


class FlowLayout(QtWidgets.QLayout):
    """A layout that arranges widgets in a flow, wrapping to new lines when needed."""

    def __init__(self, parent=None, margin=0, spacing=-1):
        super(FlowLayout, self).__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return QtCore.Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._do_layout(QtCore.QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super(FlowLayout, self).setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        margin, _, _, _ = self.getContentsMargins()
        size += QtCore.QSize(2 * margin, 2 * margin)
        return size

    def _do_layout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0
        spacing = self.spacing()

        for item in self.itemList:
            wid = item.widget()
            spaceX = spacing + wid.style().layoutSpacing(
                QtWidgets.QSizePolicy.PushButton,
                QtWidgets.QSizePolicy.PushButton,
                QtCore.Qt.Horizontal,
            )
            spaceY = spacing + wid.style().layoutSpacing(
                QtWidgets.QSizePolicy.PushButton,
                QtWidgets.QSizePolicy.PushButton,
                QtCore.Qt.Vertical,
            )
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()


class ScriptRunner(QtWidgets.QMainWindow, Ui_MainWindow):
    """
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
    """

    def __init__(self, parent=None, *, embedded: bool = False):
        # set graphical user interface
        self.app = QtCore.QCoreApplication.instance()
        if self.app is None:
            instance_ready = False
            self.app = QtWidgets.QApplication([])
        else:
            instance_ready = True

        super(QtWidgets.QMainWindow, self).__init__(parent)
        self._embedded = embedded or parent is not None
        self.setupUi(self)
        # Global polish
        self.setStyleSheet("""
        QWidget#CommandCard {
            background: #fafafa;
            border: 1px solid #e1e1e1;
            border-radius: 10px;
        }
        QPushButton {
            padding: 8px 14px;
            border-radius: 8px;
        }
        QPushButton:hover {
            background: #f2f2f2;
        }
        QLineEdit {
            padding: 6px 8px;
            border: 1px solid #d0d0d0;
            border-radius: 6px;
        }
        QLabel {
            color: #333;
        }
        """)

        self.commands_layout.setHorizontalSpacing(12)
        self.commands_layout.setVerticalSpacing(12)
        self.commands_layout.setContentsMargins(10, 10, 10, 10)

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

        if not self._embedded:
            self.show()
            if not instance_ready:
                self.app.exec()

    def add_function(self, func: Any, command_name: str = None, **kwargs):
        """
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
        """
        self._add_command(Function(func, command_name, **kwargs))

    def add_cell(
        self, cell: Union[str, int], python_file: str, command_name: str = None
    ):
        """
        Add an IPython cell with Python code to be run as command in ScriptRunner.

        If command_name is not specified then cell+filename with be used as command name.

        Args:
            cell: name or number of cell to run.
            python_file: filename of Python file.
            command_name: Optional name to show for the command in ScriptRunner.
        """
        if runcell is None:
            raise Exception(
                "runcell not available. Upgrade to Spyder 4+ to use add_cell()"
            )
        self._add_command(Cell(cell, python_file, command_name))

    @qt_log_exception
    def closeEvent(self, event):
        self.timer.stop()
        self.timer = None

    @qt_log_exception
    @qt_log_exception
    def _run_command(self, command, arg_inputs):
        try:
            self._update_video_mode_status()
            running = self.video_mode_running
            if running:
                self.video_mode_paused = True
                self._video_mode_start_stop(running)
                self._show_video_mode_status("PAUSED", "#FF8")
                self.app.processEvents()

            kwargs = {
                name: (
                    inp.currentText()
                    if isinstance(inp, QtWidgets.QComboBox)
                    else inp.text()
                )
                for name, inp in arg_inputs.items()
            }
            try:
                command_result = command(**kwargs)
            except ValueError as vex:
                QtWidgets.QMessageBox.warning(self, "Invalid parameter value", str(vex))
                command_result = vex
            except Exception as ex_inner:
                QtWidgets.QMessageBox.critical(
                    self, "Command failed", f"{type(ex_inner).__name__}: {ex_inner}"
                )
                command_result = ex_inner
        except Exception as ex:
            command_result = ex
            logger.error("Failure running command", exc_info=True)
        finally:
            self.latest_result = command_result
            if running:
                self.video_mode_paused = False
                self._video_mode_start_stop(running)

    def _add_command(self, command):
        i = len(self.commands)
        self.commands.append(command)

        # Create a container widget for this command (as a "card")
        command_container = QtWidgets.QWidget(self.commands_widget)
        command_container.setObjectName("CommandCard")
        command_layout = QtWidgets.QVBoxLayout(command_container)
        command_layout.setContentsMargins(12, 12, 12, 12)
        command_layout.setSpacing(10)

        # Add the command button – let it expand
        cmd_btn = QtWidgets.QPushButton(command.name, command_container)
        cmd_btn.setObjectName(f"command_{i}")
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        cmd_btn.setSizePolicy(sizePolicy)
        cmd_btn.setMinimumHeight(36)  # taller, easier to click
        cmd_btn.setMaximumHeight(48)
        command_layout.addWidget(cmd_btn)

        # Create parameters area with flow layout
        if command.parameters:
            params_widget = QtWidgets.QWidget(command_container)
            params_layout = self._create_flow_layout(params_widget)

            arg_inputs = {}
            for j, (name, parameter) in enumerate(command.parameters.items()):
                # Create a container for each parameter (label + input stacked)
                param_container = QtWidgets.QWidget(params_widget)
                param_layout = QtWidgets.QVBoxLayout(param_container)
                param_layout.setContentsMargins(0, 0, 0, 0)
                param_layout.setSpacing(4)

                # Small caption label (name only)
                _label = QtWidgets.QLabel(param_container)
                _label.setObjectName(f"{command.name}_label_{j}")
                _label.setText(name)
                _label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
                param_layout.addWidget(_label)

                annotation = parameter.annotation
                # Input widget
                if (
                    annotation != inspect._empty
                    and inspect.isclass(annotation)
                    and issubclass(annotation, Enum)
                ):
                    _input = QtWidgets.QComboBox(param_container)
                    for e in annotation:
                        _input.addItem(e.name, e)
                    if name in command.defaults:
                        default = command.defaults[name]
                        if isinstance(default, str):
                            try:
                                default = annotation(default)
                            except ValueError:
                                default = annotation[default]
                        _input.setCurrentText(default.name)
                else:
                    _input = QtWidgets.QLineEdit(param_container)
                    if name in command.defaults and command.defaults[name] is not None:
                        _input.setText(str(command.defaults[name]))

                # Sizing so all fields feel uniform
                _input.setObjectName(f"{command.name}_input_{j}")
                _input.setMinimumSize(QtCore.QSize(220, 0))  # consistent column width
                _input.setMaximumSize(QtCore.QSize(360, 44))
                param_layout.addWidget(_input)

                # Optional tiny type hint under the input (or use placeholders you already added)
                if annotation is not inspect._empty and not isinstance(annotation, str):
                    type_lbl = QtWidgets.QLabel(param_container)
                    type_lbl.setText(f"Param type: {pretty_type_str(annotation)}")
                    type_lbl.setStyleSheet(
                        "color:#777; font-size:11px; margin-top:2px;"
                    )
                    param_layout.addWidget(type_lbl)

                arg_inputs[name] = _input
                params_layout.addWidget(param_container)

            params_widget.setLayout(params_layout)
            command_layout.addWidget(params_widget)
        else:
            arg_inputs = {}

        command_container.setLayout(command_layout)

        # Add the command container to the main layout
        self.commands_layout.addWidget(command_container, i, 0, 1, 1)

        cmd_btn.clicked.connect(lambda: self._run_command(command, arg_inputs))

    def _create_flow_layout(self, parent):
        """Create a layout that flows widgets to new lines when they don't fit."""
        # Use a custom flow layout implementation
        return FlowLayout(parent, margin=0, spacing=12)

    def add_commands(self, commands):
        for i, command in enumerate(commands):
            self._add_command(i, command)

    def _update_video_mode_status(self):
        if self.video_mode_paused:
            return
        if liveplotting.last_instance is None:
            self._show_video_mode_status("<unknown>", "")
            self.video_mode_running = False
            return
        running = liveplotting.last_instance.is_running
        if not running:
            self._show_video_mode_status("stopped", "")
        elif running == "1D":
            self._show_video_mode_status("1D running", "#4D6")
        elif running == "2D":
            self._show_video_mode_status("2D running", "#4D6")
        else:
            self._show_video_mode_status("???", "#AA4")
        self.video_mode_running = running

    def _show_video_mode_status(self, text, color):
        self.video_mode_label.setText(f"VideoMode: {text}")
        self.video_mode_label.setStyleSheet(f"QLabel {{ background-color : {color} }}")

    def _video_mode_start_stop(self, mode):
        if mode == "1D":
            liveplotting.last_instance._1D_start_stop()
        if mode == "2D":
            liveplotting.last_instance._2D_start_stop()


class Command(ABC):
    def __init__(self, name, parameters, defaults={}):
        self.name = name
        self.parameters = parameters
        self.defaults = defaults

    @abstractmethod
    def __call__(self):
        pass


class Cell(Command):
    """
    A reference to an IPython cell with Python code to be run as command in
    ScriptRunner.

    If command_name is not specified then cell+filename with be used as command name.

    Args:
        cell: name or number of cell to run.
        python_file: filename of Python file.
        command_name: Optional name to show for the command in ScriptRunner.
    """

    def __init__(
        self, cell: Union[str, int], python_file: str, command_name: str = None
    ):
        filename = os.path.basename(python_file)
        name = f"{cell} ({filename})" if command_name is None else command_name
        super().__init__(name, {})
        self.cell = cell
        self.python_file = python_file
        if runcell is None:
            raise Exception("runcell not available. Upgrade to Spyder 4+ to use Cell()")

    def __call__(self):
        command = f"runcell({self.cell}, '{self.python_file}')"
        print(command)
        logger.info(command)
        runcell(self.cell, self.python_file)


class Function(Command):
    """
    A reference to a function to be run as command in ScriptRunner.

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
    """

    def __init__(self, func: Any, command_name: str = None, **kwargs):
        if command_name is None:
            command_name = func.__name__
        signature = inspect.signature(func)
        parameters = {p.name: p for p in signature.parameters.values()}
        defaults = {}
        for name, parameter in parameters.items():
            if parameter.default is not inspect._empty:
                defaults[name] = parameter.default
            if parameter.annotation is inspect._empty:
                logger.warning(f"No annotation for `{name}`, assuming string")
        defaults.update(**kwargs)
        super().__init__(command_name, parameters, defaults)
        self.func = func

    def _convert_arg(self, param_name, value):
        """
        Best-effort conversion:
        - obeys type hints (int/float/bool/Enum/Path)
        - handles Optional[T] / Union[T1, T2]
        - supports list[T], tuple[T], dict[K,V] (JSON, Python literal, or comma-separated for lists)
        - falls back to the original string on failure
        """
        annotation = self.parameters[param_name].annotation

        # No hint → pass string
        if annotation is inspect._empty or isinstance(annotation, str):
            return value

        def _coerce(val, anno):
            origin = get_origin(anno)
            args = get_args(anno)

            # Optional[T] / Union[...] → try each type until one works
            if origin is Union:
                # Put non-None types first
                ordered = [a for a in args if a is not type(None)] + [
                    a for a in args if a is type(None)
                ]
                for a in ordered:
                    try:
                        return _coerce(val, a)
                    except Exception:
                        continue
                # Nothing worked
                raise ValueError(f"Cannot coerce {val!r} to {anno!r}")

            # Enums: allow by name or by value (case-insensitive name)
            if inspect.isclass(anno) and issubclass(anno, Enum):
                if isinstance(val, anno):
                    return val
                # exact value
                try:
                    return anno(val)
                except Exception:
                    pass
                # by NAME (case-insensitive)
                try:
                    return anno[val]  # exact name
                except Exception:
                    # case-insensitive match
                    names = {e.name.lower(): e for e in anno}
                    m = names.get(str(val).lower())
                    if m is not None:
                        return m
                raise ValueError(f"{val!r} is not a valid {anno.__name__}")

            # Bool: accept true/false/1/0/yes/no
            if anno is bool:
                if isinstance(val, bool):
                    return val
                s = str(val).strip().lower()
                if s in {"1", "true", "t", "yes", "y", "on"}:
                    return True
                if s in {"0", "false", "f", "no", "n", "off"}:
                    return False
                raise ValueError(f"Cannot coerce {val!r} to bool")

            # Path
            if anno is Path:
                return Path(str(val))

            # Plain scalars
            if anno in (int, float, str):
                return anno(val)

            # Sequences: list[T] / tuple[T]
            if origin in (list, tuple) and len(args) == 1:
                subtype = args[0]
                # Already a sequence?
                if isinstance(val, (list, tuple)):
                    seq = [_coerce(v, subtype) for v in val]
                else:
                    # Try JSON / Python literal first
                    parsed = None
                    if isinstance(val, str):
                        v = val.strip()
                        try:
                            parsed = json.loads(v)
                        except Exception:
                            try:
                                parsed = ast.literal_eval(v)
                            except Exception:
                                # Fallback: comma-separated
                                parsed = [x.strip() for x in v.split(",")] if v else []
                    else:
                        parsed = [val]
                    seq = [_coerce(v, subtype) for v in parsed]
                return origin(seq)

            # Dicts: dict[K,V]
            if origin is dict and len(args) == 2:
                k_t, v_t = args
                if isinstance(val, dict):
                    items = val.items()
                else:
                    v = str(val).strip()
                    try:
                        parsed = json.loads(v)
                    except Exception:
                        parsed = ast.literal_eval(v)  # may raise
                    if not isinstance(parsed, dict):
                        raise ValueError("Not a dict")
                    items = parsed.items()
                return {_coerce(k, k_t): _coerce(v, v_t) for k, v in items}

            # Last resort: call the type on the value
            return anno(val)

        # Convert (raise on failure so GUI shows an error)
        try:
            return _coerce(value, annotation)
        except Exception as e:
            expected = pretty_type_str(annotation)
            raise ValueError(
                f"Invalid value for '{param_name}': {value!r} (expected {expected})"
            ) from e

    def __call__(self, **kwargs):
        """
        Build kwargs to call the function:
        - start from defaults
        - overlay user-provided values
        - skip blanks ("" -> not provided)
        - convert to hinted type when possible
        """
        call_args = {}

        for name in self.parameters:
            value_set = False

            # 1) If user provided something, prefer that
            if name in kwargs:
                raw = kwargs[name]

                # Treat empty strings as "not provided"
                if isinstance(raw, str):
                    raw = raw.strip()
                    if raw == "":
                        raw = None

                if raw is not None:
                    # Convert according to type hints (falls back to original on failure)
                    coerced = self._convert_arg(name, raw)
                    if coerced is not None:
                        call_args[name] = coerced
                        value_set = True

            # 2) Otherwise, use default if we have one
            if not value_set and name in self.defaults:
                call_args[name] = self.defaults[name]
                value_set = True

            # 3) No user value and no default → pass None so the function can handle it
            if not value_set:
                param = self.parameters[name]
                if getattr(param, "default", inspect._empty) is inspect._empty:
                    call_args[name] = None
        # Pretty log of what we’re actually passing
        args_list = [f"{n}={repr(v)}" for n, v in call_args.items()]
        command = f"{self.func.__name__}({', '.join(args_list)})"
        print(command)
        logger.info(command)

        return self.func(**call_args)


if __name__ == "__main__":

    def sayHi(name: str, times: int = 1):
        for _ in range(times):
            print(f"Hi {name}")
        return name

    class Mode(str, Enum):
        LEFT = "left"
        CENTER = "center"
        RIGHT = "right"

    def fit(x: float, mode: Mode):
        print(f"fit {x}, {mode}")

    path = os.path.dirname(__file__)

    ui = ScriptRunner()
    ui.add_function(sayHi)
    ui.add_function(sayHi, name="Bob", times=3)
    ui.add_function(sayHi, "Greet all", name="all")
    ui.add_function(fit, "Fit it", mode=Mode.CENTER, x=1.0)
    ui.add_function(fit, "Fit it", mode="center", x=1.0)
    ui.add_function(fit, "Fit it", mode="CENTER", x=1.0)
    ui.add_cell("Say Hi", path + "/test_script.py")
    ui.add_cell(2, path + "/test_script.py", "Magic Button")
    ui.add_cell("Oops", path + "/test_script.py")
    ui.add_cell("Syntax Error", path + "/test_script.py")
