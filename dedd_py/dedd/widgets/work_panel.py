# -*- coding: utf-8 -*-
"""工作面板 —— 对应原 DEDD 项目的 WorkPanel

一个视图（口内/正面）内的层叠结构：
  image_view  底层：原图显示 + 缩放平移（所有覆盖层共享其变换）
  lip_panel   唇线覆盖层（仅正面视图使用）
  mark_panel  牙位标记覆盖层
  adjust_panel 牙齿调整覆盖层

状态机：EDIT_IMAGE / UNIFY / MARK_LIP / MARK_TEETH / ADJUST
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..image_utils import (np_to_qimage, qimage_bytes, qimage_bytes_to_rgba,
                           rotate90, rotate_align_horizontal)
from ..models import ToothData
from .adjust_panel import MODE_CONTOUR, MODE_NONE, MODE_REAL, TeethAdjustPanel
from .image_view import ImageView
from .lip_panel import LipPanel
from .mark_panel import TeethMarkPanel
from .unify_panel import UnifyPanel

VIEW_BASE = 0
VIEW_FRONT = 1

STATUS_EDIT = 0
STATUS_UNIFY = 1
STATUS_MARK_LIP = 2
STATUS_MARK_TEETH = 3
STATUS_ADJUST = 4


class WorkPanel(QWidget):
    def __init__(self, view_id: int, parent=None):
        super().__init__(parent)
        self.view_id = view_id          # VIEW_BASE / VIEW_FRONT
        self.status = STATUS_EDIT

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶部视图标注条（左=正面视图，右=口内视图）
        self.title_label = QLabel("正面视图" if view_id == VIEW_FRONT else "口内视图", self)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet(
            "QLabel { background: #2b2b2b; color: #e8e8e8; font-weight: bold; padding: 3px; }")
        root.addWidget(self.title_label)

        self.image_view = ImageView(self)
        root.addWidget(self.image_view, 1)

        # 覆盖层（与 image_view 同几何，堆叠在其上）
        self.lip_panel = LipPanel(self.image_view, self)
        self.mark_panel = TeethMarkPanel(self.image_view, self)
        self.adjust_panel = TeethAdjustPanel(self.image_view,
                                             view_kind="front" if view_id == VIEW_FRONT else "base", parent=self)
        self.unify_panel = UnifyPanel(self.image_view, self)   # 平行合平面（口内视图）
        self.lip_panel.setVisible(False)
        self.mark_panel.setVisible(False)
        self.adjust_panel.setVisible(False)
        self.unify_panel.setVisible(False)
        self._unify_orig = None      # 合平面旋转前的原图（用于恢复）

        # 中轴线（仅正面视图有效）
        self.sym_axis = None
        self.mark_panel.is_front = (view_id == VIEW_FRONT)

        # 无图时中央提示：明确告知该导入哪类照片
        if view_id == VIEW_FRONT:
            self.image_view.set_hint("请点击『载入照片』按钮或双击本区域\n导入 正面微笑照")
        else:
            self.image_view.set_hint("请点击『载入照片』按钮或双击本区域\n导入 口内牙列照")

        # 底部按钮条
        self.button_bar = QWidget(self)
        bar = QHBoxLayout(self.button_bar)
        bar.setContentsMargins(8, 4, 8, 4)
        bar.addStretch(1)
        self.btn_load = QPushButton("载入照片", self.button_bar)
        self.btn_rot_left = QPushButton("⟲ 左转90°", self.button_bar)
        self.btn_rot_right = QPushButton("⟳ 右转90°", self.button_bar)
        self.btn_mode_contour = QPushButton("轮廓", self.button_bar)
        self.btn_mode_real = QPushButton("牙冠", self.button_bar)
        self.btn_mode_none = QPushButton("隐藏", self.button_bar)
        self.btn_apply_unify = QPushButton("应用旋转", self.button_bar)
        self.btn_restore_unify = QPushButton("恢复原图", self.button_bar)
        self.btn_lip_lower = QPushButton("下唇线", self.button_bar)
        self.btn_lip_upper = QPushButton("上唇线", self.button_bar)
        for b in (self.btn_load, self.btn_rot_left, self.btn_rot_right,
                  self.btn_mode_contour, self.btn_mode_real, self.btn_mode_none,
                  self.btn_apply_unify, self.btn_restore_unify,
                  self.btn_lip_lower, self.btn_lip_upper):
            b.setFixedHeight(26)
            bar.addWidget(b)
        bar.addStretch(1)
        self.button_bar.setVisible(False)

        self.on_load_photo = None
        self.on_teeth_cleared = None      # 图像变化导致标记/调整被清除时的回调
        self.btn_load.clicked.connect(self._load_clicked)
        self.btn_rot_left.clicked.connect(lambda: self._rotate("left"))
        self.btn_rot_right.clicked.connect(lambda: self._rotate("right"))
        self.btn_mode_contour.clicked.connect(lambda: self.adjust_panel.set_mode(MODE_CONTOUR))
        self.btn_mode_real.clicked.connect(lambda: self.adjust_panel.set_mode(MODE_REAL))
        self.btn_mode_none.clicked.connect(lambda: self.adjust_panel.set_mode(MODE_NONE))
        self.btn_apply_unify.clicked.connect(self.apply_unify_rotation)
        self.btn_restore_unify.clicked.connect(self.restore_unify)
        self.btn_lip_lower.clicked.connect(lambda: self._set_lip_kind("lower"))
        self.btn_lip_upper.clicked.connect(lambda: self._set_lip_kind("upper"))

    def _load_clicked(self):
        if self.on_load_photo:
            self.on_load_photo(self)

    # ---------- 布局 ----------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout_overlays()

    def _relayout_overlays(self):
        g = self.image_view.geometry()
        for w in (self.lip_panel, self.mark_panel, self.adjust_panel, self.unify_panel):
            w.setGeometry(g)
        self.button_bar.setGeometry(0, self.height() - 34, self.width(), 34)

    def _rotate(self, direction: str):
        img = self.image_view.get_image()
        if img is None:
            return
        from PySide6.QtGui import QImage
        rgba = img.convertToFormat(QImage.Format_RGBA8888)
        w, h = rgba.width(), rgba.height()
        buf = qimage_bytes(rgba)
        arr = np.frombuffer(buf, np.uint8).reshape(h, w, 4)
        out = rotate90(arr[:, :, :3].copy(), direction)
        self.set_image(np_to_qimage(out))

    # ---------- 图像 ----------
    def set_image(self, img):
        self.image_view.set_image(img)
        self.image_view.reset_view()

    def get_image(self):
        return self.image_view.get_image()

    def has_image(self) -> bool:
        return self.image_view.has_image()

    # ---------- 中轴线 ----------
    def set_sym_axis(self, axis_x):
        """设置中轴线（图像x坐标，None=隐藏），同步给标记/调整覆盖层"""
        self.sym_axis = axis_x
        self.mark_panel.set_sym_axis(axis_x)
        self.adjust_panel.set_sym_axis(axis_x)
        self.update()

    def get_sym_axis(self):
        return self.sym_axis

    # ---------- 状态切换 ----------
    def enter_edit(self):
        self.status = STATUS_EDIT
        self.lip_panel.setVisible(False)
        self.mark_panel.setVisible(False)
        self.adjust_panel.setVisible(False)
        self.button_bar.setVisible(True)
        self.btn_mode_contour.setVisible(False)
        self.btn_mode_real.setVisible(False)
        self.btn_mode_none.setVisible(False)
        self.btn_load.setVisible(True)
        self.btn_rot_left.setVisible(True)
        self.btn_rot_right.setVisible(True)
        self.btn_apply_unify.setVisible(False)
        self.btn_restore_unify.setVisible(False)
        self.update()

    def enter_unify(self):
        self.status = STATUS_UNIFY
        self.lip_panel.setVisible(False)
        self.mark_panel.setVisible(False)
        self.adjust_panel.setVisible(False)
        # 合平面仅口内视图使用：进入时记住当前图像以便恢复
        if self.view_id == VIEW_BASE:
            self.unify_panel.setVisible(True)
            if self._unify_orig is None:
                img = self.image_view.get_image()
                if img is not None:
                    self._unify_orig = img.copy()
        else:
            self.unify_panel.setVisible(False)
        self.button_bar.setVisible(True)
        self.btn_load.setVisible(False)
        self.btn_rot_left.setVisible(True)
        self.btn_rot_right.setVisible(True)
        self.btn_mode_contour.setVisible(False)
        self.btn_mode_real.setVisible(False)
        self.btn_mode_none.setVisible(False)
        self.btn_apply_unify.setVisible(self.view_id == VIEW_BASE)
        self.btn_restore_unify.setVisible(self.view_id == VIEW_BASE)
        self.update()

    # ---------- 平行合平面 ----------
    def apply_unify_rotation(self):
        """按合平面两点旋转口内图像，使合平面水平；清除因图像变化而失效的标记/调整"""
        if not self.has_image():
            return
        if not self.unify_panel.has_two():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "平行合平面",
                                    "请先在口内视图沿咬合平面点两个点（左键单击，可拖动/右键删除），再点『应用旋转』。")
            return
        p1, p2 = self.unify_panel.get_img_points()
        arr = self.render_pre_np()
        if arr is None:
            return
        rotated = rotate_align_horizontal(arr, p1, p2)
        if rotated is None:
            return
        if self._unify_orig is None:
            img = self.image_view.get_image()
            if img is not None:
                self._unify_orig = img.copy()
        self.set_image(np_to_qimage(rotated))
        self.unify_panel.clear()
        # 图像已变化：该视图的标记/调整坐标作废，清除并通知
        if self.mark_panel.rects or self.adjust_panel.items:
            self.mark_panel.clear()
            self.adjust_panel.clear()
            if self.on_teeth_cleared:
                self.on_teeth_cleared()
        self.update()

    def restore_unify(self):
        """恢复合平面旋转前的口内原图"""
        if self._unify_orig is None:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "恢复原图", "当前没有可恢复的原图（尚未执行过旋转）。")
            return
        self.set_image(self._unify_orig)
        self._unify_orig = None
        self.unify_panel.clear()
        if self.mark_panel.rects or self.adjust_panel.items:
            self.mark_panel.clear()
            self.adjust_panel.clear()
        self.update()

    def enter_mark_lip(self):
        self.status = STATUS_MARK_LIP
        self.lip_panel.setVisible(self.view_id == VIEW_FRONT)
        self.mark_panel.setVisible(False)
        self.adjust_panel.setVisible(False)
        self.unify_panel.setVisible(False)
        # 唇线步骤显示按钮条（仅上/下唇线切换）
        self.button_bar.setVisible(self.view_id == VIEW_FRONT)
        self.btn_load.setVisible(False)
        self.btn_rot_left.setVisible(False)
        self.btn_rot_right.setVisible(False)
        self.btn_mode_contour.setVisible(False)
        self.btn_mode_real.setVisible(False)
        self.btn_mode_none.setVisible(False)
        self.btn_apply_unify.setVisible(False)
        self.btn_restore_unify.setVisible(False)
        self.btn_lip_lower.setVisible(self.view_id == VIEW_FRONT)
        self.btn_lip_upper.setVisible(self.view_id == VIEW_FRONT)
        self.update()

    def _set_lip_kind(self, kind: str):
        self.lip_panel.set_current(kind)
        self.btn_lip_lower.setEnabled(kind != "lower")
        self.btn_lip_upper.setEnabled(kind != "upper")

    def enter_mark_teeth(self):
        self.status = STATUS_MARK_TEETH
        self.lip_panel.setVisible(False)
        self.mark_panel.setVisible(True)
        self.adjust_panel.setVisible(False)
        self.unify_panel.setVisible(False)
        self.button_bar.setVisible(False)
        self.update()

    def enter_adjust(self):
        self.status = STATUS_ADJUST
        self.lip_panel.setVisible(False)
        self.mark_panel.setVisible(False)
        self.adjust_panel.setVisible(True)
        self.unify_panel.setVisible(False)
        self.button_bar.setVisible(True)
        self.btn_load.setVisible(False)
        self.btn_rot_left.setVisible(False)
        self.btn_rot_right.setVisible(False)
        self.btn_mode_contour.setVisible(True)
        self.btn_mode_real.setVisible(True)
        self.btn_mode_none.setVisible(True)
        self.btn_apply_unify.setVisible(False)
        self.btn_restore_unify.setVisible(False)
        self.update()

    # ---------- 数据 ----------
    def set_marked_teeth(self, data: List[ToothData]):
        self.mark_panel.set_teeth(data)

    def get_marked_teeth_data(self):
        return self.mark_panel.get_teeth_data()

    def set_adjusted_teeth(self, data: List[ToothData]):
        self.adjust_panel.set_teeth(data)

    def get_adjusted_teeth_data(self):
        return self.adjust_panel.get_current_teeth_data()

    def set_lip_points(self, points):
        """设置当前唇线（默认下唇线）的点"""
        self.lip_panel.set_current("lower")
        self.lip_panel.set_img_points(points)

    def get_lip_points(self):
        """下唇线图像坐标（兼容旧接口，供美学参数使用）"""
        return self.lip_panel.get_points_of("lower")

    def set_lip_upper_points(self, points):
        self.lip_panel.set_points_of("upper", points)

    def get_lip_upper_points(self):
        return self.lip_panel.get_points_of("upper")

    def is_lip_closed(self) -> bool:
        return self.lip_panel._lines["lower"]["closed"]

    def set_lip_closed(self, closed: bool):
        self.lip_panel.set_points_of("lower", self.lip_panel.get_points_of("lower"), closed=closed)

    def is_lip_upper_closed(self) -> bool:
        return self.lip_panel._lines["upper"]["closed"]

    def set_lip_upper_closed(self, closed: bool):
        self.lip_panel.set_points_of("upper", self.lip_panel.get_points_of("upper"), closed=closed)

    # ---------- 缩放同步 ----------
    def sync_overlays_zoom(self):
        self.mark_panel.zoom_sync()
        self.lip_panel.zoom_sync()
        self.adjust_panel.zoom_sync()

    # ---------- 导出渲染 ----------
    def render_to_np(self, with_overlay: bool = True) -> Optional[np.ndarray]:
        """把当前面板渲染为 numpy 图像（可含覆盖层），并裁剪到图像显示区域"""
        if not self.has_image():
            return None
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QPixmap
        pm = QPixmap(self.width(), self.height())
        pm.fill(Qt.black)
        p = QPainter(pm)
        self.image_view.render(p, QPoint(0, 0))
        if with_overlay:
            for w in (self.lip_panel, self.mark_panel, self.adjust_panel):
                if w.isVisible():
                    w.render(p, QPoint(0, 0))
        p.end()
        img = pm.toImage()
        arr = qimage_bytes_to_rgba(img)
        rect = self.image_view.draw_rect()
        if rect.width() <= 1 or rect.height() <= 1:
            return None
        x1 = max(0, int(rect.x()))
        y1 = max(0, int(rect.y()))
        x2 = min(self.width(), int(rect.x() + rect.width()))
        y2 = min(self.height(), int(rect.y() + rect.height()))
        if x2 - x1 < 2 or y2 - y1 < 2:
            return None
        return arr[y1:y2, x1:x2][:, :, :3].copy()

    def render_pre_np(self) -> Optional[np.ndarray]:
        """渲染原图（无覆盖层）"""
        return self.render_to_np(with_overlay=False)
