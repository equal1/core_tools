from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from qcodes import Parameter
from pulse_lib.sequencer import index_param


class SequenceStartAction:
    def __init__(self, sequence):
        self._sequence = sequence

    def __call__(self):
        sequence = self._sequence
        sequence.upload()
        sequence.play()


def get_pulselib_sweeps(sequence) -> list[sweep_info]:
    '''
    Returns sweep parameters for the axes in the pulse sequence.

    Args:
        sequence (pulselib.sequencer.sequencer) : sequence object

    Returns:
        list[sweep_info] : sweeps along the axes of the sequence.
    '''
    set_params = []
    if sequence.shape == (1,):
        return set_params
    seq_params = sequence.params

    # Note: reverse order, because axis=0 is fastest running and must thus be last.
    for param in seq_params[::-1]:
        sweep = sweep_info(param)
        sweep.set_values(param.values)
        set_params.append(sweep)

    return set_params


@dataclass
class sweep_info:
    '''
    data class that hold the sweep info for one of the paramters.
    '''
    param: Parameter = None
    start: float = 0
    stop: float = 0
    n_points: int = 50
    delay: float = 0

    def __post_init__(self):
        self._values = None
        self.original_value = None
        if not isinstance(self.param, index_param):
            self.original_value = self.param()

    def reset_param(self):
        if self.original_value is not None:
            self.param.set(self.original_value)

    def set_values(self, values):
        self._values = values
        self.n_points = len(values)

    def values(self):
        if self._values is None:
            return np.linspace(self.start, self.stop, self.n_points)
        else:
            return self._values
