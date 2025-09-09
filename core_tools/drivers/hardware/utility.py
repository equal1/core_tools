from core_tools.data.ds.data_set import load_by_id, load_by_uuid

import numpy as np
import qcodes as qc


def load_virtual_gate_matrix_from_ds(ds_id, hardware_name='hardware'):
    '''
    load virtual gate matrix from a existing dataset.

    Args:
        ds_id (int) : id of the dataset to load
        hardware_name (str) : name of hardware in the snapshot present in the dataset
    '''
    load_virtual_gate_matrix_from_snapshot(load_by_id(ds_id).snapshot, hardware_name)


def load_virtual_gate_matrix_by_uuid(ds_uuid, hardware_name='hardware'):
    '''
    load virtual gate matrix from a existing dataset.

    Args:
        ds_uuid (int) : uuid of the dataset to load
        hardware_name (str) : name of hardware in the snapshot present in the dataset
    '''
    load_virtual_gate_matrix_from_snapshot(load_by_uuid(ds_uuid).snapshot, hardware_name)


def load_virtual_gate_matrix_from_snapshot(snapshot, hardware_name='hardware', no_norm=True):
    '''
    load virtual gate matrix from a existing datasset.

    Args:
        snapshot (dict) : snapshot of the station (loaded JSON)
        hardware_name (str) : name of hardware in the snapshot present in the dataset
    '''
    virtual_gates = snapshot['station']['instruments'][hardware_name]['virtual_gates']

    print('Loading all virtual gates matrices from dataset:')

    for vgm_name, value in virtual_gates.items():
        if no_norm:
            try:
                matrix = value['virtual_gate_matrix_no_norm']
            except KeyError:
                matrix = value['virtual_gate_matrix']
        else:
            matrix = value['virtual_gate_matrix']

        mat = np.array(eval(matrix))

        hw = qc.Station.default.hardware
        if vgm_name not in hw.virtual_gates.virtual_gate_names:
            hw.virtual_gates.add(vgm_name, value['real_gate_names'], value['virtual_gate_names'], mat)
            print(f"Added virtual gate matrix '{vgm_name}' ({mat.shape[0]}x{mat.shape[1]})")
        else:
            vgm = hw.virtual_gates[vgm_name]
            vgm.matrix = mat
            print(f"Updated virtual gate matrix '{vgm_name}' ({mat.shape[0]}x{mat.shape[1]})")


def load_AWG_to_dac_conversion_by_uuid(ds_uuid, hardware_name='hardware'):
    '''
    load AWG to dac conversion from a exisisting dataset.

    Args:
        ds_uuid (int) : uuid of the dataset to load
        hardware_name (str) : name of the hardware in the dataset its snapshot
    '''
    load_AWG_to_dac_conversion_from_snapshot(load_by_uuid(ds_uuid).snapshot, hardware_name)


def load_AWG_to_dac_conversion_from_ds(ds_id, hardware_name='hardware'):
    '''
    load AWG to dac conversion from a exisisting dataset.

    Args:
        ds_id (int) : id of the dataset to load
        hardware_name (str) : name of the hardware in the dataset its snapshot
    '''
    load_AWG_to_dac_conversion_from_snapshot(load_by_id(ds_id).snapshot, hardware_name)


def load_AWG_to_dac_conversion_from_snapshot(snapshot, hardware_name='hardware'):
    hardware_info = snapshot['station']['instruments'][hardware_name]
    if 'AWG_to_DAC' in hardware_info.keys():
        AWG_to_DAC = hardware_info['AWG_to_DAC']
    elif 'awg2dac_ratios' in hardware_info.keys():
        AWG_to_DAC = hardware_info['awg2dac_ratios']
    else:
        raise ValueError('AWG to DAC conversion not found!')

    hw = qc.Station.default.hardware
    hw.awg2dac_ratios.add(AWG_to_DAC.keys())

    for gate, value in AWG_to_DAC.items():
        hw.awg2dac_ratios[gate] = value
    print('AWG to dac conversions loaded!')
