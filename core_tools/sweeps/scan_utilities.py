
from time import perf_counter, sleep
from typing import Any

import numpy as np
from qcodes.instrument.parameter import Parameter, ManualParameter

from core_tools.sweeps.scans import ArraySetter


class Repeat(ArraySetter):
    """ Repeat loop in measurement. """

    def __init__(
            self,
            name: str,
            n: int,
            param_label: str | None = None,
            resume_label: str | None = None,
            ):
        """Repeat loop.

        Args:
            name: The name of the parameter.
            n: number of repetitions.
            param_label: label for parameter in dataset.
            resume_label: Label to use for resume after break.
        """
        parameter = ManualParameter(name, label=param_label)
        parameter(0)
        values = np.arange(n)

        super().__init__(parameter, values, label=resume_label)


class Periodic(ArraySetter):
    """ Periodic loop in measurement measuring at regular intervals. """

    def __init__(
            self,
            name: str,
            interval: float,
            duration: float,
            margin: float = 0.05,
            param_label: str | None = None,
            resume_label: str | None = None,
            ):
        """ Periodic loop.

        Args:
            name: The name of the parameter.
            interval: measurement interval [s].
            duration: measurement duration [s].
            margin: Maximum allowed overshoot when setting the time.
            param_label: label for parameter in dataset.
            resume_label: Label to use for resume after break.
        """
        parameter = TimerParameter(name, label=param_label, margin=margin)

        values = np.arange(0, duration+(interval/1000), interval)
        super().__init__(parameter, values, label=resume_label)


class TimerParameter(Parameter):
    """
    Parameter to time and register elapsed time. It uses wall clock time since the
    last reset of the instance's clock. Setting the time pauses execution till the
    elapsed time has reached the specified value.
    The clock is reset upon creation of the instance and when the value is set to 0.0.
    The constructor passes kwargs along to the Parameter constructor.

    Args:
        name: The local name of the parameter. See the documentation of
            :class:`qcodes.instrument.parameter.Parameter` for more details.
        margin: Maximum allowed overshoot when setting the time.

    Example:
        timer_param = TimerParameter('t')

        Scan(
            sweep(timer_param, 0, 5, 0.5), # measure during 5 seconds with 11 points (of 0.5 s interval)
            param_x,  # measure param X
            param_y,  # measure param Y
            ).run()

    """

    def __init__(self, name: str,
                 label: str | None = None,
                 margin: float = 0.05,
                 **kwargs: Any):

        hardcoded_kwargs = ['unit', 'get_cmd', 'set_cmd']

        for hck in hardcoded_kwargs:
            if hck in kwargs:
                raise ValueError(f'Can not set "{hck}" for an '
                                 'ElapsedTimeParameter.')

        super().__init__(name=name,
                         label=label,
                         unit='s',
                         **kwargs)

        self._t0: float = perf_counter()
        self._margin = margin

    def get_raw(self) -> float:
        return perf_counter() - self.t0

    def set_raw(self, value: float) -> None:
        """
        Waits till the elapsed time has the reached `value`.
        Raises:
            Exception when the wait time is negative and smaller than
            configured margin.
        """
        if value == 0.0:
            self.reset_clock()
            return
        sleep_time = value - self.get_raw()
        if sleep_time < -self._margin:
            raise Exception(f'Measurement too late by {-sleep_time:.3f} s (margin={self._margin:.3f})')
        if sleep_time >= 0.001:
            sleep(sleep_time)
        overshoot = self.get_raw() - value
        if overshoot > self._margin:
            raise Exception(f'Measurement too late by {overshoot:.3f} s (margin={self._margin:.3f})')

    def reset_clock(self) -> None:
        self._t0 = perf_counter()

    @property
    def t0(self) -> float:
        return self._t0
