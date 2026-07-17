# NebulaShare / 星云互传

局域网文件互传 + 网络测速服务器，部署于 Raspberry Pi 4B。

## 背景

用户运行在 Raspberry Pi 4B（ARM 架构，资源受限），需要一套**无需任何外部依赖、开箱即用**的局域网文件共享方案。核心诉求：

- 同一 WiFi 下的手机/PC 通过浏览器即可上传/下载文件
- 不设置任何认证（信任局域网环境）
- 文件 7 天自动过期，总量不超过 10G
- 支持内网/外网测速
- 前端要有科技感、宇宙粒子动效、毛玻璃 UI
- 24h 持续运行，断电重启后自动恢复
- 开机自检

## 技术选型

| 层级 | 技术 | 理由 |
|------|------|------|
| 后端 | Python 3 + Flask | 轻量、树莓派原生支持、单文件即可跑 |
| 前端 | 纯 HTML/CSS/JS（全部内联） | 零外部 CDN、无网络也能打开 |
| 测速 | speedtest-cli + 自制 HTTP 流式测速 | 外网用官方 CLI，内网用前后端配合 |
| 部署 | systemd system service | 开机自启，崩溃自动重启 |
| 环境 | Python venv | 隔离依赖，不污染系统 Python |

## 目录结构

```
NebulaShare/
├── app.py              # 主服务（后端 API + 前端页面）
├── venv/               # Python 虚拟环境
├── uploads/            # 文件存储目录
├── start.sh            # 手动启动脚本
├── nebulashare.service # systemd 服务文件
├── requirements.txt    # Python 依赖
└── README.md           # 本文档
```

## 功能清单

### 文件互传
- 拖拽/点击上传，支持多文件
- 文件列表展示（大小、上传时间、剩余有效期）
- 下载（直接下载）/ 删除
- 自动清理：超过 7 天删除；超过 10G 按时间顺序删最老的

### 网络测速
- **内网测速**：测量"设备 ↔ 树莓派"之间的上传/下载速度和延迟
  - 下载：后端流式生成 30MB 随机数据，前端计时
  - 上传：前端生成 10MB 随机数据上传，后端直接丢弃不计存储
  - 数据不落盘，零磁盘占用
- **外网测速**：调用 speedtest-cli（speedtest.net），测量"路由器 ↔ 互联网"
  - 自动指定 `--source` 走真实网卡（eth0/wlan0），绕过 mihomo TUN 虚拟接口
  - Ping / 下载 / 上传 三项指标

### 前端特效
- Canvas 宇宙粒子背景动画（80 个粒子 + 连线 + 鼠标交互）
- CSS 毛玻璃卡片（backdrop-filter blur + 发光边框）
- 浮动光晕（cyan / purple / pink 三色渐变）
- 响应式布局（PC 双栏 / 手机单栏）
- 无外部资源，所有 CSS/JS 内联在 app.py 中

### 运维
- 启动自检：目录可写性、磁盘空间、端口占用
- systemd system service：开机自启、崩溃自动重启、24h 持续运行
- 服务管理命令：
  ```bash
  sudo systemctl status nebulashare
  sudo systemctl restart nebulashare
  sudo systemctl stop nebulashare
  ```

## 过程记录

1. **基础服务搭建**：Flask 单文件后端，内联前端，实现上传/下载/列表/删除 API
2. **自动清理**：后台线程每 10 分钟检查，按时间和总量双维度清理
3. **前端升级**：加入宇宙粒子 Canvas 动画、毛玻璃特效、三色浮动光晕
4. **测速功能**：
   - 内网：流式随机数据测速，数据不落盘
   - 外网：集成 speedtest-cli，解决 mihomo TUN 接口干扰问题
5. **IP 过滤**：排除 TUN/虚拟网卡，页面只显示真实局域网 IP
6. **部署固化**：systemd system service，开机自启

## 运行结果

- **访问地址**：`http://192.168.50.34:8080`
- **外网测速参考值**（杭州电信 500M）：
  - Ping: ~3-5ms
  - 下载: ~550-600 Mbps
  - 上传: ~30-50 Mbps
- **资源占用**：树莓派 4B 轻松承载，内存占用 < 50MB
- **兼容性**：Chrome/Safari/Firefox 全支持，iOS/Android 均可扫码访问

## 启动方式

```bash
# 手动启动
cd /home/aw/NebulaShare && ./start.sh

# 或 systemd（推荐）
sudo systemctl restart nebulashare
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NEBULA_DIR` | `/home/aw/NebulaShare/uploads` | 文件存储目录 |
| `NEBULA_PORT` | `8080` | 服务端口 |

## 注意事项

- 树莓派网口为千兆，内网有线传输上限约 800-900Mbps
- 内网 WiFi 速度受手机/路由器 5GHz 信号质量影响
- 外网测速时若 mihomo TUN 活跃，会自动绕过虚拟接口走真实网卡
- 所有测速数据均在内存中流转，**不占用磁盘空间**
