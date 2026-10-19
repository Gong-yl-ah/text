# -*- coding: utf-8 -*-
"""图像视图 —— 对应原 DEDD 项目的 EditableImageView / ImageView / ZoomableJPanel

- 显示图像，自适应缩放（fit）
- 滚轮缩放、中键拖拽平移
- 提供 图像坐标 <-> 视图坐标 变换
- 叠加子层（标记面板/调整面板）共享同一变换
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

from ..image_utils import np_to_qimage

from PySide6.QtWidgets import QWidget


class ImageView(QWidget):
    """图像显示基类：管理 scale/offset，提供坐标变换与平移缩放"""
    image_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._qimage: Optional[QImage] = None
        self._hint_text = ""          # 无图时中央提示文字
        self.scale = 1.0          # 图像->视图 比例
        self.offset_x = 0.0       # 图像原点到视图原点偏移
        self.offset_y = 0.0
        self._fit_scale = 1.0
        self._auto_fit = True
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # ---------- 无图提示 ----------
    def set_hint(self, text: str):
        self._hint_text = text or ""
        self.update()

    # ---------- 图像设置 ----------
    def set_image(self, img):
        if img is None:
            self._qimage = None
        elif isinstance(img, QImage):
            self._qimage = img
        elif isinstance(img, np.ndarray):
            self._qimage = np_to_qimage(img)
        elif isinstance(img, QPixmap):
            self._qimage = img.toImage()
        else:
            self._qimage = None
        self._apply_fit()
        self.image_changed.emit()
        self.update()

    def get_image(self) -> Optional[QImage]:
        return self._qimage

    def has_image(self) -> bool:
        return self._qimage is not None and not self._qimage.isNull()

    # ---------- 缩放/平移 ----------
    def _apply_fit(self):
        if not self.has_image():
            return
        w, h = self.width(), self.height()
        iw, ih = self._qimage.width(), self._qimage.height()
        if w <= 1 or h <= 1 or iw <= 1 or ih <= 1:
            return
        self._fit_scale = min(w / iw, h / ih)
        if self._auto_fit:
            self.scale = self._fit_scale
            self.offset_x = (w - iw * self.scale) / 2.0
            self.offset_y = (h - ih * self.scale) / 2.0

    def zoom_by(self, factor: float, anchor: QPointF):
        """以 anchor（视图坐标）为中心缩放"""
        if not self.has_image():
            return
        old = self.scale
        new = min(20.0, max(0.02, old * factor))
        if abs(new - old) < 1e-9:
            return
        # 保持 anchor 下的图像点不动
        img_x = (anchor.x() - self.offset_x) / old
        img_y = (anchor.y() - self.offset_y) / old
        self.scale = new
        self.offset_x = anchor.x() - img_x * new
        self.offset_y = anchor.y() - img_y * new
        self._auto_fit = False
        self.update()

    def pan_by(self, dx: float, dy: float):
        self.offset_x += dx
        self.offset_y += dy
        self._auto_fit = False
        self.update()

    def reset_view(self):
        self._auto_fit = True
        self._apply_fit()
        self.update()

    # ---------- 坐标变换 ----------
    def to_view(self, ix: float, iy: float) -> QPointF:
        return QPointF(ix * self.scale + self.offset_x, iy * self.scale + self.offset_y)

    def to_image(self, vx: float, vy: float) -> QPointF:
        if self.scale == 0:
            return QPointF(0, 0)
        return QPointF((vx - self.offset_x) / self.scale, (vy - self.offset_y) / self.scale)

    def draw_rect(self) -> QRectF:
        """图像在视图中的显示区域（原版 getDrawRect）"""
        if not self.has_image():
            return QRectF()
        iw, ih = self._qimage.width(), self._qimage.height()
        return QRectF(self.offset_x, self.offset_y, iw * self.scale, ih * self.scale)

    # ---------- 事件 ----------
    def wheelEvent(self, e):
        if not self.has_image():
            return
        factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self.zoom_by(factor, QPointF(e.position().x(), e.position().y()))

    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._pan_last = e.position()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if hasattr(self, "_pan_last") and self._pan_last is not None:
            pos = e.position()
            self.pan_by(pos.x() - self._pan_last.x(), pos.y() - self._pan_last.y())
            self._pan_last = pos

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._pan_last = None
            self.unsetCursor()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._auto_fit:
            self._apply_fit()

    # ---------- 绘制 ----------
    def paintEvent(self, e):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        if self.has_image():
            rect = self.draw_rect()
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawImage(rect, self._qimage)
        else:
            self._paint_hint(painter)
        self.paint_overlay(painter)
        painter.end()

    def _paint_hint(self, painter: QPainter):
        if not self._hint_text:
            return
        painter.setPen(QColor(160, 160, 160))
        f = painter.font()
        f.setPointSize(11)
        painter.setFont(f)
        painter.drawText(self.rect(), Qt.AlignCenter, self._hint_text)

    def paint_overlay(self, painter: QPainter):
        """子类覆盖：绘制覆盖层"""
        pass
