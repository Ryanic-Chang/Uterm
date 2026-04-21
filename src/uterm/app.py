from __future__ import annotations

from datetime import datetime
import json
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
        self._meta_buffer = b""
        self._info = {
            "hostname": "-",
            "username": "-",
            "cwd": "-",
            "timestamp": "-",
        }

        self._build_layout()
        self.after(50, self._process_events)
        self.after(300, self._sync_terminal_size)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=4)
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
        terminal_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            terminal_card,
            text="交互终端",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8), columnspan=2)

        info_panel = ctk.CTkFrame(terminal_card, corner_radius=14)
        info_panel.grid(row=1, column=0, sticky="nsw", padx=(16, 10), pady=(0, 16))
        info_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            info_panel,
            text="主机信息",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 8))

        self._info_labels: dict[str, ctk.CTkLabel] = {}
        self._info_labels["hostname"] = self._info_row(info_panel, 1, "主机名", self._info["hostname"])
        self._info_labels["username"] = self._info_row(info_panel, 2, "用户名", self._info["username"])
        self._info_labels["cwd"] = self._info_row(info_panel, 3, "路径", self._info["cwd"])
        self._info_labels["timestamp"] = self._info_row(info_panel, 4, "时间", self._info["timestamp"])
        self._info_labels["local"] = self._info_row(
            info_panel, 5, "本地", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        self.terminal = ctk.CTkTextbox(
            terminal_card,
            wrap="word",
            corner_radius=14,
            font=ctk.CTkFont(family="Cascadia Mono", size=13),
        )
        self.terminal.grid(row=1, column=1, sticky="nsew", padx=(10, 16), pady=(0, 16))
        self.terminal.configure(state="normal")

        inner = self.terminal._textbox
        inner.bind("<KeyPress>", self._on_keypress)
        for key in ("<Up>", "<Down>", "<Left>", "<Right>", "<Return>", "<BackSpace>", "<Tab>", "<Delete>", "<Control-c>"):
            inner.bind(key, self._on_keypress)
        inner.bind("<Button-1>", lambda _event: inner.focus_set())
        inner.bind("<<Paste>>", self._on_paste)
        inner.bind("<<Copy>>", self._on_copy)
        if self._is_mac():
            inner.bind("<Button-2>", self._show_context_menu)
        else:
            inner.bind("<Button-3>", self._show_context_menu)
        inner.bind("<Configure>", self._schedule_terminal_resize)

        self._context_menu = self._create_context_menu()

    def _is_mac(self) -> bool:
        import sys
        return sys.platform == "darwin"

    def _create_context_menu(self) -> Any:
        import tkinter as tk
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="复制 (Copy)", command=lambda: self._on_copy(None))
        menu.add_command(label="粘贴 (Paste)", command=lambda: self._on_paste(None))
        return menu

    def _show_context_menu(self, event: Any) -> str:
        self._context_menu.tk_popup(event.x_root, event.y_root)
        return "break"


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
                remaining = self._consume_output_bytes(payload)
                if remaining:
                    self.terminal_buffer.feed(remaining)
                    self._terminal_dirty = True
            elif kind == "status":
                self._append_log(str(payload))
                self._update_status_label(str(payload))

        if self._terminal_dirty:
            self._render_terminal()

        self.after(50, self._process_events)

    def _render_terminal(self) -> None:
        self._terminal_dirty = False
        try:
            lines, cursor_y, cursor_x = self.terminal_buffer.get_lines_and_cursor()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Failed to render terminal buffer: {exc}", exc_info=True)
            return

        self.terminal.delete("1.0", "end")
        
        # Apply plain text and colors
        for y, line_dict in enumerate(lines):
            line_text = ""
            for x in range(self.terminal_buffer.columns):
                char_obj = line_dict.get(x)
                if char_obj:
                    line_text += char_obj.data
                else:
                    line_text += " "
            
            # Avoid inserting trailing newline for the last line
            if y == len(lines) - 1:
                self.terminal.insert("end", line_text)
            else:
                self.terminal.insert("end", line_text + "\n")
            
            current_tag = None
            start_idx = 0
            for x in range(self.terminal_buffer.columns):
                char_obj = line_dict.get(x)
                if char_obj and (char_obj.fg != "default" or char_obj.bg != "default"):
                    tag_name = f"fg_{char_obj.fg}_bg_{char_obj.bg}"
                    if current_tag != tag_name:
                        if current_tag:
                            self.terminal.tag_add(current_tag, f"{y+1}.{start_idx}", f"{y+1}.{x}")
                        current_tag = tag_name
                        start_idx = x
                        
                    # Configure the tag if not exists
                    try:
                        self.terminal.tag_config(tag_name, foreground=char_obj.fg if char_obj.fg != "default" else None, background=char_obj.bg if char_obj.bg != "default" else None)
                    except Exception:
                        pass
                else:
                    if current_tag:
                        self.terminal.tag_add(current_tag, f"{y+1}.{start_idx}", f"{y+1}.{x}")
                        current_tag = None
            if current_tag:
                self.terminal.tag_add(current_tag, f"{y+1}.{start_idx}", f"{y+1}.{self.terminal_buffer.columns}")

        self.terminal.see("end")
        
        # Sync cursor position
        cursor_index = f"{cursor_y + 1}.{cursor_x}"
        self.terminal.mark_set("insert", cursor_index)
        self.terminal.see("insert")

    def _append_log(self, message: str) -> None:
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")

    def _info_row(self, parent: ctk.CTkBaseClass, row: int, key: str, value: str) -> ctk.CTkLabel:
        ctk.CTkLabel(parent, text=key, text_color=("gray35", "gray75")).grid(
            row=row * 2 - 1, column=0, sticky="w", padx=12, pady=(8, 2)
        )
        label = ctk.CTkLabel(parent, text=value, justify="left")
        label.grid(row=row * 2, column=0, sticky="w", padx=12, pady=(0, 2))
        return label

    def _set_info(self, data: dict[str, Any]) -> None:
        for key in ("hostname", "username", "cwd", "timestamp"):
            value = data.get(key)
            if value is None:
                continue
            self._info[key] = str(value)
            label = self._info_labels.get(key)
            if label is not None:
                label.configure(text=self._info[key])

        local_label = self._info_labels.get("local")
        if local_label is not None:
            local_label.configure(text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def _consume_output_bytes(self, chunk: bytes) -> bytes:
        if not chunk:
            return b""
        data = self._meta_buffer + chunk
        self._meta_buffer = b""

        prefix = b"\x1b]9;UTERM_META:"
        while True:
            start = data.find(prefix)
            if start == -1:
                return data
            end = data.find(b"\x07", start + len(prefix))
            if end == -1:
                self._meta_buffer = data[start:]
                return data[:start]

            meta_raw = data[start + len(prefix) : end]
            try:
                meta = json.loads(meta_raw.decode("utf-8", errors="ignore"))
                if isinstance(meta, dict):
                    self._set_info(meta)
            except Exception:
                pass

            data = data[:start] + data[end + 1 :]

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

        control_pressed = bool(event.state & 0x4)
        if control_pressed and event.keysym.lower() == "c":
            if self.terminal._textbox.tag_ranges("sel"):
                self._on_copy(event)
                return "break"
            else:
                self.connection.send_signal(2)
                return "break"
        
        # If the input method or OS translates it to \x03 directly without the Ctrl state being cleanly captured
        if event.char == "\x03":
            if self.terminal._textbox.tag_ranges("sel"):
                self._on_copy(event)
                return "break"
            else:
                self.connection.send_signal(2)
                return "break"

        data = self._translate_key(event)
        if data:
            self.connection.send_bytes(data)
        
        # Raw mode: always return "break" to disable local echo/editing
        return "break"

    def _on_paste(self, _event: Any) -> str:
        if self.connection is not None:
            try:
                pasted = self.clipboard_get()
                self.connection.send_bytes(pasted.encode("utf-8"))
            except Exception:
                pass
        return "break"

    def _on_copy(self, _event: Any) -> str:
        try:
            if self.terminal._textbox.tag_ranges("sel"):
                selected_text = self.terminal._textbox.get("sel.first", "sel.last")
                self.clipboard_clear()
                self.clipboard_append(selected_text)
        except Exception:
            pass
        return "break"

    def _translate_key(self, event: Any) -> bytes | None:
        control_pressed = bool(event.state & 0x4)
        special = {
            "Return": b"\r",
            "BackSpace": b"\x08",
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

        if event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Caps_Lock", "Num_Lock", "Scroll_Lock"):
            return None

        if control_pressed and len(event.keysym) == 1:
            if event.keysym.lower() == "c":
                return None
            char_code = ord(event.keysym.lower()) - ord('a') + 1
            if 1 <= char_code <= 26:
                return bytes([char_code])

        if event.keysym in special:
            return special[event.keysym]

        if event.char:
            return event.char.encode("utf-8", errors="ignore")

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
