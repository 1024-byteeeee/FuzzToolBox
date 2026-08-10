# FuzzToolBox

FuzzToolBox 是面向 Windows 与 macOS 的桌面 IT 工具箱。内置 IP Scanner，提供：

- CIDR、单 IP、起止范围解析，目标地址惰性生成
- 有界 `asyncio` 工作池，不为大网段一次性创建任务
- TCP 探测与严格的系统 Ping 探测（只有目标 Echo Reply 才判定在线）
- DNS、mDNS、NetBIOS 分层主机名解析及本地网络 MAC 地址获取
- 可停止的实时扫描、异步设备信息补全、精确 IP 搜索与 CSV/JSON 导出
- PySide6 桌面界面，以及无 GUI 依赖的命令行入口

子网划分计算器支持 IPv4 与 IPv6 网络摘要、FLSM 等长划分、VLSM 可变长规划、
超大网段连续按需加载、IP 所属子网定位、复制和 CSV 导出。

> 请只扫描你拥有或已获授权的网络。大网段扫描可能触发防火墙、IDS 或网络限速。

## 快速开始

需要 Python 3.9 或更高版本。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[gui]'
fuzztoolbox-gui
```

不安装 GUI 也可直接运行：

```bash
PYTHONPATH=src python3 -m ip_scanner.cli 192.168.1.0/24 --method tcp --ports 80,443
```

系统 Ping 模式调用当前平台自带的 `ping` 程序，不要求 Python raw socket 权限：

```bash
PYTHONPATH=src python3 -m ip_scanner.cli 192.168.1.0/24 --method ping
```

## 结果判定与功能边界

- Ping 模式只有收到目标 IP 的有效 ICMP Echo Reply 才显示在线；ARP/MAC 不参与在线判定。
- TCP 模式只有指定端口完成真实 TCP 握手才显示在线，并使用控制端口检测透明代理或隧道劫持。
- 扫描结果会先实时显示，MAC 和主机名随后在原行补全，不阻塞在线/离线结果。
- MAC 地址通常只能在本地二层网络获得；跨路由网络无法可靠取得目标 MAC。
- 主机名按反向 DNS、局域网 mDNS、NetBIOS 的顺序查询。目标没有注册真实名称时保持为空。
- 手机休眠、Wi-Fi 漫游、设备防火墙或网络丢包可能造成真实的扫描结果变化。

## 测试

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## VS Code

项目已提供 `.vscode` 配置。使用 VS Code 打开本目录后：

1. 按 `F5`，选择“FuzzToolBox：桌面版”启动 GUI。
2. 按 `Cmd+Shift+P`，运行“Tasks: Run Test Task”执行全部测试。
3. 如 VS Code 未自动识别解释器，选择 `.venv/bin/python`。

## 构建原生应用

PyInstaller 不支持跨系统编译，需要在目标操作系统上分别执行：

```bash
# macOS
sh scripts/build_macos.sh

# Windows PowerShell
.\scripts\build_windows.ps1
```

无需目标电脑安装 Python。PyInstaller 会将 Python 解释器、PySide6 和项目依赖嵌入发布产物。Windows 使用 `onedir` 快速启动结构并通过单个 Inno Setup 安装包分发，安装后由桌面或开始菜单启动；macOS 提供带应用图标的 DMG，打开后将 `FuzzToolBox.app` 拖入 `Applications` 即可安装。正式分发 macOS 版本前仍建议使用 Apple Developer ID 签名与公证。

## GitHub Release

`.github/workflows/release-build.yml` 会在发布 Release 或推送版本标签时，分别在 Windows 和 macOS 原生 Runner 上执行测试、GUI 初始化检查和打包。两个系统全部成功后，工作流才会统一替换 Release 附件，避免混合不同提交的构建，并附带 `SHA256SUMS.txt` 校验文件。工作流也支持手动运行，手动运行时产物保存在 Workflow Artifacts 中。
