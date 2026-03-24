"""Lightweight local HTTP server that listens for the OAuth callback."""
from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


class _CallbackHandler(BaseHTTPRequestHandler):
    """Handle exactly one GET to /callback, extract query params, then signal."""

    # These are set on the *class* before starting the server
    result: dict | None = None
    ready_event: threading.Event

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        query = parse_qs(parsed.query)
        code = query.get("code", [""])[0]
        state = query.get("state", [""])[0]

        _CallbackHandler.result = {"code": code, "state": state}

        # Respond with a user-friendly page
        html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>授权成功</title></head><body style='display:flex;"
            "align-items:center;justify-content:center;height:100vh;"
            "font-family:system-ui;background:#f5f5f5'>"
            "<div style='text-align:center'>"
            "<h1 style='color:#2b7a0b'>✅ 飞书授权成功</h1>"
            "<p>你可以关闭此页面了。</p></div></body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

        # Signal that we got the callback
        _CallbackHandler.ready_event.set()

    def log_message(self, format: str, *args: object) -> None:
        """Silence default stderr logging from BaseHTTPRequestHandler."""


def wait_for_callback(host: str = "127.0.0.1", port: int = 9768, timeout: float = 120) -> dict:
    """Start a local HTTP server, block until the OAuth callback arrives or timeout.

    Returns
    -------
    dict with keys ``code`` and ``state``.

    Raises
    ------
    TimeoutError if no callback is received within *timeout* seconds.
    """
    event = threading.Event()
    _CallbackHandler.result = None
    _CallbackHandler.ready_event = event

    server = HTTPServer((host, port), _CallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    logger.info("本地回调服务器已启动 http://%s:%s/callback", host, port)

    try:
        if not event.wait(timeout=timeout):
            raise TimeoutError(f"等待飞书授权回调超时 ({timeout}s)")
    finally:
        server.shutdown()
        server_thread.join(timeout=5)

    return _CallbackHandler.result  # type: ignore[return-value]
