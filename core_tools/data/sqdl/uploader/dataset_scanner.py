import os
import json
import logging
from typing import Any
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass
class FileInfo:
    path: str
    name: str
    st_mtime_us: int
    file_type: str
    mimetype: str
    size: int
    seq_number: float = 0.0


def fix_dataset_name(name):
    name = name.strip()
    if len(name) > 100:
        name = name[:100]
    return name


def fix_filename(filename):
    # filename = filename.replace("'", '')
    return filename


class DatasetScanner:

    def __init__(self, uid, path):
        self.uid = uid
        self.path = path

    def get_description(self) -> dict[str, Any]:
        with open(f'{self.path}/{self.uid}.json', 'r') as f:
            result = json.load(f)
        # Fix version 0.0.1 export
        if 'uid' not in result:
            result['uid'] = result['uuid']
        return result

    def get_files(self):
        files = []
        with os.scandir(self.path) as it:
            for entry in it:
                if not entry.is_file():
                    logger.info(f"skipping non-file '{entry.name}' in {self.path}")
                    continue
                filename = fix_filename(entry.name)
                if filename.endswith('.tmp'):
                    logger.info(f"skipping tmp file '{entry.name}' in {self.path}")
                    continue
                st_mtime_us = entry.stat().st_mtime_ns // 1000

                if filename.endswith('.json'):
                    filetype = 'conf'
                    mimetype = 'application/json'
                elif filename == f'ds_{self.uid}.hdf5':
                    filetype = 'raw'
                    mimetype = 'application/octet-stream'
                elif filename.endswith('.hdf5'):
                    filetype = 'data'  # @@@ ??
                    mimetype = 'application/octet-stream'
                elif filename.endswith('.png'):
                    filetype = 'preview'
                    mimetype = 'image/png'
                else:
                    filetype = 'derived'
                    mimetype = 'application/octet-stream'

                files.append(
                    FileInfo(
                        entry.path,
                        filename,
                        st_mtime_us,
                        filetype,
                        mimetype,
                        entry.stat().st_size
                    )
                )
        logger.debug(f"found {len(files)} files")
        return files
