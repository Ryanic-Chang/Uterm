from __future__ import annotations

import argparse
from dataclasses import dataclass
import logging
import os
import socket
import threading
import time

from .protocol import (
    MAX_PAYLOAD_SIZE,
    MessageType,
    Packet,
    ProtocolError,
    build_resize_payload,
    chunk_bytes,
    parse_input_payload,
    parse_resize_payload,
    InputKind,
)
from .session import RemoteShellSession
from .transport import Address, ReliableChannel, TransportError

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ClientRuntime:
    channel: ReliableChannel
    session: RemoteShellSession


class UtermServer:
    def __init__(
        self,
        host: str,
        port: int,
        heartbeat_timeout: int = 15,
    ) -> None:
        self.host = host
        self.port = port
        self.heartbeat_timeout = heartbeat_timeout
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, port))
        self.sock.settimeout(0.5)
        self._clients: dict[int, ClientRuntime] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        LOGGER.info("Uterm server listening on udp://%s:%s", self.host, self.port)
        self._threads = [
            threading.Thread(target=self._recv_loop, daemon=True),
            threading.Thread(target=self._janitor_loop, daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def run_forever(self) -> None:
        self.start()
        try:
            while not self._stop_event.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            LOGGER.info("Stopping server ...")
        finally:
            self.stop()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            for runtime in self._clients.values():
                runtime.session.stop()
        self.sock.close()

    def _recv_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                data, addr = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                packet = Packet.decode(data)
            except ProtocolError as exc:
                LOGGER.warning("Discard invalid packet from %s: %s", addr, exc)
                continue

            runtime = self._get_or_create_runtime(packet.client_id, addr)
            delivered = runtime.channel.accept(packet, addr)
            if delivered is None:
                continue

            if delivered.message_type is MessageType.HEARTBEAT:
                continue
            if delivered.message_type is not MessageType.COMMAND_INPUT:
                LOGGER.debug("Ignore unexpected packet type %s", delivered.message_type)
                continue

            self._handle_command_input(runtime, delivered)

    def _handle_command_input(self, runtime: ClientRuntime, packet: Packet) -> None:
        try:
            kind, payload = parse_input_payload(packet.payload)
        except ProtocolError as exc:
            LOGGER.warning("Client %s sent malformed input payload: %s", packet.client_id, exc)
            return

        if kind is InputKind.DATA:
            runtime.session.write(payload)
            return

        if kind is InputKind.RESIZE:
            try:
                rows, columns = parse_resize_payload(payload)
            except ProtocolError as exc:
                LOGGER.warning("Client %s sent malformed resize payload: %s", packet.client_id, exc)
                return
            runtime.session.resize(rows, columns)

    def _get_or_create_runtime(self, client_id: int, addr: Address) -> ClientRuntime:
        with self._lock:
            runtime = self._clients.get(client_id)
            if runtime is not None:
                runtime.channel.update_remote(addr)
                return runtime

            channel = ReliableChannel(
                sock=self.sock,
                remote_addr=addr,
                client_id=client_id,
                name=f"server-client-{client_id}",
                on_transport_error=lambda message: LOGGER.error(message),
            )
            session = RemoteShellSession(
                client_id=client_id,
                on_output=lambda data, cid=client_id: self._forward_output(cid, data),
                on_status=lambda message, cid=client_id: self._forward_status(cid, message),
            )
            session.start()
            runtime = ClientRuntime(channel=channel, session=session)
            self._clients[client_id] = runtime
            LOGGER.info("Client %s connected from %s", client_id, addr)
            return runtime

    def _forward_output(self, client_id: int, data: bytes) -> None:
        runtime = self._clients.get(client_id)
        if runtime is None:
            return

        max_chunk = MAX_PAYLOAD_SIZE
        for chunk in chunk_bytes(data, max_chunk):
            try:
                runtime.channel.send_packet(MessageType.COMMAND_OUTPUT, chunk)
            except TransportError:
                LOGGER.warning("Stop streaming output to client %s after repeated timeouts", client_id)
                break

    def _forward_status(self, client_id: int, message: str) -> None:
        LOGGER.info("[client %s] %s", client_id, message)
        self._forward_output(client_id, f"\r\n[uterm] {message}\r\n".encode("utf-8"))

    def _janitor_loop(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(1.0)
            stale_ids: list[int] = []

            with self._lock:
                now = time.monotonic()
                for client_id, runtime in self._clients.items():
                    if now - runtime.channel.last_seen_at > self.heartbeat_timeout:
                        stale_ids.append(client_id)

                for client_id in stale_ids:
                    runtime = self._clients.pop(client_id)
                    runtime.session.stop()
                    LOGGER.info("Client %s marked offline after heartbeat timeout", client_id)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Uterm UDP remote terminal server")
    parser.add_argument("--host", default="0.0.0.0", help="UDP bind host")
    parser.add_argument("--port", type=int, default=9527, help="UDP bind port")
    parser.add_argument(
        "--heartbeat-timeout",
        type=int,
        default=15,
        help="Seconds without heartbeat before a client is considered offline",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    if os.name != "posix":
        LOGGER.warning("Server is running without PTY support; advanced full-screen apps require POSIX.")

    server = UtermServer(
        host=args.host,
        port=args.port,
        heartbeat_timeout=args.heartbeat_timeout,
    )
    server.run_forever()


if __name__ == "__main__":
    main()
