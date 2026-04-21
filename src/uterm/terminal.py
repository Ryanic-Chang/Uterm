from __future__ import annotations

import codecs

import pyte


class TerminalBuffer:
    """Keep a VT-compatible in-memory terminal for GUI rendering."""

    def __init__(self, rows: int = 30, columns: int = 100, history: int = 2000) -> None:
        self.rows = rows
        self.columns = columns
        self._screen = pyte.HistoryScreen(columns, rows, history=history, ratio=0.5)
        self._stream = pyte.Stream(self._screen)
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")

    def feed(self, data: bytes) -> None:
        if not data:
            return
        self._stream.feed(self._decoder.decode(data))

    def resize(self, rows: int, columns: int) -> None:
        self.rows = rows
        self.columns = columns
        self._screen.resize(lines=rows, columns=columns)

    def snapshot(self) -> str:
        return "\n".join(self._screen.display)

    def reset(self) -> None:
        self._screen.reset()
