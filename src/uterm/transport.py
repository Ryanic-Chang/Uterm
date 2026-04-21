from __future__ import annotations

from dataclasses import dataclass, field
import logging
import socket
import threading
import time
from typing import Callable

from .protocol import MessageType, Packet

LOGGER = logging.getLogger(__name__)


class TransportError(RuntimeError):
    """Raised when a reliable UDP send exhausts all retries."""


Address = tuple[str, int]


@dataclass(slots=True)
class ChannelStats:
    retransmissions: int = 0
    duplicates: int = 0
    acks_sent: int = 0
    packets_sent: int = 0
    packets_received: int = 0


@dataclass(slots=True)
class ReliableChannel:
    sock: socket.socket
    remote_addr: Address
    client_id: int
    name: str
    timeout_seconds: float = 0.7
    max_retries: int = 6
    on_transport_error: Callable[[str], None] | None = None
    _send_lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _state_lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _pending_ack: dict[int, threading.Event] = field(default_factory=dict, init=False)
    _next_sequence: int = field(default=1, init=False)
    _last_delivered_sequence: int = field(default=0, init=False)
    last_seen_at: float = field(default_factory=time.monotonic, init=False)
    stats: ChannelStats = field(default_factory=ChannelStats, init=False)

    def update_remote(self, remote_addr: Address) -> None:
        with self._state_lock:
            self.remote_addr = remote_addr

    def send_packet(self, message_type: MessageType, payload: bytes = b"") -> int:
        if message_type is MessageType.ACK:
            raise ValueError("ACK packets must be sent via send_ack")

        with self._send_lock:
            sequence = self._reserve_sequence()
            event = threading.Event()
            with self._state_lock:
                self._pending_ack[sequence] = event

            packet = Packet(
                message_type=message_type,
                sequence=sequence,
                client_id=self.client_id,
                payload=payload,
            )
            datagram = packet.encode()

            for attempt in range(1, self.max_retries + 1):
                try:
                    self.sock.sendto(datagram, self.remote_addr)
                except OSError as exc:
                    with self._state_lock:
                        self._pending_ack.pop(sequence, None)
                    raise TransportError(f"socket send failed: {exc}") from exc
                self.stats.packets_sent += 1
                if event.wait(self.timeout_seconds):
                    with self._state_lock:
                        self._pending_ack.pop(sequence, None)
                    return sequence

                self.stats.retransmissions += 1
                LOGGER.warning(
                    "%s: timeout waiting for ACK for seq=%s, retry %s/%s",
                    self.name,
                    sequence,
                    attempt,
                    self.max_retries,
                )

            with self._state_lock:
                self._pending_ack.pop(sequence, None)

        self._report_transport_error(
            f"{self.name} 与对端通信超时，序列号 {sequence} 在多次重传后仍未收到 ACK。"
        )
        raise TransportError(f"timed out waiting for ACK for sequence {sequence}")

    def send_ack(self, sequence: int) -> None:
        packet = Packet(
            message_type=MessageType.ACK,
            sequence=sequence,
            client_id=self.client_id,
            payload=b"",
        )
        try:
            self.sock.sendto(packet.encode(), self.remote_addr)
        except OSError:
            return
        self.stats.acks_sent += 1

    def accept(self, packet: Packet, addr: Address) -> Packet | None:
        self.update_remote(addr)
        self.last_seen_at = time.monotonic()
        self.stats.packets_received += 1

        if packet.message_type is MessageType.ACK:
            with self._state_lock:
                event = self._pending_ack.get(packet.sequence)
            if event is not None:
                event.set()
            return None

        self.send_ack(packet.sequence)

        with self._state_lock:
            if packet.sequence <= self._last_delivered_sequence:
                self.stats.duplicates += 1
                return None
            self._last_delivered_sequence = packet.sequence

        return packet

    def _reserve_sequence(self) -> int:
        with self._state_lock:
            sequence = self._next_sequence
            self._next_sequence += 1
        return sequence

    def _report_transport_error(self, message: str) -> None:
        LOGGER.error(message)
        if self.on_transport_error is not None:
            self.on_transport_error(message)
