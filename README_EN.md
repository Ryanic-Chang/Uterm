# Uterm 💻

[中文版本](README.md)

*A modern remote terminal built on top of unreliable UDP, made reliable in the application layer.*

[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)]()
[![Transport](https://img.shields.io/badge/transport-UDP-0ea5e9.svg)]()
[![Reliability](https://img.shields.io/badge/reliability-Stop--and--Wait%20ARQ-f97316.svg)]()
[![GUI](https://img.shields.io/badge/gui-CustomTkinter-22c55e.svg)]()

---

Uterm is an open-source remote terminal system written in Python for the "UDP-based remote terminal" experiment. It implements a custom application-layer protocol, stop-and-wait ARQ reliability, multi-client isolation, heartbeat liveness detection, and a polished desktop GUI capable of rendering ANSI terminal updates in real time.

The project is designed to satisfy the full baseline acceptance criteria from the lab guide while also covering several advanced goals:

- 📦 **Fixed binary header protocol** with magic number, packet type, sequence number, payload length, and client ID
- 🛡️ **Reliable transmission** on top of UDP with timeout, retransmission, duplicate suppression, and ACK confirmation
- 👥 **Concurrent multi-client sessions** with per-client shell isolation
- 💓 **5-second heartbeat** and offline cleanup
- ⚡ **Real-time command streaming** for long-running commands such as `ping`
- ⌨️ **Control character forwarding** (`Ctrl+C`, backspace, tab, newline, and cursor-keys)
- 🎨 **ANSI-aware terminal rendering** in the GUI
- 📏 **Terminal size synchronization** for PTY-backed servers
- 🖥️ **POSIX PTY mode** for interactive full-screen programs such as `top` and `vim`

### 📖 Project Overview

Uterm ships as two cooperating components:

- `uterm-server`: a UDP server that hosts one remote shell session per client ID
- `uterm-gui`: a desktop client with a modern GUI, connection controls, logs, quick commands, and a VT-style terminal surface

The server runs best on Linux or macOS, where PTY support enables advanced terminal behavior. A Windows server fallback is included for development and validation; it supports baseline command execution and real-time output, but PTY-only scenarios such as `top` and `vim` require a POSIX server.

### ✨ Feature Set

#### 📡 Protocol
- Fixed header format using the required fields from the lab guide
- Invalid packet rejection by magic number and payload-length validation
- Explicit packet typing: `0x01` input, `0x02` output, `0x03` ACK, `0x04` heartbeat
- Client-scoped sessions using a 32-bit client ID

#### 🛡️ Reliability
- Stop-and-wait ARQ implemented in the application layer
- ACK-based confirmation for all non-ACK packets
- Retransmission on timeout and duplicate detection by sequence number
- Safe upper bound on UDP payload size to avoid fragmentation
- Adaptive retransmission: ACK waiting uses jitter + exponential backoff to reduce timeout storms
- Background sending: GUI input never blocks; bounded send queue prevents lockups under loss/congestion

#### 💻 Terminal Experience
- Real-time output streaming from the server to the GUI
- ANSI escape handling through `pyte`, avoiding raw control-sequence garbage
- Support for `Enter`, `Backspace`, `Tab`, `Ctrl+C`, arrow keys, and more
- Terminal resize reporting from client to server
- MobaXterm-like input feel: type directly in the terminal area with server-side echo and proper control handling

#### ⚙️ Operations
- Multi-client concurrency without session crossover
- Heartbeat every 5 seconds with offline detection and server-side cleanup
- Graceful handling of unreachable peers and broken transport
- Output decoupling: server streams output via a dedicated queue/thread to avoid blocking the receive loop

### 🏗️ System Architecture

```text
┌──────────────────────────────────────────────────────────────────┐
│                          Uterm GUI Client                        │
│                                                                  │
│  CustomTkinter UI  →  Input Mapper  →  Reliable UDP Sender       │
│         ↑                         ↓                              │
│  pyte VT Renderer  ←  Output Stream  ←  UDP Receiver             │
└──────────────────────────────────────────────────────────────────┘
                                │
                                │ UDP + Custom Header + ACK
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                           Uterm Server                           │
│                                                                  │
│  UDP Listener  →  Client Runtime Registry  →  Reliable Channel   │
│                                │                                 │
│                                ├─ Client A → Shell / PTY         │
│                                ├─ Client B → Shell / PTY         │
│                                └─ Client N → Shell / PTY         │
└──────────────────────────────────────────────────────────────────┘
```

#### 🧩 Module Map
- `src/uterm/protocol.py`: wire format, packet validation, payload helpers
- `src/uterm/transport.py`: stop-and-wait ARQ channel and ACK tracking
- `src/uterm/session.py`: POSIX PTY session and Windows compatibility execution mode
- `src/uterm/server.py`: UDP server, client registry, heartbeat cleanup, output forwarding
- `src/uterm/client.py`: non-blocking client transport runtime
- `src/uterm/terminal.py`: ANSI/VT terminal buffer backed by `pyte`
- `src/uterm/app.py`: modern GUI application

### ✅ Acceptance Coverage

| Basic requirement | Uterm status |
| --- | --- |
| UDP client/server communication | 🟢 Implemented |
| Custom protocol pack/unpack | 🟢 Implemented |
| Magic/type/seq/client ID/length validation | 🟢 Implemented |
| Stop-and-wait ARQ | 🟢 Implemented |
| ACK, timeout, retransmission, dedupe | 🟢 Implemented |
| Non-interactive command execution | 🟢 Implemented |
| `\n`, `\r`, `\b` handling | 🟢 Implemented |
| Multi-client separation | 🟢 Implemented |
| Heartbeat and offline detection | 🟢 Implemented |
| Basic error handling | 🟢 Implemented |
| Real-time command output | 🟢 Implemented |
| `Ctrl+C` interrupt | 🟢 Implemented |
| ANSI filtering/rendering | 🟢 Implemented via terminal emulation |
| PTY-backed full-screen apps | 🟢 Implemented on POSIX server |
| Terminal resize sync | 🟢 Implemented on POSIX server |

### 📦 Dependency List

**Runtime dependencies:**
- `customtkinter >= 5.2.2`
- `pyte >= 0.8.2`

**Development dependencies:**
- `pytest >= 9.0.0`

**Python requirement:**
- `Python 3.10+`

### 🛠️ Installation

#### 1. Clone the repository
```bash
git clone <your-fork-or-repo-url>
cd Uterm
```

#### 2. Create a virtual environment
Windows PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
*(Note: For environments like MSYS2 / MinGW, executables might be located in `.venv/bin` instead of `Scripts`. In that case, use `.\.venv\bin\activate` or specify the python path directly, e.g. `.\.venv\bin\python.exe -m pip install -e .[dev]`)*

Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### 3. Install Uterm
After activating the virtual environment, run:
```bash
pip install -e .[dev]
```
*(Note: If you encounter issues activating the environment, you can use the python executable inside the environment directly. For example: `.\.venv\Scripts\python.exe -m pip install -e .[dev]` on Windows, or `.venv/bin/python -m pip install -e .[dev]` on Linux)*

### 🚀 Usage

#### Start the server
With the virtual environment activated, run:
```bash
uterm-server --host 0.0.0.0 --port 9527
```
*(Note: If the environment is not activated, you can run the executable directly, e.g. `.\.venv\Scripts\uterm-server.exe` or `.\.venv\bin\uterm-server`)*

#### Start the GUI client
With the virtual environment activated, run:
```bash
uterm-gui
```
*(Note: Similarly, if the command is not found, use the direct path, e.g. `.\.venv\Scripts\uterm-gui.exe` or `.\.venv\bin\uterm-gui`)*
Then enter the server IP, port, and a unique client ID, and click **连接** (Connect).

### 🌐 Remote Server Deployment & Port Forwarding

If you deploy the server on a cloud provider (e.g., AWS, Azure, Aliyun), you must **open the UDP port** (default `9527`), otherwise the client will timeout connecting.

1. **Cloud Security Group Configuration**
   Go to your cloud provider's console -> Security Groups / Firewall -> Add an **Inbound** rule:
   - Protocol: `UDP`
   - Port Range: `9527`
   - Source: `0.0.0.0/0` (or your specific IP)

2. **OS Firewall Configuration**
   - **Ubuntu / Debian (ufw)**:
     ```bash
     sudo ufw allow 9527/udp
     ```
   - **CentOS / RHEL (firewalld)**:
     ```bash
     sudo firewall-cmd --zone=public --add-port=9527/udp --permanent
     sudo firewall-cmd --reload
     ```
   - **iptables**:
     ```bash
     sudo iptables -A INPUT -p udp --dport 9527 -j ACCEPT
     ```

### 🧭 Host Info Panel

The GUI renders a host info panel on the left side of the terminal area. The server periodically reports:

- hostname / username / current working directory / timestamp

### 🧩 Management API (OpenAPI)

Install the API extra and start the management API (Swagger UI + OpenAPI 3.0):

```bash
pip install -e .[api]
uterm-api --host 0.0.0.0 --port 8080 --udp-host 0.0.0.0 --udp-port 9527
```

- Swagger UI: `http://<server-ip>:8080/docs`
- OpenAPI: `http://<server-ip>:8080/openapi.json`

### 🐳 Docker Deployment

See [DEPLOYMENT.md](file:///d:/Ryan/Desktop/Uterm/docs/DEPLOYMENT.md).

### 💡 Usage Examples

#### Basic commands
```text
pwd
ls
whoami
ip addr
```

#### Real-time output
```text
ping 127.0.0.1
```
*(Stop it with `Ctrl+C`)*

#### Full-screen applications
Run the server on Linux or macOS, then use:
```text
top
vim README.md
```

### 🧪 Validation

Run the full verification suite (unit & end-to-end tests) with:
```bash
python -m pytest
```

### 🤝 Contribution Guide

Contributions are welcome! Recommended workflow:
1. Fork the repository and create a feature branch.
2. Install `.[dev]` dependencies.
3. Add or update focused tests for your change.
4. Run `python -m pytest`.
5. Open a pull request with a concise explanation.

### 📄 License

This project is released under the MIT License. See [LICENSE](LICENSE).

### 🕒 Version History

| Version | Date | Notes |
| --- | --- | --- |
| `0.1.0` | `2026-04-20` | Initial open-source release with UDP protocol, stop-and-wait ARQ, multi-client support, heartbeat, real-time streaming, modern GUI, POSIX PTY support, and automated validation |
