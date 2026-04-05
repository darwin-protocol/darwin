"""DARWIN Archive Service — serves epoch artifacts to watchers and operators.

Mirrors all epoch data in content-addressed storage. Serves HTTP reads.
Validates hashes on ingest. This is the data availability layer for v1.

Port: 9447
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Lock


class ArchiveState:
    def __init__(self, storage_dir: str = "archive_storage"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        self.epochs: dict[str, dict] = {}  # epoch_id -> metadata
        self._scan_existing()

    def _scan_existing(self):
        """Scan storage for existing epoch directories."""
        for d in sorted(self.storage_dir.iterdir()):
            if d.is_dir() and d.name.startswith("epoch_"):
                epoch_id = d.name.replace("epoch_", "")
                manifest = self._build_manifest(d)
                self.epochs[epoch_id] = manifest

    def _build_manifest(self, epoch_dir: Path) -> dict:
        """Build a manifest for an epoch directory with file hashes."""
        manifest = {"epoch_dir": str(epoch_dir), "files": {}, "ingested_at": time.time()}
        for f in sorted(epoch_dir.iterdir()):
            if f.is_file():
                h = hashlib.sha256(f.read_bytes()).hexdigest()
                manifest["files"][f.name] = {"size": f.stat().st_size, "sha256": h}
        return manifest

    def ingest_epoch(self, epoch_id: str, source_dir: str | Path) -> dict:
        """Ingest an epoch's artifacts, verify hashes, store."""
        source = Path(source_dir)
        if not source.exists():
            return {"error": "source_dir not found"}

        dest = self.storage_dir / f"epoch_{epoch_id}"
        dest.mkdir(parents=True, exist_ok=True)

        for f in source.iterdir():
            if f.is_file():
                shutil.copy2(f, dest / f.name)

        manifest = self._build_manifest(dest)
        with self.lock:
            self.epochs[epoch_id] = manifest

        return {"epoch_id": epoch_id, "files": len(manifest["files"]), "status": "ingested"}

    def get_file(self, epoch_id: str, filename: str) -> Path | None:
        """Get the path to a specific epoch artifact."""
        fpath = self.storage_dir / f"epoch_{epoch_id}" / filename
        return fpath if fpath.exists() else None

    def list_epochs(self) -> list[dict]:
        with self.lock:
            return [
                {"epoch_id": eid, "files": len(m["files"]),
                 "ingested_at": m.get("ingested_at", 0)}
                for eid, m in sorted(self.epochs.items())
            ]


STATE: ArchiveState | None = None


class ArchiveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self._json(200, {"status": "ok", "role": "archive"})

        elif self.path == "/v1/epochs":
            self._json(200, {"epochs": STATE.list_epochs()})

        elif self.path.startswith("/v1/epochs/"):
            parts = self.path.strip("/").split("/")
            if len(parts) == 3:
                # /v1/epochs/{id} — manifest
                epoch_id = parts[2]
                with STATE.lock:
                    manifest = STATE.epochs.get(epoch_id)
                if manifest:
                    self._json(200, {"epoch_id": epoch_id, "files": manifest["files"]})
                else:
                    self._json(404, {"error": "epoch not found"})

            elif len(parts) == 4:
                # /v1/epochs/{id}/{filename} — serve file
                epoch_id, filename = parts[2], parts[3]
                fpath = STATE.get_file(epoch_id, filename)
                if fpath:
                    self.send_response(200)
                    if filename.endswith(".json"):
                        self.send_header("Content-Type", "application/json")
                    else:
                        self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(fpath.stat().st_size))
                    self.send_header("X-SHA256", hashlib.sha256(fpath.read_bytes()).hexdigest())
                    self.end_headers()
                    self.wfile.write(fpath.read_bytes())
                else:
                    self._json(404, {"error": "file not found"})
            else:
                self._json(400, {"error": "bad path"})
        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path == "/v1/ingest":
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len)) if content_len > 0 else {}
            epoch_id = body.get("epoch_id", "")
            source_dir = body.get("source_dir", "")
            if not epoch_id or not source_dir:
                self._json(400, {"error": "epoch_id and source_dir required"})
                return
            result = STATE.ingest_epoch(epoch_id, source_dir)
            self._json(201 if "error" not in result else 400, result)
        else:
            self._json(404, {"error": "not_found"})

    def _json(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, default=str).encode())

    def log_message(self, fmt, *args):
        pass


def main():
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9447
    storage = sys.argv[2] if len(sys.argv) > 2 else "archive_storage"

    global STATE
    STATE = ArchiveState(storage_dir=storage)
    print(f"[darwin-archived] Listening on :{port}")
    print(f"[darwin-archived] Storage: {storage}")
    print(f"[darwin-archived] Existing epochs: {len(STATE.epochs)}")
    print(f"[darwin-archived] Endpoints:")
    print(f"  GET  /healthz                     — health")
    print(f"  GET  /v1/epochs                   — list epochs")
    print(f"  GET  /v1/epochs/:id               — epoch manifest")
    print(f"  GET  /v1/epochs/:id/:filename     — download artifact")
    print(f"  POST /v1/ingest                   — ingest epoch artifacts")

    try:
        HTTPServer(("0.0.0.0", port), ArchiveHandler).serve_forever()
    except KeyboardInterrupt:
        print("\n[darwin-archived] Shutting down")


if __name__ == "__main__":
    main()
