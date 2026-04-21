from __future__ import annotations

import queue
import random
import tkinter.font as tkfont
from typing import Any

import customtkinter as ctk

from .client import ClientConnection
from .terminal import TerminalBuffer


class UtermApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Uterm")
        self.geometry("1280x820")
        self.minsize(1080, 720)

        self.connection: ClientConnection | None = None
        self.event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.terminal_buffer = TerminalBuffer()
        self._terminal_dirty = False
        self._resize_after_id: str | None = None
        self._terminal_size = (30, 100)

        self._build_layout()
        self.after(50, self._process_events)
        self.after(300, self._sync_terminal_size)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, corner_radius=18)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(18, 10), pady=18)
        sidebar.grid_columnconfigure(0, weight=1)

        content = ctk.CTkFrame(self, corner_radius=18)
        content.grid(row=0, column=1, sticky="nsew", padx=(10, 18), pady=18)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            sidebar,
            text="Uterm",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 4))
        ctk.CTkLabel(
            sidebar,
            text="Reliable Remote Terminal over UDP",
            text_color=("gray30", "gray75"),
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 20))

        self.host_entry = self._labeled_entry(sidebar, "服务端地址", "127.0.0.1", row=2)
        self.port_entry = self._labeled_entry(sidebar, "端口", "9527", row=4)
        self.client_id_entry = self._labeled_entry(
            sidebar,
            "客户端 ID",
            str(random.randint(1001, 9999)),
            row=6,
        )

        button_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        button_frame.grid(row=8, column=0, sticky="ew", padx=20, pady=(12, 10))
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.connect_button = ctk.CTkButton(button_frame, text="连接", command=self.connect)
        self.connect_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.disconnect_button = ctk.CTkButton(
            button_frame,
            text="断开",
            command=self.disconnect,
            fg_color="#374151",
            hover_color="#4B5563",
        )
        self.disconnect_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ctk.CTkLabel(
            sidebar,
            text="快速命令",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=9, column=0, sticky="w", padx=20, pady=(18, 8))

        quick_frame = ctk.CTkFrame(sidebar)
        quick_frame.grid(row=10, column=0, sticky="ew", padx=20)
        quick_frame.grid_columnconfigure((0, 1), weight=1)

        quick_commands = [
            ("pwd", "pwd"),
            ("ls", "ls"),
            ("whoami", "whoami"),
            ("ping", "ping 127.0.0.1"),
        ]
        for index, (label, command) in enumerate(quick_commands):
            row = index // 2
            column = index % 2
            ctk.CTkButton(
                quick_frame,
                text=label,
                height=34,
                command=lambda value=command: self.send_command(value),
            ).grid(row=row, column=column, sticky="ew", padx=6, pady=6)

        ctk.CTkLabel(
            sidebar,
            text="状态日志",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=11, column=0, sticky="w", padx=20, pady=(18, 8))

        self.log_box = ctk.CTkTextbox(sidebar, corner_radius=14, height=220)
        self.log_box.grid(row=12, column=0, sticky="nsew", padx=20, pady=(0, 20))
        sidebar.grid_rowconfigure(12, weight=1)
        self._append_log("等待连接。")

        header = ctk.CTkFrame(content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 12))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Remote Terminal",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        self.status_label = ctk.CTkLabel(
            header,
            text="未连接",
            text_color="#F59E0B",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.status_label.grid(row=0, column=1, sticky="e")

        terminal_card = ctk.CTkFrame(content, corner_radius=16)
        terminal_card.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        terminal_card.grid_rowconfigure(1, weight=1)
        terminal_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            terminal_card,
            text="交互终端",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        self.terminal = ctk.CTkTextbox(
            terminal_card,
            wrap="none",
            corner_radius=14,
            font=ctk.CTkFont(family="Cascadia Mono", size=13),
        )
        self.terminal.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.terminal.configure(state="disabled")

        inner = self.terminal._textbox
        inner.bind("<KeyPress>", self._on_keypress)
        inner.bind("<Button-1>", lambda _event: inner.focus_set())
        inner.bind("<<Paste>>", self._on_paste)
        inner.bind("<Configure>", self._schedule_terminal_resize)

    def _labeled_entry(self, parent: ctk.CTkBaseClass, label: str, value: str, *, row: int) -> ctk.CTkEntry:
        ctk.CTkLabel(
            parent,
            text=label,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=row, column=0, sticky="w", padx=20, pady=(0, 6))
        entry = ctk.CTkEntry(parent)
        entry.grid(row=row + 1, column=0, sticky="ew", padx=20)
        entry.insert(0, value)
        return entry

    def connect(self) -> None:
        if self.connection is not None:
            self._append_log("连接已存在。")
            return

        try:
            port = int(self.port_entry.get())
            client_id = int(self.client_id_entry.get())
        except ValueError:
            self._append_log("端口和客户端 ID 必须是整数。")
            return

        self.connection = ClientConnection(
            self.host_entry.get().strip(),
            port,
            client_id,
            on_output=lambda data: self.event_queue.put(("output", data)),
            on_status=lambda message: self.event_queue.put(("status", message)),
        )
        self.connection.start()
        rows, columns = self._terminal_size
        self.connection.send_resize(rows, columns)
        self._set_connection_state(True)
        self.focus_terminal()

    def disconnect(self) -> None:
        if self.connection is None:
            return
        self.connection.close()
        self.connection = None
        self._set_connection_state(False)

    def send_command(self, command: str) -> None:
        if self.connection is None:
            self._append_log("尚未连接，无法发送命令。")
            return
        self.connection.send_bytes((command + "\r").encode("utf-8"))
        self.focus_terminal()

    def focus_terminal(self) -> None:
        self.terminal._textbox.focus_set()

    def _process_events(self) -> None:
        while True:
            try:
                kind, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "output":
                self.terminal_buffer.feed(payload)
                self._terminal_dirty = True
            elif kind == "status":
                self._append_log(str(payload))
                self._update_status_label(str(payload))

        if self._terminal_dirty:
            self._render_terminal()

        self.after(50, self._process_events)

    def _render_terminal(self) -> None:
        self._terminal_dirty = False
        snapshot = self.terminal_buffer.snapshot()
        self.terminal.configure(state="normal")
        self.terminal.delete("1.0", "end")
        self.terminal.insert("1.0", snapshot)
        self.terminal.configure(state="disabled")

    def _append_log(self, message: str) -> None:
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")

    def _update_status_label(self, message: str) -> None:
        connected = self.connection is not None
        self.status_label.configure(
            text=message,
            text_color=("#10B981" if connected else "#F59E0B"),
        )

    def _set_connection_state(self, connected: bool) -> None:
        self.status_label.configure(
            text="已连接" if connected else "未连接",
            text_color=("#10B981" if connected else "#F59E0B"),
        )
        self.connect_button.configure(state="disabled" if connected else "normal")
        self.disconnect_button.configure(state="normal" if connected else "disabled")

    def _on_keypress(self, event: Any) -> str | None:
        if self.connection is None:
            return "break"

        data = self._translate_key(event)
        if data:
            self.connection.send_bytes(data)
        return "break"

    def _on_paste(self, _event: Any) -> str:
        if self.connection is not None:
            pasted = self.clipboard_get()
            self.connection.send_bytes(pasted.encode("utf-8"))
        return "break"

    def _translate_key(self, event: Any) -> bytes | None:
        control_pressed = bool(event.state & 0x4)
        special = {
            "Return": b"\r",
            "BackSpace": b"\x7f",
            "Tab": b"\t",
            "Escape": b"\x1b",
            "Up": b"\x1b[A",
            "Down": b"\x1b[B",
            "Right": b"\x1b[C",
            "Left": b"\x1b[D",
            "Home": b"\x1b[H",
            "End": b"\x1b[F",
            "Delete": b"\x1b[3~",
            "Prior": b"\x1b[5~",
            "Next": b"\x1b[6~",
            "Insert": b"\x1b[2~",
        }

        if event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"):
            return None

        if control_pressed and event.keysym.lower() == "c":
            return b"\x03"

        if event.keysym in special:
            return special[event.keysym]

        if event.char:
            return event.char.encode("utf-8")

        return None

    def _schedule_terminal_resize(self, _event: Any) -> None:
        if self._resize_after_id is not None:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(120, self._sync_terminal_size)

    def _sync_terminal_size(self) -> None:
        self._resize_after_id = None
        font = tkfont.Font(font=self.terminal._textbox["font"])
        char_width = max(font.measure("M"), 1)
        line_height = max(font.metrics("linespace"), 1)

        width = max(self.terminal.winfo_width() - 12, char_width)
        height = max(self.terminal.winfo_height() - 12, line_height)
        columns = max(width // char_width, 20)
        rows = max(height // line_height, 8)

        if (rows, columns) == self._terminal_size:
            return

        self._terminal_size = (rows, columns)
        self.terminal_buffer.resize(rows, columns)
        self._terminal_dirty = True
        if self.connection is not None:
            self.connection.send_resize(rows, columns)


def main() -> None:
    app = UtermApp()
    app.mainloop()


if __name__ == "__main__":
    main()
