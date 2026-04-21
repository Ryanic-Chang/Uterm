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
    build_info_payload,
    build_resize_payload,
    build_signal_payload,
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
        timeout_seconds: float = 0.7,
        max_retries: int = 6,
    ) -> None:
        self.server_addr = (host, port)
        self.client_id = client_id
        self.on_output = on_output
        self.on_status = on_status
        self.heartbeat_interval = heartbeat_interval
        self._socket_lock = threading.Lock()
        self._connection_lock = threading.Lock()
        self.sock = self._create_socket()
        self.channel = ReliableChannel(
            sock=self.sock,
            remote_addr=self.server_addr,
            client_id=self.client_id,
            name=f"client-{self.client_id}",
            on_transport_error=self.on_status,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._send_queue: queue.Queue[tuple[MessageType, bytes, bool]] = queue.Queue(maxsize=4096)
        self._consecutive_send_failures = 0
        self._reconnect_in_progress = False

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
        self._send(MessageType.DISCONNECT, b"", silent=True)
        self._stop_event.set()
        time.sleep(0.1)  # Allow disconnect packet to be sent
        try:
            with self._socket_lock:
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

    def send_info_request(self) -> None:
        self._send(MessageType.COMMAND_INPUT, build_info_payload(), silent=True)

    def send_signal(self, signum: int) -> None:
        self._send(MessageType.COMMAND_INPUT, build_signal_payload(signum))

    def send_heartbeat(self) -> None:
        self._send(MessageType.HEARTBEAT, b"", silent=True)

    def _recv_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                with self._socket_lock:
                    sock = self.sock
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                if self._stop_event.is_set():
                    break
                time.sleep(0.5)
                continue

            if addr != self.server_addr:
                LOGGER.debug("Ignore packet from unexpected peer %s", addr)
                continue

            try:
                packet = Packet.decode(data)
            except ProtocolError as exc:
                self.on_status(f"收到非法报文，已丢弃: {exc}")
                continue

            if packet.client_id != self.client_id:
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
            self.send_info_request()

    def _send(self, message_type: MessageType, payload: bytes, *, silent: bool = False) -> None:
        if self._stop_event.is_set():
            return
        try:
            self._send_queue.put_nowait((message_type, payload, silent))
        except queue.Full:
            if silent:
                return
            self.on_status("发送队列已满，已丢弃本次输入。请检查网络连接是否稳定。")

    def _send_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                message_type, payload, silent = self._send_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                self.channel.send_packet(message_type, payload)
                self._consecutive_send_failures = 0
            except TransportError as exc:
                self._consecutive_send_failures += 1
                if not silent:
                    self.on_status(f"发送失败: {exc}")
                if self._consecutive_send_failures >= 3:
                    self._maybe_reconnect()

    def _create_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
        sock.settimeout(0.5)
        try:
            sock.connect(self.server_addr)
        except OSError:
            pass
        return sock

    def _maybe_reconnect(self) -> None:
        if self._reconnect_in_progress:
            return
        with self._connection_lock:
            if self._reconnect_in_progress:
                return
            self._reconnect_in_progress = True

        def worker() -> None:
            backoff = 0.5
            while not self._stop_event.is_set():
                try:
                    with self._socket_lock:
                        try:
                            self.sock.close()
                        except OSError:
                            pass
                        self.sock = self._create_socket()
                        self.channel.rebind_socket(self.sock)
                    self._consecutive_send_failures = 0
                    self.on_status("已重连")
                    self.send_heartbeat()
                    self.send_info_request()
                    break
                except Exception:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
            with self._connection_lock:
                self._reconnect_in_progress = False

        threading.Thread(target=worker, daemon=True).start()
