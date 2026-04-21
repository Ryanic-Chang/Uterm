from __future__ import annotations

import logging
import queue
import socket
import threading
import time
from typing import Callable

from .protocol import (
    MessageType,
    Packet,
    ProtocolError,
    build_input_payload,
    build_resize_payload,
)
from .transport import ReliableChannel, TransportError

LOGGER = logging.getLogger(__name__)

OutputCallback = Callable[[bytes], None]
StatusCallback = Callable[[str], None]


class ClientConnection:
    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        *,
        on_output: OutputCallback,
        on_status: StatusCallback,
        heartbeat_interval: float = 5.0,
    ) -> None:
        self.server_addr = (host, port)
        self.client_id = client_id
        self.on_output = on_output
        self.on_status = on_status
        self.heartbeat_interval = heartbeat_interval
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(0.5)
        self.channel = ReliableChannel(
            sock=self.sock,
            remote_addr=self.server_addr,
            client_id=client_id,
            name=f"client-{client_id}",
            on_transport_error=self.on_status,
        )
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._send_queue: queue.Queue[tuple[MessageType, bytes, bool]] = queue.Queue()

    def start(self) -> None:
        self._threads = [
            threading.Thread(target=self._recv_loop, daemon=True),
            threading.Thread(target=self._heartbeat_loop, daemon=True),
            threading.Thread(target=self._send_loop, daemon=True),
        ]
        for thread in self._threads:
            thread.start()

        self.on_status(f"已连接到 udp://{self.server_addr[0]}:{self.server_addr[1]}")
        self.send_heartbeat()

    def close(self) -> None:
        self._stop_event.set()
        try:
            self.sock.close()
        except OSError:
            pass
        self.on_status("连接已关闭")

    def send_bytes(self, data: bytes) -> None:
        if not data:
            return
        self._send(MessageType.COMMAND_INPUT, build_input_payload(data))

    def send_resize(self, rows: int, columns: int) -> None:
        self._send(MessageType.COMMAND_INPUT, build_resize_payload(rows, columns))

    def send_heartbeat(self) -> None:
        self._send(MessageType.HEARTBEAT, b"", silent=True)

    def _recv_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                data, addr = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break

            if addr != self.server_addr:
                LOGGER.debug("Ignore packet from unexpected peer %s", addr)
                continue

            try:
                packet = Packet.decode(data)
            except ProtocolError as exc:
                self.on_status(f"收到非法报文，已丢弃: {exc}")
                continue

            delivered = self.channel.accept(packet, addr)
            if delivered is None:
                continue

            if delivered.message_type is MessageType.COMMAND_OUTPUT:
                self.on_output(delivered.payload)

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(self.heartbeat_interval)
            if self._stop_event.is_set():
                break
            self.send_heartbeat()

    def _send(self, message_type: MessageType, payload: bytes, *, silent: bool = False) -> None:
        if self._stop_event.is_set():
            return
        self._send_queue.put((message_type, payload, silent))

    def _send_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                message_type, payload, silent = self._send_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                self.channel.send_packet(message_type, payload)
            except TransportError as exc:
                if not silent:
                    self.on_status(f"发送失败: {exc}")
