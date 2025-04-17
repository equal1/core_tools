import os
import time
import logging
import datetime

from core_tools.data.SQL.SQL_connection_mgr import (
        SQL_database_manager as DatabaseManager
)
from core_tools.data.SQL.model.settings import get_database_version
from core_tools.data.sqdl.export.coretools_export import Exporter

from sqdl_uploader import SqdlUploader


logger = logging.getLogger(__name__)


class SQDLSync():
    """
    Event loop that polls for measurement data to be uploaded to SQDL.
    Expects the core-tools configurations to be initialised (see core-tools/startup/config.py).
    Start the loop using the 'run' method.
    """

    def __init__(self, config):
        database = DatabaseManager()

        if not database.local_conn_active:
            raise Exception(
                "Local database setup is a requirement for SQDL Sync, but no "
                "local configuration has been found."
            )
        get_database_version(assert_requirement=True)

        base_path = config.get("sqdl_sync.base_path", "~/.sqdl")
        self.base_path = os.path.expanduser(base_path)
        os.makedirs(self.base_path, exist_ok=True)
        os.makedirs(f"{self.base_path}/export", exist_ok=True)

        self.exporter = Exporter(config)
        self.uploader = SqdlUploader(config)

        self.tick_rate = datetime.timedelta(
            seconds=config.get("sqdl_sync.tick_rate", default=0.1)
        )
        self.next_tick = None

    def run(self):
        """
        Start the SQDL Writer event loop.
        """
        try:
            logger.info("Starting SQDL Writer event loop...")
            self.next_tick = datetime.datetime.now() + self.tick_rate

            while True:
                self.exporter.poll()
                self.uploader.poll()
                self.sleep_to_limit_rate()

        except Exception as exc:
            logger.error(
                f"An unhandled exception with the following message occured: {exc}",
                exc_info=True
            )

        finally:
            self.uploader.shut_down()
            logger.info("Stopping SQDL Writer event loop...")

    def sleep_to_limit_rate(self) -> None:
        """
        Calculate if and how long the program should sleep at the end of an event loop.
        Limits the event loop frequency to at most one iteration per ```self.tick_rate``` seconds.
        """
        now = datetime.datetime.now()
        if self.next_tick > now:
            seconds = (self.next_tick - now).total_seconds()
            time.sleep(seconds)
        self.next_tick = datetime.datetime.now() + self.tick_rate
