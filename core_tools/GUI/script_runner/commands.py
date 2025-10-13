import ast
import inspect
import json
import logging
import os
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Union, get_args, get_origin

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
        parameter = self.parameters[param_name]
        annotation = parameter.annotation
        if annotation is inspect._empty:
            # no type specified. Pass string.
            return value
        if isinstance(annotation, str):
            raise Exception('Cannot convert to type specified as a string')

        def _coerce(val, anno):
            if anno is inspect._empty:
                return val

            if isinstance(anno, str):
                raise Exception('Cannot convert to type specified as a string')

            origin = get_origin(anno)
            args = get_args(anno)

            # Simple classes
            if origin is None:
                if inspect.isclass(anno):
                    if issubclass(anno, bool):
                        return val in [True, 1, 'True', 'true', '1']
                    if issubclass(anno, Enum):
                        if isinstance(val, anno):
                            return val
                        try:
                            return anno(val)
                        except Exception:
                            return anno[str(val)]
                    return anno(val)
                return val

            # Sequences: list[T], tuple[T], set[T], frozenset[T]
            if origin in (list, tuple, set, frozenset):
                subtype = args[0] if args else Any
                if isinstance(val, str):
                    v = val.strip()
                    parsed = None
                    try:
                        parsed = json.loads(v)
                    except Exception:
                        try:
                            parsed = ast.literal_eval(v)
                        except Exception:
                            parsed = [x.strip() for x in v.split(',') if x.strip()]
                else:
                    parsed = val

                if isinstance(parsed, (list, tuple, set, frozenset)):
                    seq = [_coerce(item, subtype) for item in parsed]
                else:
                    seq = [_coerce(parsed, subtype)]
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
                        parsed = ast.literal_eval(v)
                    if not isinstance(parsed, dict):
                        raise ValueError('Not a dict')
                    items = parsed.items()
                return {_coerce(k, k_t): _coerce(v, v_t) for k, v in items}

            # Union types, try each option in order
            if origin is Union:
                for sub in args:
                    try:
                        return _coerce(val, sub)
                    except Exception:
                        continue
                raise ValueError(f'Value {val!r} does not match any allowed type')

            # Fallback: call the origin on the coerced value
            coerced = _coerce(val, origin or anno)
            return coerced

        try:
            return _coerce(value, annotation)
        except Exception as e:
            expected = pretty_type_str(annotation)
            raise ValueError(
                f"Invalid value for '{param_name}': {value!r} (expected {expected})"
            ) from e

    def __call__(self, **kwargs):
        call_args = {}

        for name in self.parameters:
            value_set = False

            if name in kwargs:
                raw_value = kwargs[name]
                if isinstance(raw_value, str):
                    raw_value = raw_value.strip()
                    if raw_value == '':
                        raw_value = None

                if raw_value is not None:
                    call_args[name] = self._convert_arg(name, raw_value)
                    value_set = True

            if not value_set and name in self.defaults:
                call_args[name] = self.defaults[name]
                value_set = True

            if not value_set:
                param = self.parameters[name]
                if getattr(param, 'default', inspect._empty) is inspect._empty:
                    call_args[name] = None

        args_list = [f'{name}={repr(value)}' for name, value in call_args.items()]
        command = f'{self.func.__name__}({", ".join(args_list)})'
        print(command)
        logger.info(command)
        return self.func(**call_args)
