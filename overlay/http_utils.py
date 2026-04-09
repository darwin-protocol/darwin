"""Shared HTTP helpers for DARWIN overlay services."""

from __future__ import annotations

import ipaddress
import json
import os
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.request import Request, urlopen


def resolve_bind_host(default: str = "127.0.0.1") -> str:
    return os.environ.get("DARWIN_BIND_HOST", default)


def is_loopback_host(host: str) -> bool:
    normalized = host.strip().strip("[]").lower()
    if normalized in {"localhost", "ip6-localhost"}:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def bind_host_requires_admin_token(host: str) -> bool:
    return not is_loopback_host(host)


def admin_token() -> str:
    return os.environ.get("DARWIN_ADMIN_TOKEN", "").strip()


def enforce_secure_bind(service_name: str, bind_host: str) -> None:
    if not bind_host_requires_admin_token(bind_host):
        return
    if admin_token():
        return
    raise SystemExit(
        f"{service_name} refuses non-loopback bind host {bind_host!r} without DARWIN_ADMIN_TOKEN"
    )


def request_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if extra:
        headers.update(extra)
    token = admin_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def load_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_len = int(handler.headers.get("Content-Length", 0))
    if content_len <= 0:
        return {}
    body = handler.rfile.read(content_len)
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_json") from exc


def require_admin_token(handler: BaseHTTPRequestHandler) -> bool:
    token = admin_token()
    if not token:
        return True

    presented = handler.headers.get("X-Darwin-Token", "").strip()
    if not presented:
        auth = handler.headers.get("Authorization", "").strip()
        if auth.lower().startswith("bearer "):
            presented = auth[7:].strip()

    if presented == token:
        return True

    raw = json.dumps({"error": "unauthorized"}).encode()
    handler.send_response(401)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)
    return False


def http_get_bytes(url: str, timeout: float = 10.0) -> bytes:
    req = Request(url, headers=request_headers())
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()
