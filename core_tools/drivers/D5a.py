import logging

from qcodes_contrib_drivers.drivers.QuTech.D5a import D5a as D5a_qcodes


logger = logging.getLogger(__name__)


class D5a(D5a_qcodes):

    def __init__(self, name, spi_rack, module, inter_delay=0.1, dac_step=10e-3,
                 reset_voltages=False, mV=False, number_dacs=16, **kwargs):
        logger.warning(
            "core_tools.drivers.D5a.D5a is deprecated. "
            "Use qcodes_contrib_drivers.drivers.QuTech.D5a.D5a."
        )
        super().__init__(
            name, spi_rack, module,
            inter_delay=inter_delay,
            dac_step=dac_step,
            reset_voltages=reset_voltages,
            mV=mV,
            number_dacs=number_dacs,
            **kwargs
        )
