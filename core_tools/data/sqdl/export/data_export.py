import os
import json
import re
import logging
from typing import Any
from pathlib import Path

from core_tools import __version__ as ct_version
from core_tools.data.ds.ds_hdf5 import save_xr_hdf5
from core_tools.data.ds.ds2xarray import ds2xarray

from .utils import atomic_write

import numpy as np

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
    info, var_descr = get_dataset_info(ds, scope)
    var_summary = make_variable_summary(var_descr)
    logger.debug(f'info: {ds.exp_uuid}, {var_summary}')

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
    determine_update_behaviour(updates, ds, metadata_path)

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


def determine_update_behaviour(updates, ds, path):
    if os.path.exists(path):
        with open(path) as fp:
            old_info = json.load(fp)

        if old_info['name'] != ds.name:
            updates.update_name = True

        try:
            if old_info['starred'] != ds.starred:
                updates.update_star = True
        except KeyError:
            if bool(old_info['rating']) != ds.starred:
                updates.update_star = True
    else:
        updates.upload_dataset = True


def update_metadata(ds_path, uuid):
    metadata_path = f'{ds_path}/{uuid}.json'
    with open(metadata_path) as file:
        info = json.load(file)

    exported_files = get_exported_files(dataset_path=ds_path)
    update_file_info(info, exported_files)

    # review todo: do we still need atomic writes in the case of single-process
    #  exporting? can't imagine so
    with atomic_write(metadata_path) as metadata_path_tmp:
        with open(metadata_path_tmp, 'w') as fp:
            json.dump(info, fp, indent=2)


def get_dataset_info(dataset, scope: str) -> tuple[dict[str, Any], list[Any]]:
    """
    review todo

    Args:
        dataset: Dataset object being exported.
        scope: Scope name that the dataset belongs to.

    Returns:
        info  A dictionary containing metadata to be exported.
        description: A nested datastructure containing all the measurement
            parameters defined in the Dataset.
    """
    var_descr = get_var_descr(dataset)

    var_list = [d['name'] for d in var_descr]
    dims = set(
        dim['name']
        for var in var_descr
        for dim in var['dims']
    )
    name_value = fix_dataset_name(dataset.name)
    info = {
        'name': name_value,
        'title': name_value,
        'description': name_value,
        'uid': dataset.exp_uuid,
        'scope': scope,
        'project': dataset.project,
        'setup': dataset.set_up,
        'sample': dataset.sample_name,
        'date_collected': str(dataset.run_timestamp),
        'rating': 1 if dataset.starred else 0,
        'vars': var_list,
        'dims': list(dims),
        'var_description': var_descr,
        'application': f"core-tools:{ct_version}",
        'files': [],
    }

    return info, var_descr


def make_variable_summary(variable_description: list[dict[str, Any]]) -> list[str]:
    var_summary = []
    for var in variable_description:
        dim_desr = [
            f"{dim['name']}:(" + ','.join(str(i) for i in dim['shape']) + ')'
            for dim in var['dims']
        ]
        var_summary.append(f"{var['name']}({var['written']}):" + ','.join(dim_desr))
    return var_summary


def update_file_info(info: dict[str, Any], file_paths: list[Path]):
    output_file_info = []
    sequence_numbers = make_sequence_number_map(info["var_description"])
    for fp in file_paths:
        file_info = parse_file_info(
            path=fp,
            sequence_number=sequence_numbers.get(fp.name, 0)
        )
        output_file_info.append(file_info)

    info['files'] = output_file_info


def make_sequence_number_map(
    description: list[str],
) -> dict[str, int]:
    mapping = {}
    for i, variable in enumerate(description):
        shape = variable["shape"]
        if not variable["written"] or not shape or shape == [1]:
            continue
        name = variable["label"]
        dims = [dim["name"] for dim in variable["dims"]]
        fname = fix_filename(f"{name}({','.join(dims)}).png")
        mapping[fname] = i + 1
    return mapping


def parse_file_info(path: Path, sequence_number: int) -> dict[str, Any]:
    """
    Extract information from file path and metadata.

    Args:
        path: Path object pointing to the file under inspection.

    Returns:
        A dictionary containing inferred information about the file. Keys
            include 'filename', 'filetype', 'mimetype' and 'sequence_number'.

    """
    match path.suffix:
        case ".hdf5":
            if re.fullmatch(r"ds_\d+", path.stem):
                filetype = "raw"
            else:
                filetype = "data"
            mimetype = "application/octet-stream"
        case ".png":
            filetype = "preview"
            mimetype = "image/png"
        case ".json":
            filetype = "conf"
            mimetype = "application/json"
        case _:
            logger.info(
                f"Unfamiliar file suffix '{path.suffix}', assigning filetype "
                "'derived'."
            )
            filetype = "derived"
            mimetype = "application/octet-stream"

    return {
        "filename": path.name,
        "filetype": filetype,
        "mimetype": mimetype,
        "sequence_number": sequence_number,
    }


def get_exported_files(dataset_path: str) -> list[Path]:
    file_paths = []
    for entry in Path(dataset_path).iterdir():
        if not entry.is_file():
            logger.info(f"excluding non-file entry from export: {entry}")
            continue
        if entry.name.endswith(".tmp"):
            logger.info(f"excluding temporary file from export: {entry}")
            continue

        file_paths.append(entry)
    return file_paths


def generate_file_sequence_numbers(files: list[Path], description: dict[str, Any]):
    fnames = [fi.name for fi in files]
    for i, var in enumerate(description["var_description"]):
        shape = var["shape"]
        if not var["written"] or not shape or shape == [1]:
            continue
        name = var["label"]
        dims = [dim["name"] for dim in var["dims"]]
        fname = fix_filename(f"{name}({','.join(dims)}).png")
        try:
            index = fnames.index(fname)
            files[index].seq_number = i + 1.0
        except Exception:
            logger.warning(f"file {fname} not found for sorting. {var}")


def fix_filename(filename: str) -> str:
    invalid_chars = re.compile(r'[*/\<>:"|?]')
    return re.sub(invalid_chars, "_", filename)
