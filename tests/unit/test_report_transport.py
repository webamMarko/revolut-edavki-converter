"""Report transport performance regressions."""

import gzip
import io

from src.report_cache import (
    get_cached_gzip,
    invalidate_user_html,
    put_cached_html,
)
from src.web.portfolio import _accepts_gzip, _send_report_html


class FakeHandler:
    def __init__(self):
        self.status = None
        self.headers = {}
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers[name] = value

    def end_headers(self):
        pass


def test_gzip_negotiation_respects_q_zero():
    assert _accepts_gzip("br, gzip")
    assert _accepts_gzip("gzip; q=0.5")
    assert not _accepts_gzip("gzip; q=0")
    assert not _accepts_gzip("gzip; q=0.0")


def test_report_response_uses_cached_gzip_and_length():
    username = "report-perf-test"
    report_hash = "hash:SI"
    html = "<html>" + ("portfolio report " * 10_000) + "</html>"
    try:
        put_cached_html(username, report_hash, html)
        compressed = get_cached_gzip(username, report_hash)
        assert compressed is get_cached_gzip(username, report_hash)

        handler = FakeHandler()
        _send_report_html(handler, html, '"etag-gzip"', compressed)

        assert handler.status == 200
        assert handler.headers["Content-Encoding"] == "gzip"
        assert handler.headers["Vary"] == "Accept-Encoding"
        assert int(handler.headers["Content-Length"]) == len(compressed)
        assert gzip.decompress(handler.wfile.getvalue()).decode() == html
        assert len(compressed) < len(html.encode()) * 0.1
    finally:
        invalidate_user_html(username)
