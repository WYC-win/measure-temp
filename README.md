# 🌡️ 室内温度监测与云端可视化系统

> 面向 **STC89C52** 的室内温度采集、实时绘图与云端展示工程。

这是一个面向单片机温度采集场景的完整工程：
- 🧭 本地实时采集串口温度数据
- 💾 自动按日期落盘为 CSV
- 📈 本地实时曲线监测
- 🌐 云端网页展示温度曲线与统计信息
- 🔄 本地到云端的持续数据同步

---

## 1. 功能概览

### 本地监测（Local Monitor）
- 🔌 自动或指定串口读取（默认支持 CH340/USB 串口识别）
- 🧾 正则解析温度报文（如 `Temp=24.3125 C`）
- 📁 按北京时间自然日保存到 `temperature_YYYY-MM-DD.csv`
- 📊 Matplotlib 实时仪表板显示：
  - 当前温度
  - 最小/最大/平均值
  - 最近 10 分钟曲线
  - 串口连接状态

### 云端展示（Web Dashboard）
- 🛰️ Python 轻量 HTTP 服务（标准库实现）
- 🖼️ 前端 Chart.js 实时轮询接口绘图
- ⏱️ 支持窗口切换：最近 10 分钟 / 最近 1 小时 / 当天全部
- 🏠 页面内展示监测点位说明：`16楼321室内温度`

### 数据同步（CSV Sync）
- 🔁 独立同步进程，不修改本地监测程序
- ☁️ 持续检测本地 `temperature_*.csv` 变更并上传服务器
- ⏳ 支持定时间隔同步（默认 2 秒）

### 硬件平台
- 🧩 单片机：**STC89C52**
- 🌡️ 温度传感器：DS18B20
- 🔗 通讯链路：USB 转串口（当前推荐直连电脑，避免 USB 隔离器引入不稳定）
- 🪟 串口参数：COM7 / 9600（以你的实际接线为准）

---

## 2. 工程结构

```text
measure temp/
├─ local_monitor/
│  ├─ monitor.py                 # 本地实时监测主程序
│  └─ start_monitor.ps1          # 本地监测启动脚本
├─ web_host/
│  ├─ web_dashboard.py           # 云端网页服务（可本地运行测试）
│  ├─ start_web_dashboard.ps1    # 网页服务启动脚本
│  ├─ sync_csv_to_server.py      # CSV 持续同步脚本
│  └─ start_csv_sync.ps1         # CSV 同步启动脚本
├─ temperature_YYYY-MM-DD.csv    # 每日温度数据文件
├─ temperature_data.csv          # 历史兼容数据文件
└─ temperature_raw_data.csv      # 历史兼容原始数据文件
```

---

## 3. 运行环境

- 🪟 操作系统：Windows（本地）
- 🐍 Python：3.14（建议使用 `.venv`）
- 🔌 串口芯片：CH340（或兼容 USB 串口）

### 关键依赖
- `pyserial`
- `matplotlib`
- `numpy`
- `paramiko`

如果你需要重新安装依赖（在项目目录执行）：

```powershell
.\.venv\Scripts\python.exe -m pip install pyserial matplotlib numpy paramiko
```

---

## 4. 快速开始

### 4.1 仅本地监测

在 PowerShell 中执行：

```powershell
cd "c:\Users\WYC\Desktop\My code\measure temp"
powershell -ExecutionPolicy Bypass -File .\local_monitor\start_monitor.ps1
```

启动成功后，你会看到：
- 监测窗口弹出
- 终端显示串口连接信息（例如 `Serial connected: COM7 @ 9600`）
- 当天 CSV 文件持续追加新数据

### 4.2 指定串口启动（例如 COM7）

```powershell
cd "c:\Users\WYC\Desktop\My code\measure temp"
.\.venv\Scripts\python.exe .\local_monitor\monitor.py --port COM7 --baud 9600
```

---

## 5. 云端部署与运行方式

> 你的服务器已部署完成，本节用于后续维护与重启。

### 5.1 云端服务组件

- 🗂️ 网页应用目录：`/opt/temperature-web`
- ⚙️ systemd 服务：`temperature-web.service`
- 🌍 nginx 反向代理：`/etc/nginx/conf.d/temperature-web.conf`
- 🔗 公网地址：`http://39.105.108.171/`

### 5.2 本地启动数据同步

在新的 PowerShell 窗口执行：

```powershell
cd "c:\Users\WYC\Desktop\My code\measure temp"
powershell -ExecutionPolicy Bypass -File .\web_host\start_csv_sync.ps1
```

说明：
- 启动脚本会提示输入云服务器密码
- 使用 `.venv` Python 运行，避免 `paramiko` 缺失
- 同步进程运行时会输出 `Uploaded: ...` 或 `No changes`

---

## 6. 推荐运行流程

1. 启动本地监测：`start_monitor.ps1`
2. 启动数据同步：`start_csv_sync.ps1`
3. 浏览器打开云端页面：`http://39.105.108.171/`

这样可以实现：
- 本地实时采集 + 绘图
- 云端实时展示最新曲线

---

## 7. 常见问题（FAQ）

### Q1：为什么只启动本地监测，云端也在更新？
A：因为后台仍有 `sync_csv_to_server.py` 进程在运行。该同步进程会自动上传本地 CSV 变化。

### Q2：为什么程序运行几分钟后单片机停发？
A：常见原因是 USB 链路稳定性（例如低质量 USB 隔离器、供电不足、线材问题）。你当前案例中，改为单片机直连电脑后问题已消失。

### Q3：终端出现 `PermissionError: could not open COM7`？
A：通常是串口被其他程序占用。关闭重复监测进程后重试。

### Q4：网页有数据但刷新慢？
A：可调整同步脚本参数 `--interval`（默认 2 秒）。

---

## 8. 运维检查命令

### 本地检查同步进程

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'sync_csv_to_server.py' } |
  Select-Object ProcessId, Name, CommandLine | Format-List
```

### 云端检查服务状态（服务器上）

```bash
systemctl status temperature-web.service
systemctl status nginx
curl -s http://127.0.0.1:8000/api/data?window=86400
```

---

## 9. 安全建议

- 🔒 不要在命令行直接明文传 `--password`，优先使用 `start_csv_sync.ps1` 的交互输入方式。
- 👤 如需长期运行，建议使用独立低权限用户替代 root 上传数据。

---

## 10. 版本说明

当前版本已完成：
- ✅ 本地监测与绘图稳定运行
- ✅ 云端页面可公网访问
- ✅ 本地到云端自动同步
- ✅ 页面已加入点位标识文案：`16楼321室内温度`
- ✅ 硬件平台明确为 **STC89C52**

如果后续需要，我可以再为你补一版：
- 一键双启动脚本（同时启动监测 + 同步）
- 带截图的 README 文档版
- 自动开机启动方案（Windows 任务计划 + Linux systemd）
