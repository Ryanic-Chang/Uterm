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

    def get_lines_and_cursor(self) -> tuple[list[dict[int, pyte.screens.Char]], int, int]:
        lines = []
        for history_line in self._screen.history.top:
            if hasattr(history_line, "data"):
                lines.append({i: pyte.screens.Char(c) for i, c in enumerate(history_line.data)})
            else:
                # Handle StaticDefaultDict or other dict-like objects in newer pyte versions
                line_dict = {}
                for i in range(self.columns):
                    char = history_line.get(i)
                    if char is not None:
                        line_dict[i] = char
                    else:
                        line_dict[i] = pyte.screens.Char(" ")
                lines.append(line_dict)
        
        for y in range(self._screen.lines):
            lines.append(self._screen.buffer[y])
            
        history_offset = len(self._screen.history.top)
        cursor_y = history_offset + self._screen.cursor.y
        cursor_x = self._screen.cursor.x
        
        return lines, cursor_y, cursor_x

    def reset(self) -> None:
        self._screen.reset()
