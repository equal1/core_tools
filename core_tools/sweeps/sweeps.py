import logging

from core_tools.sweeps.scans import Scan, ArraySetter
# re-export scan_generic for compatibility reasons
from core_tools.sweeps.sweeps_legacy import scan_generic

import numpy as np


logger = logging.getLogger(__name__)


def do0D(*m_instr, name="", silent=False):
    """
    do a 0D scan

    Args:
        m_instr (*list) :  list of parameters to measure
    """
    return Scan(
        *m_instr,
        name=name,
        reset_param=False,
        silent=silent,
    )


def do1D(
    param, start, stop, n_points, delay, *m_instr, name="", reset_param=False,
    silent=False
):
    """
    do a 1D scan

    Args:
        param (qc.Parameter) : parameter to be swept
        start (float) : start value of the sweep
        stop (float) : stop value of the sweep
        delay (float) : time to wait after the set of the parameter
        m_instr (*list) :  list of parameters to measure
        reset_param (bool) : reset the setpoint parametes to their original value
            after the meaurement
        silent (bool) : If True do not print dataset id and progress bar
    """
    m_param = ArraySetter(
        param=param,
        data=np.linspace(start, stop, n_points),
        delay=delay,
    )
    return Scan(
        m_param,
        *m_instr,
        name=name,
        reset_param=reset_param,
        silent=silent
    )


def do2D(
    param_1, start_1, stop_1, n_points_1, delay_1,
    param_2, start_2, stop_2, n_points_2, delay_2,
    *m_instr, name="", reset_param=False, silent=False
):
    """
    do a 2D scan

    Args:
        param_1 (qc.Parameter) : parameter to be swept
        start_1 (float) : start value of the sweep
        stop_1 (float) : stop value of the sweep
        delay_1 (float) : time to wait after the set of the parameter
        param_2 (qc.Parameter) : parameter to be swept
        start_2 (float) : start value of the sweep
        stop_2 (float) : stop value of the sweep
        delay_2 (float) : time to wait after the set of the parameter
        m_instr (*list) :  list of parameters to measure
        reset_param (bool) : reset the setpoint parametes to their original value
            after the meaurement
        silent (bool) : If True do not print dataset id and progress bar
    """

    m_param_1 = ArraySetter(
        param=param_1,
        data=np.linspace(start_1, stop_1, n_points_1),
        delay=delay_1,
    )
    m_param_2 = ArraySetter(
        param=param_2,
        data=np.linspace(start_2, stop_2, n_points_2),
        delay=delay_2,
    )

    return Scan(
        m_param_2,
        m_param_1,
        *m_instr,
        name=name,
        reset_param=reset_param,
        silent=silent
    )
