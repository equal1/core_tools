import json
import os
import time

import core_tools as ct
from core_tools.data.ds.reader import load_by_uuid
from core_tools.data.SQL.queries.dataset_gui_queries import query_for_measurement_results
from core_tools.data.SQL.SQL_connection_mgr import SQL_database_manager

from core_tools.data.ds.ds2xarray import ds2xarray

"""
TIP:
    Switch project to 'Game', so all data is for Game
"""


class LiveExporter:
    def __init__(self, project_name):
        self.project_name = project_name
        self.export_path = 'C:/measurements/export/Game/'
        os.makedirs(self.export_path, exist_ok=True)
        self.start_time = '2025-02-20'
        self.active_ds = None
        self.ds_written = 0
        self.max_id = None

    def export_ds_json(self, ds, variables: list[str] | None = None):
        xds = ds2xarray(ds, snapshot=False)

        if variables is not None:
            xds = xds[vars]

        d = xds.to_dict()
        fname = self.export_path + f"ds_{ds.exp_uuid}.json"
        tmp_file = fname + ".tmp"
        with open(tmp_file, "w") as fp:
            json.dump(d, fp, indent=1)

        if os.path.exists(fname):
            os.remove(fname)
        os.rename(tmp_file, fname)

    def export_active_ds(self):
        active_ds = self.active_ds
        if active_ds is not None:
            active_ds.sync()
            written = 0
            for m_param in active_ds:
                for name, descr in m_param:
                    written += descr.written()
            if self.ds_written != written:
                self.export_ds_json(active_ds)
                self.ds_written = written
            if active_ds.completed:
                self.active_ds = None
                self.ds_written = 0

    def export_new_ds(self):
        # New measurements detected. Do last update of active_ds
        self.export_active_ds()
        self.active_ds = None
        self.ds_written = 0

        res = query_for_measurement_results.search_query(
                start_time=self.start_time,
                name=None,  # part of name
                project=self.project_name,  # optional
                keywords=None,  # optional
                )
        # Export all
        ds = None
        for e in res:
            ds = load_by_uuid(e.uuid)
            self. export_ds_json(ds)
            self.start_time = ds.run_timestamp
            self.max_id = ds.exp_id

        # check if last ds needs updating
        if ds is not None and not ds.completed:
            self.active_ds = ds

    def run(self):
        try:
            while True:
                try:
                    self.export_active_ds()

                    # check for new measurements. This is a fast query on the database
                    new_max_id = query_for_measurement_results.detect_new_meaurements(
                        self.max_id,
                        project=self.project_name
                        )
                    if new_max_id != self.max_id:
                        self.export_new_ds()
                    time.sleep(0.1)

                except Exception as ex:
                    """
                    Things that could go wrong:
                        * writing or copying file fails because other application is accessing it.
                    """
                    print(ex)
                    time.sleep(0.5)

        except KeyboardInterrupt:
            SQL_database_manager.disconnect()
            raise


ct.configure('./setup_config/ct_config_laptop.yaml')


exporter = LiveExporter()
exporter.run()
