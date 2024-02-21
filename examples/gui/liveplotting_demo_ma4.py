
from functools import partial
from pathlib import Path
import sys
import logging
import numpy as np
import PyQt5
import qcodes
from qcodes.data.io import DiskIO
from qcodes.data.data_set import DataSet
from qcodes.parameters import DelegateParameter
import qcodes.logger as qc_logger
from qcodes.logger import start_all_logging

from core_tools.GUI.keysight_videomaps.liveplotting import liveplotting, set_data_saver
from core_tools.GUI.keysight_videomaps.data_saver.qcodes import QCodesDataSaver
from core_tools.GUI.keysight_videomaps.data_getter.scan_generator_OPX import fake_digitizer
from core_tools.GUI.qt_util import qt_init

from pulse_lib.base_pulse import pulselib

from core_tools.drivers.gates import gates as Gates
from core_tools.drivers.hardware.hardware import hardware as Hardware

from core_tools.GUI.virt_gate_matrix_qml.gui_controller import (
    virt_gate_matrix_GUI as VirtGateMatrixGUI,
)
from core_tools.GUI.param_viewer.param_viewer_GUI_main import (
    param_viewer as ParamViewerGUI,
)

sys.path.append(str(Path('~/work/eq1x-scripts/opx-scripts').expanduser()))
from alice.Reflecto.opx_vm_functions import OPX_VM_Functions


# %%

start_all_logging()
qc_logger.get_console_handler().setLevel(logging.WARN)
qc_logger.get_file_handler().setLevel(logging.DEBUG)



# logger = logging.getLogger(__name__)
# start_all_logging()
# logger.get_file_handler().setLevel(logging.DEBUG)

try:
    qcodes.Instrument.close_all()
except: pass



class DummyAwg(qcodes.Instrument):
    def __init__(self, name):
        super().__init__(name)
    def get_idn(self):
        return {}
    def awg_flush(self, ch):
        pass
    def release_waveform_memory(self):
        pass


def create_pulse_lib(awgs):
    pulse = pulselib()
    for awg in awgs:
        pulse.add_awg(awg)
        # define channels
        chs =  ["HG13b", "HG11b", "HG09b", "HG07b", "HG12b"]
        for ch in chs:
            pulse.define_channel(ch, awg.name, ch)
    pulse.finish_init()
    return pulse


station = qcodes.Station()

# QDACII driver
from qcodes_contrib_drivers.drivers.QDevil import QDAC2
# OPX driver
from qualang_tools.external_frameworks.qcodes.opx_driver import OPX

# host: router IP address, port: 11+ last 3 dig of OPX
#opx = OPX(config, name="OPX_alice", host="opx-sc-001", port='11253', close_other_machines=False)
# opx = OPX(config, name="OPX_alice", host="opx-sc-001", port='11253', close_other_machines=True)
# #Add the OPX instrument to the QCoDeS station
# station.add_component(opx)



qdac2_addr = 'qdac-sc-001'
qdac2 = QDAC2.QDac2('QDAC', visalib='@py', address=f'TCPIP::{qdac2_addr}::5025::SOCKET')
# Create duplicates of the QDAC2 parameters from qdac2.ch<N>.dc_constant_V  to  qdac2.dac<N>
# this is needed because the Gate function assumes that the SPIRACK is being used 
# which uses parameters with a name 'dac<N>' with values in mV
for i in range(1,1+24):
    qdac2.add_parameter(    
        name=f'dac{i}',
        parameter_class=qcodes.DelegateParameter,
        source=qdac2.channel(i).dc_constant_V,
        label=f'dac{i}',
        unit='mV',
        scale=0.001,
    )



    
# Add the QDAC2 instrument to the QCoDeS station
station.add_component(qdac2)



########## Static Gate Stuff  ################################################################
hw = Hardware("hardware")

 
hw.dac_gate_map = {
    'Varactor_ctl': (0,10),  
    'HG13b'       : (0,13,1),
    'HG11b'       : (0,11,2),
    'HG09b'       : (0,12,3),
    'HG07b'       : (0,14,4),
    'HG12b'       : (0,15,9),
}
# The gate map definition, has been extended to support the Alpha3 sample 
# board where 2 channels can be specified, where
# The Alpha3 sample board connections do not use a bias-t, and the sample 
# is only connected to the second channel, the first channel is a dummy channel
# that is used to 'store' the DC component of the gate. 
# When writing to a gate it will write to two the QDAC2 channels at the same time
# the first is used to hold the DC component, while the second is used to
# write to the QDAC2 with its sweep pulse configuration


hw.boundaries = {name: (-10000, +10000) for name in hw.dac_gate_map}  # mV limits

# In the case of the Alpha3 Vcm and Vds offset voltages the 
# Matrix to go from virtual voltages to real voltages is simple
# but we need to use the inverse matrix for the pulse_lib functions
# (note pulse.add_virtual_matrix( real2virtual=False) does not seem to work)
v2r_VirtGateMatrix = [
    # Vgs13    Vgs11    Vgs09    Vds     Vcm
    [  1,        0,       0,      0,      1  ],   # HG13b
    [  0,        1,       0,      0,      1  ],   # HG11b
    [  0,        0,       1,      0,      1  ],   # HG09b
    [  0,        0,       0,    +0.5,     1  ],   # HG07b
    [  0,        0,       0,    -0.5,     1  ],   # HG12b
] 
r2v_VirtGateMatrix = np.linalg.inv(v2r_VirtGateMatrix)

v_gate_names = ["Vgs13", "Vgs11", "Vgs09", "Vds", "Vcm"]
gate_names = ["HG13b", "HG11b", "HG09b", "HG07b", "HG12b"]
hw.virtual_gates.add(
    "v_gates",
    gates=gate_names,
    virtual_gates=v_gate_names,
    matrix = r2v_VirtGateMatrix,
)

gates = Gates("gates", hardware=hw, dac_sources=[qdac2], dc_gain={})


# Create a dummy OPXQDAC AWG for performing the OPX sweeps
awg = DummyAwg(f'SWPQDAC')
awgs = [awg]
station.add_component(awg)

dig = fake_digitizer("fake_digitizer")  # creates a Multiparamter containing parameters chan_1, chan_2 of shape tuple([(20,20)]*2)
station.add_component(dig)

station.add_component(gates)
pulse = create_pulse_lib(awgs)

pulse.add_virtual_matrix(
    name="AWG_VirtGateMatrix",
    real_gate_names=    ["HG13b", "HG11b", "HG09b", "HG07b", "HG12b"],
    virtual_gate_names= ["Vgs13", "Vgs11", "Vgs09", "Vds", "Vcm"],  
    matrix=r2v_VirtGateMatrix,
    real2virtual=False,  # If True v_real = M^-1 @ v_virtual else v_real = M @ v_virtual ## not sure this is doing anything the way i'm using it!
    filter_undefined=False,
    keep_squared=True,
)

settings = {
    'gen':{
        '2D_colorbar':True,
        '2D_cross':True,
        'max_V_swing': 1500,
        },
    '1D':{
        'offsets':{'AWG3_1': 10.0},
        },
    '2D':{

        "gate1_name": "Vgs13",
        "V1_swing": 1000.0,  # mV
        "gate2_name": "Vgs11",
        "V2_swing": 1000.0,  # mV

        'offsets':{
            'Vgs13': 500,
            'Vgs11': 800,
            },
        },
    }

# By starting the Qt app before running the liveplotting function
# we cause the liveplotting function to exit and defer the running
# the app.exec() mainloop. This allows the running of the ParamViewerGui
app = PyQt5.QtWidgets.QApplication([])
plotting = liveplotting(pulse, dig, "OPX", settings, iq_mode='I+Q', gates=gates)
param_viewer = ParamViewerGUI(gates_object=gates, max_diff=10000)

pulse.opx = OPX_VM_Functions(pulse,gates,param_viewer)
pulse.opx.opx_startup_2D()

app.exec()



# ALL SETTIMGS:
#settings = {
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




plotting._2D_gate2_name.setCurrentIndex(1)
plotting._2D_t_meas.setValue(1)
plotting._2D_V1_swing.setValue(100)
plotting._2D_npt.setValue(80)


# %%
