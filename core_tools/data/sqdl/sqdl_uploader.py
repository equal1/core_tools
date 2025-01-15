import logging
import os
import re
import time
from collections.abc import Mapping
from datetime import datetime

import psutil
import core_tools as ct
from core_tools.startup.config import get_configuration
from sqdl_client.api.v1.dataset import Dataset
from sqdl_client.api.v1.file import File
from sqdl_client.api.v1.scope import Scope
from sqdl_client.client import QDLClient
from sqdl_client.exceptions import (
    ObjectNotFoundException,
    RequestException,
    UniqueConstraintViolationException
)
from requests.exceptions import ConnectionError, ReadTimeout

from .dataset_scanner import DatasetScanner, FileInfo
from .exceptions import InvalidNameError, NoScopeError, DatasetError
from .metadata_formatter import MetadataFormatter
from .uploader_db import UploaderDb
from .uploader_task_queue import UploaderTaskQueue
from .uploader_registry import UploadRegistry
from .upload_logger import UploadLogger


logger = logging.getLogger(__name__)


class SqdlUploader:

    def __init__(self, cfg, client=None):
        self.cfg = cfg
        if client is None:
            self.client = QDLClient()
        else:
            self.client = client

        api_key = self.cfg.get('sqdl.api_key')
        if api_key:
            self.client.use_api_key(api_key)

        db_path = self.cfg.get('uploader.database', '~/.sqdl_uploader/uploader.db')
        self.db = UploaderDb(db_path)
        self.task_queue = UploaderTaskQueue(self.db)
        self.upload_registry = UploadRegistry(self.db)
        self.logger = UploadLogger(self.db)
        self.metadata_formatter = MetadataFormatter()
        # load scopes to fix them when not set during export
        self.scopes = cfg.get('export.scopes', {})
        if cfg.get('uploader.retry_failed', False):
            self.task_queue.retry_all_failed()
        self.pid = os.getpid()
        self.cleanup_abandoned_tasks()
        logger.info(f"Started uploader, pid:{self.pid}")

    def process_task(self) -> bool:
        start = time.perf_counter()
        task = self.task_queue.get_oldest_task(self.pid)
        if task is None:
            task = self.task_queue.get_newest_retry_task(self.pid)
        if task is None:
            return False

        try:
            duration = time.perf_counter() - start
            logger.info(f'Uploading {task.uid} (query: {duration * 1000:.1f} ms) {task.ds_path}')
            ds_scanner = DatasetScanner(task.uid, task.ds_path)
            desc = ds_scanner.get_description()
            if not task.scope:
                task.scope = self.get_scope(desc)
                self.log(task, f"Resolved scope using project {desc['project']}")

            logger.debug(f'Get/create {task.uid}')
            # get / create sQDL dataset
            sqdl_ds = self.get_create_sqdl_dataset(task.scope, desc)
            if task.update_dataset or task.set_raw_final:
                ds_upload_id = self.upload_registry.get_create_dataset(sqdl_ds.uuid, task.scope, task.uid)
                files = self.sort_files(ds_scanner.get_files(), desc)
                self.upload_files(task, ds_upload_id, files, sqdl_ds)

            if task.update_name and sqdl_ds.name != desc['name']:
                sqdl_ds.update_name(desc['name'])

            if task.update_rating:
                new_rating = 1 if desc['starred'] else 0
                if new_rating != sqdl_ds.rating:
                    logger.info(f"update rating {task.uid} {sqdl_ds.rating} -> {new_rating}")
                    sqdl_ds.update_rating(new_rating)

            deleted = self.task_queue.delete_task(task)
            if not deleted:
                logger.debug(f'Task {task.uid} has been modified during upload. Release task')
                self.task_queue.release_task(task)
            # log success
            self.log(task, 'Uploaded')
            duration = time.perf_counter() - start
            logger.info(f'Uploaded {task.uid} in {duration * 1000:5.1f} ms')

        except DatasetError as ex:
            logger.error(f"Exception processing {task.uid} '{ex}' {task.ds_path}")
            self.task_queue.set_failed(task)
            self.log(task, f'{type(ex)}: {ex}')

        except (ConnectionError, ReadTimeout) as ex:
            # server cannot be reached
            logger.error(f"Exception processing {task.uid} '{ex}'", exc_info=True)
            self.task_queue.release_task(task)
            time.sleep(1.0)

        except RequestException as ex:
            logger.error(f'Exception processing {task.uid} {task.ds_path}. Response:{ex.response}', exc_info=True)
            if ex.response is not None:
                logger.info(f'Response: {ex.response.url}; {ex.response.headers}')
            self.task_queue.set_failed(task)
            self.log(task, f'{type(ex)}: {ex}')
            time.sleep(0.5)

        except Exception as ex:
            # TODO: Catch all should be split in dataset related errors and connection errors @@@
            # database connection failures, sQDL connecton failures should be given a retry.
            # dataset errors should mark the task as failed.
            logger.error(f'Exception processing {task.uid} {task.ds_path}', exc_info=True)
            self.task_queue.set_failed(task)
            self.log(task, f'{type(ex)}: {ex}')
            time.sleep(0.5)
        return True

    def log(self, task, message):
        self.logger.log(task.scope, task.uid, message)

    def get_scope(self, desc):
        # is it in the json file?
        scope = desc.get('scope')
        if not scope:
            scope = self.scopes.get(desc['project'])
            if isinstance(scope, Mapping):
                scope = scope.get(desc['setup'])
        if not scope:
            raise NoScopeError(desc['project'])
        return scope

    def get_create_sqdl_dataset(self, scope_name, desc) -> Dataset:
        self._validate_dataset_name(desc['name'])
        metadata = self.metadata_formatter.format(desc)
        sqdl_api = self.client.api
        try:
            scope = sqdl_api.scope.retrieve_from_name(scope_name)
        except ObjectNotFoundException:
            scope = None
        if scope is None:
            scope = sqdl_api.scope.create(
                name=scope_name,
                description=scope_name,
                schema_name='coretools-default'
            )
        uid = str(desc['uid'])
        try:
            sqdl_ds = sqdl_api.dataset.create(
                desc['name'],
                desc['name'],
                desc['name'],
                metadata,
                uid,
                date_collected=datetime.fromisoformat(desc['start_time']),
                rating=1 if desc['starred'] else 0,
                source_application=f'core-tools:{ct.__version__}',
                scope=scope)
            logger.debug(f"Created dataset with uid {uid}")
        except UniqueConstraintViolationException:
            sqdl_ds = None
        if sqdl_ds is None:
            sqdl_ds = scope.retrieve_dataset_from_uid(uid)
            logger.debug(f"Retrieved dataset with uid {uid}")
            if metadata != sqdl_ds.metadata:
                logger.warning(f"Updating metadata differs for {uid}: {metadata} {sqdl_ds.metadata}")

        return sqdl_ds

    def _validate_dataset_name(self, name):
        if len(name) < 2:
            raise InvalidNameError(f"Dataset name '{name}' is too short. Min length is 2 chars")
        if len(name) > 100:
            raise InvalidNameError("Dataset name is too long. Max is 100")
        if '{' in name:
            raise InvalidNameError(f"Illegal name. Did you forget the f in front of the string? {name}")
        valid_names = r"^[A-Za-z0-9_\-.,:()[\]*+&/ =@<>'%?|]*$"
        if not re.match(valid_names, name):
            raise InvalidNameError(f"Invalid dataset name {name}")

    def sort_files(self, files: list[FileInfo], desc) -> list[FileInfo]:
        fnames = [fi.name for fi in files]
        for i, var in enumerate(desc['var_description']):
            shape = var['shape']
            if not var['written'] or not shape or shape == [1]:
                continue
            name = var['label']
            dims = [dim['name'] for dim in var['dims']]
            fname = fix_filename(f'{name}({",".join(dims)}).png')
            try:
                index = fnames.index(fname)
                files[index].seq_number = i + 1.0
            except Exception:
                logger.warning(f"file {fname} not found for sorting. {var}")

        return sorted(files, key=lambda fi: fi.seq_number)

    def upload_files(self, task, ds_upload_id, file_entries: list[FileInfo], sqdl_ds: Dataset):

        uploaded_files_list = self.upload_registry.get_files(ds_upload_id)
        logger.debug(f"{len(uploaded_files_list)} uploaded files registry")
        uploaded_files = {uf.filename: uf for uf in self.upload_registry.get_files(ds_upload_id)}
        logger.debug(f"{len(uploaded_files)} different files in registry for {task.uid}: {[uploaded_files.keys()]}")

        # get file list of sQDL dataset
        sqdl_file_list = sqdl_ds.files
        if sqdl_file_list is not None:
            logger.debug(f"sqdl_file_list: {len(sqdl_file_list)}")
            sqdl_files = {f.name: f for f in sqdl_file_list}
        else:
            logger.debug("sqdl_file_list: None")
            sqdl_files = {}

        # compare file lists.
        for fi in file_entries:
            is_new = fi.name not in uploaded_files
            modified_file = not is_new and fi.st_mtime_us != uploaded_files[fi.name].st_mtime_us
            sqdl_file = sqdl_files.get(fi.name)
            has_data = sqdl_file is not None and sqdl_file.has_data
            if is_new or modified_file or not has_data:
                logger.debug(f"upload {fi.name} exists:{sqdl_file is not None} {fi.size // 1024} KB")
                if sqdl_file is None:
                    sqdl_file = sqdl_ds.create_new_file(fi.name, fi.file_type, fi.mimetype,
                                                        sequence_number=fi.seq_number)
                elif not sqdl_file.is_mutable:
                    logger.error(f"Cannot upload modified file '{fi.name}'. It's immutable. {task}; {fi}; {uploaded_files.get(fi.name)}")
                    continue
                make_immutable = fi.file_type == 'raw' and task.set_raw_final
                self.upload_file(fi, sqdl_file, make_immutable)
                self.upload_registry.add_update_file(ds_upload_id, sqdl_file.uuid, fi.name, fi.st_mtime_us)
            elif fi.name not in sqdl_files:
                # Strange: it is registered as uploaded, but not there?
                raise Exception(f'File {fi.name} of {task.scope}:{task.uid} missing in sQDL')

    def upload_file(self, fi: FileInfo, sqdl_file: File, make_immutable):
        tries = 2
        while tries:
            try:
                with open(fi.path, 'rb') as fs:
                    sqdl_file.upload(fs, make_immutable)
                return
            except FileNotFoundError:
                tries -= 1
                if tries > 0:
                    logger.warning(f"File {fi.path} not found. Exporter could be updating it. Retrying upload")
                    time.sleep(0.01)
                else:
                    raise

    def cleanup_abandoned_tasks(self):
        pids = psutil.pids()
        for task in self.task_queue.get_claimed_tasks():
            alive = task.claimed_by in pids
            logger.info(f"task (uid:{task.uid}) is claimed by {task.claimed_by}, alive: {alive}")
            if not alive:
                self.task_queue.release_task(task)

    def run(self) -> None:
        # NOTE: KeyboardInterrupt and SystemExit will not be caught.
        idle_cnt = 0
        while True:
            try:
                work_done = self.process_task()
                if not work_done:
                    idle_cnt += 1
                    if idle_cnt % 300 == 0:
                        logger.info('Nothing to upload')
                    time.sleep(0.2)
                else:
                    idle_cnt = 0
            except Exception:
                # anticipated causes: database connection failure when trying to get task.
                logger.error('Task processing failed', exc_info=True)
                time.sleep(1.0)


def fix_filename(filename):
    invalid_chars = re.compile(r'[*/\<>:"|?]')
    m = invalid_chars.search(filename)
    while m:
        filename = filename[:m.start()] + '_' * (m.end() - m.start()) + filename[m.end():]
        m = invalid_chars.search(filename)
    return filename


def main(configuration_file: str, client: QDLClient = None):
    ct.configure(configuration_file)
    cfg = get_configuration()
    try:
        uploader = SqdlUploader(cfg, client=client)
        uploader.run()
    except Exception:
        logger.error('Error running exporter', exc_info=True)
        raise
    finally:
        logger.info('Exit application')
