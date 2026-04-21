# 部署手册（生产环境）

## 1. 概览

Uterm 服务端基于 UDP（默认端口 `9527/udp`）。生产部署时需同时处理：

- 云安全组/网络 ACL 放行 UDP 端口
- 服务器 OS 防火墙放行 UDP 端口
- 进程守护与日志收集

本仓库提供 Docker 方案，默认同时启动：

- UDP 服务端：`9527/udp`
- 管理 API（OpenAPI 3.0 / Swagger UI）：`8080/tcp`

## 2. Docker 部署

### 2.1 使用 docker compose

```bash
docker compose up --build -d
```

端口：

- UDP：`9527/udp`
- HTTP：`8080/tcp`

访问 API：

- Health：`http://<server-ip>:8080/health`
- Swagger UI：`http://<server-ip>:8080/docs`
- OpenAPI JSON：`http://<server-ip>:8080/openapi.json`

### 2.2 单容器启动

```bash
docker build -t uterm:latest .
docker run --rm -p 9527:9527/udp -p 8080:8080 uterm:latest
```

## 3. 防火墙与端口开放

### 3.1 云安全组

入方向规则：

- 协议：UDP
- 端口：9527
- 源：建议限制为办公网/个人 IP 段；测试阶段可用 `0.0.0.0/0`

如需开放管理 API：

- 协议：TCP
- 端口：8080
- 源：强烈建议限制到内网或跳板机

### 3.2 Linux 防火墙

Ubuntu/Debian (ufw):

```bash
sudo ufw allow 9527/udp
sudo ufw allow 8080/tcp
```

CentOS/RHEL (firewalld):

```bash
sudo firewall-cmd --zone=public --add-port=9527/udp --permanent
sudo firewall-cmd --zone=public --add-port=8080/tcp --permanent
sudo firewall-cmd --reload
```

## 4. 运维建议

- 建议将 `client_id` 作为会话标识，断线重连需保持同一 `client_id`
- 将 `8080` 管理 API 置于内网，或加反向代理与访问控制
- 生产环境建议使用 Linux 服务端以获得 PTY 支持与最佳终端体验

