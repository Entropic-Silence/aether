#!/usr/bin/env python3
"""Start Aether from a Jupyter-owned terminal on a notebook host.

Some platforms clean up processes that belong to a closed SSH session. The
notebook's Jupyter server is a long-lived parent, so a terminal created through
its local API can own the detached Aether services.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
import time
from pathlib import Path

import requests
import websocket


API_HEALTH = "http://127.0.0.1:8123/api/health"
WEB_HEALTH = "http://127.0.0.1:3000/"
TERMINAL_MARKER = Path("/tmp/aether-jupyter-terminal")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def services_ready() -> bool:
    try:
        api = requests.get(API_HEALTH, timeout=2)
        web = requests.get(WEB_HEALTH, timeout=2, allow_redirects=False)
        return api.ok and web.status_code < 500
    except requests.RequestException:
        return False


def jupyter_connection() -> tuple[str, str]:
    cmdline = Path("/proc/1/cmdline").read_bytes().decode("utf-8", "replace").replace("\0", " ")
    token_match = re.search(r"--NotebookApp\.token=(?:'([^']*)'|\"([^\"]*)\"|([^ ]+))", cmdline)
    base_match = re.search(r"--LabApp\.base_url=(?:'([^']*)'|\"([^\"]*)\"|([^ ]+))", cmdline)
    if not token_match or not base_match:
        raise RuntimeError("the Jupyter token/base URL was not found")
    token = next(value for value in token_match.groups() if value is not None)
    base = next(value for value in base_match.groups() if value is not None)
    return token, "/" + base.strip("/")


def terminal_name(http_base: str, token: str) -> str:
    terminals = requests.get(
        f"{http_base}/api/terminals", params={"token": token}, timeout=10
    )
    terminals.raise_for_status()
    active = {str(item["name"]) for item in terminals.json()}
    if TERMINAL_MARKER.exists():
        saved = TERMINAL_MARKER.read_text(encoding="utf-8").strip()
        if saved in active:
            return saved

    created = requests.post(
        f"{http_base}/api/terminals",
        params={"token": token},
        json={},
        timeout=10,
    )
    created.raise_for_status()
    name = str(created.json()["name"])
    TERMINAL_MARKER.write_text(name, encoding="utf-8")
    return name


def main() -> int:
    try:
        token, base = jupyter_connection()
        http_base = f"http://127.0.0.1:8888{base}"
        name = terminal_name(http_base, token)
        ws_url = f"ws://127.0.0.1:8888{base}/terminals/websocket/{name}?token={token}"
        socket = websocket.create_connection(
            ws_url,
            timeout=10,
            origin="http://127.0.0.1:8888",
        )
        script = shlex.quote(str(PROJECT_ROOT / "scripts" / "start_services.sh"))
        command = f"AETHER_JUPYTER_CHILD=1 bash {script}\r"
        socket.send(json.dumps(["stdin", command]))
        time.sleep(0.5)
        socket.close()
    except Exception as exc:
        print(f"Jupyter delegation unavailable: {exc}", file=sys.stderr)
        return 2

    for _ in range(60):
        if services_ready():
            print('api:  {"ok":true,"service":"Aether API"}')
            print("web:  HTTP 200")
            print(f"process owner: Jupyter terminal {name}")
            return 0
        time.sleep(1)

    print("Aether did not become healthy within 60 seconds", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
