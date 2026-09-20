"""Loopback-only synthetic UI server. Never serves the workspace directory."""

from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from threading import Thread
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


def validate_demo_url(value: str) -> str:
    """Accept only an exact copy of our demo on the local loopback interface."""
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.port is None
    ):
        raise ValueError("Enter the local demo page URL.")
    url = f"http://127.0.0.1:{parsed.port}"

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
            return None

    expected = files("interface_automation").joinpath("demo.html").read_bytes()
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(Request(url), timeout=3) as response:
            if response.read(len(expected) + 1) != expected:
                raise ValueError("The URL does not serve the bundled demo page.")
    except OSError as error:
        raise ValueError("The demo page is unavailable.") from error
    return url


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if urlsplit(self.path).path != "/":
            self.send_error(404)
            return
        body = files("interface_automation").joinpath("demo.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass  # Do not log request data.


@contextmanager
def serve(port: int = 0) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
