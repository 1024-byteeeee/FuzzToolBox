"""PySide6 page for IP information lookup."""

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from fuzztoolbox.ui.components import SkeletonBar
from fuzztoolbox.ui.style_loader import apply_style

from .service import LookupReport, discover_public_ips, lookup


class IPValueCard(QFrame):
    def __init__(self, title, copied):
        super().__init__()
        self.title = title
        self.value = "—"
        self.setObjectName("ipValueCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 12, 12)
        layout.setSpacing(5)
        heading = QHBoxLayout()
        label = QLabel(title)
        label.setObjectName("ipValueTitle")
        self.copy_button = QPushButton("复制")
        self.copy_button.setObjectName("ipValueCopy")
        self.copy_button.setCursor(Qt.PointingHandCursor)
        self.copy_button.clicked.connect(lambda: copied(self))
        heading.addWidget(label)
        heading.addStretch()
        heading.addWidget(self.copy_button)
        layout.addLayout(heading)
        self.value_label = QLabel("—")
        self.value_label.setObjectName("ipValueText")
        self.value_label.setWordWrap(True)
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.value_label)

    def set_value(self, value):
        self.value = value
        self.value_label.setText(value)
        self.setProperty("missing", value in {"未检测到", "未提供", "未找到 PTR 记录"})
        self.style().unpolish(self)
        self.style().polish(self)


class LookupWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, ip: str, current_ipv4: str = "", current_ipv6: str = ""):
        super().__init__()
        self.ip = ip
        self.current_ipv4 = current_ipv4
        self.current_ipv6 = current_ipv6

    def run(self):
        try:
            target = self.ip.strip()
            current_ipv4 = self.current_ipv4
            current_ipv6 = self.current_ipv6
            if not current_ipv4 and not current_ipv6:
                current_ipv4, current_ipv6 = discover_public_ips()
            if not target:
                target = current_ipv4 or current_ipv6
            if not target:
                raise ValueError("无法获取当前公网 IP，请输入指定 IP")
            report = lookup(target)
            report.current_ipv4 = current_ipv4
            report.current_ipv6 = current_ipv6
            self.completed.emit(report)
        except (OSError, ValueError) as exc:
            self.failed.emit(str(exc))


class PublicIPWorker(QThread):
    completed = Signal(str, str)

    def run(self):
        self.completed.emit(*discover_public_ips())


def format_report(report: LookupReport) -> str:
    def shown(value):
        if value is None:
            return "未提供"
        if isinstance(value, bool):
            return "是" if value else "否"
        return str(value)

    lines = [
        f"当前公网 IPv4：{report.current_ipv4 or '未检测到'}",
        f"当前公网 IPv6：{report.current_ipv6 or '未检测到'}",
        "",
        f"IP：{report.ip}",
        f"分类：{report.classification}",
        f"PTR / rDNS：{report.ptr or '未找到'}",
        f"国家 / 地区 / 城市：{shown(report.merged('country'))} / "
        f"{shown(report.merged('region'))} / {shown(report.merged('city'))}",
        f"ASN：{shown(report.merged('asn'))}",
        f"ISP：{shown(report.merged('isp'))}",
        f"组织：{shown(report.merged('org'))}",
    ]
    return "\n".join(lines)


class IPLookupPage(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.public_ip_worker = None
        self._current_ipv4 = ""
        self._current_ipv6 = ""
        self._public_ip_pending = False
        self._report_text = ""
        self._result_columns = 2
        self._detail_cards = []
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(12)

        intro = QLabel(
            "查询当前或指定公网 IP 的归属、ASN、ISP 与 PTR / rDNS 信息"
        )
        apply_style(intro, "tools.ip_lookup.page:132")
        root.addWidget(intro)

        query_row = QHBoxLayout()
        self.ip_label = QLabel("IP 地址")
        apply_style(self.ip_label, "tools.ip_lookup.page:137")
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("正在获取当前公网 IP…")
        self.ip_input.setMinimumHeight(40)
        self.query_button = QPushButton("开始查询")
        self.query_button.setMinimumHeight(40)
        self.my_ip_button = QPushButton("查询当前公网 IP")
        self.my_ip_button.setObjectName("secondary")
        self.my_ip_button.setMinimumHeight(40)
        query_row.addWidget(self.ip_label)
        query_row.addWidget(self.ip_input, 1)
        query_row.addWidget(self.my_ip_button)
        query_row.addWidget(self.query_button)
        root.addLayout(query_row)

        self.status = QLabel("准备就绪")
        apply_style(self.status, "tools.ip_lookup.page:153")
        root.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.result_card = QFrame()
        self.result_card.setObjectName("ipLookupResultCard")
        apply_style(self.result_card, "tools.ip_lookup.page:164")
        result_layout = QVBoxLayout(self.result_card)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(10)
        self.result_state = QLabel("输入公网 IP 后开始查询，结果将在这里显示")
        self.result_state.setObjectName("ipResultState")
        self.result_state.setAlignment(Qt.AlignCenter)
        result_layout.addWidget(self.result_state)

        self.skeleton_content = self._build_skeleton_content()
        self.skeleton_content.setVisible(False)
        result_layout.addWidget(self.skeleton_content)

        self.result_content = QWidget()
        content = QVBoxLayout(self.result_content)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(10)
        hero = QFrame()
        hero.setObjectName("ipHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(18, 14, 18, 16)
        hero_top = QHBoxLayout()
        caption = QLabel("查询地址")
        caption.setObjectName("ipHeroCaption")
        self.hero_state = QLabel("● 查询完成")
        self.hero_state.setObjectName("ipOnlineDot")
        hero_top.addWidget(caption)
        hero_top.addStretch()
        hero_top.addWidget(self.hero_state)
        hero_layout.addLayout(hero_top)
        self.hero_ip = QLabel("—")
        self.hero_ip.setObjectName("ipHeroValue")
        self.hero_ip.setTextInteractionFlags(Qt.TextSelectableByMouse)
        hero_layout.addWidget(self.hero_ip)
        badges = QHBoxLayout()
        self.version_badge = QLabel("IPv4")
        self.version_badge.setObjectName("ipHeroBadge")
        self.classification_badge = QLabel("公网地址")
        self.classification_badge.setObjectName("ipHeroBadge")
        badges.addWidget(self.version_badge)
        badges.addWidget(self.classification_badge)
        badges.addStretch()
        hero_layout.addLayout(badges)
        content.addWidget(hero)

        self.result_values = {}
        self.current_group, self.current_grid = self._make_result_group(
            "当前公网地址", (("current_ipv4", "IPv4"), ("current_ipv6", "IPv6"))
        )
        content.addWidget(self.current_group)
        self.details_group, self.details_grid = self._make_result_group(
            "详细信息",
            (("location", "地理位置"), ("asn", "ASN"), ("isp", "ISP"),
             ("org", "组织"), ("ptr", "PTR / rDNS")),
        )
        content.addWidget(self.details_group)
        content.addStretch()
        self.result_content.setVisible(False)
        result_layout.addWidget(self.result_content)
        root.addWidget(self.result_card, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        self.copy_button = QPushButton("复制检测报告")
        self.copy_button.setObjectName("secondary")
        self.copy_button.setEnabled(False)
        actions.addWidget(self.copy_button)
        root.addLayout(actions)

        self.query_button.clicked.connect(self.start_lookup)
        self.my_ip_button.clicked.connect(self._load_public_ip)
        self.ip_input.returnPressed.connect(self.start_lookup)
        self.copy_button.clicked.connect(self.copy_report)
        self.public_ip_timeout = QTimer(self)
        self.public_ip_timeout.setSingleShot(True)
        self.public_ip_timeout.setInterval(30_000)
        self.public_ip_timeout.timeout.connect(self._public_ip_timed_out)

    def _make_result_group(self, title, fields):
        group = QFrame()
        group.setObjectName("ipGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(9)
        heading = QLabel(title)
        heading.setObjectName("ipGroupTitle")
        layout.addWidget(heading)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for index, (key, label) in enumerate(fields):
            card = IPValueCard(label, self._copy_value)
            self.result_values[key] = card
            if title == "详细信息":
                self._detail_cards.append((key, card))
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        return group, grid

    def _build_skeleton_content(self):
        """Build a skeleton placeholder mirroring the real result layout."""
        content = QWidget()
        content.setObjectName("ipSkeletonContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        hero = QFrame()
        hero.setObjectName("ipSkeletonHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(18, 14, 18, 16)
        hero_layout.setSpacing(6)
        # 与真实 hero 一致：标题行 23px（含状态点）、地址 29px、徽章 21px、行距 6px。
        hero_layout.addWidget(SkeletonBar(height=23, width_ratio=0.18))
        hero_layout.addWidget(SkeletonBar(height=29, width_ratio=0.42))
        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        badge_row.addWidget(SkeletonBar(height=21, width_ratio=1.0))
        badge_row.addWidget(SkeletonBar(height=21, width_ratio=1.0))
        badge_row.addStretch()
        hero_layout.addLayout(badge_row)
        layout.addWidget(hero)

        for card_count in (2, 5):
            group = QFrame()
            group.setObjectName("ipSkeletonGroup")
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(14, 12, 14, 14)
            group_layout.setSpacing(9)
            # 与真实分组标题一致：21px。
            group_layout.addWidget(SkeletonBar(height=21, width_ratio=0.22))
            grid = QGridLayout()
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(10)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            for index in range(card_count):
                card = QFrame()
                card.setObjectName("ipSkeletonCard")
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(14, 11, 12, 12)
                card_layout.setSpacing(5)
                # 与真实值卡片一致：标题 23px、值 17px。
                card_layout.addWidget(SkeletonBar(height=23, width_ratio=0.30))
                card_layout.addWidget(SkeletonBar(height=17, width_ratio=0.65))
                grid.addWidget(card, index // 2, index % 2)
            group_layout.addLayout(grid)
            layout.addWidget(group)

        layout.addStretch()
        return content

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = 1 if event.size().width() < 820 else 2
        if columns == self._result_columns:
            return
        self._result_columns = columns
        for index, (_key, card) in enumerate(self._detail_cards):
            self.details_grid.removeWidget(card)
            self.details_grid.addWidget(card, index // columns, index % columns)

    def showEvent(self, event):
        super().showEvent(event)
        lookup_running = self.worker and self.worker.isRunning()
        public_ip_running = self.public_ip_worker and self.public_ip_worker.isRunning()
        if not lookup_running and not public_ip_running:
            self._load_public_ip()

    def _load_public_ip(self):
        self._public_ip_pending = True
        self.ip_input.setEnabled(False)
        self.query_button.setEnabled(False)
        self.my_ip_button.setEnabled(False)
        self.progress.setVisible(True)
        self.status.setText("正在获取当前公网 IP…")
        self.public_ip_timeout.start()
        self.public_ip_worker = PublicIPWorker()
        self.public_ip_worker.completed.connect(self._set_public_ip)
        self.public_ip_worker.start()

    def _set_public_ip(self, ipv4: str, ipv6: str):
        if not self._public_ip_pending:
            return
        self._public_ip_pending = False
        self.public_ip_timeout.stop()
        self._current_ipv4 = ipv4
        self._current_ipv6 = ipv6
        if ipv4 or ipv6:
            self.ip_input.setText(ipv4 or ipv6)
            self.status.setText("已获取当前公网 IP")
        else:
            self.status.setText("获取当前公网 IP 失败，请手动输入")
        self.ip_input.setPlaceholderText("输入公网 IPv4 / IPv6")
        self.ip_input.setEnabled(True)
        self.query_button.setEnabled(True)
        self.my_ip_button.setEnabled(True)
        self.progress.setVisible(False)
        if ipv4 or ipv6:
            self.start_lookup()

    def _public_ip_timed_out(self):
        if not self._public_ip_pending:
            return
        self._public_ip_pending = False
        self.ip_input.setPlaceholderText("输入公网 IPv4 / IPv6")
        self.ip_input.setEnabled(True)
        self.query_button.setEnabled(True)
        self.my_ip_button.setEnabled(True)
        self.progress.setVisible(False)
        self.status.setText("获取当前公网 IP 超时（30 秒），请手动输入")

    def start_lookup(self):
        if self.worker and self.worker.isRunning():
            return
        self.ip_input.setEnabled(False)
        self.query_button.setEnabled(False)
        self.my_ip_button.setEnabled(False)
        self.copy_button.setEnabled(False)
        self.progress.setVisible(True)
        self.status.setText("正在查询 IP 信息…")
        self._show_loading_state()
        self.worker = LookupWorker(
            self.ip_input.text(), self._current_ipv4, self._current_ipv6
        )
        self.worker.completed.connect(self._show_report)
        self.worker.failed.connect(self._show_error)
        self.worker.finished.connect(self._lookup_finished)
        self.worker.start()

    def _lookup_finished(self):
        self.ip_input.setEnabled(True)
        self.query_button.setEnabled(True)
        self.my_ip_button.setEnabled(True)
        self.progress.setVisible(False)

    def _show_report(self, report: LookupReport):
        def shown(value, fallback="未提供"):
            return fallback if value in (None, "") else str(value)

        self._report_text = format_report(report)
        location = " / ".join(
            shown(report.merged(key)) for key in ("country", "region", "city")
        )
        values = {
            "current_ipv4": report.current_ipv4 or "未检测到",
            "current_ipv6": report.current_ipv6 or "未检测到",
            "ip": report.ip,
            "classification": report.classification,
            "location": location,
            "asn": shown(report.merged("asn")),
            "isp": shown(report.merged("isp")),
            "org": shown(report.merged("org")),
            "ptr": report.ptr or "未找到 PTR 记录",
        }
        for key, value in values.items():
            if key in self.result_values:
                self.result_values[key].set_value(value)
        classification_parts = report.classification.split(" · ")
        self.hero_ip.setText(report.ip)
        self.version_badge.setText(classification_parts[0])
        self.classification_badge.setText(" · ".join(classification_parts[1:]) or "公网地址")
        self.result_state.setVisible(False)
        self.skeleton_content.setVisible(False)
        self.result_content.setVisible(True)
        self.status.setText("查询完成")
        self.copy_button.setEnabled(True)

    def _show_error(self, message: str):
        self._report_text = ""
        self.copy_button.setEnabled(False)
        self.result_content.setVisible(False)
        self.skeleton_content.setVisible(False)
        self.result_state.setText(f"查询失败\n{message}")
        apply_style(self.result_state, "tools.ip_lookup.page:405")
        self.result_state.setVisible(True)
        self.status.setText(f"查询失败：{message}")

    def copy_report(self):
        QGuiApplication.clipboard().setText(self._report_text)
        self.status.setText("检测报告已复制")

    def _show_loading_state(self):
        self.result_content.setVisible(False)
        self.result_state.setVisible(False)
        # 查询期间用骨架屏占位，结构贴近最终结果，减少加载完成后的跳变。
        self.skeleton_content.setVisible(True)

    def _copy_value(self, card):
        if card.value in {"—", "未检测到", "未提供", "未找到 PTR 记录"}:
            return
        QGuiApplication.clipboard().setText(card.value)
        card.copy_button.setText("已复制")
        QTimer.singleShot(900, lambda: card.copy_button.setText("复制"))
        self.status.setText(f"已复制 · {card.title}")

    def prepare_close(self, on_ready) -> bool:
        workers = (self.worker, self.public_ip_worker)
        running = [worker for worker in workers if worker and worker.isRunning()]
        if running:
            self.status.setText("正在完成网络查询，完成后将自动关闭…")
            running[-1].finished.connect(on_ready)
            return False
        return True
