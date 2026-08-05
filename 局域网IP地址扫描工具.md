# IP-Scanner 局域网IP地址扫描工具 — 技术方案文档

## 一、需求概述

### 1.1 项目背景

在企业网络运维、安全审计、设备清点等场景中，快速准确地扫描局域网内活跃主机是一项高频需求。传统的命令行工具（如 `nmap`、`arp-scan`）虽然功能强大，但学习曲线陡峭，且缺乏直观的图形界面，不适合非专业用户使用。同时，现有很多GUI扫描工具在面对大地址段（如A类网段 10.0.0.0/8，约1600万地址）时，往往出现界面卡顿、内存暴涨、扫描速度急剧下降等问题。

IP-Scanner 旨在打造一款**高性能、跨平台、扁平化美观界面**的局域网IP地址扫描工具，既满足专业运维人员的大地址段扫描需求，又兼顾普通用户的易用性。

### 1.2 核心需求

1. **大地址段扫描不卡顿**：支持扫描从 /8 到 /32 任意规模的地址段（如 10.0.0.0 - 10.255.255.255，约1600万地址），扫描过程中UI保持流畅响应，无明显卡顿或假死现象。
2. **扁平化优美界面**：采用现代扁平化设计风格，界面简洁美观，操作直观易用，告别传统工具的生硬感。
3. **跨平台兼容**：原生支持 macOS 和现代 Windows 桌面操作系统，提供一致的用户体验。
4. **软件命名**：软件正式名称为 **IP-Scanner**。

### 1.3 扩展功能需求（推导）

基于核心需求，推导以下必要的扩展功能：

- **多种扫描方式**：支持 ICMP Ping、ARP扫描、TCP端口扫描等多种探测方式，适应不同网络环境。
- **实时结果展示**：扫描过程中实时显示已发现的主机信息，包括IP地址、MAC地址、主机名、响应时间等。
- **扫描历史记录**：自动保存历史扫描结果，支持查看、对比、删除历史记录。
- **结果导出**：支持将扫描结果导出为 CSV、JSON、HTML 等多种格式。
- **扫描配置**：可配置超时时间、重试次数、并发数、扫描端口范围等参数。
- **网段快速选择**：提供常用网段模板（如 192.168.1.0/24、10.0.0.0/8），支持CIDR notation输入。

---

## 二、技术选型

### 2.1 编程语言选择与对比

| 语言 | 优势 | 劣势 | 跨平台支持 | 性能 | 开发效率 |
|------|------|------|------------|------|----------|
| **Python** | 生态丰富、网络库强大、开发速度快、跨平台好 | GIL限制多线程并发、打包后体积大 | ★★★★★ | ★★★ | ★★★★★ |
| **Go** | 原生高并发、goroutine轻量、编译为单文件、跨平台好 | GUI生态较弱、内存占用略高 | ★★★★★ | ★★★★ | ★★★★ |
| **Rust** | 极致性能、内存安全、零成本抽象 | 学习曲线陡峭、开发周期长、GUI生态不成熟 | ★★★★ | ★★★★★ | ★★ |
| **C++/Qt** | 性能优秀、Qt框架成熟 | 编译复杂、跨平台部署麻烦、开发效率低 | ★★★★ | ★★★★★ | ★★ |
| **Java** | 跨平台好、Swing/JavaFX可用 | 需要JVM、启动慢、内存占用高 | ★★★★★ | ★★★ | ★★★★ |

**选型结论：Python + PySide6（Qt for Python）**

理由如下：

1. **开发效率优先**：本项目核心难点在于扫描引擎的并发设计和UI体验，而非极致的底层性能。Python丰富的网络库（`scapy`、`python-nmap`、`icmplib`）可以快速搭建扫描引擎。
2. **Qt框架成熟**：PySide6 是 Qt 官方维护的 Python 绑定，提供了成熟的跨平台GUI组件，扁平化样式支持良好（QSS样式表）。
3. **并发方案可行**：虽然Python有GIL限制，但网络IO密集型场景下，使用 `asyncio` 异步IO + 多进程架构可以有效绕过GIL，达到足够的并发性能。
4. **跨平台打包成熟**：PyInstaller、Nuitka 等工具可以将Python应用打包为各平台原生可执行文件。

> **备选方案**：如果后续对性能有极致要求，可考虑将扫描引擎用 Go/Rust 重写为独立的动态库，Python 通过 FFI 调用。但第一版优先保证开发效率和功能完整性。

### 2.2 GUI库选择与对比

| GUI库 | 风格 | 跨平台 | 扁平化支持 | 与Python集成 | 体积 |
|-------|------|--------|------------|--------------|------|
| **PySide6 (Qt)** | 原生风格+可定制 | 全平台 | ★★★★★（QSS样式表） | 官方绑定，API完整 | 较大（~50MB） |
| Tkinter | 原生风格 | 全平台 | ★★（定制能力弱） | 标准库，零依赖 | 极小 |
| wxPython | 原生风格 | 全平台 | ★★★ | 成熟稳定 | 中等 |
| PyQt5/6 | 同PySide | 全平台 | ★★★★★ | API几乎相同 | 较大 |
| Electron (Web技术) | Web风格 | 全平台 | ★★★★★ | 需Node.js+前端栈 | 极大（~100MB+） |
| Flutter Desktop | Material/Cupertino | 全平台 | ★★★★★ | 需Dart语言 | 中等 |

**选型结论：PySide6**

理由：

1. **QSS样式表**：Qt的样式表机制类似CSS，可以非常精细地控制控件外观，轻松实现扁平化设计。
2. **Model/View架构**：Qt的Model/View框架非常适合展示大量扫描结果（QTableView + QAbstractTableModel），支持虚拟滚动，百万级数据不卡顿。
3. **信号与槽机制**：Qt的信号槽机制天然支持线程间通信，扫描引擎在后台线程运行，通过信号更新UI，避免UI卡顿。
4. **Qt Designer**：可视化UI设计工具，快速搭建界面原型。

### 2.3 核心依赖库

| 功能模块 | 选用库 | 说明 |
|----------|--------|------|
| **GUI框架** | PySide6 | Qt 6 for Python，官方维护 |
| **ICMP扫描** | icmplib | 纯Python实现的ICMP库，无需root权限（部分平台） |
| **ARP扫描** | scapy | 强大的网络包处理库，支持ARP请求 |
| **端口扫描** | asyncio + socket | 异步TCP连接扫描，轻量高效 |
| **主机名解析** | socket.gethostbyaddr | 标准库，反向DNS解析 |
| **MAC厂商查询** | manuf | Wireshark的MAC地址厂商数据库 |
| **数据存储** | SQLite (sqlite3) | 标准库，轻量嵌入式数据库，存历史记录 |
| **异步框架** | asyncio | 标准库，异步IO并发 |
| **进程池** | multiprocessing | 标准库，多进程绕过GIL |
| **打包工具** | PyInstaller | 打包为各平台可执行文件 |

---

## 三、架构设计

### 3.1 整体架构

IP-Scanner 采用**分层架构**设计，自上而下分为四层：

```
┌─────────────────────────────────────────┐
│              UI 表现层                   │
│  (主窗口、扫描面板、结果表格、设置对话框)  │
├─────────────────────────────────────────┤
│            业务逻辑层                    │
│  (扫描任务管理、历史记录管理、导出管理)    │
├─────────────────────────────────────────┤
│            扫描引擎层                    │
│  (ICMP扫描器、ARP扫描器、端口扫描器)      │
├─────────────────────────────────────────┤
│            数据持久层                    │
│  (SQLite数据库、配置文件、导出文件)       │
└─────────────────────────────────────────┘
```

**核心设计原则**：

1. **UI与业务分离**：UI层只负责展示和交互，所有业务逻辑在独立的业务层处理，避免UI线程阻塞。
2. **引擎可插拔**：不同扫描方式（ICMP/ARP/TCP）实现统一接口，可灵活组合和扩展。
3. **数据流式处理**：扫描结果以流式方式实时推送至UI，而非等待全部完成再展示。

### 3.2 多线程/异步扫描模型

针对大地址段扫描不卡顿的核心需求，采用 **"多进程 + 异步IO + 线程池"** 三层并发模型：

#### 3.2.1 架构图

```
┌──────────────────────────────────────────────────────┐
│                     UI 进程 (主线程)                   │
│  Qt事件循环 + 信号槽接收结果 + 实时刷新表格             │
└───────────────────────┬──────────────────────────────┘
                        │  (信号槽 / 进程间通信)
┌───────────────────────▼──────────────────────────────┐
│                  扫描调度进程 (主进程)                  │
│  任务分片 → 分发到Worker进程 → 结果汇总 → 推送UI       │
└───────────┬───────────┬───────────┬──────────────────┘
            │           │           │
     ┌──────▼──┐  ┌─────▼───┐  ┌────▼─────┐
     │Worker 1 │  │Worker 2 │  │Worker N  │  (多进程)
     │asyncio  │  │asyncio  │  │asyncio  │
     │事件循环  │  │事件循环  │  │事件循环  │
     └─────────┘  └─────────┘  └─────────┘
```

#### 3.2.2 各层职责

**第一层：UI进程（Qt主线程）**
- 负责所有UI渲染和用户交互
- 通过Qt信号槽机制接收扫描结果
- 绝对不执行任何阻塞式网络操作
- 使用 `QAbstractTableModel` 的 `beginInsertRows`/`endInsertRows` 批量插入数据，减少重绘次数

**第二层：扫描调度进程（multiprocessing.Process）**
- 独立于UI进程的后台进程，避免扫描逻辑影响UI
- 负责地址段分片、任务分发、结果汇总
- 维护Worker进程池
- 通过 `multiprocessing.Queue` 与UI进程通信

**第三层：Worker进程池（asyncio 异步IO）**
- 每个Worker进程内部运行一个 asyncio 事件循环
- 使用协程进行并发网络探测，单进程可支持数千并发
- 每个Worker负责一个地址分片的扫描
- Worker数量 = CPU核心数（可配置）

#### 3.2.3 为什么不用纯多线程？

Python的GIL（全局解释器锁）导致多线程在CPU密集型场景下无法并行。虽然网络IO密集型场景下线程切换会释放GIL，但：
1. 大量线程（数千个）的上下文切换开销很大
2. scapy等库的底层操作可能持有GIL时间较长
3. 多进程可以真正利用多核CPU，尤其在包构造和解析时

**asyncio 协程 vs 线程**：
- 协程开销远小于线程，单进程可轻松支持上万并发
- 网络IO场景下，asyncio的性能优于线程池
- 代码结构更清晰，异常处理更方便

### 3.3 并发控制机制

#### 3.3.1 三级并发控制

为了避免扫描速度过快导致网络拥塞或被防火墙拦截，同时保证扫描效率，采用三级并发控制：

```
总并发数 = Worker进程数 × 单进程协程并发数
```

| 控制级别 | 配置项 | 默认值 | 说明 |
|----------|--------|--------|------|
| 进程级 | `worker_processes` | CPU核心数 | Worker进程数量 |
| 协程级 | `concurrent_coros` | 500 | 单进程内并发协程数 |
| 速率级 | `packets_per_second` | 0（不限） | 每秒发送数据包上限 |

#### 3.3.2 信号量控制

使用 `asyncio.Semaphore` 控制单进程内的并发协程数：

```python
semaphore = asyncio.Semaphore(concurrent_coros)

async def scan_ip(ip):
    async with semaphore:
        # 执行扫描逻辑
        result = await ping(ip)
        return result
```

#### 3.3.3 令牌桶限速

当配置了 `packets_per_second` 时，使用令牌桶算法限制发包速率：

```python
class TokenBucket:
    def __init__(self, rate, capacity):
        self.rate = rate          # 每秒令牌数
        self.capacity = capacity  # 桶容量
        self.tokens = capacity
        self.last_refill = time.time()
    
    async def consume(self, tokens=1):
        while self.tokens < tokens:
            self._refill()
            if self.tokens < tokens:
                await asyncio.sleep(0.001)
        self.tokens -= tokens
```

### 3.4 线程池设计

虽然主扫描引擎使用多进程+asyncio，但部分场景仍需要线程池：

1. **阻塞式API封装**：某些库只提供同步阻塞API（如部分数据库操作、文件IO），用线程池包裹避免阻塞asyncio事件循环。
2. **CPU密集型任务**：如大量MAC地址厂商查询、结果数据处理等。

**线程池配置**：
- 默认大小：`min(32, os.cpu_count() + 4)`
- 使用 `concurrent.futures.ThreadPoolExecutor`
- 通过 `asyncio.run_in_executor` 调用

### 3.5 数据流向

```
用户输入网段
    ↓
地址解析与分片（CIDR → IP列表 → 分片）
    ↓
分发到Worker进程
    ↓
Worker内 asyncio 并发扫描
    ↓
实时结果 → 结果队列 → 调度进程汇总
    ↓
批量信号 → UI进程 Model更新
    ↓
QTableView 实时刷新
    ↓
扫描完成 → 写入历史记录数据库
```

**关键优化点**：
- 结果不是逐条推送，而是**批量推送**（每100ms或每100条推送一次），大幅减少UI刷新次数
- UI Model使用**增量更新**，而非全量替换
- 大数据量时启用**虚拟滚动**（Qt的 `QTableView` 天然支持）

---

## 四、核心功能模块设计

### 4.1 扫描引擎模块

扫描引擎是IP-Scanner的核心，采用**策略模式**设计，支持多种扫描方式灵活组合。

#### 4.1.1 扫描器接口

```python
class BaseScanner(ABC):
    """扫描器基类"""
    
    @abstractmethod
    async def scan(self, ip: str, timeout: float, retries: int) -> ScanResult:
        """扫描单个IP地址"""
        pass
    
    @abstractmethod
    def name(self) -> str:
        """扫描器名称"""
        pass
```

#### 4.1.2 扫描器实现

**1. ICMP Ping 扫描器（IcmpScanner）**
- 使用 `icmplib` 库，纯Python实现，无需root权限（Windows/macOS下普通用户可发送ICMP）
- 支持设置超时时间、重试次数、数据包大小
- 返回响应时间、TTL等信息
- 优点：标准协议，大多数主机响应，结果可靠
- 缺点：部分防火墙禁Ping，可能漏报

**2. ARP 扫描器（ArpScanner）**
- 使用 `scapy` 发送ARP请求，获取MAC地址
- 仅适用于同一局域网内（二层可达）
- 优点：速度极快，几乎所有主机都会响应ARP，准确率高
- 缺点：只能扫描同一网段，部分实现需要额外的 raw socket 权限

**3. TCP 端口扫描器（TcpScanner）**
- 异步TCP半连接扫描（SYN扫描需要root，改用全连接扫描）
- 可配置扫描端口列表（如常用端口：22, 80, 443, 3389等）
- 优点：禁Ping的主机也能发现，可探测开放服务
- 缺点：速度较慢，容易被防火墙记录

**4. 主机名解析器（HostnameResolver）**
- 反向DNS解析（`socket.gethostbyaddr`）
- 使用线程池异步执行，避免阻塞
- 超时控制，避免慢DNS拖累整体速度

#### 4.1.3 扫描结果数据结构

```python
@dataclass
class ScanResult:
    ip: str                    # IP地址
    is_alive: bool             # 是否存活
    mac: Optional[str] = None  # MAC地址
    mac_vendor: Optional[str] = None  # MAC厂商
    hostname: Optional[str] = None    # 主机名
    response_time: Optional[float] = None  # 响应时间(ms)
    ttl: Optional[int] = None  # TTL
    open_ports: List[int] = None  # 开放端口列表
    scan_time: float = 0.0     # 扫描耗时
    error: Optional[str] = None  # 错误信息
```

### 4.2 结果展示模块

#### 4.2.1 数据模型设计

使用 Qt 的 Model/View 架构，自定义 `ScanResultModel` 继承自 `QAbstractTableModel`：

```python
class ScanResultModel(QAbstractTableModel):
    COLUMNS = [
        ("IP地址", "ip"),
        ("状态", "status"),
        ("MAC地址", "mac"),
        ("厂商", "mac_vendor"),
        ("主机名", "hostname"),
        ("响应时间", "response_time"),
        ("开放端口", "open_ports"),
    ]
    
    def __init__(self):
        super().__init__()
        self._results: List[ScanResult] = []
        self._alive_count = 0
    
    def add_results(self, results: List[ScanResult]):
        """批量添加结果"""
        start = len(self._results)
        end = start + len(results) - 1
        self.beginInsertRows(QModelIndex(), start, end)
        self._results.extend(results)
        for r in results:
            if r.is_alive:
                self._alive_count += 1
        self.endInsertRows()
```

#### 4.2.2 虚拟滚动与性能

`QTableView` + `QAbstractTableModel` 天然支持虚拟滚动：
- 只有可见区域的单元格才会被渲染
- 即使底层有百万条数据，内存中只保存数据本身，渲染开销极小
- 配合 `setUniformRowHeights(True)` 进一步优化

#### 4.2.3 排序与过滤

- 支持按任意列排序（重写 `sort` 方法）
- 支持实时过滤（使用 `QSortFilterProxyModel`）
- 过滤条件：IP地址段、存活/全部、关键字搜索等

### 4.3 历史记录模块

#### 4.3.1 数据库设计

使用 SQLite 存储历史扫描记录，表结构：

```sql
-- 扫描任务表
CREATE TABLE scan_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT,                    -- 任务名称
    target_range TEXT NOT NULL,        -- 扫描范围 (CIDR)
    scan_type TEXT NOT NULL,           -- 扫描类型 (icmp/arp/tcp)
    start_time DATETIME NOT NULL,      -- 开始时间
    end_time DATETIME,                 -- 结束时间
    total_ips INTEGER NOT NULL,        -- 总IP数
    alive_count INTEGER DEFAULT 0,     -- 存活数
    status TEXT DEFAULT 'running',     -- 状态 (running/completed/failed)
    config_json TEXT                   -- 扫描配置(JSON)
);

-- 扫描结果表
CREATE TABLE scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    ip TEXT NOT NULL,
    is_alive INTEGER NOT NULL,
    mac TEXT,
    mac_vendor TEXT,
    hostname TEXT,
    response_time REAL,
    ttl INTEGER,
    open_ports TEXT,                   -- JSON数组
    FOREIGN KEY (task_id) REFERENCES scan_tasks(id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX idx_results_task_id ON scan_results(task_id);
CREATE INDEX idx_results_ip ON scan_results(ip);
```

#### 4.3.2 历史记录功能

- 扫描自动保存，无需手动操作
- 历史记录列表展示：任务名、扫描范围、时间、存活数量
- 支持查看历史详情、重命名、删除、导出
- 支持对比两次扫描结果（新增/消失的主机）

### 4.4 导出功能模块

#### 4.4.1 支持的导出格式

| 格式 | 说明 | 适用场景 |
|------|------|----------|
| **CSV** | 逗号分隔值，通用表格格式 | Excel导入、数据处理 |
| **JSON** | 结构化数据格式 | 程序对接、API集成 |
| **HTML** | 网页格式，带样式 | 直接查看、打印、分享 |
| **TXT** | 纯文本，每行一个IP | 简单列表、脚本输入 |

#### 4.4.2 导出实现

- CSV：使用 `csv` 标准库，流式写入，大数据量不占内存
- JSON：使用 `json` 标准库，支持缩进格式化
- HTML：使用 Jinja2 模板引擎，生成带样式的美观报表
- 导出在后台线程执行，不阻塞UI

### 4.5 配置管理模块

#### 4.5.1 配置项

```json
{
  "scan": {
    "default_scan_type": "icmp",
    "timeout": 1.0,
    "retries": 2,
    "worker_processes": 4,
    "concurrent_coros": 500,
    "packets_per_second": 0,
    "tcp_ports": [22, 80, 443, 3389, 8080]
  },
  "ui": {
    "theme": "light",
    "window_size": [1200, 800],
    "show_mac": true,
    "show_hostname": true
  },
  "history": {
    "auto_save": true,
    "max_records": 100
  }
}
```

#### 4.5.2 配置存储

- 使用 `QSettings` 或 JSON 文件存储
- 配置文件位置：
  - Windows: `%APPDATA%\IP-Scanner\config.json`
  - macOS: `~/Library/Application Support/IP-Scanner/config.json`

---

## 五、UI设计方案

### 5.1 扁平化风格具体方案

#### 5.1.1 设计原则

1. **极简主义**：去除多余的装饰元素（阴影、渐变、立体效果），用色块和线条区分区域
2. **内容优先**：界面以内容为核心，扫描结果占据最大视觉空间
3. **一致的圆角**：统一使用 4px-8px 圆角，避免尖锐棱角
4. **清晰的层次**：通过颜色深浅、间距大小区分信息层级
5. **微动效**：按钮悬停、切换页面时添加平滑过渡动画，提升质感

#### 5.1.2 QSS样式表核心实现

```css
/* 全局样式 */
QWidget {
    background-color: #f5f7fa;
    color: #303133;
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
}

/* 主窗口 */
QMainWindow {
    background-color: #ffffff;
}

/* 按钮 - 扁平化 */
QPushButton {
    background-color: #409eff;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #66b1ff;
}

QPushButton:pressed {
    background-color: #3a8ee6;
}

QPushButton:disabled {
    background-color: #a0cfff;
    color: #ffffff;
}

/* 次要按钮 */
QPushButton[class="secondary"] {
    background-color: #ffffff;
    color: #606266;
    border: 1px solid #dcdfe6;
}

QPushButton[class="secondary"]:hover {
    color: #409eff;
    border-color: #c6e2ff;
    background-color: #ecf5ff;
}

/* 表格 - 扁平化 */
QTableView {
    background-color: white;
    border: 1px solid #ebeef5;
    border-radius: 4px;
    gridline-color: #f0f2f5;
    selection-background-color: #ecf5ff;
    selection-color: #303133;
}

QHeaderView::section {
    background-color: #fafafa;
    color: #606266;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #ebeef5;
    font-weight: 600;
}

/* 输入框 */
QLineEdit, QComboBox {
    border: 1px solid #dcdfe6;
    border-radius: 4px;
    padding: 6px 10px;
    background-color: white;
    selection-background-color: #409eff;
}

QLineEdit:focus, QComboBox:focus {
    border-color: #409eff;
}

/* 进度条 */
QProgressBar {
    border: none;
    background-color: #f0f2f5;
    border-radius: 4px;
    text-align: center;
    height: 8px;
}

QProgressBar::chunk {
    background-color: #409eff;
    border-radius: 4px;
}
```

### 5.2 布局结构

#### 5.2.1 主窗口布局

```
┌─────────────────────────────────────────────────────────┐
│  菜单栏 (File / View / Tools / Help)                     │
├─────────────────────────────────────────────────────────┤
│  工具栏                                                   │
│  [扫描范围输入框] [扫描方式下拉] [开始按钮] [停止按钮]     │
│  [导出] [历史记录] [设置]                                 │
├─────────────────────────────────────────────────────────┤
│  扫描状态栏                                               │
│  进度条  已扫描: 12345 / 16777216  存活: 28  速度: 5000/s │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  扫描结果表格 (占据主要空间)                               │
│  IP地址    状态   MAC地址         厂商    主机名   响应时间 │
│  192.168.1.1  存活  xx:xx:xx:...  华为   router    1ms   │
│  192.168.1.2  存活  xx:xx:xx:...  小米   phone     5ms   │
│  ...                                                    │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  底部状态栏                                               │
│  就绪 | 扫描中... | 完成 (耗时: 12.5s)                    │
└─────────────────────────────────────────────────────────┘
```

#### 5.2.2 侧边栏设计（可选高级模式）

高级模式下左侧增加侧边栏，显示扫描配置、常用网段模板、扫描历史快速访问。

### 5.3 交互流程

#### 5.3.1 快速扫描流程

1. 用户在地址栏输入网段（支持 CIDR 如 `192.168.1.0/24`，或范围 `192.168.1.1-192.168.1.254`）
2. 选择扫描方式（ICMP/ARP/TCP）
3. 点击「开始扫描」按钮
4. 进度条实时更新，结果表格实时刷新
5. 扫描完成后，状态栏显示统计信息

#### 5.3.2 关键交互细节

- **输入验证**：实时验证IP地址格式，非法输入红色边框提示
- **一键填充**：自动检测本机IP，一键填充所在网段
- **暂停/继续**：支持扫描过程中暂停和继续
- **停止确认**：点击停止时弹出确认对话框，防止误操作
- **右键菜单**：结果表格右键支持复制IP、复制MAC、打开网页、扫描端口等

### 5.4 配色建议

#### 5.4.1 主色调（浅色主题）

| 用途 | 颜色值 | 说明 |
|------|--------|------|
| **主色** | `#409EFF` | 品牌蓝，用于按钮、高亮、进度条 |
| **成功色** | `#67C23A` | 存活状态、成功提示 |
| **警告色** | `#E6A23C` | 警告、慢速响应 |
| **危险色** | `#F56C6C` | 错误、失败 |
| **主文字** | `#303133` | 标题、重要文字 |
| **常规文字** | `#606266` | 正文、次要文字 |
| **次要文字** | `#909399` | 辅助说明、时间戳 |
| **边框色** | `#DCDFE6` | 输入框边框、分割线 |
| **背景色** | `#F5F7FA` | 页面背景 |
| **卡片背景** | `#FFFFFF` | 表格、面板背景 |

#### 5.4.2 深色主题（可选）

提供深色主题切换，适合夜间使用：

| 用途 | 颜色值 |
|------|--------|
| 主色 | `#409EFF` |
| 背景 | `#1D1E1F` |
| 卡片背景 | `#2C2D2E` |
| 主文字 | `#E5EAF3` |
| 次要文字 | `#A3A6AD` |
| 边框 | `#3D3E3F` |

---

## 六、跨平台兼容方案

### 6.1 各平台差异处理

#### 6.1.1 Windows 平台（Windows 7+）

**特殊处理点**：

1. **ICMP权限**：Windows Vista及以上，普通用户可以发送ICMP（通过 `IcmpSendEcho` API），`icmplib` 库已封装好，无需管理员权限。
2. **ARP扫描**：需要管理员权限才能发送raw socket。检测到权限不足时，提示用户以管理员身份运行，或自动降级为ICMP扫描。
3. **MAC地址获取**：可以通过 `arp -a` 命令解析ARP缓存，或使用 `GetIpNetTable` API。
4. **打包格式**：`.exe` 可执行文件，可选安装包（NSIS/Inno Setup）。
5. **Windows 7 兼容**：
   - PySide6 最低支持 Windows 8.1，**Windows 7 需要使用 PySide5.15**
   - 提供两个版本：Win7版（PySide5）和现代版（PySide6）
   - 或者统一使用 PySide5.15，兼容性更好

#### 6.1.2 macOS 平台

**特殊处理点**：

1. **ICMP权限**：macOS 下普通用户可以发送 ICMP，无需 sudo。
2. **ARP扫描**：需要 root 权限。检测到权限不足时，弹出授权对话框，使用 `osascript` 提权执行。
3. **菜单栏**：macOS 的菜单栏在屏幕顶部，需要遵循 macOS HIG（人机界面指南）调整菜单项顺序。
4. **Dock 图标**：设置应用图标，支持 Badge 显示未读数量。
5. **打包格式**：`.app` 应用包，可选 `.dmg` 镜像。
6. **公证与签名**：可选进行代码签名和公证，避免 Gatekeeper 拦截。

#### 6.1.3 跨平台抽象层

为了隔离平台差异，设计统一的平台抽象层：

```python
class PlatformAdapter(ABC):
    """平台适配器基类"""
    
    @abstractmethod
    def has_ping_permission(self) -> bool:
        """是否有Ping权限"""
        pass
    
    @abstractmethod
    def has_arp_permission(self) -> bool:
        """是否有ARP扫描权限"""
        pass
    
    @abstractmethod
    def request_arp_permission(self) -> bool:
        """请求ARP扫描权限（提权）"""
        pass
    
    @abstractmethod
    def get_local_ip(self) -> str:
        """获取本机IP"""
        pass
    
    @abstractmethod
    def get_config_dir(self) -> str:
        """获取配置文件目录"""
        pass

# 平台工厂
def get_platform_adapter() -> PlatformAdapter:
    if sys.platform == 'win32':
        return WindowsAdapter()
    elif sys.platform == 'darwin':
        return MacOSAdapter()
    raise RuntimeError('Unsupported operating system')
```

### 6.2 打包部署方案

#### 6.2.1 打包工具选型

使用 **PyInstaller** 作为主打包工具：
- 成熟稳定，跨平台支持好
- 支持单文件/目录模式
- 支持自定义图标、版本信息

**备选**：Nuitka（编译为C，性能更好，但打包慢，兼容性稍差）

#### 6.2.2 各平台打包方案

**Windows**：
- 单文件模式：`IP-Scanner.exe`（约50-60MB）
- 安装包：使用 Inno Setup 制作安装程序
- Win7 版本：单独使用 PySide5 打包

**macOS**：
- 应用包：`IP-Scanner.app`
- DMG 镜像：使用 `create-dmg` 制作带背景的DMG
- 代码签名：`codesign` 签名应用
- 公证：`xcrun notarytool` 提交公证

#### 6.2.3 打包优化

1. **减小体积**：
   - 排除不需要的 Qt 模块（如 QtWebEngine、QtMultimedia 等）
   - 使用 `--exclude-module` 参数排除无用模块
   - UPX 压缩（可选，可能触发杀毒软件误报）
2. **启动优化**：
   - 懒加载模块，启动时只加载必要的
   - 显示启动画面（Splash Screen）
3. **更新机制**：
   - 内置自动更新检查
   - 增量更新（可选）

---

## 七、性能优化策略

### 7.1 大地址段扫描优化

#### 7.1.1 地址分片算法

大地址段（如 /8 网段 1600万地址）不能一次性全部加载到内存，需要**分片处理**：

```python
def split_ip_range(start_ip: str, end_ip: str, chunk_size: int = 10000):
    """将IP范围分片"""
    start = ip_to_int(start_ip)
    end = ip_to_int(end_ip)
    total = end - start + 1
    
    for i in range(0, total, chunk_size):
        chunk_start = start + i
        chunk_end = min(start + i + chunk_size - 1, end)
        yield [int_to_ip(chunk_start + j) for j in range(chunk_end - chunk_start + 1)]
```

**分片策略**：
- 每个 Worker 进程处理一个分片
- 分片大小：10000个IP（可配置）
- 好处：内存中始终只保留一个分片的IP列表，而非全部

#### 7.1.2 渐进式扫描

不是一次性把所有任务都丢给协程，而是**生产者-消费者模式**：

```python
async def scan_worker(ip_generator, result_queue):
    """扫描Worker：渐进式消费IP列表"""
    semaphore = asyncio.Semaphore(500)
    
    async def scan_one(ip):
        async with semaphore:
            result = await ping(ip)
            if result.is_alive:
                await result_queue.put(result)
    
    tasks = []
    for ip in ip_generator:
        task = asyncio.create_task(scan_one(ip))
        tasks.append(task)
        
        # 控制任务队列长度，避免内存暴涨
        if len(tasks) >= 1000:
            done, tasks = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
    
    # 等待剩余任务完成
    if tasks:
        await asyncio.gather(*tasks)
```

**关键优化**：
- IP列表用生成器（generator）按需生成，不一次性展开
- 控制并发任务数量，避免同时创建上百万个协程
- 结果实时输出，不缓存所有结果

#### 7.1.3 自适应并发

根据网络状况动态调整并发数：
- 监控丢包率，如果丢包率过高，自动降低并发
- 监控响应时间，如果平均响应时间上升，降低并发
- 实现简单的 AIMD（加增乘减）拥塞控制算法

### 7.2 内存占用控制

#### 7.2.1 数据结构优化

1. **IP地址存储**：
   - 内部用整数（uint32）存储IP，而非字符串
   - 显示时再转换为字符串
   - 节省内存：字符串约15字节 vs 整数4字节

2. **结果存储**：
   - 只存储存活主机的详细信息
   - 未存活的IP只计数，不存储详细记录
   - 大地址段扫描时，99%的IP不存活，节省大量内存

3. **批量处理**：
   - 结果批量写入数据库，而非逐条写入
   - 使用事务（transaction）批量提交，提升性能

#### 7.2.2 内存上限保护

设置内存使用上限，超过阈值时自动降级：

```python
class MemoryGuard:
    """内存守护：监控内存使用，超过阈值自动降速"""
    
    def __init__(self, max_memory_mb: int = 512):
        self.max_memory = max_memory_mb * 1024 * 1024
    
    def check_memory(self) -> float:
        """检查当前内存使用（MB）"""
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024
    
    async def throttle_if_needed(self):
        """内存过高时节流"""
        current = self.check_memory()
        if current > self.max_memory * 0.8:
            # 内存超过80%，暂停一下
            await asyncio.sleep(0.1)
```

### 7.3 UI响应性保证

#### 7.3.1 UI线程零阻塞原则

- **绝对不在UI线程执行网络操作、文件IO、大量计算**
- 所有耗时操作全部放到后台线程/进程
- 通过信号槽通信，UI线程只处理渲染

#### 7.3.2 批量更新UI

**问题**：如果每秒发现上千台主机，逐条更新UI会导致卡顿。

**解决方案**：批量更新 + 帧率控制

```python
class ResultBuffer(QObject):
    """结果缓冲：批量收集结果，定时刷新UI"""
    
    result_batch = Signal(list)  # 批量结果信号
    
    def __init__(self, flush_interval_ms=100, max_batch_size=200):
        super().__init__()
        self.buffer = []
        self.flush_interval = flush_interval_ms
        self.max_batch_size = max_batch_size
        
        # 定时器定时刷新
        self.timer = QTimer()
        self.timer.timeout.connect(self.flush)
        self.timer.start(flush_interval_ms)
    
    def add_result(self, result):
        self.buffer.append(result)
        if len(self.buffer) >= self.max_batch_size:
            self.flush()
    
    def flush(self):
        if self.buffer:
            batch = self.buffer
            self.buffer = []
            self.result_batch.emit(batch)
```

**效果**：
- 最多每100ms刷新一次UI，每秒最多10次重绘
- 每次最多刷新200条数据，避免单次插入过多
- UI始终保持流畅，即使扫描速度很快

#### 7.3.3 虚拟滚动与懒加载

Qt 的 `QTableView` 已经实现了虚拟滚动，但还有额外优化空间：

1. **设置统一行高**：`setUniformRowHeights(True)`，Qt不需要计算每行高度
2. **禁用自动调整大小**：避免滚动时动态计算列宽
3. **分页加载**：极端情况下（超过10万条存活主机），改用分页加载模式

### 7.4 扫描速度优化

#### 7.4.1 协议选择策略

不同场景选择最优扫描方式：

| 场景 | 推荐扫描方式 | 速度 | 准确率 |
|------|-------------|------|--------|
| 同局域网 | ARP扫描 | ★★★★★ 极快 | ★★★★★ 最高 |
| 跨网段 | ICMP Ping | ★★★★ 快 | ★★★ 一般（禁Ping漏报） |
| 禁Ping环境 | TCP扫描 | ★★ 较慢 | ★★★★ 较高 |

**智能模式**：先尝试ARP，失败自动降级为ICMP，再失败降级为TCP。

#### 7.4.2 超时与重试优化

1. **自适应超时**：
   - 前100个IP测量平均响应时间
   - 根据平均响应时间动态调整超时值
   - 局域网内通常 <1ms，超时设为 500ms 足够
   - 跨网段可能较慢，超时设为 1-2s

2. **重试策略**：
   - 第一次超时不立即判定为不存活
   - 快速重试1次（间隔很短），如果仍超时再判定
   - 可配置重试次数

#### 7.4.3 预解析与缓存

1. **MAC厂商数据库**：
   - 启动时预加载到内存（字典结构，O(1)查询）
   - 使用 manuf 库的数据库，约3万条记录

2. **DNS解析缓存**：
   - 相同IP的主机名解析结果缓存
   - 避免重复解析

3. **常用端口缓存**：
   - 常用端口列表预编译，避免重复构造

#### 7.4.4 多核利用

通过多进程架构充分利用多核CPU：
- Worker进程数 = CPU核心数
- 每个进程独立运行asyncio事件循环
- 进程间通过队列通信，开销很小

**理论加速比**：接近线性（N核 → N倍加速），因为网络IO是主要瓶颈。

---

## 八、总结

IP-Scanner 技术方案围绕**"大地址段扫描不卡顿、扁平化优美界面、跨平台兼容"**三大核心需求展开，采用 Python + PySide6 技术栈，通过"多进程 + 异步IO + 批量UI更新"的三层架构实现高性能扫描，同时保证界面流畅。

方案兼顾了**开发效率**（Python生态丰富、Qt框架成熟）和**性能表现**（多进程绕过GIL、asyncio高并发、多种优化策略），能够满足从 /24 小网段到 /8 大地址段的各种扫描场景需求，同时提供美观的扁平化界面和良好的跨平台体验。

下一步可基于本方案进入详细设计与编码阶段，优先实现核心扫描引擎和基础UI，再逐步完善历史记录、导出、高级设置等功能。
