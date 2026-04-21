from uterm.terminal import TerminalBuffer


def test_terminal_renders_ansi_sequences() -> None:
    buffer = TerminalBuffer(rows=5, columns=20)
    buffer.feed(b"hello\r\n")
    buffer.feed(b"\x1b[2J\x1b[H")
    buffer.feed(b"top-like screen")

    snapshot = buffer.snapshot()

    assert "top-like screen" in snapshot


def test_terminal_resize_keeps_buffer_valid() -> None:
    buffer = TerminalBuffer(rows=5, columns=10)
    buffer.feed(b"1234567890")
    buffer.resize(10, 20)

    snapshot = buffer.snapshot()

    assert isinstance(snapshot, str)
    assert buffer.rows == 10
    assert buffer.columns == 20
