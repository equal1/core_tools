import qcodes as qcodes
import os

import setup_config

from setup_config.setup_hardware import setup_hardware
from pulse_lib.tests.mock_m3202a import MockM3202A


def init_station():
    # load config file with the instrument settings
    instrument_config_path = os.path.join(
            os.path.dirname(setup_config.__file__),
            'instruments.yaml'
    )
    station = qcodes.Station(config_file=instrument_config_path)

    station.load_instrument('D5a1')
    station.load_instrument('D5a2')
    station.load_instrument('D5a3')
    # station.load_instrument('D5a1', spi_rack=None)
    # station.load_instrument('D5a2', spi_rack=None)
    # station.load_instrument('D5a3', spi_rack=None)

    hw = setup_hardware()
    station.add_component(hw)
    station.load_instrument(
        'gates',
        hardware=hw,
        dac_sources=[
            station.D5a1,
            station.D5a2,
            station.D5a3
        ]
    )

    # load the digitizer
    dig = MockM3202A(
            name="Dig1",
            chassis=1,
            slot=11
    )
    station.add_component(dig)

    station.load_instrument('AWG1')
    station.load_instrument('AWG2')
    station.load_instrument('AWG3')
    station.load_instrument('AWG4')
    station.load_instrument('AWG5')
    station.load_instrument('AWG6')
    station.load_instrument('AWG7')
    station.load_instrument('AWG8')

    return station
