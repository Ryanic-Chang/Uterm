from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import struct

MAGIC = 0x5554
HEADER = struct.Struct("!HBIHI")
HEADER_SIZE = HEADER.size
MAX_DATAGRAM_SIZE = 1400
MAX_PAYLOAD_SIZE = MAX_DATAGRAM_SIZE - HEADER_SIZE


class ProtocolError(ValueError):
    """Raised when a datagram does not match the Uterm wire format."""


class MessageType(IntEnum):
    COMMAND_INPUT = 0x01
    COMMAND_OUTPUT = 0x02
    ACK = 0x03
    HEARTBEAT = 0x04


class InputKind(IntEnum):
    DATA = 0x01
    RESIZE = 0x02


@dataclass(slots=True, frozen=True)
class Packet:
    message_type: MessageType
    sequence: int
    client_id: int
    payload: bytes = b""

    def encode(self) -> bytes:
        if len(self.payload) > 0xFFFF:
            raise ProtocolError("payload too large for fixed header length field")

        header = HEADER.pack(
            MAGIC,
            int(self.message_type),
            self.sequence & 0xFFFFFFFF,
            len(self.payload),
            self.client_id & 0xFFFFFFFF,
        )
        return header + self.payload

    @classmethod
    def decode(cls, data: bytes) -> "Packet":
        if len(data) < HEADER_SIZE:
            raise ProtocolError("packet shorter than header")

        magic, message_type, sequence, payload_length, client_id = HEADER.unpack(
            data[:HEADER_SIZE]
        )
        if magic != MAGIC:
            raise ProtocolError("invalid magic")

        payload = data[HEADER_SIZE:]
        if len(payload) != payload_length:
            raise ProtocolError("payload length mismatch")

        try:
            enum_type = MessageType(message_type)
        except ValueError as exc:
            raise ProtocolError(f"unknown message type {message_type}") from exc

        return cls(
            message_type=enum_type,
            sequence=sequence,
            client_id=client_id,
            payload=payload,
        )


def build_input_payload(data: bytes) -> bytes:
    return bytes((InputKind.DATA,)) + data


def parse_input_payload(payload: bytes) -> tuple[InputKind, bytes]:
    if not payload:
        raise ProtocolError("input payload missing kind")

    try:
        kind = InputKind(payload[0])
    except ValueError as exc:
        raise ProtocolError(f"unknown input kind {payload[0]}") from exc

    return kind, payload[1:]


def build_resize_payload(rows: int, columns: int) -> bytes:
    if rows < 1 or columns < 1:
        raise ProtocolError("terminal size must be positive")
    return bytes((InputKind.RESIZE,)) + struct.pack("!HH", rows, columns)


def parse_resize_payload(payload: bytes) -> tuple[int, int]:
    if len(payload) != 4:
        raise ProtocolError("resize payload must contain 4 bytes")
    rows, columns = struct.unpack("!HH", payload)
    return rows, columns


def chunk_bytes(data: bytes, chunk_size: int = MAX_PAYLOAD_SIZE) -> list[bytes]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    return [data[index : index + chunk_size] for index in range(0, len(data), chunk_size)]
