# FuzzToolBox Code Wiki

> 版本：v2.1.0  
> 最后更新：2026-08-13  
> 本文件是 FuzzToolBox 项目的完整技术文档，涵盖架构设计、模块职责、关键类与函数说明、依赖关系及项目运行方式。

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术栈与依赖](#2-技术栈与依赖)
3. [项目目录结构](#3-项目目录结构)
4. [整体架构设计](#4-整体架构设计)
5. [核心模块详解](#5-核心模块详解)
6. [UI 层详解](#6-ui-层详解)
7. [工具模块详解](#7-工具模块详解)
8. [数据模型与类型定义](#8-数据模型与类型定义)
9. [主题系统](#9-主题系统)
10. [构建与部署](#10-构建与部署)
11. [测试体系](#11-测试体系)
12. [开发指南](#12-开发指南)
13. [附录](#13-附录)

---

## 1. 项目概述

**FuzzToolBox** 是一款面向 Windows 与 macOS 的桌面 IT 工具箱，使用 Python + PySide6（Qt for Python）构建。产品定位为 IT 专业人员的一站式桌面工具集，核心亮点是功能完善的 **IP Scanner**（局域网扫描器），并辅以 15+ 个开发与网络工具。

### 主要特性

- **IP Scanner（旗舰功能）**：基于 `asyncio` 的有界并发扫描引擎，支持 TCP 端口探测和系统 Ping 探测，内置 DNS/mDNS/NetBIOS 分层主机名解析、MAC 地址获取、CSV/JSON 导出、SQLite 历史存储
- **跨平台 GUI**：统一的 PySide6 界面，支持 macOS（.app）和 Windows（.exe + Inno Setup 安装包）原生打包
- **双入口**：无 GUI 依赖的命令行入口 `fuzztoolbox` 和桌面 GUI 入口 `fuzztoolbox-gui`
- **主题系统**：支持亮色/深色/跟随系统三种模式，QSS 样式表 + 语义化颜色变量
- **模块化设计**：每个工具遵循"核心逻辑 + UI 页面"分离模式，便于测试和扩展

---

## 2. 技术栈与依赖

### 2.1 运行时依赖

| 依赖 | 版本约束 | 用途 |
|------|---------|------|
| `psutil` | `>=5.9, <8` | 系统网络接口枚举、IP/MAC/网关检测 |
| `getmac` | `>=0.9, <1` | 跨平台 MAC 地址查询 |
| `segno` | `>=1.6, <2` | 纯 Python QR 码生成 |

### 2.2 GUI 依赖（可选）

| 依赖 | 版本约束 | 用途 |
|------|---------|------|
| `PySide6` | `>=6.5, <7` | Qt for Python，桌面 UI 框架 |

### 2.3 开发依赖

| 依赖 | 版本约束 | 用途 |
|------|---------|------|
| `pytest` | `>=7` | 单元测试框架 |
| `ruff` | `>=0.5` | 代码格式化与 Lint |
| `pyinstaller` | `>=6, <7` | 原生应用打包 |

### 2.4 Python 标准库关键模块

| 模块 | 用途 |
|------|------|
| `asyncio` | IP Scanner 并发扫描引擎 |
| `ipaddress` | IP 地址解析与网络计算 |
| `socket` | 主机名解析、TCP 连接、mDNS/NetBIOS |
| `subprocess` | 系统 Ping 调用、ARP 查询 |
| `sqlite3` | 扫描历史存储 |
| `json`/`csv` | 数据导出 |
| `colorsys` | 颜色空间转换 |
| `difflib` | 文本对比 |
| `secrets` | 加密安全的随机生成 |
| `uuid` | UUID v1/v3/v4/v5 生成 |
| `datetime` | 日期时间处理 |

---

## 3. 项目目录结构

```
IP-Scanner/
├── src/
│   └── fuzztoolbox/
│       ├── __init__.py              # 包版本声明
│       ├── app.py                   # 桌面应用入口
│       ├── core/                    # 核心共享服务层
│       │   ├── __init__.py
│       │   └── network_info.py      # 网络信息检测
│       ├── ui/                      # UI 框架层
│       │   ├── __init__.py
│       │   ├── main_window.py       # 主窗口
│       │   ├── home_page.py         # 首页/工具启动器
│       │   ├── tool_registry.py     # 工具注册表
│       │   ├── components.py        # 公共控件（ComboBox、Table）
│       │   ├── line_number_editor.py # 带行号编辑器
│       │   ├── style_loader.py      # QSS 样式加载器
│       │   ├── theme.py             # 主题兼容层
│       │   └── theme_colors.py      # 语义化颜色定义
│       ├── tools/                   # 工具模块层
│       │   ├── __init__.py
│       │   ├── ip_scanner/          # IP 扫描器
│       │   ├── ip_lookup/           # 公网 IP 查询
│       │   ├── subnet_calculator/   # 子网计算器
│       │   ├── uuid_generator/      # UUID 生成器
│       │   ├── token_generator/     # Token 生成器
│       │   ├── json_formatter/      # JSON 格式化
│       │   ├── text_comparer/       # 文本对比
│       │   ├── text_statistics/     # 文本统计
│       │   ├── ipv4_converter/      # IPv4 转换器
│       │   ├── qr_generator/        # 二维码生成器
│       │   ├── wifi_qr_generator/   # WiFi 二维码
│       │   ├── color_picker/        # 取色器
│       │   ├── roman_numeral/       # 罗马数字转换
│       │   ├── password_strength/   # 密码强度分析
│       │   ├── random_port/         # 随机端口
│       │   ├── timer/               # 计时器
│       │   └── datetime_converter/  # 日期时间转换
│       ├── assets/                  # SVG/PNG 资源
│       └── styles/                  # QSS 样式表
├── tests/                           # 测试目录（镜像 src 结构）
│   ├── core/
│   ├── ui/
│   ├── tools/<tool_name>/
│   └── packaging/
├── packaging/                       # 打包配置
│   ├── build_release.py             # PyInstaller 构建脚本
│   ├── macos_entry.py               # macOS 入口点
│   ├── FuzzToolBox.icns             # macOS 图标
│   ├── FuzzToolBox.ico              # Windows 图标
│   ├── windows_installer.iss       # Inno Setup 脚本
│   └── windows_version_info.txt     # Windows 版本信息
├── scripts/                         # 开发者脚本
│   ├── build_macos.sh               # macOS 构建入口
│   ├── build_windows.ps1            # Windows 构建入口
│   └── build_icons.py               # 图标生成脚本
├── docs/                            # 文档
│   ├── architecture.md              # 架构说明
│   └── code-wiki.md                 # 本文档
├── .github/workflows/               # CI/CD
│   └── release-build.yml            # GitHub Release 工作流
├── pyproject.toml                   # 项目配置
├── AGENTS.md                        # Agent 工作流说明
└── README.md                        # 项目说明
```

---

## 4. 整体架构设计

### 4.1 分层架构

```
┌─────────────────────────────────────────────────────┐
│                    用户界面层 (UI)                    │
│  main_window.py · home_page.py · components.py       │
│  tool_registry.py · style_loader.py · theme_colors.py │
├─────────────────────────────────────────────────────┤
│                    工具页面层 (Pages)                 │
│  tools/<name>/page.py · 每个工具的 PySide6 UI        │
├─────────────────────────────────────────────────────┤
│                   核心逻辑层 (Core)                  │
│  tools/<name>/<logic>.py · 纯 Python 业务逻辑        │
│  不依赖 PySide6，可独立测试                          │
├─────────────────────────────────────────────────────┤
│                   共享服务层 (Services)              │
│  core/network_info.py · 系统网络信息检测             │
├─────────────────────────────────────────────────────┤
│                   外部依赖层 (Dependencies)          │
│  psutil · getmac · segno · PySide6 · 标准库          │
└─────────────────────────────────────────────────────┘
```

### 4.2 设计原则

1. **逻辑与 UI 分离**：每个工具的核心逻辑放在独立模块中（如 `engine.py`、`generator.py`、`converter.py`），不依赖 PySide6，便于单元测试
2. **统一页面模式**：所有工具页面统一命名为 `page.py`，在 `MainWindow` 中集中装配
3. **公共控件复用**：通过 `components.py` 中的 `configure_combo()` 和 `configure_table()` 保持 UI 一致性
4. **样式系统**：QSS 外部样式表 + `style_loader.py` 命名样式 + 主题色变量，实现亮色/深色切换
5. **异步优先**：IP Scanner 使用 `asyncio` 实现有界并发，避免大网段内存溢出

### 4.3 数据流（IP Scanner 示例）

```
用户输入 → page.py (UI)
    │
    ▼
ScanWorker (QThread)  ←──  ScanConfig (models.py)
    │
    ▼
Scanner (engine.py)
    ├── TargetRange (targets.py)  ←  惰性 IP 生成
    ├── asyncio.Semaphore 控制并发
    ├── _probe_liveness()
    │   ├── _tcp_probe() → _check_ports() → _connect_port()
    │   └── _ping_probe() → _run_command() (系统 ping)
    └── _enrich()
        ├── _lookup_mac() (getmac + arp fallback)
        └── _resolve_hostname() (reverse_dns → multicast_dns → netbios)
    │
    ▼
ScanResult → Signal → ResultModel → QTableView
    │
    ▼
exporters.py (CSV/JSON) · storage.py (SQLite)
```

---

## 5. 核心模块详解

### 5.1 `core/network_info.py` — 网络信息检测

**文件**：`src/fuzztoolbox/core/network_info.py`

**职责**：自动检测本机网络接口信息，包括 IP 地址、子网掩码、网关、MAC 地址。

#### 关键类

**`NetworkInfo`** (frozen dataclass)

| 字段 | 类型 | 说明 |
|------|------|------|
| `interface` | `Optional[str]` | 网络接口名 |
| `ip` | `Optional[str]` | IPv4 地址 |
| `prefix_length` | `Optional[int]` | 子网前缀长度 |
| `gateway` | `Optional[str]` | 默认网关 |
| `mac` | `Optional[str]` | MAC 地址 |

| 属性/方法 | 说明 |
|----------|------|
| `address` | 返回 IP 或"未检测到 IPv4" |
| `netmask` | 计算子网掩码 |
| `cidr` | 计算 CIDR 表示法 |
| `scan_range` | 计算可用主机范围（考虑 /30、/32 特殊情况） |
| `display_text()` | 格式化显示文本 |

#### 关键函数

| 函数 | 说明 |
|------|------|
| `get_network_info(include_gateway)` | **主入口**，检测本机网络信息。优先使用 psutil，回退到平台特定命令 |
| `_psutil_network_info()` | 使用 psutil 枚举网络接口并评分选择最优接口 |
| `_interface_score()` | 接口评分算法：UP 状态 +30、RFC1918 私网 +50、虚拟接口 -100 等 |
| `_macos_network_info()` | macOS 平台回退：解析 `route` + `ifconfig` 输出 |
| `_windows_network_info()` | Windows 平台回退：解析 PowerShell `Get-NetIPConfiguration` |
| `_socket_source_ip()` | 通过 UDP socket 探测本机出站 IP（连接 1.1.1.1 或 8.8.8.8） |

#### 评分算法说明

`_interface_score()` 综合多个因素为每个网络接口打分：
- 接口 UP：+30；DOWN：-300
- RFC1918 私网：+50；CGNAT (100.64/10)：+30；全局公网：+20；链路本地：-80
- 虚拟接口（utun/tun/docker/vmnet 等）：-100
- 接口名匹配物理网卡模式（en*/eth*/wlan*）：+40
- 匹配 socket 探测的首选 IP：+100（虚拟接口仅 +20）
- 前缀 /31 或 /32：-20
- 有 MAC 地址：+10

---

## 6. UI 层详解

### 6.1 `ui/main_window.py` — 主窗口

**文件**：`src/fuzztoolbox/ui/main_window.py`

#### 关键类

**`MainWindow(QMainWindow)`**

| 方法/属性 | 说明 |
|----------|------|
| `__init__()` | 初始化所有工具页面、顶部导航栏、首页、主题设置 |
| `open_tool(tool_id)` | 根据 tool_id 切换到对应工具页面，配置页面标题和图标 |
| `show_home()` | 返回首页 |
| `cycle_theme()` | 切换亮色/深色主题 |
| `apply_theme()` | 应用当前主题，更新 QSS、图标、GitHub 链接色 |
| `closeEvent()` | 优雅关闭：等待扫描线程停止，保存窗口几何 |
| `_connect_system_theme()` | 监听系统主题变化信号 |
| `_system_theme_changed()` | 系统主题变化时自动更新（当 theme_mode="system" 时） |

**页面映射表**（`open_tool` 方法）：

| tool_id | 页面 | 分类标题 |
|---------|------|---------|
| `ip-scanner` | `IPScannerPage` | IP Scanner · 网络扫描 |
| `ip-lookup` | `IPLookupPage` | 公网IP信息查询 · 网络工具 |
| `subnet-calculator` | `SubnetCalculatorPage` | 子网划分计算器 · 网络规划 |
| `uuid-generator` | `UUIDGeneratorPage` | UUID 生成器 · 开发工具 |
| `token-generator` | `TokenGeneratorPage` | Token 生成器 · 开发工具 |
| `json-formatter` | `JSONFormatterPage` | JSON 格式化与校验器 · 开发工具 |
| `text-comparer` | `TextComparerPage` | 文本对比工具 · 开发工具 |
| `text-statistics` | `TextStatisticsPage` | 文本统计工具 · 实用工具 |
| `ipv4-converter` | `IPv4ConverterPage` | IPv4 地址转换器 · 网络工具 |
| `qr-generator` | `QRGeneratorPage` | 二维码生成器 · 开发工具 |
| `wifi-qr-generator` | `WiFiQRGeneratorPage` | WiFi 二维码生成器 · 网络工具 |
| `color-picker` | `ColorPickerPage` | 取色器 · 开发工具 |
| `roman-numeral` | `RomanNumeralPage` | 罗马数字转换器 · 开发工具 |
| `password-strength` | `PasswordStrengthPage` | 密码强度分析器 · 开发工具 |
| `random-port` | `RandomPortPage` | 随机端口生成器 · 网络工具 |
| `timer` | `TimerPage` | 计时器 · 实用工具 |
| `datetime-converter` | `DateTimeConverterPage` | 日期时间转换器 · 开发工具 |

#### 关键函数

| 函数 | 说明 |
|------|------|
| `main()` | **GUI 入口**：创建 QApplication，配置主题、窗口图标，启动事件循环 |
| `configure_windows_app_id()` | 设置 Windows AppUserModelID，确保任务栏正确分组 |

### 6.2 `ui/home_page.py` — 首页

**文件**：`src/fuzztoolbox/ui/home_page.py`

#### 关键类

**`ToolboxHomePage(QWidget)`**

| 信号 | 说明 |
|------|------|
| `tool_requested` | 用户点击工具卡片时发射，携带 tool_id |
| `theme_requested` | 用户点击主题切换按钮时发射 |

| 方法 | 说明 |
|------|------|
| `refresh_tools()` | 根据搜索文本和分类过滤工具卡片，自适应网格布局 |
| `set_category(category)` | 切换分类过滤 |
| `resizeEvent()` | 窗口大小变化时重新排列卡片网格 |

**`ToolCard(QFrame)`** — 工具卡片组件
- 显示工具图标（40x40）、名称、描述和分类
- 点击时发射 `activated` 信号，携带 `tool.id`

**`ThemeToggleButton(QPushButton)`** — 主题切换按钮
- 悬停时图标大小动画（23→28px）
- 160ms InOutCubic 缓动曲线

### 6.3 `ui/tool_registry.py` — 工具注册表

**文件**：`src/fuzztoolbox/ui/tool_registry.py`

#### 关键类

**`ToolDefinition`** (frozen dataclass)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 唯一标识（如 `ip-scanner`） |
| `name` | `str` | 显示名称 |
| `description` | `str` | 功能描述 |
| `category` | `str` | 分类（网络工具/开发工具/实用工具） |
| `icon` | `str` | SVG 图标文件名 |
| `keywords` | `Tuple[str, ...]` | 搜索关键词 |

| 方法 | 说明 |
|------|------|
| `matches(query, category)` | 判断工具是否匹配搜索词和分类 |

#### 工具清单

共 **16 个工具**，分为 3 个分类：

**网络工具**（6 个）：ip-scanner、ip-lookup、subnet-calculator、ipv4-converter、wifi-qr-generator、random-port

**开发工具**（8 个）：uuid-generator、token-generator、json-formatter、text-comparer、qr-generator、color-picker、roman-numeral、password-strength、datetime-converter

**实用工具**（2 个）：text-statistics、timer

#### 关键函数

| 函数 | 说明 |
|------|------|
| `filter_tools(tools, query, category)` | 根据搜索词和分类过滤工具列表 |

### 6.4 `ui/components.py` — 公共控件

**文件**：`src/fuzztoolbox/ui/components.py`

#### 关键类

**`ComboItemDelegate(QStyledItemDelegate)`** — 自定义下拉项委托
- 自定义绘制圆角高亮、行高 34px

**`ComboListView(QListView)`** — 自定义下拉列表视图
- 自定义背景、边框、选中色
- `prepare_popup()`：配置弹出窗口为无边框、半透明

**`GridCellDelegate(QStyledItemDelegate)`** — 自定义表格单元格委托
- 自定义网格线绘制

#### 关键函数

| 函数 | 说明 |
|------|------|
| `configure_combo(combo)` | **公共下拉配置**：应用统一样式、委托、弹出窗口行为 |
| `configure_table(table)` | **公共表格配置**：设置委托、交替行色、网格、选择行为 |

### 6.5 `ui/style_loader.py` — 样式加载器

**文件**：`src/fuzztoolbox/ui/style_loader.py`

#### 关键概念

样式系统采用 **外部 QSS 文件 + 命名样式目录 + 主题变量** 三级架构：

1. **`base.qss`** — 全局 QSS 样式表，使用 CSS-like 语法
2. **`catalog.qss`** — 命名样式目录，通过 `@style key ... @endstyle` 注释定义
3. **主题色变量** — `theme_colors.py` 中的 `LIGHT`/`DARK` 字典

#### 关键函数

| 函数 | 说明 |
|------|------|
| `load_qss(name)` | 加载 QSS 文件，解析主题变量，返回完整样式字符串 |
| `style_text(key, **values)` | 从 catalog 获取命名样式，支持动态值替换 |
| `apply_style(widget, key, **values)` | 对控件应用命名样式 |
| `set_theme(theme)` | 设置全局主题（"light"/"dark"），清除缓存 |
| `theme_color(role)` | 获取当前主题的语义化颜色值 |
| `refresh_widget_styles(widgets)` | 主题切换时刷新所有已应用命名样式的控件 |
| `on_theme_changed(callback)` | 注册主题变化回调 |

---

## 7. 工具模块详解

### 7.1 IP Scanner（旗舰模块）

#### 目录结构

```
tools/ip_scanner/
├── __init__.py
├── engine.py          # 扫描引擎（核心）
├── models.py          # 数据模型
├── targets.py         # 目标解析
├── hostname.py        # 主机名解析
├── exporters.py       # 导出功能
├── storage.py         # SQLite 历史存储
├── cli.py             # 命令行入口
└── page.py            # GUI 页面
```

#### 7.1.1 `models.py` — 数据模型

**`ScanConfig`** (frozen dataclass) — 扫描配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `method` | `str` | `"tcp"` | 探测方式：`"tcp"` 或 `"ping"` |
| `timeout` | `float` | `0.5` | 单次探测超时（秒），范围 0.05-30 |
| `retries` | `int` | `0` | 失败重试次数，范围 0-5 |
| `concurrency` | `int` | `256` | 并发数，范围 1-512 |
| `ports` | `List[int]` | `[22,80,443,445,3389,8080]` | TCP 模式探测端口列表 |
| `resolve_hostname` | `bool` | `False` | 是否解析主机名 |
| `include_dead` | `bool` | `False` | 是否包含离线主机 |

| 方法 | 说明 |
|------|------|
| `validate()` | 校验所有配置参数的合法性 |

**`ScanResult`** (dataclass) — 扫描结果

| 字段 | 类型 | 说明 |
|------|------|------|
| `ip` | `str` | IP 地址 |
| `is_alive` | `bool` | 是否在线 |
| `method` | `str` | 探测方式 |
| `response_time_ms` | `Optional[float]` | 响应时间（毫秒） |
| `hostname` | `Optional[str]` | 主机名 |
| `mac` | `Optional[str]` | MAC 地址 |
| `open_ports` | `List[int]` | 开放端口列表 |
| `error` | `Optional[str]` | 错误信息 |
| `details_pending` | `bool` | 是否仍在补充详情 |

| 方法 | 说明 |
|------|------|
| `to_dict()` | 转换为字典（排除 `details_pending`） |

**`ScanProgress`** (frozen dataclass) — 扫描进度

| 字段 | 类型 | 说明 |
|------|------|------|
| `scanned` | `int` | 已扫描数 |
| `total` | `int` | 总目标数 |
| `alive` | `int` | 在线数 |
| `elapsed_seconds` | `float` | 已用时间 |

| 属性 | 说明 |
|------|------|
| `rate` | 扫描速率（IP/s） |

#### 7.1.2 `targets.py` — 目标解析

**`TargetRange`** (frozen dataclass)

| 字段 | 类型 | 说明 |
|------|------|------|
| `start` | `int` | 起始 IP（整数） |
| `end` | `int` | 结束 IP（整数） |
| `source` | `str` | 原始输入文本 |

| 属性/方法 | 说明 |
|----------|------|
| `total` | 地址总数 |
| `__iter__` | 惰性迭代生成 IP 字符串，**不一次性生成全部门牌** |

**关键函数**

| 函数 | 说明 |
|------|------|
| `parse_target(value)` | 解析扫描目标：支持 CIDR（`192.168.1.0/24`）、单 IP、起止范围（`192.168.1.1-192.168.1.254`） |
| `parse_ports(value)` | 解析端口列表：支持逗号分隔和范围（`80,443,8000-9000`） |

#### 7.1.3 `engine.py` — 扫描引擎

**`Scanner`** — 核心扫描引擎

**设计模式**：有界生产者-消费者模型

```
                    asyncio.Queue (maxsize = concurrency * 2)
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ producer│───▶│  worker  │───▶│result_queue│───▶│  drain   │
│ (IP生成) │    │ (探测)   │    │ (结果)    │    │ (UI更新) │
└─────────┘    └──────────┘    └──────────┘    └──────────┘
                     │
                     ▼
              ┌──────────┐
              │enricher │  MAC + 主机名补全
              └──────────┘
                     │
                     ▼
              ┌──────────┐
              │update_queue│
              └──────────┘
```

| 信号量 | 说明 |
|--------|------|
| `_port_semaphore` | 控制 TCP 端口并发（max(32, concurrency*4, 256)） |
| `_ping_semaphore` | 控制系统 Ping 进程并发（min(concurrency, 32)），防止进程调度过载 |
| `_neighbor_semaphore` | 控制 MAC 查询并发 |
| `_hostname_semaphore` | 控制主机名解析并发 |

| 方法 | 说明 |
|------|------|
| `scan(targets, on_results, on_progress, on_updates, ...)` | **主扫描方法**：启动生产者和消费者，批量交付结果 |
| `cancel()` | 取消扫描，杀死活跃子进程 |
| `_probe_liveness(ip)` | 执行 liveness 探测（按方法分发） |
| `_tcp_probe(ip)` | TCP 端口探测 + 透明代理检测 |
| `_ping_probe(ip, timeout)` | 系统 Ping 探测（2 包突发） |
| `_enrich(result)` | 并发查询 MAC 和主机名 |
| `_lookup_mac(ip)` | getmac 查询 + arp 命令回退 |
| `_resolve_hostname(ip)` | 分层解析：reverse DNS → mDNS → NetBIOS |
| `_connect_port(ip, port, timeout)` | 建立 TCP 连接 |
| `_check_ports(ip, ports, timeout)` | 批量端口检查（分批并发） |
| `_has_echo_reply(text, ip)` | 严格验证 ICMP Echo Reply（按 IP + TTL 匹配） |
| `_parse_ping_time(text, ip)` | 解析 Ping RTT（仅网络延迟，不含进程启动/销毁时间） |
| `_is_on_link(ip)` | 判断目标是否在同一子网 |

**TCP 透明代理检测**：
- 如果检测到开放端口，额外探测 3 个高位控制端口（65535、65404、65273）
- 如果全部响应 → 判定为透明代理/隧道劫持，清除所有开放端口结果

**`ScanCancelled`** — 自定义异常，用于优雅取消

#### 7.1.4 `hostname.py` — 主机名解析

| 函数 | 说明 |
|------|------|
| `reverse_dns(ip)` | 通过系统解析器反查 DNS PTR 记录 |
| `multicast_dns(ip, source_ip, timeout)` | 通过 mDNS (224.0.0.251:5353) 直接查询 PTR |
| `netbios_name(ip, source_ip, timeout)` | 通过 NBSTAT 查询 NetBIOS 名称（Windows 机器名） |
| `parse_dns_ptr(packet, expected_name)` | 解析 DNS 响应包 |
| `build_nbstat_query(transaction_id)` | 构造 NBSTAT 查询包 |
| `parse_nbstat_response(packet, transaction_id)` | 解析 NBSTAT 响应 |

**解析优先级**：reverse DNS → mDNS → NetBIOS（后两者仅限本地子网）

#### 7.1.5 `exporters.py` — 数据导出

| 函数 | 说明 |
|------|------|
| `export_csv(path, results)` | 导出为 CSV（UTF-8-BOM，Excel 兼容） |
| `export_json(path, results)` | 导出为 JSON（格式化、中文友好） |
| `export_results(path, results)` | 自动根据扩展名选择导出格式 |

#### 7.1.6 `storage.py` — SQLite 历史存储

**`HistoryStore`**

| 方法 | 说明 |
|------|------|
| `create_task(target, total, config)` | 创建扫描任务记录 |
| `add_results(task_id, results)` | 批量写入扫描结果（仅在线主机） |
| `finish_task(task_id, alive_count, status)` | 完成任务记录 |
| `recent_tasks(limit)` | 查询最近任务 |
| `close()` | 关闭数据库连接 |

**数据库表结构**：

`scan_tasks` — 扫描任务
- `id`, `target`, `method`, `started_at`, `finished_at`, `total_ips`, `alive_count`, `status`, `config_json`

`scan_results` — 扫描结果
- `id`, `task_id` (FK), `ip`, `method`, `response_time_ms`, `hostname`, `mac`, `open_ports_json`

#### 7.1.7 `cli.py` — 命令行入口

**`main()`** — 命令行主入口

**CLI 参数**：

| 参数 | 说明 |
|------|------|
| `target` | 扫描目标（CIDR/单 IP/范围） |
| `--method` | 探测方式：`tcp`（默认）或 `ping` |
| `--ports` | TCP 端口列表（默认 `22,80,443,445,3389,8080`） |
| `--timeout` | 超时时间（默认 0.5s） |
| `--concurrency` | 并发数（默认 256） |
| `--retries` | 重试次数（默认 0） |
| `--resolve-hostname` | 启用主机名解析 |
| `--include-dead` | 包含离线主机 |
| `--json` | JSON Lines 输出格式 |

**使用示例**：
```bash
# TCP 扫描
fuzztoolbox 192.168.1.0/24 --method tcp --ports 80,443

# 系统 Ping 扫描
fuzztoolbox 192.168.1.0/24 --method ping

# JSON 输出 + 主机名解析
fuzztoolbox 192.168.1.0/24 --resolve-hostname --json
```

#### 7.1.8 `page.py` — GUI 页面

**`ResultModel(QAbstractTableModel)`** — 表格数据模型

| 方法 | 说明 |
|------|------|
| `add_batch(batch)` | 批量添加/更新结果（按 IP 去重更新） |
| `clear()` | 清空所有结果 |
| `set_scan_method(method)` | 切换列显示（ping 显示 MAC，tcp 显示端口） |

**`ResultFilterModel(QSortFilterProxyModel)`** — 过滤模型

- 支持精确 IP 匹配和模糊搜索（主机名/MAC/端口）
- 支持在线/离线状态过滤

**`ScanWorker(QThread)`** — 后台扫描线程

| 方法 | 说明 |
|------|------|
| `run()` | 在线程中创建 asyncio 事件循环，启动 Scanner |
| `cancel(force)` | 请求取消，force=True 时取消正在进行的任务 |

**信号**：`results`、`updates`、`progress`、`completed`

**`IPScannerPage(QWidget)`** — 扫描页面

| 方法 | 说明 |
|------|------|
| `start_scan()` | 启动扫描：创建 ScanWorker，连接信号 |
| `stop_scan()` | 停止扫描：断开信号 + 请求取消 + 看门狗强制终止 |
| `export()` | 导出结果为 CSV/JSON |
| `prepare_close(on_ready)` | 优雅关闭：等待扫描线程停止 |
| `_refresh_network_info()` | 刷新本机网络信息 |

### 7.2 其他工具模块

#### 7.2.1 `subnet_calculator/` — 子网计算器

**`calculator.py`**

| 函数/类 | 说明 |
|---------|------|
| `parse_network(value)` | 解析 IPv4/IPv6 网络 |
| `network_summary(network)` | 返回网络摘要字典（版本、掩码、可用范围等） |
| `usable_range(network)` | 计算可用主机范围（IPv6 返回全部，IPv4 扣除网络/广播地址） |
| `address_scope(network)` | 地址属性分类（私有/公网/回环等） |
| `FLSMPlan` | 等长子网规划，支持 `subnet_at(index)` 和 `index_for_ip(value)` |
| `flsm_by_count(network, count)` | 按数量计算 FLSM 方案 |
| `allocate_vlsm(network, requirements)` | VLSM 分配，按需求降序排列 |
| `SubnetRow` | VLSM 分配结果行 |

#### 7.2.2 `uuid_generator/` — UUID 生成器

**`generator.py`**

| 函数/类 | 说明 |
|---------|------|
| `UUID7Generator` | RFC 9562 UUID v7 生成器，单调递增，线程安全 |
| `generate_uuids(version, count, ...)` | 统一 UUID 生成入口，支持 v1/v3/v4/v5/v7 |
| `format_uuid(value, options)` | 格式化 UUID（大小写、连字符、花括号） |
| `resolve_namespace(value)` | 解析命名空间（dns/url/oid/x500 或自定义 UUID） |

#### 7.2.3 `ip_lookup/` — 公网 IP 查询

**`service.py`**

| 函数/类 | 说明 |
|---------|------|
| `LookupReport` | 查询报告（IP 分类、PTR、多数据源结果） |
| `lookup(ip)` | 主查询入口，依次查询 ipwho.is 和 ipapi.co |
| `discover_public_ip(version)` | 通过 ipify.org 检测本机公网 IP |
| `classify_ip(value)` | IP 分类（公网/私有/回环/链路本地等） |

#### 7.2.4 `json_formatter/` — JSON 格式化

**`formatter.py`**

| 函数 | 说明 |
|------|------|
| `parse_json(source)` | 解析 JSON，出错时返回精确行列信息 |
| `format_json(source, indent, sort_keys)` | 格式化 JSON |
| `compact_json(source, sort_keys)` | 压缩 JSON |
| `validate_json(source)` | 校验 JSON，返回错误详情或 None |
| `JSONErrorDetails` | 错误详情（消息、行、列、位置） |

#### 7.2.5 `text_comparer/` — 文本对比

**`comparer.py`**

| 函数/类 | 说明 |
|---------|------|
| `compare_texts(left, right)` | 逐行对比 + 字符级高亮差异 |
| `unified_diff(left, right, context)` | 生成 unified diff 格式 |
| `context_diff(left, right, context)` | 生成 context diff 格式 |
| `ComparisonResult` | 对比结果（对齐行列表 + 统计） |
| `AlignedLine` | 对齐行（equal/delete/insert/replace + 字符级 span） |
| `DiffStats` | 差异统计（added/deleted/modified） |

**`syntax.py`** — 语法高亮编辑器

| 类 | 说明 |
|----|------|
| `CodeSyntaxHighlighter` | 支持 25+ 语言的语法高亮器 |
| `detect_language(text)` | 自动检测编程语言 |
| `LANGUAGES` | 支持的语言列表 |
| `KEYWORDS` | 各语言关键字映射 |

#### 7.2.6 `password_strength/` — 密码强度分析

**`analyzer.py`**

| 函数/类 | 说明 |
|---------|------|
| `analyze_password(password)` | 分析密码强度，返回熵值/评分/破解时间 |
| `infer_charset_size(password)` | 推断字符集大小（小写+26、大写+26、数字+10、标点等） |
| `format_crack_time(guesses, rate)` | 格式化暴力破解时间 |
| `PasswordStrength` | 分析结果（长度/字符集/熵/评分/破解时间/猜测数） |

默认破解速率：100 亿次/秒

#### 7.2.7 `qr_generator/` — 二维码生成

**`generator.py`**

| 函数 | 说明 |
|------|------|
| `generate_qr_png(text, foreground, background, error_level, scale)` | 生成 PNG 格式二维码，返回字节数据 |

支持容错率：L/M/Q/H

#### 7.2.8 `wifi_qr_generator/` — WiFi 二维码

**`generator.py`**

| 函数 | 说明 |
|------|------|
| `make_wifi_payload(ssid, password, security, hidden)` | 构造 WiFi QR 负载 |
| `generate_wifi_qr_png(...)` | 生成 WiFi 配置二维码 PNG |

支持加密方式：WPA、WEP、nopass、WPA3

#### 7.2.9 `color_picker/` — 取色器

**`converter.py`**

| 类 | 说明 |
|----|------|
| `ColorValue` | 颜色值数据类，支持 HEX/RGB/HSL/HWB/LCH/CMYK 六种格式输出 |

色彩转换基于 CSS Color Level 4 标准，LCH 使用 Bradford D65→D50 白点适配。

#### 7.2.10 `ipv4_converter/` — IPv4 转换器

**`converter.py`**

| 函数/类 | 说明 |
|---------|------|
| `convert_ipv4(value)` | IPv4 地址转换：二进制、十进制、十六进制、IPv4-mapped IPv6 |
| `IPv4Conversion` | 转换结果数据类 |

#### 7.2.11 `token_generator/` — Token 生成器

**`generator.py`**

| 函数 | 说明 |
|------|------|
| `generate_token(length, lowercase, uppercase, digits, symbols, custom_characters)` | 使用 `secrets` 生成加密安全随机 Token |
| `_secure_shuffle(values)` | Fisher-Yates 安全洗牌 |
| `unique_characters(value)` | 去重保序 |

#### 7.2.12 `random_port/` — 随机端口

**`generator.py`**

| 函数 | 说明 |
|------|------|
| `generate_random_port(previous)` | 生成 1024-65535 随机端口，可选避开上一个值 |

#### 7.2.13 `timer/` — 计时器

**`countdown.py`**

| 类 | 说明 |
|----|------|
| `CountdownTimer` | 倒计时器，支持 start/pause/resume/reset |
| `StopwatchTimer` | 秒表，支持 start/pause/resume/reset |
| `format_duration(seconds)` | 格式化时长为 `HH:MM:SS.mmm` |

状态机：`idle → running → (paused → running)* → finished → idle`

#### 7.2.14 `datetime_converter/` — 日期时间转换

**`converter.py`**

| 函数/类 | 说明 |
|---------|------|
| `convert_timestamp(value, unit, timezone)` | Unix 时间戳 → 15 种格式输出 |
| `convert_datetime(value, timezone)` | ISO 8601/自定义格式 → 15 种格式输出 |
| `current_result(timezone)` | 获取当前时间 |
| `parse_timezone(value)` | 解析时区（UTC/GMT/偏移量） |
| `DateTimeResult` | 结果数据类 |

支持的时间戳单位：秒、毫秒、微秒（自动检测）

#### 7.2.15 `roman_numeral/` — 罗马数字

**`converter.py`**

| 函数 | 说明 |
|------|------|
| `integer_to_roman(value)` | 1-3999 → 罗马数字 |
| `roman_to_integer(value)` | 罗马数字 → 1-3999 |

#### 7.2.16 `text_statistics/` — 文本统计

**`analyzer.py`**

| 函数/类 | 说明 |
|---------|------|
| `analyze_text(text)` | 分析文本：字符数/字数/行数/段落数/句子数/UTF-8/16 字节等 |
| `TextStatistics` | 统计结果数据类 |
| `format_report(stats)` | 格式化统计报告 |

支持中日韩（CJK）字符识别和 Unicode 感知的单词计数。

---

## 8. 数据模型与类型定义

### 8.1 核心数据类汇总

| 数据类 | 文件 | 不可变 | 说明 |
|--------|------|--------|------|
| `NetworkInfo` | `core/network_info.py` | ✅ | 本机网络信息 |
| `ScanConfig` | `tools/ip_scanner/models.py` | ✅ | 扫描配置 |
| `ScanResult` | `tools/ip_scanner/models.py` | ❌ | 扫描结果（可变，补充详情时更新） |
| `ScanProgress` | `tools/ip_scanner/models.py` | ✅ | 扫描进度 |
| `TargetRange` | `tools/ip_scanner/targets.py` | ✅ | IP 目标范围 |
| `ToolDefinition` | `ui/tool_registry.py` | ✅ | 工具元数据 |
| `SubnetRow` | `tools/subnet_calculator/calculator.py` | ✅ | VLSM 分配行 |
| `FLSMPlan` | `tools/subnet_calculator/calculator.py` | ✅ | FLSM 规划方案 |
| `UUIDFormat` | `tools/uuid_generator/generator.py` | ✅ | UUID 格式化选项 |
| `ColorValue` | `tools/color_picker/converter.py` | ✅ | 颜色值 |
| `IPv4Conversion` | `tools/ipv4_converter/converter.py` | ✅ | IPv4 转换结果 |
| `DateTimeResult` | `tools/datetime_converter/converter.py` | ✅ | 日期时间转换结果 |
| `PasswordStrength` | `tools/password_strength/analyzer.py` | ✅ | 密码强度分析结果 |
| `LookupReport` | `tools/ip_lookup/service.py` | ❌ | IP 查询报告 |
| `SourceResult` | `tools/ip_lookup/service.py` | ❌ | 数据源结果 |
| `JSONErrorDetails` | `tools/json_formatter/formatter.py` | ✅ | JSON 错误详情 |
| `DiffStats` | `tools/text_comparer/comparer.py` | ✅ | 差异统计 |
| `AlignedLine` | `tools/text_comparer/comparer.py` | ✅ | 对齐行 |
| `ComparisonResult` | `tools/text_comparer/comparer.py` | ✅ | 对比结果 |
| `TextStatistics` | `tools/text_statistics/analyzer.py` | ✅ | 文本统计结果 |

### 8.2 回调类型定义

| 类型 | 签名 | 说明 |
|------|------|------|
| `ResultCallback` | `Callable[[List[ScanResult]], None]` | 结果批次回调 |
| `UpdateCallback` | `Callable[[List[ScanResult]], None]` | 详情更新回调 |
| `ProgressCallback` | `Callable[[ScanProgress], None]` | 进度回调 |

---

## 9. 主题系统

### 9.1 架构

```
theme_colors.py          style_loader.py           styles/
┌──────────────┐    ┌──────────────────┐    ┌──────────────┐
│ LIGHT/DARK   │───▶│ style_text()     │───▶│ base.qss     │
│ 语义化颜色    │    │ apply_style()    │    │ catalog.qss  │
│ DARK_REPLACE  │    │ set_theme()      │    │              │
└──────────────┘    │ theme_color()    │    └──────────────┘
                    │ refresh_widgets()│
                    └──────────────────┘
```

### 9.2 语义化颜色变量

**UI 色**：`window`、`surface`、`surface_alt`、`surface_muted`、`text`、`text_secondary`、`text_muted`、`border`、`border_soft`、`primary`、`primary_soft`、`primary_text`

**编辑器色**：`gutter`、`gutter_border`、`current_line`、`error_bg`、`error`

**Diff 色**：`diff_remove_bg`、`diff_remove_strong`、`diff_add_bg`、`diff_add_strong`、`diff_change_bg`、`diff_info_bg`、`diff_context_bg`

**语法高亮色**：`syntax_keyword`、`syntax_string`、`syntax_number`、`syntax_comment`、`syntax_type`、`syntax_tag`、`syntax_property`、`syntax_preprocessor`

### 9.3 主题切换

- **三种模式**：`system`（跟随系统）、`light`、`dark`
- **持久化**：通过 `QSettings("1024_byteeeee", "FuzzToolBox")` 存储
- **初始化**：启动时读取设置，无设置时跟随系统
- **回调机制**：`on_theme_changed(callback)` 注册回调，主题切换时自动刷新

---

## 10. 构建与部署

### 10.1 开发环境搭建

```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装（含 GUI 依赖）
pip install -e '.[gui]'

# 仅安装核心（CLI 使用）
pip install -e '.'
```

### 10.2 开发运行

```bash
# GUI 模式
fuzztoolbox-gui

# CLI 模式
fuzztoolbox 192.168.1.0/24 --method ping

# 不安装直接运行
PYTHONPATH=src python3 -m fuzztoolbox.app
PYTHONPATH=src python3 -m fuzztoolbox.tools.ip_scanner.cli 192.168.1.0/24
```

### 10.3 测试

```bash
# 运行所有测试
PYTHONPATH=src python3 -m unittest discover -s tests -v

# 或使用 VS Code 任务
# Cmd+Shift+P → "Tasks: Run Test Task"
```

### 10.4 原生构建

#### macOS

```bash
sh scripts/build_macos.sh
```

产物：`build/FuzzToolBox.app` + `build/releases/FuzzToolBox-macOS-{arch}.dmg`

#### Windows

```powershell
.\scripts\build_windows.ps1
```

产物：`build/FuzzToolBox/` + `build/releases/FuzzToolBox-v{version}-Windows-{arch}-Setup.exe`

### 10.5 构建流程详解

`packaging/build_release.py` 的 `build()` 函数：

1. 清理旧版 IP-Scanner 产物
2. 调用 PyInstaller 打包
   - `--windowed`（无控制台窗口）
   - `--osx-bundle-identifier` / `--version-file`
   - `--icon` 应用图标
   - `--add-data` 包含 assets 和 styles
3. macOS 后处理
   - 更新 `Info.plist` 版本号
   - `codesign --force --deep --sign -` 签名
   - `hdiutil` 创建 DMG
4. Windows 后处理
   - Inno Setup 创建安装包

### 10.6 CI/CD — GitHub Actions

**工作流**：`.github/workflows/release-build.yml`

**触发条件**：
- Release 发布
- 手动触发（`workflow_dispatch`）

**流程**：
1. 在 `windows-latest` 和 `macos-latest` 上并行构建
2. Python 3.11 + pip 安装
3. 运行单元测试
4. Smoke 测试 GUI 初始化（`QT_QPA_PLATFORM=offscreen`）
5. 执行 `build_release.py`
6. 验证 Windows exe 图标
7. 上传构建产物
8. 在 macOS Runner 上汇总所有产物
9. 生成 SHA-256 校验
10. 替换 GitHub Release 附件

---

## 11. 测试体系

### 11.1 测试结构

```
tests/
├── core/
│   └── test_network_info.py
├── ui/
│   ├── test_gui_model.py
│   └── test_style_architecture.py
├── tools/
│   ├── ip_scanner/
│   │   ├── test_engine.py
│   │   ├── test_hostname.py
│   │   ├── test_storage_export.py
│   │   └── test_targets.py
│   ├── ip_lookup/
│   │   └── test_service.py
│   ├── subnet_calculator/
│   │   └── test_subnet_calculator.py
│   ├── uuid_generator/
│   │   └── test_uuid_generator.py
│   ├── json_formatter/
│   │   └── test_formatter.py
│   ├── text_comparer/
│   │   ├── test_comparer.py
│   │   └── test_syntax.py
│   ├── text_statistics/
│   │   └── test_analyzer.py
│   ├── qr_generator/
│   │   └── test_generator.py
│   ├── wifi_qr_generator/
│   │   └── test_generator.py
│   ├── color_picker/
│   │   └── test_converter.py
│   ├── datetime_converter/
│   │   └── test_converter.py
│   ├── password_strength/
│   │   └── test_analyzer.py
│   ├── random_port/
│   │   └── test_generator.py
│   ├── roman_numeral/
│   │   └── test_converter.py
│   ├── timer/
│   │   └── test_countdown.py
│   ├── token_generator/
│   │   └── test_generator.py
│   └── ipv4_converter/
│       └── test_ipv4_converter.py
└── packaging/
    └── test_packaging.py
```

### 11.2 测试策略

- **核心逻辑优先**：每个工具的纯逻辑模块（`engine.py`、`generator.py`、`converter.py` 等）都有独立测试
- **镜像结构**：测试目录镜像 `src` 结构，便于定位
- **无 GUI 依赖**：核心逻辑测试不需要 PySide6
- **unittest 框架**：使用标准库 `unittest`，无需额外测试依赖

---

## 12. 开发指南

### 12.1 新增工具步骤

1. **创建目录**：`src/fuzztoolbox/tools/<tool_name>/`
2. **创建核心逻辑**：`<logic>.py` — 纯 Python，不依赖 PySide6
3. **创建 UI 页面**：`page.py` — 在页面中实例化核心逻辑
4. **注册工具**：在 `ui/tool_registry.py` 的 `TOOLS` 元组中添加 `ToolDefinition`
5. **装配页面**：在 `ui/main_window.py` 中实例化页面并添加到 `QStackedWidget`，在 `open_tool()` 映射表中注册
6. **创建测试**：`tests/tools/<tool_name>/test_<logic>.py`
7. **添加 QSS**：如需要特殊样式，在 `styles/catalog.qss` 中添加命名样式
8. **添加图标**：在 `assets/` 中添加 SVG 图标

### 12.2 代码规范

- **行宽**：100 字符（`ruff` 配置）
- **Python 版本**：3.9+ 兼容
- **不可变数据类**：配置和结果类优先使用 `frozen=True` dataclass
- **类型注解**：所有公共函数和方法都应添加类型注解
- **错误处理**：使用中文错误信息，保持用户友好
- **异步模式**：IP Scanner 使用 `asyncio`，其他工具使用同步模式

### 12.3 Git 工作流

- **分支命名**：`feature/<tool-name>`、`fix/<description>`
- **提交规范**：中文提交信息
- **构建验证**：修改后必须运行测试 + 重建 macOS 应用 + 验证启动

---

## 13. 附录

### 13.1 端口扫描默认值

| 端口 | 用途 |
|------|------|
| 22 | SSH |
| 80 | HTTP |
| 443 | HTTPS |
| 445 | SMB |
| 3389 | RDP |
| 8080 | HTTP 备用 |

### 13.2 虚拟接口识别

`core/network_info.py` 中的 `VIRTUAL_INTERFACE_HINTS` 用于识别虚拟接口（评分 -100）：

utun, tun, tap, wireguard, tailscale, zerotier, docker, bridge, br-, br0, veth, virbr, vmnet, vbox, vethernet, hyper-v, awdl, llw, loopback, hamachi, ppp

### 13.3 CLI 退出码

| 退出码 | 说明 |
|--------|------|
| 0 | 成功 |
| 2 | 参数错误 |
| 130 | 扫描被用户取消 |

### 13.4 关键文件索引

| 用途 | 文件路径 |
|------|---------|
| 项目配置 | `pyproject.toml` |
| 包入口 | `src/fuzztoolbox/app.py` |
| CLI 入口 | `src/fuzztoolbox/tools/ip_scanner/cli.py` |
| 主窗口 | `src/fuzztoolbox/ui/main_window.py` |
| 扫描引擎 | `src/fuzztoolbox/tools/ip_scanner/engine.py` |
| 样式加载 | `src/fuzztoolbox/ui/style_loader.py` |
| 颜色定义 | `src/fuzztoolbox/ui/theme_colors.py` |
| 构建脚本 | `packaging/build_release.py` |
| macOS 构建 | `scripts/build_macos.sh` |
| CI/CD | `.github/workflows/release-build.yml` |
| 架构文档 | `docs/architecture.md` |