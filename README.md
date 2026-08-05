# IP-Scanner

IP-Scanner 是一个跨平台局域网主机发现工具。首版提供：

- CIDR、单 IP、起止范围解析，目标地址惰性生成
- 有界 `asyncio` 工作池，不为大网段一次性创建任务
- TCP 探测与系统 Ping 探测
- 可停止的实时扫描、CSV/JSON 导出、SQLite 历史记录
- PySide6 桌面界面，以及无 GUI 依赖的命令行入口

> 请只扫描你拥有或已获授权的网络。大网段扫描可能触发防火墙、IDS 或网络限速。

## 快速开始

需要 Python 3.9 或更高版本。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[gui]'
ip-scanner-gui
```

不安装 GUI 也可直接运行：

```bash
PYTHONPATH=src python3 -m ip_scanner.cli 192.168.1.0/24 --method tcp --ports 80,443
```

系统 Ping 模式调用当前平台自带的 `ping` 程序，不要求 Python raw socket 权限：

```bash
PYTHONPATH=src python3 -m ip_scanner.cli 192.168.1.0/24 --method ping
```

## 测试

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## VS Code

项目已提供 `.vscode` 配置。使用 VS Code 打开本目录后：

1. 按 `F5`，选择“IP-Scanner：桌面版”启动 GUI。
2. 按 `Cmd+Shift+P`，运行“Tasks: Run Test Task”执行全部测试。
3. 如 VS Code 未自动识别解释器，选择 `.venv/bin/python`。

## 构建 macOS 应用

安装开发依赖后执行：

```bash
sh scripts/build_macos.sh
```

生成的应用位于 `build/IP-Scanner.app`。当前构建为本机 ARM64 架构，并使用临时签名；对外发布前还需要 Apple Developer ID 签名与公证。
