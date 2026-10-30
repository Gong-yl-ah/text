# -*- coding: utf-8 -*-
"""启动引导页 —— 未打开项目时显示，取代原来的空白区域

三个入口：新建项目 / 打开已有工程 / 打开示例工程，并给出六步流程速览。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from .. import constants as C

_FLOW = [
    ("1", C.TAB_EDIT, "双击左/右视图载入正面照、口内照"),
    ("2", C.TAB_UNIFY, "检查咬合平面，必要时左右旋转"),
    ("3", C.TAB_MARK_LIP, "点几下勾出唇线（可跳过）"),
    ("4", C.TAB_MARK_TEETH, "AI 检测自动生成牙位框，再手动微调"),
    ("5", C.TAB_ADJUST, "拖框/右键调亮度黄度，或点『自动优化』"),
    ("6", C.TAB_EXPORT, "查看前后对比，保存 JPG"),
]


class _BigButton(QPushButton):
    def __init__(self, text: str, hint: str, primary: bool = False, parent=None):
        super().__init__(parent)
        self.setText(f"{text}\n{hint}")
        self.setMinimumHeight(76)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton {"
            f"background: {'#1a73e8' if primary else '#f2f3f5'};"
            f"color: {'#ffffff' if primary else '#202124'};"
            "border: 1px solid " + ("#1a73e8" if primary else "#d7d9dd") + ";"
            "border-radius: 8px; padding: 10px 18px; font-size: 15px; text-align: left;"
            "}"
            "QPushButton:hover { border-color: #1a73e8; }"
        )


class WelcomePanel(QWidget):
    """启动引导页"""

    new_requested = Signal()
    open_requested = Signal()
    sample_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WelcomePanel")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(48, 36, 48, 36)
        outer.setSpacing(18)

        title = QLabel(C.APP_NAME)
        title.setStyleSheet("font-size: 26px; font-weight: 600; color: #202124;")
        outer.addWidget(title)

        sub = QLabel(
            "纯本地运行 · 无需联网 · 照片不出本机。先新建一个工程，或直接打开已有 .deddp 工程。"
        )
        sub.setStyleSheet("font-size: 13px; color: #5f6368;")
        outer.addWidget(sub)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.btn_new = _BigButton("新建项目", "填写患者信息，开始一次新的美学设计", primary=True)
        self.btn_open = _BigButton("打开已有工程", "读取 .deddp 工程，或导入原版 .depx")
        self.btn_sample = _BigButton("打开示例工程", "用内置示例快速熟悉流程")
        for b in (self.btn_new, self.btn_open, self.btn_sample):
            btn_row.addWidget(b, 1)
        outer.addLayout(btn_row)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #e3e5e8;")
        outer.addWidget(line)

        flow_title = QLabel("流程速览（顶部标签依次对应这六步；熟练后可点工具栏『一键完成』）")
        flow_title.setStyleSheet("font-size: 13px; font-weight: 600; color: #202124;")
        outer.addWidget(flow_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        for i, (num, name, desc) in enumerate(_FLOW):
            badge = QLabel(num)
            badge.setFixedSize(22, 22)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                "background: #e8f0fe; color: #1a73e8; border-radius: 11px;"
                "font-size: 12px; font-weight: 600;"
            )
            label = QLabel(f"<b>{name}</b>　{desc}")
            label.setStyleSheet("font-size: 13px; color: #3c4043;")
            grid.addWidget(badge, i, 0, Qt.AlignTop)
            grid.addWidget(label, i, 1)
        grid.setColumnStretch(1, 1)
        outer.addLayout(grid)

        outer.addStretch(1)

        self.btn_new.clicked.connect(self.new_requested)
        self.btn_open.clicked.connect(self.open_requested)
        self.btn_sample.clicked.connect(self.sample_requested)
