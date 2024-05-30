import time, sys
from pathlib import Path
import numpy as np
from qcodes import MultiParameter

class fake_digitizer(MultiParameter):
        """docstring for fake_digitizer"""
        def __init__(self, name):
            super().__init__(name=name, names = ("chan_1", "chan_2"), shapes = tuple([(20,20)]*2),
                        labels = ("chan 1", "chan 2"), units =("mV", "mV"),
                        docstring='1D scan parameter for digitizer')

        def get_raw(self):
            return 0


def construct_1D_scan_fast(gate, swing, n_pt, t_step, biasT_corr, pulse_lib, digitizer, channels,
                           dig_samplerate=None, dig_vmax=None, iq_mode=None, acquisition_delay_ns=None,
                           enabled_markers=[], channel_map=None, pulse_gates={}, line_margin=0):
    """
    1D fast scan parameter constructor.

    Args:
        gate (str) : gate/gates that you want to sweep.
        swing (double) : swing to apply on the AWG gates. [mV]
        n_pt (int) : number of points to measure (current firmware limits to 1000)
        t_step (double) : time in ns to measure per point. [ns]
        biasT_corr (bool) : correct for biasT by taking data in different order.
        pulse_lib : pulse library object, needed to make the sweep.
        digitizer : digitizer object
        channels : digitizer channels to read
        dig_samplerate : digitizer sample rate [Sa/s]
        iq_mode (str or dict): when digitizer is in MODE.IQ_DEMODULATION then this parameter specifies how the
                complex I/Q value should be plotted: 'I', 'Q', 'abs', 'angle', 'angle_deg'. A string applies to
                all channels. A dict can be used to specify selection per channel, e.g. {1:'abs', 2:'angle'}.
                Note: channel_map is a more generic replacement for iq_mode.
        acquisition_delay_ns (float):
                Time in ns between AWG output change and digitizer acquisition start.
                This also increases the gap between acquisitions.
        enable_markers (List[str]): marker channels to enable during scan
        channel_map (Dict[str, Tuple(int, Callable[[np.ndarray], np.ndarray])]):
            defines new list of derived channels to display. Dictionary entries name: (channel_number, func).
            E.g. {(ch1-I':(1, np.real), 'ch1-Q':(1, np.imag), 'ch3-Amp':(3, np.abs), 'ch3-Phase':(3, np.angle)}
            The default channel_map is:
                {'ch1':(1, np.real), 'ch2':(2, np.real), 'ch3':(3, np.real), 'ch4':(4, np.real)}
        pulse_gates (Dict[str, float]):
            Gates to pulse during scan with pulse voltage in mV.
            E.g. {'vP1': 10.0, 'vB2': -29.1}
        line_margin (int): number of points to add to sweep 1 to mask transition effects due to voltage step.
            The points are added to begin and end for symmetry (bias-T).

    Returns:
        Parameter (QCODES multiparameter) : parameter that can be used as input in a conversional scan function.
    """
    if dig_vmax is not None:
        print(f'Parameter dig_vmax is deprecated.')
    vp = swing/2

    # set up sweep voltages (get the right order, to compenstate for the biasT).
    voltages_sp = np.linspace(-vp,vp,n_pt)
    if biasT_corr:
        m = (n_pt+1)//2
        voltages = np.zeros(n_pt)
        voltages[::2] = voltages_sp[:m]
        voltages[1::2] = voltages_sp[m:][::-1]
    else:
        voltages = voltages_sp

    return dummy_digitzer_scan_parameter(digitizer, None, pulse_lib, t_step, (n_pt, ), (gate, ),
                                          ( tuple(voltages_sp), ), tuple(voltages), biasT_corr, 500e6)


def construct_2D_scan_fast(gate1, swing1, n_pt1, gate2, swing2, n_pt2, t_step, biasT_corr, pulse_lib,
                           digitizer, channels, dig_samplerate=None, dig_vmax=None, iq_mode=None,
                           acquisition_delay_ns=None, enabled_markers=[], channel_map=None,
                           pulse_gates={}, line_margin=0):
    """
    2D fast scan parameter constructor.

    Args:
        gates1 (str) : gate that you want to sweep on x axis.
        swing1 (double) : swing to apply on the AWG gates.
        n_pt1 (int) : number of points to measure (current firmware limits to 1000)
        gate2 (str) : gate that you want to sweep on y axis.
        swing2 (double) : swing to apply on the AWG gates.
        n_pt2 (int) : number of points to measure (current firmware limits to 1000)
        t_step (double) : time in ns to measure per point.
        biasT_corr (bool) : correct for biasT by taking data in different order.
        pulse_lib : pulse library object, needed to make the sweep.
        digitizer_measure : digitizer object
        iq_mode (str or dict): when digitizer is in MODE.IQ_DEMODULATION then this parameter specifies how the
                complex I/Q value should be plotted: 'I', 'Q', 'abs', 'angle', 'angle_deg'. A string applies to
                all channels. A dict can be used to speicify selection per channel, e.g. {1:'abs', 2:'angle'}
                Note: channel_map is a more generic replacement for iq_mode.
        acquisition_delay_ns (float):
                Time in ns between AWG output change and digitizer acquisition start.
                This also increases the gap between acquisitions.
        enable_markers (List[str]): marker channels to enable during scan
        channel_map (Dict[str, Tuple(int, Callable[[np.ndarray], np.ndarray])]):
            defines new list of derived channels to display. Dictionary entries name: (channel_number, func).
            E.g. {(ch1-I':(1, np.real), 'ch1-Q':(1, np.imag), 'ch3-Amp':(3, np.abs), 'ch3-Phase':(3, np.angle)}
            The default channel_map is:
                {'ch1':(1, np.real), 'ch2':(2, np.real), 'ch3':(3, np.real), 'ch4':(4, np.real)}
        pulse_gates (Dict[str, float]):
            Gates to pulse during scan with pulse voltage in mV.
            E.g. {'vP1': 10.0, 'vB2': -29.1}
        line_margin (int): number of points to add to sweep 1 to mask transition effects due to voltage step.
            The points are added to begin and end for symmetry (bias-T).

    Returns:
        Parameter (QCODES multiparameter) : parameter that can be used as input in a conversional scan function.
    """
    if dig_vmax is not None:
        print(f'Parameter dig_vmax is deprecated.')

    # set up sweep voltages (get the right order, to compenstate for the biasT).
    vp1 = swing1/2
    vp2 = swing2/2

    voltages1 = np.linspace(-vp1,vp1,n_pt1)
    voltages2_sp = np.linspace(-vp2,vp2,n_pt2)
    if biasT_corr:
        m = (n_pt2+1)//2
        voltages2 = np.zeros(n_pt2)
        voltages2[::2] = voltages2_sp[:m]
        voltages2[1::2] = voltages2_sp[m:][::-1]
    else:
        voltages2 = voltages2_sp
    # Note: setpoints are in qcodes order
    return dummy_digitzer_scan_parameter(digitizer, None, pulse_lib, t_step,
                                         (n_pt2, n_pt1), (gate2, gate1),
                                         (tuple(voltages2_sp), (tuple(voltages1),)*n_pt2), (tuple(voltages2)),
                                         biasT_corr, 500e6, iq_mode=iq_mode )


class dummy_digitzer_scan_parameter(MultiParameter):
    """
    generator for the parameter f
    """
    def __init__(self, digitizer, my_seq, pulse_lib, t_measure, shape, names, setpoint, voltages2,
                 biasT_corr, sample_rate, data_mode = 0, channels = [1,2], iq_mode=None ):
        """
        args:
            digitizer (SD_DIG) : digizer driver:
            my_seq (sequencer) : sequence of the 1D scan
            pulse_lib (pulselib): pulse library object
            t_measure (int) : time to measure per step
            shape (tuple<int>): expected output shape
            names (tuple<str>): name of the gate(s) that are measured.
            setpoint (tuple<np.ndarray>): array witht the setpoints of the input data
            biasT_corr (bool): bias T correction or not -- if enabled -- automatic reshaping of the data.
            sample_rate (float): sample rate of the digitizer card that should be used.
            data mode (int): data mode of the digizer
            channels (list<int>): channels to measure
            voltages2: list of voltages for the y axis (outer loop) that may be alternating values if biasT_corr is enabled
        """


        # Define the plots to be displayed depending on the measurement_type
        if iq_mode == 'I+Q':
            channels = [ '_I', '_Q']
        elif iq_mode == 'I':
            channels = [ '_I']
        elif iq_mode == 'Q':
            channels = [ '_Q']
        elif iq_mode == 'Magnitude':
            channels = [ '_Magnitude']
        elif iq_mode == 'Mag+Phase':
            channels = [ '_Magnitude', '_Phase']
        elif iq_mode == 'MagdBm':
            channels = [ '_Mag_dBm']
        elif iq_mode == 'MagdBm+Phase':
            channels = [ '_Mag_dBm', '_Phase']
        elif iq_mode == 'Phase':
            channels = [ '_Phase']
        elif iq_mode == 'transport':
            channels = [ '_Transport_DC_current']
        pulse_lib.opx.channels = channels

        channel_names = [f'ch{ch}' for ch in channels]
        units = [''] * len(channels)

        self.dig = digitizer
        self.my_seq = my_seq
        self.pulse_lib = pulse_lib
        self.t_measure = t_measure
        self.n_rep = np.prod(shape)
        self.sample_rate =sample_rate
        self.data_mode = data_mode
        self.channels = channels
        self.biasT_corr = biasT_corr
        self.shape = shape
        self.channel_names = channel_names
        self.offset = 0.0
        self.voltages2 = voltages2

        super().__init__(
                name=digitizer.name,
                names=channel_names,
                shapes=tuple([shape]*len(channels)),
                labels=channel_names,
                units=units,
                setpoints=tuple([setpoint]*len(channels)),
                setpoint_names=tuple([names]*len(channels)),
                setpoint_labels=tuple([names]*len(channels)),
                setpoint_units=tuple([tuple(["mV"]*len(names))]*len(channels)),
                docstring='scan parameter for digitizer')

        pulse_lib.opx.opx_update_sweep(self, names, setpoint, t_measure, sample_rate, biasT_corr, voltages2)


       
    ###########################################################################################################
    def get_raw(self):
        data_out = self.pulse_lib.opx.opx_run()
        return tuple(data_out)
    ###########################################################################################################

    def stop(self):
        pass

    def restart(self):
        pass

    def close(self):
        self.opx.opx_close()

    def __del__(self):
        pass


if __name__ == '__main__':
    dig = fake_digitizer("test")

    param = construct_2D_scan_fast('P2', 10, 10, 'P5', 10, 10,50000, biasT_corr = True,
                               pulse_lib = None, digitizer= dig, channels=None, dig_samplerate = None)
    data = param.get()
    print(data)

    param_1D = construct_1D_scan_fast("P2", 10,10,5000, True, None, dig, channels=None, dig_samplerate = None)
    data_1D = param_1D.get()
    print(data_1D)