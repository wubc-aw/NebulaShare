# PC 控制台设计文档

## 目标
将现有 WOL 按钮升级为完整的 PC 控制台，支持：
1. 实时状态检测（ping 轮询）
2. WOL 远程唤醒
3. SSH 远程关机（Windows OpenSSH）

## 后端 API

### `GET /api/pc/status`
- 行为：`subprocess.run(["ping", "-c", "1", "-W", "2", PC_IP])`
- 返回：`{ok, online, ip, mac, rtt_ms|null}`

### `POST /api/pc/shutdown`
- 行为：`ssh -o ConnectTimeout=5 -o BatchMode=yes {user}@{ip} "shutdown /s /t 0"`
- 支持密码或密钥认证（优先密钥）
- 返回：`{ok}` 或 `{ok: false, error}`

### `POST /api/wol`（已有，增强）
- 行为不变，调用 `wakeonlan` 发送魔法包

## 环境变量配置
```
PC_IP=192.168.50.206
PC_MAC=34:5A:60:CE:E6:DB
PC_NAME=Windows PC
PC_SSH_USER=aw          # Windows 用户名
PC_SSH_KEY=             # 私钥路径，空则尝试密码（交互式输入）
```

## 前端 UI

将现有 `#secWol` 升级为完整的 PC 控制台卡片：

```
┌──────────────────────────────────────┐
│ 🖥  Windows PC                        │
│ 192.168.50.206  ·  34:5A:60:CE:E6:DB │
│                                      │
│  ● 在线 / ○ 离线                      │
│                                      │
│ [ 唤醒 PC ]        [ 关闭 PC ]        │
└──────────────────────────────────────┘
```

- 状态灯：在线绿色脉冲 / 离线红色
- 唤醒按钮：离线时可用，在线时禁用
- 关机按钮：在线时可用，离线时禁用
- 每 5 秒自动 ping 刷新
- 状态条折叠持久化（`localStorage`）

## Windows OpenSSH 配置引导（内嵌 UI）

在控制台卡片下方提供折叠的帮助面板，包含：

1. **启用 OpenSSH 服务**（PowerShell 管理员）：
   ```powershell
   Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
   Start-Service sshd
   Set-Service -Name sshd -StartupType 'Automatic'
   ```

2. **生成 SSH 密钥**（树莓派上执行）：
   ```bash
   ssh-keygen -t ed25519 -C "nebulashare"
   ssh-copy-id aw@192.168.50.206
   ```

## 错误处理

| 场景 | 行为 |
|------|------|
| ping 超时 | 标记 offline，不报错 |
| wakeonlan 未安装 | 返回 500，提示安装命令 |
| SSH 连接失败 | 返回具体错误（认证失败/超时/命令不存在） |
| SSH 密钥未配置 | 提示用户参考配置引导 |
