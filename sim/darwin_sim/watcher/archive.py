"""Archive mirroring for watcher operators.

Fetches epoch artifacts from the archive service, verifies hashes, and stores
them locally so replay uses the exact same inputs an outside watcher would see.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen


class ArchiveSyncError(RuntimeError):
    """Raised when archive mirroring or verification fails."""


def _fetch_json(url: str) -> dict:
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _fetch_bytes(url: str) -> tuple[bytes, str]:
    req = Request(url)
    with urlopen(req, timeout=30) as resp:
        data = resp.read()
        return data, resp.headers.get("X-SHA256", "")


def _epoch_sort_key(epoch: dict) -> tuple[int, str]:
    epoch_id = str(epoch.get("epoch_id", ""))
    try:
        return (0, f"{int(epoch_id):020d}")
    except ValueError:
        return (1, epoch_id)


def list_archive_epochs(archive_url: str) -> list[dict]:
    payload = _fetch_json(f"{archive_url.rstrip('/')}/v1/epochs")
    epochs = payload.get("epochs", [])
    return sorted(epochs, key=_epoch_sort_key)


def resolve_archive_epoch_id(archive_url: str, epoch_id: str = "latest") -> str:
    if epoch_id != "latest":
        return str(epoch_id)

    epochs = list_archive_epochs(archive_url)
    if not epochs:
        raise ArchiveSyncError("archive_empty")
    return str(epochs[-1]["epoch_id"])


def fetch_epoch_manifest(archive_url: str, epoch_id: str) -> dict:
    payload = _fetch_json(f"{archive_url.rstrip('/')}/v1/epochs/{epoch_id}")
    files = payload.get("files", {})
    if not files:
        raise ArchiveSyncError(f"epoch_{epoch_id}_manifest_empty")
    return {"epoch_id": str(epoch_id), "files": files}


def mirror_epoch_from_archive(archive_url: str, artifacts_dir: str | Path, epoch_id: str = "latest") -> dict:
    archive_url = archive_url.rstrip("/")
    resolved_epoch_id = resolve_archive_epoch_id(archive_url, epoch_id=epoch_id)
    manifest = fetch_epoch_manifest(archive_url, resolved_epoch_id)

    root = Path(artifacts_dir)
    epoch_dir = root / f"epoch_{resolved_epoch_id}"
    epoch_dir.mkdir(parents=True, exist_ok=True)

    downloaded_files: list[str] = []
    for filename, meta in sorted(manifest["files"].items()):
        data, header_sha = _fetch_bytes(f"{archive_url}/v1/epochs/{resolved_epoch_id}/{filename}")
        computed_sha = hashlib.sha256(data).hexdigest()
        expected_sha = str(meta.get("sha256", ""))

        if header_sha and header_sha != computed_sha:
            raise ArchiveSyncError(f"{filename}_header_sha_mismatch")
        if expected_sha and expected_sha != computed_sha:
            raise ArchiveSyncError(f"{filename}_manifest_sha_mismatch")

        with tempfile.NamedTemporaryFile(dir=epoch_dir, delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        tmp_path.replace(epoch_dir / filename)
        downloaded_files.append(filename)

    manifest_path = epoch_dir / "archive_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return {
        "epoch_id": resolved_epoch_id,
        "artifact_dir": str(epoch_dir),
        "downloaded_files": downloaded_files,
        "file_count": len(downloaded_files),
        "manifest_path": str(manifest_path),
    }
