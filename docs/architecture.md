# FuzzToolBox 架构

FuzzToolBox 使用 Python `src` 布局。产品代码位于 `src/fuzztoolbox`，每个工具都以
“独立核心逻辑 + 独立页面”的形式放在 `tools` 下。

## 目录职责

- `fuzztoolbox/app.py`：稳定的桌面应用入口，不承载业务逻辑。
- `fuzztoolbox/core/`：多个工具共享的系统与网络服务。
- `fuzztoolbox/ui/`：主窗口、首页、工具注册表、应用状态和公共控件。
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

## 应用外壳与原生能力

- `ui/app_state.py` 是设置、快捷键动作和截图/取色会话的统一状态边界。主窗口负责
  展示与调度，不自行保存并行会话标志。
- `ui/global_hotkey.py` 是稳定兼容门面；快捷键解析、生命周期管理以及 Windows、
  macOS 原生注册分别位于 `ui/hotkeys/`。平台 API 不应重新进入主窗口。
- `ui/single_instance.py` 独占单例锁与本地 IPC。主窗口进入事件循环且原生窗口可见后
  才发布运行期 ready 标记；重复启动只有在旧窗口恢复可见并返回确认后才算成功。
  测试必须传入独立临时运行目录，禁止使用正式应用的锁或端点。

## 截图模块

`tools/screenshot/overlay.py` 只编排输入事件和界面生命周期，具体能力位于：

- `capture_backend.py`：平台捕获调度、失败收敛、虚拟桌面计算与多屏拼接。
- `selection.py`：选区锚点、缩放、Dock 候选区域与几何去重。
- `annotations.py`：标注数据、笔迹插值、命中检测与平移。
- `renderer.py`：图形、文字、箭头与马赛克渲染。
- `controls.py`：截图工具条使用的基础控件。
- `toolbar.py`：工具条、颜色/粗细/字号/字体弹层及其语义信号。

新增截图功能时优先扩展对应深模块，避免把平台调用、几何、状态和绘制重新堆回
覆盖层类。

## 质量门禁

- 本地和 Release CI 均运行 Ruff 与自动化测试。
- `tests/native/` 验证冻结应用的可见窗口就绪和单例激活握手；测试必须带超时、校验
  ready/activation 标记，并在失败后清理进程及运行期文件。
- 原生快捷键、屏幕录制等受系统权限控制的能力，以适配器契约和资源释放测试为主，
  不在无桌面权限的 CI 中伪造端到端成功。

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
