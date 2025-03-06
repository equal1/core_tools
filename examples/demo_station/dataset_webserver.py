import json
from functools import cached_property
from http.cookies import SimpleCookie
from http.server import HTTPServer, BaseHTTPRequestHandler, HTTPStatus
from urllib.parse import parse_qsl, urlparse

import core_tools as ct
from core_tools.data.ds.reader import load_by_uuid
from core_tools.data.SQL.queries.dataset_gui_queries import query_for_measurement_results

from core_tools.data.ds.ds2xarray import ds2xarray


"""
TIP:
    Switch project name to 'Game', so all data is for Game
"""


class DatasetRequestHandler(BaseHTTPRequestHandler):

    @cached_property
    def url(self):
        return urlparse(self.path)

    @cached_property
    def query_data(self):
        return dict(parse_qsl(self.url.query))

    @cached_property
    def post_data(self):
        content_length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(content_length)

    @cached_property
    def form_data(self):
        return dict(parse_qsl(self.post_data.decode("utf-8")))

    @cached_property
    def cookies(self):
        return SimpleCookie(self.headers.get("Cookie"))

    def log_request(self, code='-', size='-'):
        pass

    def do_GET(self):
        if self.url.path != "/latest":
            self.send_error(HTTPStatus.NOT_FOUND)
        else:
            start_time = self.query_data.get("start_time")
            ds = self.get_last_ds(start_time)
            if ds is None:
                self.send_error(HTTPStatus.NO_CONTENT)
            else:
                response = self.get_ds_json(ds).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response)

    def get_last_ds(self, start_time: str | None):
        res = query_for_measurement_results.search_query(
                start_time=start_time,  # optional
                name=None,  # part of name optional
                project=self.server.project_name,  # optional
                keywords=None,  # optional
                )
        if len(res) == 0:
            return None
        uuid = res[-1].uuid
        ds = load_by_uuid(uuid)
        return ds

    def get_ds_json(self, ds, variables: list[str] | None = None):
        xds = ds2xarray(ds, snapshot=False)
        for m_param in ds:
            for name, descr in m_param:
                var_name = descr.param_name
                xds[var_name].attrs["written"] = descr.written()

        if variables is not None:
            xds = xds[variables]

        d = xds.to_dict()
        return json.dumps(d, indent=1)


def run_web_server(project_name: str | None, server_address: tuple[str, int] | None = None):
    if server_address is None:
        server_address = ('0.0.0.0', 8002)
    httpd = HTTPServer(server_address, DatasetRequestHandler)
    httpd.project_name = project_name
    try:
        print(f"Server running at http://{server_address[0]}:{server_address[1]}")
        print("Interrupt kernel to stop server")
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


 # %%

ct.configure('./setup_config/ct_config_laptop.yaml')

run_web_server(None)
