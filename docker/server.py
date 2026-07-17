#!/usr/bin/env python3
"""Single-process MeterMesh server for the Docker runtime.

Subclasses the upstream DashboardHandler so the built SPA's static assets
(/, /index.html, /assets/*) are served from ./dist, while every /api/* and
/data.json request falls through to the original handlers unchanged.

The Dockerfile bakes in METERMESH_ALLOW_REMOTE=1 so --host 0.0.0.0 is always
allowed inside the container; the host port is still bound to 127.0.0.1 by
docker-compose.yml.

Run instead of dashboard_api.py for the Docker runtime:
    python3 docker/server.py --host 0.0.0.0 --port 8765 [more flags...]
"""
from __future__ import annotations

import mimetypes
import sys
from http import HTTPStatus
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dashboard_api  # noqa: E402

DIST_DIR = Path(__file__).resolve().parent.parent / "dist"
STATIC_INDEX_ROUTES = {"/", "/index.html"}


def _safe_join(root: Path, relative: str) -> Path | None:
    """Resolve `relative` under `root`, rejecting traversal escapes."""
    candidate = (root / unquote(relative).lstrip("/")).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


class StaticDashboardHandler(dashboard_api.DashboardHandler):
    """DashboardHandler that serves the built SPA before falling through to the API."""

    def do_GET(self) -> None:  # type: ignore[override]
        parsed = urlparse(self.path)
        path = parsed.path

        if path in STATIC_INDEX_ROUTES and (DIST_DIR / "index.html").is_file():
            self._serve_file(DIST_DIR / "index.html", "text/html; charset=utf-8")
            return

        if path.startswith("/assets/"):
            file_path = _safe_join(DIST_DIR, path)
            if file_path and file_path.is_file():
                content_type, _ = mimetypes.guess_type(file_path.name)
                self._serve_file(file_path, content_type or "application/octet-stream")
                return

        super().do_GET()

    def _serve_file(self, file_path: Path, content_type: str) -> None:
        try:
            body = file_path.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main() -> None:
    # Replace DashboardHandler in the upstream module so its main() wires up
    # our subclass when it builds the ThreadingHTTPServer and sets class
    # attributes. main() blocks for the lifetime of the process.
    dashboard_api.DashboardHandler = StaticDashboardHandler
    dashboard_api.main()


if __name__ == "__main__":
    main()