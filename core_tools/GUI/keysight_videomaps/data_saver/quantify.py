from pathlib import Path

import logging

from qcodes import Instrument

from quantify_core.measurement import MeasurementControl
from quantify_core.data.handling import set_datadir, get_datadir, get_latest_tuid

from core_tools.utility.multiparameter_conversions import AwgScanToQuantifyMapper

DEFAULT_DATADIR = Path('./data')
"""The default data directory to use if none is set up for quantify_core"""
_MEASUREMENT_CONTROL_INSTRUMENT_NAME = 'MC_live_plot_saving'
"""The name to use for the measurement control instance."""


def save_data(vm_data_parameter, label):
    """
    Performs a measurement using quantify_core and writes the data to disk.

    Args:
        vm_data_parameter: a MultiParameter instance describing the measurement with settables, gettables and setpoints.
        label: a string that is used to label the dataset.

    Returns:
        A Tuple (ds, metadata) containing the created dataset ds and a metadata dict with information about the dataset.
    """
    try:
        datadir = get_datadir()
    except NotADirectoryError:
        logging.warning("No quantify_core datadir set. Using default.")
        datadir = str(DEFAULT_DATADIR)
        set_datadir(datadir)

    logging.info(f"Data directory set to: \"{datadir}\".")

    try:
        meas_ctrl = Instrument.find_instrument(_MEASUREMENT_CONTROL_INSTRUMENT_NAME)
    except KeyError:
        meas_ctrl = MeasurementControl(_MEASUREMENT_CONTROL_INSTRUMENT_NAME)
    meas_ctrl.verbose(False)

    unraveled_param = AwgScanToQuantifyMapper(vm_data_parameter)
    meas_ctrl.settables(unraveled_param.set_params)
    meas_ctrl.gettables(unraveled_param.get_params)

    if len(unraveled_param.set_params) > 1:
        meas_ctrl.setpoints_grid(unraveled_param.set_params_setpoints)
    else:
        meas_ctrl.setpoints(unraveled_param.set_params_setpoints[0])

    logging.debug(f'Starting measurement with name: {label}.')
    dataset = meas_ctrl.run(label)
    meas_ctrl.close()

    return dataset, {'tuid': get_latest_tuid(), 'datadir': datadir}
