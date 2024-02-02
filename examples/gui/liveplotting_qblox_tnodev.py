# WORK IN PROGRESS...

# %%
from functools import partial
import numpy as np
import PyQt5

import qcodes
from core_tools.drivers.D5a import D5a
from core_tools.drivers.gates import gates as Gates
from core_tools.drivers.hardware.hardware import hardware as Hardware
from core_tools.GUI.keysight_videomaps.data_saver.qcodes import QCodesDataSaver
from core_tools.GUI.keysight_videomaps.liveplotting import (
    liveplotting as LivePlotting,
    set_data_saver,
)
from core_tools.GUI.qt_util import qt_init
from core_tools.GUI.virt_gate_matrix_qml.gui_controller import (
    virt_gate_matrix_GUI as VirtGateMatrixGUI,
)
from core_tools.GUI.param_viewer.param_viewer_GUI_main import (
    param_viewer as ParamViewerGUI,
)
from pulse_lib.base_pulse import pulselib as PulseLib
from qblox_instruments import Cluster, ClusterType
from qcodes.data.data_set import DataSet
from qcodes.data.io import DiskIO
from spirack import SPI_rack
from core_tools.data.SQL.connect import set_up_local_storage

# %%

# start_all_logging()
# logger.get_file_handler().setLevel(logging.DEBUG)

try:
    qcodes.Instrument.close_all()
except Exception:
    pass

# %%
port = "COM3"
spi_rack = SPI_rack(port, baud=115200, timeout=1)
spi_rack.unlock()


firmware = spi_rack.get_firmware_version()
print(firmware)

# %%
cluster = Cluster(name="cluster", identifier="192.168.0.2")
cluster.reset()

# %% DAC SETTINGS
settings = {
    "mV": True,  # <-----------------------
    "reset_voltages": False,
    "inter_delay": 0.001,  # 1ms interval between steps
    "dac_step": 1,  # voltage step ~50uV~ 1mV?
}

d5a_1 = D5a("d5a_1", spi_rack, module=13, **settings)
d5a_2 = D5a("d5a_2", spi_rack, module=14, **settings)
d5a_3 = D5a("d5a_3", spi_rack, module=15, **settings)


hw = Hardware("hardware")

# REFLECTO settings
# similar to yaml settings but delays in nanoseconds
rf_frequency_Hz: float = 84.05e6
# rf_frequency_Hz: float = 113.31e6 # for sensor2
# rf_frequency_Hz: float = 113.1e6 # for sensor2

rf_pulse_power_dBm: float = 0
rf_acq_delay_ns = 120
rf_post_acq_delay_ns = 1000  # not even close to yaml value
rf_init_duration_ns = 0

hw.dac_gate_map = {
    "B5": (0, 1),
    "B6": (0, 2),
    "SD2P": (0, 3),
    # "A4": (0, 4),
    # "S3EDSR": (0, 5),
    # "A1": (0, 6),
    "SD1P": (0, 7),
    # "O2": (0, 8),
    # "A2": (0, 9),
    # "O1b": (0, 10),
    # "O1": (0, 11),
    "B0": (1, 10),
    "B1": (0, 13),
    "P1": (0, 12),
    "P2": (1, 9),
    # "L1": (0, 14),
    "SD1B2": (0, 15),
    "SD1B1": (0, 16),
    "P3": (1, 2),
    "B3": (1, 3),
    "P4": (1, 4),
    "B4": (1, 5),
    "P5": (1, 6),
    # "L4": (1, 7),
    "B2": (1, 8),  # , range: 4v bi
    "P6": (1, 11),
    # "O3": (1, 12),
    # "O4": (1, 13),
    # "A3": (1, 14),
    "SD2B1": (1, 1),
    "SD2B2": (1, 15),
    # "S1": (2, 1),
    # "S2": (2, 2),
    # "S4": (2, 3),
}  # connect the appropriate dac ports via the matrix module to your device

# mV limits
hw.boundaries = {name: (-500, +2000) for name in hw.dac_gate_map}

v_gate_names = ["SD1P", "P1", "P2", "B1"]

assert all(name in hw.dac_gate_map for name in v_gate_names)


# P1, P2 = M * (P1, P2)
##this matrix should be taken directly from the program
AWG_VirtGateMatrix = [
    [1.0, -0.058, -0.023],
    [0, 1.0, -0.144],
    [0, -0.41, 1],
    
    
    # [1.0, -0.144],
    # [-0.41, 1.0],
]


# start D:\Users\Equal1\start-postgres.bat
set_up_local_storage(
    user="myusername",
    passwd="mypasswd",
    dbname="mydbname",
    project="project_name",
    set_up="set_up_name",
    sample="sample_name",
)


hw.virtual_gates.add(
    "v_gates",
    gates=v_gate_names,
)


gates = Gates("gates", hardware=hw, dac_sources=[d5a_1, d5a_2, d5a_3], dc_gain={})


# setup QCODES data storage
path = "D:/Users/Equal1/videomode_data/20231031"

io = DiskIO(path)
DataSet.default_io = io
set_data_saver(QCodesDataSaver())

station = qcodes.Station()


def dBm_to_mVamp(dBm, Z=50):
    """
    Convert given dBm (power) value
    to mV amplitude (half of vpp)
    assuming Z=50ohm impedance
    """
    return np.sqrt(np.power(10, dBm / 10 + 3) * Z / 2)  
    # Peter's formula:
    # return np.sqrt(np.power(10, dBm / 10 + 3) * 2 * Z)
    # see also https://qtwork.tudelft.nl/~schouten/linkload/dbm-conv.pdf

def awg2gate(physical: str)->str:
    return {
        "qcm4_out1": "SD1P", # A8
        "qcm4_out3": "SD2P", # A2
        "qcm2_out1": "P1", # B10
        "qcm2_out3": "P2", # A5
    }.get(physical, physical)


def create_Qblox_PulseLib(
    cluster,
    /,
    *,
    frequency: float,
    amplitude_mV: float,
):
    pulse = PulseLib(backend="Qblox")
    pulse.add_awg(cluster.module2)
    pulse.add_awg(cluster.module4)
    pulse.add_digitizer(cluster.module6)

    for i in range(4):
        pulse.define_channel(awg2gate(f"qcm2_out{i+1}"), cluster.module2.name, i)
    for i in range(4):
        pulse.define_channel(awg2gate(f"qcm4_out{i+1}"), cluster.module4.name, i)
    for i in range(2):
        pulse.define_channel(awg2gate(f"qrm6_out{i+1}"), cluster.module6.name, i)
    for i in range(2):
        if i == 0:
            pulse.define_digitizer_channel(f"qrm6_in{i+1}", cluster.module6.name, i)

    pulse.set_digitizer_rf_source(
        channel_name="qrm6_in1",
        output=(cluster.module6.name, 0),
        mode="pulsed",
        amplitude=amplitude_mV,  #  type: ignore
        startup_time_ns=rf_init_duration_ns + rf_acq_delay_ns,
        prolongation_ns=rf_post_acq_delay_ns,
        source_delay_ns=rf_init_duration_ns,
    )
    pulse.set_digitizer_frequency("qrm6_in1", frequency)

    pulse.set_channel_attenuations(
        {
            ##assumed that P1,P2 and sensor have same attenuation
            "SD1P": 1/12.5,
            "P1": 1/12.5,  # ratio
            "P2": 1/12.5,  # ratio 
        }
    )

    """
    Adds a virtual gate matrix.
    A real gate name must either be AWG channel or an already defined
    virtual gate name of another matrix.

    Args:
        name (str): name of the virtual gate matrix.
        real_gate_names (list[str]): names of real gates
        virtual_gate_names (list[str]): names of virtual gates
        matrix (2D array-like): matrix to convert voltages of virtual gates to voltages of real gates.
        real2virtual (bool): If True v_real = M^-1 @ v_virtual else v_real = M @ v_virtual
        filter_undefined (bool): If True removes rows with unknown real gates.
        keep_squared (bool): matrix is square and should be kept square when valid_indices is used.
        awg_channels (list[str]): names of the AWG channels.
    """

    pulse.add_virtual_matrix(
        name="AWG_VirtGateMatrix",
        # real_gate_names= ["P1", "P2"], #["SD1P", "P1", "P2"],
        # virtual_gate_names=["vP1", "vP2"], #["vSD1P", "vP1", "vP2"],
        real_gate_names= ["SD1P", "P1", "P2"],
        virtual_gate_names=["vSD1P", "vP1", "vP2"],  
        #as a temporary solution we define the matrix manually, ideally we should take the input from the one defined in the GUI
        #should be smthg like VirtGateMatrixGUI()
        matrix=AWG_VirtGateMatrix,
        real2virtual=False,  # If True v_real = M^-1 @ v_virtual else v_real = M @ v_virtual
        filter_undefined=False,
        keep_squared=True,
    )

    pulse.finish_init()
    return pulse


pulse = create_Qblox_PulseLib(
    cluster, frequency=rf_frequency_Hz, amplitude_mV=dBm_to_mVamp(rf_pulse_power_dBm)
)

settings = {
    "gen": {
        "2D_colorbar": True,
        "2D_cross": True,
        "max_V_swing": 250,
    },
    "1D": {
        # "offsets": {"qcm2_out1": 10.0},
    },
    "2D": {
        "gate1_name": "vP1",
        "V1_swing": 10.0,  # mV
        "gate2_name": "vP2",
        "V2_swing": 10.0,  # mV
        "offsets": {
            # ---
            # "qcm2_out1": 12.0,
            # "qcm4_out1": 1.0,
        },
        
    },
}

station.add_component(hw)
# qt_init()
app = PyQt5.QtWidgets.QApplication([])
print(app)
plotting = LivePlotting(
    pulse,
    None,
    "Qblox",
    settings,
    # --------------------------------
    iq_mode="amplitude",  # "I+Q"
    gates=gates,
)
param_viewer = ParamViewerGUI(gates_object=gates)

if v_gate_names:
    virt_gates = VirtGateMatrixGUI()


app.exec()


# ALL SETTIMGS:
# settings = {
#    '1D': {
#        'gate_name': 'vP1',
#        'V_swing': 20.0,
#        'npt': 100,
#        't_meas': 25.0,
#        'average': 200,
#        'offsets':{'AWG3_1': 10.0},
#        },
#    '2D': {
#        'gate1_name': 'vP1',
#        'V1_swing': 20.0,
#        'gate2_name': 'vP2',
#        'V2_swing': 10.0,
#        'npt': 100,
#        't_meas': 25.0,
#        'average': 200,
#        'offsets':{'AWG3_1': 10.0},
#        },
#    'gen': {
#        'n_columns': 2,
#        '2D_colorbar':True,
#        '2D_cross':True,
#        'max_V_swing': 250,
#        }
#    }

# plotting._2D_gate2_name.setCurrentIndex(1)
# plotting._2D_t_meas.setValue(1)
# plotting._2D_V1_swing.setValue(100)
# plotting._2D_npt.setValue(80)