# -*- coding: utf-8 -*-
"""导出设计面板 —— 对应原 DEDD 项目的 ResultPanel

展示：设计方案（设计图示 + 患者信息 + 日期）
     口内对比图（设计前 / 设计后）
     正面对比图（设计前 / 设计后）
并提供"保存设计图"（jpg）
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from ..constants import (AFTER, AGE, AGE_SUFFIX, BEFORE, COMPARE_BASE,
                         COMPARE_FRONT, DATE, DESIGN_LABEL, GENDER, NAME,
                         PHONE, SCALE_LABEL, TITLE_DESIGN, UNKNOWN)
from ..image_utils import np_to_qimage, qimage_bytes
from ..models import BasicInfo, ToothData


class _ImgBox(QWidget):
    """带标题的图片显示框"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        self.label = QLabel(title, self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("font-weight: bold;")
        self.img_label = QLabel(self)
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setMinimumSize(260, 120)
        self.img_label.setStyleSheet("background:#111; border:1px solid #3366aa;")
        lay.addWidget(self.label)
        lay.addWidget(self.img_label)

    def set_image(self, np_img: Optional[np.ndarray]):
        if np_img is None:
            self.img_label.setPixmap(QPixmap())
            return
        qimg = np_to_qimage(np_img)
        pm = QPixmap.fromImage(qimg)
        max_w, max_h = 420, 320
        if pm.width() > max_w or pm.height() > max_h:
            pm = pm.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.img_label.setPixmap(pm)


class ResultPanel(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)

        root = QWidget()
        self.setWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        title = QLabel(TITLE_DESIGN)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:22px; font-weight:bold;")
        lay.addWidget(title)

        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.info_label)

        self.design_box = _ImgBox(DESIGN_LABEL)
        lay.addWidget(self.design_box)

        row = QHBoxLayout()
        self.base_before = _ImgBox(BEFORE)
        self.base_after = _ImgBox(AFTER)
        row.addWidget(self.base_before)
        row.addWidget(self.base_after)
        wrap = QWidget()
        wrap.setLayout(row)
        wrap.setStyleSheet("QWidget { border: 1px solid #446; }")
        lay.addWidget(wrap)

        row2 = QHBoxLayout()
        self.front_before = _ImgBox(BEFORE)
        self.front_after = _ImgBox(AFTER)
        row2.addWidget(self.front_before)
        row2.addWidget(self.front_after)
        wrap2 = QWidget()
        wrap2.setLayout(row2)
        wrap2.setStyleSheet("QWidget { border: 1px solid #446; }")
        lay.addWidget(wrap2)

        # 美学参数标尺（导出增强：依据期刊文章，随设计图一并输出）
        est_head = QLabel("美学参数标尺")
        est_head.setAlignment(Qt.AlignCenter)
        est_head.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 6px;")
        lay.addWidget(est_head)
        self.est_label = QLabel("")
        self.est_label.setAlignment(Qt.AlignCenter)
        self.est_label.setWordWrap(True)
        self.est_label.setTextFormat(Qt.RichText)
        lay.addWidget(self.est_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.save_btn = QPushButton("保存设计图(JPG)")
        self.save_btn.setFixedWidth(160)
        btn_row.addWidget(self.save_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.set_info(BasicInfo())

    def set_info(self, info: BasicInfo):
        gender = info.gender or UNKNOWN
        age = str(info.age) + AGE_SUFFIX if info.age else UNKNOWN
        self.info_label.setText(
            f"{NAME}: {info.name or UNKNOWN}    {GENDER}: {gender}    "
            f"{AGE}: {age}    {PHONE}: {info.phone or UNKNOWN}    {DATE}: {date.today().isoformat()}")

    def set_design(self, design: Optional[np.ndarray], teeth: Optional[list]):
        """设计图示（带牙位/宽长比标注）"""
        if design is None:
            self.design_box.set_image(None)
            return
        marked = design.copy()
        qimg = np_to_qimage(marked)
        painter = QPainter(qimg)
        painter.setRenderHint(QPainter.Antialiasing, True)
        h, w = marked.shape[:2]
        scale_x = w / 1000.0
        font = painter.font()
        font.setPointSizeF(max(8, 11 * scale_x))
        painter.setFont(font)
        painter.setPen(QPen(QColor(255, 220, 0), max(1, int(2 * scale_x))))
        if teeth:
            for t in teeth:
                if not isinstance(t, ToothData):
                    continue
                r = t.rect
                x1, y1, x2, y2 = (int(r.x1), int(r.y1), int(r.x2), int(r.y2))
                painter.drawRect(x1, y1, x2 - x1, y2 - y1)
                label = f"{t.site}  {SCALE_LABEL}:{((x2-x1)/(y2-y1)):.2f}" if (y2 - y1) else str(t.site)
                painter.drawText(x1, max(0, y1 - 4), label)
        painter.end()
        self.design_box.set_image(_qimg_to_np(qimg))

    def set_compare(self, which: str, before: Optional[np.ndarray], after: Optional[np.ndarray]):
        if which == "base":
            self.base_before.set_image(before)
            self.base_after.set_image(after)
        else:
            self.front_before.set_image(before)
            self.front_after.set_image(after)

    def set_esthetics(self, html: str):
        """美学参数标尺（宽长比/宽度比/龈缘等，随导出图输出）"""
        self.est_label.setText(html)


def _qimg_to_np(qimg: QImage) -> np.ndarray:
    qimg = qimg.convertToFormat(QImage.Format_RGB888)
    w, h = qimg.width(), qimg.height()
    buf = qimage_bytes(qimg)
    bpl = qimg.bytesPerLine()
    arr = np.frombuffer(buf, np.uint8).reshape(h, bpl)
    if bpl != w * 3:
        arr = arr[:, : w * 3]
    return arr.reshape(h, w, 3).copy()
