import json
from datetime import datetime
from functools import cached_property
from http.cookies import SimpleCookie
from http.server import HTTPServer, BaseHTTPRequestHandler, HTTPStatus
from urllib.parse import parse_qsl, urlparse

from core_tools.GUI.script_runner.commands import Command


class WebRequestHandler(BaseHTTPRequestHandler):
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
        if self.url.path == "/functions":
            # return list of functions with arguments
            response = json.dumps(self.get_function_descriptions()).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if self.url.path == "/run":
            try:
                data = self.form_data
                cmd_name = data["__name__"]
                kwargs = {
                    k: v
                    for k, v in data.items() if k != "__name__"
                    }
                for command in self.server.commands:
                    if command.name == cmd_name:
                        try:
                            result = command(**kwargs)
                        except Exception as ex:
                            print(ex)
                            raise
                        break
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
                response = json.dumps(result).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response)
            except Exception as ex:
                response = json.dumps(str(ex)).encode("utf-8")
                self.send_response(HTTPStatus.BAD_REQUEST)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def get_function_descriptions(self):
        functions = []
        for command in self.server.commands:
            command: Command = command
            parameters = command.parameters
            functions.append({
                "__name__": command.name,
                "args": [{
                    "name": name,
                    "type": parameter.annotation.__name__,
                    }
                    for name, parameter in parameters.items()],
                })
        return functions

    def get_response(self):
        return json.dumps(
            {
                "now": datetime.now().isoformat(),
                "path": self.url.path,
                "query_data": self.query_data,
                "post_data": self.post_data.decode("utf-8"),
                "form_data": self.form_data,
                "cookies": {
                    name: cookie.value
                    for name, cookie in self.cookies.items()
                },
            }
        )


def run_web_server(command_list: list[Command], server_address: tuple[str, int] | None = None):
    if server_address is None:
        server_address = ('0.0.0.0', 8001)
    httpd = HTTPServer(server_address, WebRequestHandler)
    httpd.commands = command_list
    try:
        print(f"Server running at http://{server_address[0]}:{server_address[1]}")
        print("Interrupt kernel to stop server")
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


# %%

if __name__ == "__main__":
    from enum import Enum
    from core_tools.GUI.script_runner.commands import Function

    def sayHi(name: str, times: int = 1):
        for _ in range(times):
            print(f'Hi {name}')
        return name

    class Mode(str, Enum):
        LEFT = 'left'
        CENTER = 'center'
        RIGHT = 'right'

    def fit(x: float, mode: Mode):
        print(f'fit {x}, {mode}')

    command_list = [
        Function(sayHi),
        Function(fit),
        ]

    run_web_server(command_list)
