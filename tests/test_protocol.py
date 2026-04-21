from uterm.protocol import (
    InputKind,
    MessageType,
    Packet,
    ProtocolError,
    build_input_payload,
    build_resize_payload,
    parse_input_payload,
    parse_resize_payload,
)


def test_packet_round_trip() -> None:
    packet = Packet(
        message_type=MessageType.COMMAND_INPUT,
        sequence=42,
        client_id=1001,
        payload=b"hello",
    )

    decoded = Packet.decode(packet.encode())

    assert decoded == packet


def test_invalid_magic_is_rejected() -> None:
    with_error = b"\x00\x00" + Packet(
        message_type=MessageType.HEARTBEAT,
        sequence=1,
        client_id=7,
        payload=b"",
    ).encode()[2:]

    try:
        Packet.decode(with_error)
    except ProtocolError as exc:
        assert "magic" in str(exc)
    else:
        raise AssertionError("invalid packet should raise ProtocolError")


def test_resize_payload_round_trip() -> None:
    payload = build_resize_payload(48, 160)
    kind, inner = parse_input_payload(payload)

    assert kind is InputKind.RESIZE
    assert parse_resize_payload(inner) == (48, 160)


def test_data_payload_round_trip() -> None:
    payload = build_input_payload(b"\x03ls\r")
    kind, inner = parse_input_payload(payload)

    assert kind is InputKind.DATA
    assert inner == b"\x03ls\r"
