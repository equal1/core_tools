import inspect
import logging
import os
from enum import Enum
from typing import Any

from abc import ABC, abstractmethod

try:
    from spyder_kernels.customize.spydercustomize import runcell
    runcell_version = 5
except Exception:
    runcell = None

try:
    from IPython import get_ipython  # pyright: ignore

    ipython = get_ipython()
    if ipython is not None:
        runcell = ipython.magics_manager.magics['line']['runcell']
        runcell_version = 6
except KeyError:
    # no runcell magic
    pass


logger = logging.getLogger(__name__)


class Command(ABC):
    def __init__(self, name, parameters, defaults={}):
        self.name = name
        self.parameters = parameters
        self.defaults = defaults

    @abstractmethod
    def __call__(self):
        pass


class Cell(Command):
    '''
    A reference to an IPython cell with Python code to be run as command in
    ScriptRunner.

    If command_name is not specified then cell+filename with be used as command name.

    Args:
        cell: name or number of cell to run.
        python_file: filename of Python file.
        command_name: Optional name to show for the command in ScriptRunner.
    '''

    def __init__(self, cell: str | int, python_file: str, command_name: str | None = None):
        filename = os.path.basename(python_file)
        name = f'{cell} ({filename})' if command_name is None else command_name
        super().__init__(name, {})
        self.cell = cell
        self.python_file = python_file
        if runcell is None:
            raise Exception('runcell not available. Upgrade to Spyder 4+ to use Cell()')

    def __call__(self):
        if runcell_version == 5:
            command = f"runcell({self.cell}, '{self.python_file}')"
            print(command)
            logger.info(command)
            runcell(self.cell, self.python_file)
        elif runcell_version == 6:
            if isinstance(self.cell, int):
                command = f"-i {self.cell} {self.python_file}"
            else:
                command = f"-n '{self.cell}' {self.python_file}"
            print("runcell", command)
            logger.info(f"runcell {command}")
            result = runcell(command)
            print(result)


class Function(Command):
    '''
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
    '''

    def __init__(self, func: Any, command_name: str | None = None, **kwargs):
        if command_name is None:
            command_name = func.__name__
        signature = inspect.signature(func)
        parameters = {p.name: p for p in signature.parameters.values()}
        defaults = {}
        for name, parameter in parameters.items():
            if parameter.default is not inspect._empty:
                defaults[name] = parameter.default
            if parameter.annotation is inspect._empty:
                logger.warning(f'No annotation for `{name}`, assuming string')
        defaults.update(**kwargs)
        super().__init__(command_name, parameters, defaults)
        self.func = func

    def _convert_arg(self, param_name, value):
        annotation = self.parameters[param_name].annotation
        if annotation is inspect._empty:
            # no type specified. Pass string.
            return value
        if isinstance(annotation, str):
            raise Exception('Cannot convert to type specified as a string')
        if issubclass(annotation, bool):
            return value in [True, 1, 'True', 'true', '1']
        if issubclass(annotation, Enum):
            return annotation[value]
        return annotation(value)

    def __call__(self, **kwargs):
        call_args = {}
        for name in self.parameters:
            try:
                call_args[name] = self.defaults[name]
            except KeyError:
                pass
            try:
                call_args[name] = self._convert_arg(name, kwargs[name])
            except KeyError:
                pass
        args_list = [f'{name}={repr(value)}' for name, value in call_args.items()]
        command = f'{self.func.__name__}({", ".join(args_list)})'
        print(command)
        logger.info(command)
        return self.func(**call_args)
