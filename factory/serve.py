"""Serve the factory dashboard and accept Approve / Rework requests from it.

Run from anywhere: python3 factory/serve.py [--port 8000]

It serves this folder like `python3 -m http.server` (directory listings
included), bound to 127.0.0.1. The only thing it writes is
jobs/<job-id>/human-request.json, on POST /request from the dashboard; the
orchestrator session picks that file up and does the actual approve or rework.
"""

import argparse
import contextlib
import functools
import hmac
import io
import json
import os
import re
import secrets
import tempfile
import threading
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

FACTORY = Path(__file__).resolve().parent
DASHBOARD = FACTORY / "dashboard.html"
TOKEN_PLACEHOLDER = b'<meta name="factory-token" content="">'
JOB_ID = re.compile(r"^[0-9]{3}-[a-z0-9-]+$")
MAX_BODY = 16 * 1024
MAX_NOTE = 4000

TOKEN = secrets.token_urlsafe(32)
WRITE_LOCK = threading.Lock()


class Rejected(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class Handler(SimpleHTTPRequestHandler):
    def send_head(self):
        # The dashboard gets this run's token; every other file is served as is.
        if Path(self.translate_path(self.path)) != DASHBOARD:
            return super().send_head()
        page = DASHBOARD.read_bytes().replace(
            TOKEN_PLACEHOLDER,
            f'<meta name="factory-token" content="{TOKEN}">'.encode(),
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return io.BytesIO(page)

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/request":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            job, request = self.check_request()
        except Rejected as err:
            self.send_json(err.status, {"error": err.message})
            return
        self.send_json(HTTPStatus.OK, {"ok": True, "job": job, **request})

    def check_request(self) -> tuple[str, dict[str, str]]:
        port = self.server.server_address[1]
        origin = self.headers.get("Origin")
        if origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            raise Rejected(HTTPStatus.FORBIDDEN, "origin not allowed")
        token = self.headers.get("X-Factory-Token", "")
        if not hmac.compare_digest(token.encode(), TOKEN.encode()):
            raise Rejected(HTTPStatus.FORBIDDEN, "missing or wrong token")

        content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type != "application/json":
            raise Rejected(HTTPStatus.BAD_REQUEST, "Content-Type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise Rejected(HTTPStatus.BAD_REQUEST, "Content-Length required") from None
        if length < 0 or length > MAX_BODY:
            raise Rejected(HTTPStatus.BAD_REQUEST, "body too large")
        try:
            body = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise Rejected(HTTPStatus.BAD_REQUEST, "body is not valid JSON") from None
        if not isinstance(body, dict):
            raise Rejected(HTTPStatus.BAD_REQUEST, "body must be a JSON object")

        job = body.get("job")
        if not isinstance(job, str) or not JOB_ID.match(job):
            raise Rejected(HTTPStatus.NOT_FOUND, "unknown job")
        job_dir = FACTORY / "jobs" / job
        if not (job_dir / "job.json").is_file():
            raise Rejected(HTTPStatus.NOT_FOUND, "unknown job")

        action = body.get("action")
        if action == "approve":
            request = {"action": "approve"}
        elif action == "rework":
            note = body.get("note")
            if not isinstance(note, str) or not note.strip():
                raise Rejected(HTTPStatus.BAD_REQUEST, "rework needs a note")
            if len(note) > MAX_NOTE:
                raise Rejected(HTTPStatus.BAD_REQUEST, f"note is over {MAX_NOTE} characters")
            request = {"action": "rework", "note": note}
        else:
            raise Rejected(HTTPStatus.BAD_REQUEST, "action must be approve or rework")

        with WRITE_LOCK:
            try:
                stage = json.loads((job_dir / "job.json").read_text()).get("stage")
            except (OSError, ValueError, AttributeError):
                raise Rejected(HTTPStatus.CONFLICT, "job.json is unreadable") from None
            if stage != "needs-human":
                raise Rejected(HTTPStatus.CONFLICT, f"job is in {stage}, not needs-human")
            target = job_dir / "human-request.json"
            if target.exists():
                raise Rejected(
                    HTTPStatus.CONFLICT, "a request is already waiting for the orchestrator"
                )
            write_atomic(target, json.dumps(request, separators=(",", ":"), ensure_ascii=False))
        return job, request

    def send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def write_atomic(target: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".human-request-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, target)
    except BaseException:
        os.unlink(tmp)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the factory dashboard on 127.0.0.1.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    handler = functools.partial(Handler, directory=str(FACTORY))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Dashboard: http://127.0.0.1:{args.port}/dashboard.html", flush=True)
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever()


if __name__ == "__main__":
    main()
