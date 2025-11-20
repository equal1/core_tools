import logging

from qcodes_contrib_drivers.drivers.Keysight.Keysight_E8267D import Keysight_E8267D as Keysight_E8267D_qcodes


logger = logging.getLogger(__name__)


class Keysight_E8267D(Keysight_E8267D_qcodes):

    def __init__(self, name, address, step_attenuator=False, **kwargs):
        logger.warning(
            "core_tools.drivers.Keysight_E8267D.Keysight_E8267D is deprecated. "
            "Use qcodes_contrib_drivers.drivers.Keysight.Keysight_E8267D.Keysight_E8267D."
            )

        super().__init__(name, address, step_attenuator=False, **kwargs)
