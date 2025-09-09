from core_tools.GUI.keysight_videomaps import liveplotting
from core_tools.GUI.keysight_videomaps.data_saver.qcodes import QCodesDataSaver
from core_tools.GUI.qt_util import qt_init


from pulse_lib.base_pulse import pulselib


def create_pulse_lib(awg_channels, dig_channels):
    pulse = pulselib()

    for num, ch_name in enumerate(awg_channels):
        pulse.define_channel(ch_name, "AWG_X", num)

    for num, ch_name in enumerate(dig_channels):
        pulse.define_digitizer_channel(ch_name, "Digitizer", num)

    # do not initialize backend
    # pulse.finish_init()
    return pulse


if __name__ == '__main__':

    pulse = create_pulse_lib(
        [f"P{i}" for i in range(1, 9)],
        [f"SD{i}" for i in range(1, 3)],
        )

    defaults = {
        'gen': {
            'n_columns': 2,
            'bias_T_RC': 5, # bias-T RC time [ms] only used for warnings in GUI.
            },
        }

    # Initialize Qt5 if running in IPython console
    qt_init()

    # Using the qcodes datasaver since that can be used without establishing the connection to the database.
    # Remove this line to use the default datasaver.
    liveplotting.set_data_saver(QCodesDataSaver())

    # Start the liveplotting
    plotting = liveplotting.liveplotting(
            pulse,
            scan_type="Virtual",
            cust_defaults=defaults,
            )
