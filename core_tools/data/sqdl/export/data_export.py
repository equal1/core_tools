import json
import logging
import os
import numpy as np
from core_tools import __version__ as ct_version
from core_tools.data.ds.ds_hdf5 import save_xr_hdf5
from core_tools.data.ds.ds2xarray import ds2xarray

from .utils import atomic_write


logger = logging.getLogger(__name__)


def get_dim_props(descr):
    return {
        'key': descr.name,
        'name': descr.param_name,
        'label': descr.label,
        'unit': descr.unit,
        'shape': descr.shape,
    }


def get_var_props(descr):

    return {
        'key': descr.name,
        'name': descr.param_name,
        'label': descr.label,
        'unit': descr.unit,
        'shape': descr.shape,
        'written': descr.written(),
        'dims': [
            get_dim_props(param)
            for params in descr.get_raw_content()
            for name, param in params
        ],
    }


def get_var_descr(ds):
    result = []
    for m_param in ds:
        for name, descr in m_param:
            result.append(get_var_props(descr))
    return result


def fix_dirname(dirname):
    dirname = dirname.replace('/', '_')
    return dirname


def fix_dataset_name(name):
    name = name.strip()
    if len(name) > 120:
        name = name[:120]
    return name


def export_data(ds, scope, path, timer, updates, write_raw=True):
    uuid = ds.exp_uuid
    path = os.path.expanduser(path)

    timer.time('info')
    var_descr = get_var_descr(ds)
    var_list = [d['name'] for d in var_descr]
    dims = set(
        dim['name']
        for var in var_descr
        for dim in var['dims']
    )

    name_value = fix_dataset_name(ds.name)
    info = {
        'name': name_value,
        'title': name_value,
        'description': name_value,
        'uid': ds.exp_uuid,
        'scope': scope,
        'project': ds.project,
        'setup': ds.set_up,
        'sample': ds.sample_name,
        'date_collected': str(ds.run_timestamp),
        'rating': 1 if ds.starred else 0,
        'vars': var_list,
        'dims': list(dims),
        'var_description': var_descr,
        'application': f"core-tools:{ct_version}",
    }

    var_summary = []
    for var in var_descr:
        dim_desr = [
            f"{dim['name']}:(" + ','.join(str(i) for i in dim['shape']) + ')'
            for dim in var['dims']
        ]
        var_summary.append(f"{var['name']}({var['written']}):" + ','.join(dim_desr))

    logger.debug(f'info: {ds.exp_uuid}, {var_summary}')
    # logger.debug(f'info: {ds.exp_uuid}, {var_list}, {list(dims)}')

    if sum(var['written'] for var in var_descr) == 0:
        raise Exception(f'No data in dataset {uuid}')

    dir_name = fix_dirname(ds.project)
    ds_dir = f'/{dir_name}/{ds.run_timestamp:%Y-%m-%d}/{uuid}'
    ds_path = path + ds_dir

    timer.time('save json')
    if not os.path.exists(path):
        raise Exception(f"Path '{path}' does not (yet) exist.")

    os.makedirs(ds_path, exist_ok=True)
    logger.info(f'Path {ds_path}')
    metadata_path = f'{ds_path}/{uuid}.json'
    if os.path.exists(metadata_path):
        with open(metadata_path) as fp:
            old_info = json.load(fp)

        if old_info['name'] != ds.name:
            updates.update_name = True
            old_info['name'] = ds.name

        try:
            if old_info['starred'] != ds.starred:
                updates.update_star = True
                old_info['starred'] = ds.starred
        except KeyError:
            if bool(old_info['rating']) != ds.starred:
                updates.update_star = True
                old_info['rating'] = 1 if ds.starred else 0
    else:
        updates.upload_dataset = True

    with atomic_write(metadata_path) as metadata_path_tmp:
        with open(metadata_path_tmp, 'w') as fp:
            json.dump(info, fp, indent=2)

    for var in var_descr:
        size = np.prod(var['shape'])
        if size > 2**28:
            raise Exception(f"Dataset {uuid} too big. Var {var['name']}{tuple(var['shape'])} > 2 GB.")

    hdf5_name = ds_path + f'/ds_{uuid}.hdf5'
    dsx = ds2xarray(ds)
    if write_raw:
        timer.time('save hdf5')
        save_xr_hdf5(dsx, hdf5_name)
        updates.upload_raw_data = True

    return dsx, ds_path, var_descr
