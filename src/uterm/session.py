from __future__ import annotations

import os
import socket
import getpass
from datetime import datetime, timezone
import signal
import subprocess
import threading
import collections
from typing import Callable, Deque

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
        self._cwd = os.getcwd()
        self._scrollback: Deque[bytes] = collections.deque(maxlen=10000)
        self._history: list[str] = []
        self._history_idx = 0

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

    def send_signal(self, signum: int) -> None:
        if not self._started:
            return
        
        if os.name == "posix":
            if self._master_fd is not None:
                try:
                    # In a PTY, sending the signal to the foreground process group
                    # is the correct way to interrupt the running command (e.g. ping).
                    fg_pgrp = os.tcgetpgrp(self._master_fd)
                    if fg_pgrp > 0:
                        os.killpg(fg_pgrp, signum)
                    elif self.process is not None:
                        os.kill(self.process.pid, signum)
                except OSError:
                    # Fallback to killing the shell process if tcgetpgrp fails
                    if self.process is not None:
                        try:
                            os.kill(self.process.pid, signum)
                        except ProcessLookupError:
                            pass
        else:
            if signum == getattr(signal, "SIGINT", 2):
                if self.process is not None:
                    self._send_windows_interrupt()
                else:
                    self.on_output(b"^C")
                    self._command_buffer.clear()
                    self._send_windows_prompt()

    def get_info(self) -> dict[str, str]:
        return {
            "hostname": socket.gethostname(),
            "username": getpass.getuser(),
            "cwd": self._cwd,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def stop(self) -> None:
        self._stop_event.set()

        if not self._started:
            return

        try:
            if os.name == "posix":
                if self.process is not None:
                    try:
                        os.killpg(self.process.pid, signal.SIGHUP)
                        self.process.wait(timeout=1.0)
                    except (ProcessLookupError, subprocess.TimeoutExpired):
                        pass
                    try:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if self._master_fd is not None:
                    try:
                        os.close(self._master_fd)
                    except OSError:
                        pass
                    self._master_fd = None
            else:
                self._terminate_windows_child()
        except ProcessLookupError:
            pass
        finally:
            self.process = None

    def _emit_output(self, data: bytes) -> None:
        if data:
            self._scrollback.append(data)
            self.on_output(data)

    def dump_scrollback(self) -> bytes:
        return b"".join(self._scrollback)

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
        self._emit_output(b"\r\n[uterm] Windows compatibility shell ready.\r\n")
        self._send_windows_prompt()
        
        # Execute visible whoami automatically upon connection
        self._command_buffer = bytearray(b"whoami")
        self._emit_output(b"whoami\r\n")
        command = self._command_buffer.decode("utf-8", errors="ignore").strip()
        self._command_buffer.clear()
        self._run_windows_command(command)

    def _send_windows_prompt(self) -> None:
        user = getpass.getuser()
        host = socket.gethostname()
        cwd = self._cwd
        prompt = f"\r\n\x1b[32m{user}@{host}\x1b[0m:\x1b[34m{cwd}\x1b[0m> ".encode("utf-8")
        self._emit_output(prompt)

    def _read_from_master(self) -> None:
        while not self._stop_event.is_set():
            try:
                chunk = os.read(self._master_fd, 1024) if self._master_fd is not None else b""
            except OSError:
                break
            if not chunk:
                break
            self._emit_output(chunk)

        self.on_status(f"客户端 {self.client_id} 的 shell 会话已结束。")

    def _write_windows(self, data: bytes) -> None:
        if data == b"\x1b[A":  # Up arrow
            if self._history and self._history_idx > 0:
                # Clear current input
                backspaces = b"\x08 \x08" * len(self._command_buffer)
                self._emit_output(backspaces)
                self._history_idx -= 1
                cmd = self._history[self._history_idx]
                self._command_buffer = bytearray(cmd.encode("utf-8"))
                self._emit_output(cmd.encode("utf-8"))
            return
            
        if data == b"\x1b[B":  # Down arrow
            if self._history and self._history_idx < len(self._history):
                # Clear current input
                backspaces = b"\x08 \x08" * len(self._command_buffer)
                self._emit_output(backspaces)
                self._history_idx += 1
                if self._history_idx < len(self._history):
                    cmd = self._history[self._history_idx]
                    self._command_buffer = bytearray(cmd.encode("utf-8"))
                    self._emit_output(cmd.encode("utf-8"))
                else:
                    self._command_buffer.clear()
            return

        new_data = bytearray()
        for byte in data:
            if byte in (8, 127):
                if self._command_buffer:
                    self._command_buffer.pop()
                    self._emit_output(b"\x08 \x08")
            elif byte == 27:  # ESC
                new_data.append(byte)
            else:
                new_data.append(byte)
        
        data = bytes(new_data)
        
        if b"\n" in data or b"\r" in data:
            parts = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n", 1)
            self._command_buffer.extend(parts[0])
            
            command = self._command_buffer.decode("utf-8", errors="ignore").strip()
            self._command_buffer.clear()
            
            self._emit_output(b"\r\n")
            if command:
                if not self._history or self._history[-1] != command:
                    self._history.append(command)
                self._history_idx = len(self._history)
                self._run_windows_command(command)
            else:
                self._send_windows_prompt()
                
            if len(parts) > 1 and parts[1]:
                self._command_buffer.extend(parts[1])
                self._emit_output(parts[1])
        else:
            self._command_buffer.extend(data)
            self._emit_output(data)

    def _run_windows_command(self, command: str) -> None:
        if self._stop_event.is_set():
            return
        if self.process is not None and self.process.poll() is None:
            self._emit_output(b"\r\n[uterm] A command is already running. Use Ctrl+C before starting another.\r\n")
            return

        self._handle_windows_cd(command)
        if command.strip().lower().startswith("cd"):
            self._send_windows_prompt()
            return

        def worker() -> None:
            import ctypes
            
            # Use CREATE_NEW_PROCESS_GROUP to prevent Ctrl+C from killing the server.
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            child = subprocess.Popen(
                command,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
                cwd=self._cwd,
                bufsize=0,
            )
            with self._windows_child_lock:
                self.process = child

            assert child.stdout is not None
            while not self._stop_event.is_set():
                chunk = child.stdout.read(1024)
                if not chunk:
                    break
                try:
                    text = chunk.decode("mbcs")
                    chunk = text.encode("utf-8")
                except Exception:
                    pass
                self._emit_output(chunk)

            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.terminate()
                child.wait(timeout=5)
            with self._windows_child_lock:
                if self.process is child:
                    self.process = None
            self._send_windows_prompt()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        self._reader_threads.append(thread)

    def _handle_windows_cd(self, command: str) -> None:
        raw = command.strip()
        if not raw:
            return
        lower = raw.lower()
        if lower == "cd":
            self._emit_output(self._cwd.encode("utf-8", errors="ignore") + b"\r\n")
            return
        if not lower.startswith("cd"):
            return

        parts = raw.split()
        if len(parts) < 2:
            return

        target = " ".join(parts[1:])
        if target.startswith("/d "):
            target = target[3:].strip()

        target = target.strip().strip('"')
        if not target:
            return

        new_path = target
        if not os.path.isabs(new_path):
            new_path = os.path.join(self._cwd, new_path)

        new_path = os.path.normpath(new_path)
        if os.path.isdir(new_path):
            self._cwd = new_path
        else:
            self.on_output(b"[uterm] cd: path not found\r\n")

    def _send_windows_interrupt(self) -> None:
        if self.process is None:
            return
        
        import ctypes
        
        kernel32 = ctypes.windll.kernel32
        
        try:
            # When a process is created with CREATE_NEW_PROCESS_GROUP, it ignores CTRL_C_EVENT.
            # We MUST send CTRL_BREAK_EVENT to properly interrupt it without killing the server.
            # To get ping to exit rather than just print stats, we can send CTRL_BREAK_EVENT,
            # wait a tiny bit for it to flush the stats, and then force kill it.
            kernel32.GenerateConsoleCtrlEvent(1, self.process.pid) # 1 is CTRL_BREAK_EVENT
            
            # Wait for up to 1 second for ping to gracefully finish printing its stats and exit
            try:
                self.process.wait(timeout=1.0)
                return
            except subprocess.TimeoutExpired:
                pass
        except Exception:
            pass

        # Fallback to forceful termination after letting it print stats
        self.on_output(b"^C\r\n")
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            )
        except OSError:
            pass

        self._terminate_windows_child()

    def _terminate_windows_child(self) -> None:
        if self.process is None:
            return
        try:
            self.process.terminate()
        except OSError:
            pass
