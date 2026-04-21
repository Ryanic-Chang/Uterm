# Uterm 💻

[English Version](README_EN.md)

*一个在不可靠的 UDP 之上构建的现代化可靠远程终端。*

[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)]()
[![Transport](https://img.shields.io/badge/transport-UDP-0ea5e9.svg)]()
[![Reliability](https://img.shields.io/badge/reliability-Stop--and--Wait%20ARQ-f97316.svg)]()
[![GUI](https://img.shields.io/badge/gui-CustomTkinter-22c55e.svg)]()

---

Uterm 是一个基于 Python 编写的开源远程终端系统，专为“基于 UDP 的远程终端”实验设计。它实现了自定义的应用层协议、停等（Stop-and-Wait）ARQ 可靠传输、多客户端隔离、心跳保活检测，并提供了一个能够实时渲染 ANSI 终端更新的精美桌面图形界面。

该项目旨在满足实验指导书中的全部基础验收标准，同时涵盖了多项进阶与拔高目标：

- 📦 **自定义固定头部协议**：包含魔数、报文类型、序列号、数据长度和客户端 ID
- 🛡️ **可靠传输**：在 UDP 之上实现超时重传、序列号去重和 ACK 确认机制
- 👥 **多客户端并发**：基于客户端 ID 的独立 Shell 会话隔离
- 💓 **心跳检测**：5 秒心跳机制及服务端离线清理
- ⚡ **实时输出流**：支持像 `ping` 这样的长时间运行命令的实时回显
- ⌨️ **控制字符支持**：正确处理 `Ctrl+C`、退格、Tab、换行和方向键
- 🎨 **现代化 GUI**：具备 ANSI 过滤与终端虚拟渲染能力
- 📏 **窗口大小同步**：支持 PTY 伪终端的尺寸动态同步
- 🖥️ **全屏交互程序**：在 POSIX PTY 模式下完美支持 `top`、`vim` 等交互式命令

### 📖 项目简介

Uterm 由两个协同工作的组件构成：

- `uterm-server`：UDP 服务端，为每个连接的客户端 ID 维护一个独立的远程 Shell 会话。
- `uterm-gui`：桌面客户端，拥有现代化的 GUI、连接控制、状态日志、快速命令面板以及基于 VT 的终端视图。

服务端在 Linux 或 macOS 上运行效果最佳，这些系统原生支持 PTY（伪终端），从而实现高级终端交互功能。项目中也包含了 Windows 服务端兼容模式（支持基础命令执行与实时流式输出），但若需运行 `top` 或 `vim` 等纯 PTY 场景，仍需部署在 POSIX 服务器上。

### ✨ 功能特性

#### 📡 协议层
- 采用实验指导书要求的固定头部格式
- 通过魔数与数据长度校验严格过滤非法报文
- 明确的报文类型：`0x01` 命令输入，`0x02` 命令输出，`0x03` ACK 确认，`0x04` 心跳包
- 使用 32 位客户端 ID 实现会话作用域隔离

#### 🛡️ 可靠性
- 在应用层实现停等 (Stop-and-Wait) ARQ
- 为所有非 ACK 报文提供 ACK 确认机制与超时自动重传
- 基于序列号的重复包检测与丢弃
- 设定安全的 UDP 载荷上限，避免 IP 层分片

#### 💻 终端体验
- 服务端至 GUI 的实时输出流式传输
- 通过 `pyte` 库处理 ANSI 转义序列，避免控制字符乱码
- 完善的按键支持：`Enter`, `Backspace`, `Tab`, `Ctrl+C`, 方向键，以及 `Home`, `End`, `Delete`, `PageUp`, `PageDown`
- 客户端向服务端实时汇报终端窗口大小变更

#### ⚙️ 运维与健壮性
- 多客户端并发互不干扰
- 客户端每 5 秒发送一次心跳包
- 服务端离线检测与过期会话清理
- 优雅处理网络中断与不可达的对端节点

### 🏗️ 系统架构

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

#### 🧩 模块说明
- `src/uterm/protocol.py`: 报文格式、封包解包与校验
- `src/uterm/transport.py`: 停等 ARQ 通道与 ACK 追踪
- `src/uterm/session.py`: POSIX PTY 会话与 Windows 兼容执行模式
- `src/uterm/server.py`: UDP 服务端、客户端注册表、心跳清理及输出转发
- `src/uterm/client.py`: 异步客户端传输运行时
- `src/uterm/terminal.py`: 基于 `pyte` 的 ANSI/VT 终端渲染缓冲区
- `src/uterm/app.py`: 现代化图形用户界面应用

### ✅ 验收标准覆盖

| 基本要求 | Uterm 完成情况 |
| --- | --- |
| UDP 客户端/服务端基础通信 | 🟢 已实现 |
| 自定义协议封包/解包 | 🟢 已实现 |
| 魔数/类型/序列号/ID/长度校验 | 🟢 已实现 |
| 停等 (Stop-and-wait) ARQ | 🟢 已实现 |
| ACK 确认、超时重传、序列号去重 | 🟢 已实现 |
| 非交互式命令执行 (ls/pwd 等) | 🟢 已实现 |
| `\n`, `\r`, `\b` 等控制字符处理 | 🟢 已实现 |
| 多客户端支持与会话隔离 | 🟢 已实现 |
| 5 秒心跳检测与离线处理 | 🟢 已实现 |
| 基础异常处理 (防崩溃/断网重传) | 🟢 已实现 |
| 实时命令输出 (ping 持续输出) | 🟢 已实现 |
| `Ctrl+C` 中断服务端命令 | 🟢 已实现 |
| ANSI 转义序列过滤/渲染避免乱码 | 🟢 已通过终端虚拟渲染实现 |
| 伪终端 (PTY) 支持 (top/vim) | 🟢 已在 POSIX 服务端实现 |
| 终端窗口大小动态同步 | 🟢 已在 POSIX 服务端实现 |

### 📦 依赖清单

**运行依赖：**
- `customtkinter >= 5.2.2`
- `pyte >= 0.8.2`

**开发与测试依赖：**
- `pytest >= 9.0.0`

**环境要求：**
- `Python 3.10+`

### 🛠️ 安装指南

#### 1. 克隆仓库

```bash
git clone <your-fork-or-repo-url>
cd Uterm
```

#### 2. 创建虚拟环境

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
*(注：MSYS2 / MinGW 环境可能将可执行文件放在 `.venv/bin` 下)*

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### 3. 安装 Uterm

```bash
python -m pip install -e .[dev]
```

### 🚀 使用说明

#### 启动服务端

```bash
uterm-server --host 0.0.0.0 --port 9527
```

常用选项：
- `--heartbeat-timeout 15`：设置心跳超时时间
- `--log-level DEBUG`：设置日志输出级别

#### 启动 GUI 客户端

```bash
uterm-gui
```

**操作步骤：**
1. 输入服务端的 IP、端口，以及一个独一无二的**客户端 ID**。
2. 点击 **连接**。
3. 在右侧的终端面板中直接输入命令，或点击左侧的快速命令按钮。
4. 使用 `Ctrl+C` 可中断正在运行的长耗时命令。

### 💡 使用示例

#### 基础命令
```text
pwd
ls
whoami
ip addr
```

#### 实时输出
```text
ping 127.0.0.1
```
*(可使用 `Ctrl+C` 中断)*

#### 全屏交互应用
在 Linux 或 macOS 上运行服务端后，即可使用：
```text
top
vim README.md
```

### 🧪 自动化验证

本项目提供了双层验证机制：
- **单元测试**：协议序列化、载荷解析、终端渲染逻辑。
- **端到端测试**：本地启动 UDP 服务端，连接客户端并执行命令，验证输出流式传输的正确性。

运行完整的验证套件：
```bash
python -m pytest
```

### 🤝 贡献指南

欢迎提交 Pull Request！推荐的初次贡献方向包括：
- 增强协议层的异常路径测试
- 改进 Linux PTY 交互行为
- 丰富 GUI 的人体工学设计与终端 UX
- 针对大块输出流的性能优化
- 打包与发布自动化

**推荐工作流：**
1. Fork 仓库并创建特性分支。
2. 安装 `.[dev]` 开发依赖。
3. 为您的代码更改添加对应的测试。
4. 运行 `python -m pytest` 确保测试通过。
5. 提交 PR，并简明扼要地描述更改行为及验证过程。

### 📄 许可证

本项目基于 MIT 许可证发布。详情请参阅 [LICENSE](LICENSE) 文件。

### 🕒 版本变更记录

| 版本 | 日期 | 备注 |
| --- | --- | --- |
| `0.1.0` | `2026-04-20` | 首个开源版本：实现 UDP 协议、停等 ARQ、多客户端支持、心跳检测、实时输出、现代化 GUI、POSIX PTY 支持及自动化验证套件 |
