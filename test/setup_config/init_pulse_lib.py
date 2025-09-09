from pulse_lib.base_pulse import pulselib


def init_pulse_lib(hardware, awgs):
    """
    create pulse object

    Args:
        hardware : hardware class (if not present, put None)
        awgs : AWG instances you want to add (qcodes AWG object)
    """
    pulse = pulselib(backend='M3202A')

    # add to pulse_lib
    for awg in awgs:
        pulse.add_awg(awg)

    # define channels
    pulse.define_channel('NW_P', 'AWG1', 1)
    pulse.define_channel('NE_P', 'AWG1', 2)
    pulse.define_channel('SW_P', 'AWG1', 3)
    pulse.define_channel('SE_P', 'AWG1', 4)
    pulse.define_channel('UB1', 'AWG3', 1)
    pulse.define_channel('LB1', 'AWG3', 2)
    pulse.define_channel('P1', 'AWG3', 3)
    pulse.define_channel('P2', 'AWG3', 4)
    pulse.define_channel('P7', 'AWG4', 1)
    pulse.define_channel('P4', 'AWG4', 2)
    pulse.define_channel('P5', 'AWG4', 4)
    pulse.define_channel('P6', 'AWG4', 3)
    pulse.define_channel('LB7', 'AWG5', 1)
    pulse.define_channel('UB4', 'AWG5', 2)
    pulse.define_channel('UB5', 'AWG5', 3)
    pulse.define_channel('LB8', 'AWG5', 4)
    pulse.define_channel('UB6', 'AWG6', 4)
    pulse.define_channel('UB3', 'AWG6', 3)
    pulse.define_channel('UB2', 'AWG6', 2)
    pulse.define_channel('P3', 'AWG6', 1)
    pulse.define_channel('LB6', 'AWG7', 4)
    pulse.define_channel('LB5', 'AWG7', 3)
    pulse.define_channel('LB4', 'AWG7', 2)
    pulse.define_channel('LB3', 'AWG7', 1)
    pulse.define_channel('LB2', 'AWG8', 4)
    pulse.define_channel('UB7', 'AWG8', 3)
    pulse.define_channel('UB8', 'AWG8', 2)
    pulse.define_channel('test', 'AWG8', 1)
    pulse.define_channel('MW_I', 'AWG2', 3)
    pulse.define_channel('MW_Q', 'AWG2', 4)

    pulse.define_marker('M1', 'AWG1', 0, setup_ns=60, hold_ns=60)

    # format : channel name with delay in ns (can be posive/negative)
    # pulse.add_channel_delay('I_MW',-60)
    # pulse.add_channel_delay('Q_MW',-60)
    # pulse.add_channel_delay('M1',-110)
    # pulse.add_channel_delay('M1',-25)

    # add limits on voltages for DC channel compenstation (if no limit is specified, no compensation is performed).
    # max_c = 20
    max_c = 100
    for ch in pulse.awg_channels:
        att = pulse.awg_channels[ch].attenuation
        pulse.add_channel_compensation_limit(ch, (-max_c/att, max_c/att))

    pulse.define_iq_channel("IQ-1", i_name="MW_I", q_name="MW_Q", marker_name="M1")
    pulse.set_iq_lo("IQ-1", 5e9)
    # pulse.set_iq_lo("IQ-1", station.sig_gen.frequency)
    pulse.define_qubit_channel("MW_q6", "IQ-1", resonance_frequency=5.12e9)
    pulse.define_qubit_channel("MW_q7", "IQ-1", resonance_frequency=4.92e9)

    if hardware is not None:
        pulse.load_hardware(hardware)

    pulse.finish_init()

    return pulse
