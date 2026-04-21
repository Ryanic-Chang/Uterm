from __future__ import annotations

import socket
import time

from uterm.client import ClientConnection
from uterm.server import UtermServer


def _wait_for(predicate, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def test_end_to_end_command_execution() -> None:
    server = UtermServer("127.0.0.1", 0, heartbeat_timeout=10)
    port = server.sock.getsockname()[1]
    server.start()

    outputs: list[bytes] = []
    statuses: list[str] = []
    client = ClientConnection(
        "127.0.0.1",
        port,
        4321,
        on_output=outputs.append,
        on_status=statuses.append,
        heartbeat_interval=1.0,
    )

    try:
        client.start()
        client.send_bytes(b"echo uterm-integration\r")

        assert _wait_for(
            lambda: b"uterm-integration" in b"".join(outputs),
            timeout=10.0,
        ), f"command output not observed, statuses={statuses!r}"
    finally:
        client.close()
        server.stop()
