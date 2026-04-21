from __future__ import annotations

import os
import signal
import subprocess
import threading
from typing import Callable

if os.name == "posix":
    import fcntl
    import pty
    import termios
    import struct


OutputCallback = Callable[[bytes], None]
StatusCallback = Callable[[str], None]


class RemoteShellSession:
    """Wrap an interactive shell session and expose it as a byte stream."""

    def __init__(
        self,
        *,
        client_id: int,
        on_output: OutputCallback,
        on_status: StatusCallback,
    ) -> None:
        self.client_id = client_id
        self.on_output = on_output
        self.on_status = on_status
        self._started = False
        self.process: subprocess.Popen[bytes] | None = None
        self._master_fd: int | None = None
        self._reader_threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self._command_buffer = bytearray()
        self._windows_child_lock = threading.Lock()

    def start(self, rows: int = 24, columns: int = 80) -> None:
        if self._started:
            return

        self._started = True
        if os.name == "posix":
            self._start_posix(rows, columns)
        else:
            self._start_windows()

    def write(self, data: bytes) -> None:
        if not self._started:
            return

        if os.name == "posix":
            if self._master_fd is not None:
                os.write(self._master_fd, data)
            return

        self._write_windows(data)

    def resize(self, rows: int, columns: int) -> None:
        if os.name != "posix" or self._master_fd is None:
            return
        winsize = struct.pack("HHHH", rows, columns, 0, 0)
        fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)

    def stop(self) -> None:
        self._stop_event.set()

        if not self._started:
            return

        try:
            if os.name == "posix":
                if self.process is not None:
                    os.killpg(self.process.pid, signal.SIGTERM)
            else:
                self._terminate_windows_child()
        except ProcessLookupError:
            pass
        finally:
            self.process = None

    def _start_posix(self, rows: int, columns: int) -> None:
        assert os.name == "posix"

        master_fd, slave_fd = pty.openpty()
        self._master_fd = master_fd
        self.resize(rows, columns)

        shell = os.environ.get("SHELL", "/bin/bash")
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")

        self.process = subprocess.Popen(
            [shell],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            start_new_session=True,
            env=env,
            close_fds=True,
        )
        os.close(slave_fd)

        thread = threading.Thread(target=self._read_from_master, daemon=True)
        thread.start()
        self._reader_threads.append(thread)

    def _start_windows(self) -> None:
        self.on_status(
            "Windows 服务端已启用兼容模式；PTY、top/vim 和窗口同步需要在 POSIX 服务器上运行。"
        )
        self.on_output(b"[uterm] Windows compatibility shell ready.\r\n")

    def _read_from_master(self) -> None:
        while not self._stop_event.is_set():
            try:
                chunk = os.read(self._master_fd, 1024) if self._master_fd is not None else b""
            except OSError:
                break
            if not chunk:
                break
            self.on_output(chunk)

        self.on_status(f"客户端 {self.client_id} 的 shell 会话已结束。")

    def _write_windows(self, data: bytes) -> None:
        if b"\x03" in data:
            self._send_windows_interrupt()
            data = data.replace(b"\x03", b"")

        for byte in data:
            if byte in (8, 127):
                if self._command_buffer:
                    self._command_buffer.pop()
                continue

            if byte in (10, 13):
                command = self._command_buffer.decode("utf-8", errors="ignore").strip()
                self._command_buffer.clear()
                if command:
                    self._run_windows_command(command)
                continue

            self._command_buffer.append(byte)

    def _run_windows_command(self, command: str) -> None:
        if self._stop_event.is_set():
            return
        if self.process is not None and self.process.poll() is None:
            self.on_output(b"\r\n[uterm] A command is already running. Use Ctrl+C before starting another.\r\n")
            return

        def worker() -> None:
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            child = subprocess.Popen(
                command,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
                bufsize=0,
            )
            with self._windows_child_lock:
                self.process = child

            assert child.stdout is not None
            while not self._stop_event.is_set():
                chunk = child.stdout.read(1024)
                if not chunk:
                    break
                self.on_output(chunk)

            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.terminate()
                child.wait(timeout=5)
            with self._windows_child_lock:
                if self.process is child:
                    self.process = None

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        self._reader_threads.append(thread)

    def _send_windows_interrupt(self) -> None:
        if self.process is None:
            return
        ctrl_break = getattr(signal, "CTRL_BREAK_EVENT", None)
        if ctrl_break is not None:
            try:
                self.process.send_signal(ctrl_break)
                return
            except ValueError:
                pass

        self._terminate_windows_child()

    def _terminate_windows_child(self) -> None:
        if self.process is None:
            return
        try:
            self.process.terminate()
        except OSError:
            pass
