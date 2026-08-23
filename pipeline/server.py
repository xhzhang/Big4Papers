"""Minimal local web server and safe catalog update coordinator."""
from __future__ import annotations

import argparse
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATIC_ROOT = PROJECT_ROOT / "dist" / "client"
DEFAULT_CATALOG = PROJECT_ROOT / "public" / "catalog.json"
MAX_REQUEST_BYTES = 4096


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def catalog_years(catalog_path: Path = DEFAULT_CATALOG) -> list[int]:
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        years = payload.get("coverage", {}).get("years", [])
        return sorted({int(year) for year in years})
    except (OSError, ValueError, TypeError):
        return []


def smart_update_years(current_year: int | None = None, known_years: list[int] | None = None) -> list[int]:
    """Refresh last year's final data, add this year, and catch up missed years."""
    current = current_year or datetime.now().year
    known = known_years if known_years is not None else catalog_years()
    latest = max(known) if known else current - 1
    start = min(latest, current - 1)
    return list(range(start, current + 1))


class UpdateCoordinator:
    """Runs one fixed, non-shell update at a time."""

    def __init__(self, project_root: Path = PROJECT_ROOT, catalog_path: Path = DEFAULT_CATALOG) -> None:
        self.project_root = project_root
        self.catalog_path = catalog_path
        self._lock = threading.Lock()
        self._status: dict[str, Any] = {
            "state": "idle",
            "stage": "ready",
            "message": "数据可更新",
            "years": smart_update_years(known_years=catalog_years(catalog_path)),
            "startedAt": None,
            "finishedAt": None,
            "stats": self._catalog_stats(),
            "log": [],
        }

    def _catalog_stats(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.catalog_path.read_text(encoding="utf-8"))
            stats = payload.get("stats")
            return stats if isinstance(stats, dict) else None
        except (OSError, ValueError):
            return None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._status, ensure_ascii=False))

    def start(self) -> tuple[bool, dict[str, Any]]:
        with self._lock:
            if self._status["state"] == "running":
                return False, json.loads(json.dumps(self._status, ensure_ascii=False))
            years = smart_update_years(known_years=catalog_years(self.catalog_path))
            self._status = {
                "state": "running",
                "stage": "planning",
                "message": "正在准备更新",
                "years": years,
                "startedAt": iso_now(),
                "finishedAt": None,
                "stats": self._catalog_stats(),
                "log": [],
            }
            snapshot = json.loads(json.dumps(self._status, ensure_ascii=False))
        threading.Thread(target=self._run, args=(years,), daemon=True, name="catalog-update").start()
        return True, snapshot

    def _set_stage(self, stage: str, message: str) -> None:
        with self._lock:
            self._status["stage"] = stage
            self._status["message"] = message

    def _append_log(self, line: str) -> None:
        clean = line.strip()
        if not clean:
            return
        with self._lock:
            self._status["log"] = [*self._status["log"], clean][-30:]

    def _commands(self, years: list[int]) -> list[tuple[str, str, list[str]]]:
        year_args = [str(year) for year in years]
        commands = [
            ("sync", "正在同步会议论文列表", ["sync", "--years", *year_args, "--refresh"]),
            (
                "official",
                "正在补充官网摘要与 PDF",
                [
                    "enrich-official",
                    "--years",
                    *year_args,
                    "--venues",
                    "usenix",
                    "ndss",
                    "ccs",
                    "--discover",
                    "--prune-discovered",
                    "--details",
                    "--refresh",
                ],
            ),
            ("sessions", "正在同步官方 Session 与 Track", ["enrich-sessions", "--years", *year_args, "--refresh"]),
            ("metadata", "正在补充缺失摘要与开放 PDF", ["enrich", "--only-missing"]),
            ("titles", "正在匹配重点方向缺失信息", ["enrich-titles", "--years", *year_args]),
            ("analysis", "正在分析新增论文方向与标签", ["analyze", "--provider", "rules", "--only-pending"]),
        ]
        summary_configured = all(
            os.getenv(name)
            for name in ("PAPER_SUMMARY_ENDPOINT", "PAPER_SUMMARY_API_KEY", "PAPER_SUMMARY_MODEL")
        ) or all(
            os.getenv(name)
            for name in ("PAPER_ANALYSIS_ENDPOINT", "PAPER_ANALYSIS_API_KEY", "PAPER_ANALYSIS_MODEL")
        )
        if summary_configured:
            commands.append(
                ("summaries", "正在生成新增论文中文概述", ["summarize", "--only-pending", "--web-output", ""])
            )
        commands.append(("export", "正在生成网页数据", ["export", "--format", "web", "--output", "public/catalog.json"]))
        return commands

    def _run(self, years: list[int]) -> None:
        try:
            for stage, message, arguments in self._commands(years):
                self._set_stage(stage, message)
                command = [sys.executable, "-m", "pipeline", *arguments]
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                process = subprocess.Popen(
                    command,
                    cwd=self.project_root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=creationflags,
                )
                assert process.stdout is not None
                for line in process.stdout:
                    self._append_log(line)
                return_code = process.wait()
                if return_code:
                    raise RuntimeError(f"{message}失败（退出码 {return_code}）")
            with self._lock:
                self._status.update(
                    {
                        "state": "success",
                        "stage": "complete",
                        "message": "论文数据已更新",
                        "finishedAt": iso_now(),
                        "stats": self._catalog_stats(),
                    }
                )
        except Exception as exc:
            with self._lock:
                self._status.update(
                    {
                        "state": "error",
                        "stage": "failed",
                        "message": f"{exc}。请检查网络后重试",
                        "finishedAt": iso_now(),
                    }
                )


def handler_class(
    coordinator: UpdateCoordinator,
    static_root: Path = DEFAULT_STATIC_ROOT,
    catalog_path: Path = DEFAULT_CATALOG,
    verbose: bool = False,
) -> type[SimpleHTTPRequestHandler]:
    class LocalHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(static_root), **kwargs)

        def _json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _catalog(self) -> None:
            try:
                body = catalog_path.read_bytes()
            except OSError:
                self._json({"error": "论文数据尚未生成"}, HTTPStatus.NOT_FOUND)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _catalog_shard(self, folder: str, filename: str) -> None:
            if not filename.endswith(".json") or Path(filename).name != filename:
                self._json({"error": "数据分片不存在"}, HTTPStatus.NOT_FOUND)
                return
            try:
                body = (catalog_path.parent / folder / filename).read_bytes()
            except OSError:
                self._json({"error": "数据分片尚未生成"}, HTTPStatus.NOT_FOUND)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path == "/api/update":
                self._json(coordinator.status())
                return
            if path == "/catalog.json":
                self._catalog()
                return
            if path.startswith("/catalog-details/"):
                self._catalog_shard("catalog-details", path.removeprefix("/catalog-details/"))
                return
            if path.startswith("/catalog-papers/"):
                self._catalog_shard("catalog-papers", path.removeprefix("/catalog-papers/"))
                return
            if path == "/":
                self.path = "/index.html"
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            if urlsplit(self.path).path != "/api/update":
                self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = MAX_REQUEST_BYTES + 1
            if content_length < 0 or content_length > MAX_REQUEST_BYTES:
                self._json({"error": "请求过大"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return
            try:
                payload = json.loads(self.rfile.read(content_length) or b"{}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._json({"error": "请求格式无效"}, HTTPStatus.BAD_REQUEST)
                return
            if not isinstance(payload, dict) or payload.get("scope", "smart") != "smart":
                self._json({"error": "仅支持智能更新"}, HTTPStatus.BAD_REQUEST)
                return
            started, status = coordinator.start()
            self._json(status, HTTPStatus.ACCEPTED if started else HTTPStatus.CONFLICT)

        def end_headers(self) -> None:
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("X-Frame-Options", "DENY")
            super().end_headers()

        def log_message(self, message_format: str, *args: Any) -> None:
            if verbose:
                super().log_message(message_format, *args)

    return LocalHandler


def create_server(
    host: str = "127.0.0.1",
    port: int = 3000,
    static_root: Path = DEFAULT_STATIC_ROOT,
    catalog_path: Path = DEFAULT_CATALOG,
    verbose: bool = False,
) -> ThreadingHTTPServer:
    coordinator = UpdateCoordinator(PROJECT_ROOT, catalog_path)
    return ThreadingHTTPServer((host, port), handler_class(coordinator, static_root, catalog_path, verbose))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SecAtlas local site and update service")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address; localhost-only by default")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--static-root", type=Path, default=DEFAULT_STATIC_ROOT)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    index_path = args.static_root / "index.html"
    if not index_path.exists():
        parser.error(f"{index_path} does not exist; run the frontend build once first")
    server = create_server(args.host, args.port, args.static_root, args.catalog, args.verbose)
    print(f"SecAtlas is available at http://{args.host}:{server.server_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
