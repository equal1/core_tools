import qcodes as qc
from core_tools.GUI.qt_util import qt_init

from .config import get_configuration


# global references to GUIs to avoid garbage collection
_pv_qt = None
_vmg_qt = None
_script_runner = None


def start_parameter_viewer():
    from core_tools.GUI.param_viewer.param_viewer_GUI_main import param_viewer

    global _pv_qt
    gates = _get_gates()
    cfg = get_configuration()
    qt_init(style=cfg.get('gui.style'))
    _pv_qt = param_viewer(
            gates,
            max_diff=cfg.get('max_diff'),
            locked=cfg.get('parameter_viewer.lock', False))
    _set_window(_pv_qt, cfg, 'parameter_viewer')
    return _pv_qt


def start_parameter_viewer_qml():
    raise Exception("QML is not supported anymore")


def start_virtual_matrix_gui(pulse):
    from core_tools.GUI.virt_gate_matrix.virt_gate_matrix_main import virt_gate_matrix_GUI

    global _vmg_qt
    hardware = _get_hardware()
    cfg = get_configuration()
    qt_init(style=cfg.get('gui.style'))
    _vmg_qt = virt_gate_matrix_GUI(hardware, pulse,
                                   coloring=cfg.get('virtual_matrix_gui.coloring', True))
    _set_window(_vmg_qt, cfg, 'virtual_matrix_gui')
    return _vmg_qt


def start_virtual_matrix_gui_qml():
    raise Exception("QML is not supported anymore")


def start_script_runner():
    from core_tools.GUI.script_runner.script_runner_main import ScriptRunner

    global _script_runner
    cfg = get_configuration()
    qt_init(style=cfg.get('gui.style'))
    _script_runner = ScriptRunner()
    _set_window(_script_runner, cfg, 'script_runner')
    return _script_runner


def _get_station():
    return qc.Station.default


def _get_gates():
    try:
        return _get_station().gates
    except AttributeError:
        raise AttributeError('gates not added to station')


def _get_hardware():
    try:
        return _get_station().hardware
    except AttributeError:
        raise AttributeError('hardware not added to station')


def _set_window(window, cfg, cfg_key):
    try:
        location = cfg[f'{cfg_key}.location']
        window.move(location[0], location[1])
    except KeyError:
        pass
    try:
        size = cfg[f'{cfg_key}.size']
        window.resize(size[0], size[1])
    except KeyError:
        pass
