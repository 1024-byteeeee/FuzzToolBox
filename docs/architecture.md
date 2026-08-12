# FuzzToolBox 架构

FuzzToolBox 使用 Python `src` 布局。产品代码位于 `src/fuzztoolbox`，每个工具都以
“独立核心逻辑 + 独立页面”的形式放在 `tools` 下。

## 目录职责

- `fuzztoolbox/app.py`：稳定的桌面应用入口，不承载业务逻辑。
- `fuzztoolbox/core/`：多个工具共享的系统与网络服务。
- `fuzztoolbox/ui/`：主窗口、首页、工具注册表和公共控件。
- `fuzztoolbox/tools/`：各工具的业务逻辑、数据模型和页面。
- `fuzztoolbox/assets/`：随应用打包的图标与 SVG 资源。
- `tests/`：按 `core`、`ui`、`tools`、`packaging` 镜像源码职责组织。
- `packaging/`：PyInstaller、macOS、Windows 安装包配置。
- `scripts/`：开发者使用的构建入口。
- `docs/archive/`：仅供追溯的 IP Scanner 初期方案，不代表当前产品结构。

## 工具模块约定

新增工具时创建 `fuzztoolbox/tools/<tool_name>/`：

- 纯计算或系统逻辑放在独立模块中，不依赖 PySide6。
- 页面统一命名为 `page.py`。
- 工具元数据在 `ui/tool_registry.py` 注册。
- 页面在主窗口装配，并复用 `ui/components.py` 中的公共控件行为。
- 测试放在 `tests/tools/<tool_name>/`。

## UI 约定

- 使用统一背景、卡片、圆角、字号和间距。
- 下拉列表必须通过公共配置函数创建，保持单层圆角和一致高亮。
- 表格必须通过公共配置函数创建，保持边框、选中逻辑和响应式列宽。
- 按钮按主要、辅助、中性、危险用途选择样式，并提供 hover、pressed、focus、disabled 状态。
- 网络工具需要时复用统一的本机网络信息栏。
- 标签和输入控件组成紧凑分组，不使用会被窗口宽度拉大的空白标签列。

## 命名边界

`FuzzToolBox` 是产品名和应用包名；`IP Scanner` 是其中一个工具。工具 ID
`ip-scanner` 为稳定内部标识，可以保留。构建脚本中对旧 `IP-Scanner` 产物的清理仅用于
升级兼容，不代表当前产品名称。
