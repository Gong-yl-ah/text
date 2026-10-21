# -*- coding: utf-8 -*-
"""工作区 —— 对应原 DEDD 项目的 WorkSpace

左右两个视图：正面视图（左）、口内视图（右）
负责：流程分发、数据存取、撤销/重做快照、自动优化/对齐、重新设计、缩放联动
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget

from ..models import ProjData, Tooth, ToothData
from ..optimizer import align_front, optimize_base
from .work_panel import VIEW_BASE, VIEW_FRONT, WorkPanel


class WorkSpace(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        self.front_panel = WorkPanel(VIEW_FRONT, self)   # 正面视图
        self.base_panel = WorkPanel(VIEW_BASE, self)     # 口内视图
        for p in (self.front_panel, self.base_panel):
            p.setStyleSheet("WorkPanel { border: 1px solid #555; background: #202020; }")
        lay.addWidget(self.front_panel, 1)
        lay.addWidget(self.base_panel, 1)

        # 撤销/重做快照（标记牙位数据）
        self._undo_stack: List[dict] = []
        self._redo_stack: List[dict] = []

        # 记录上一轮标记数据，用于"调整"时增量同步
        self._prev_marked: dict = {}

    # ---------- 流程分发 ----------
    def enter_edit(self):
        self.front_panel.enter_edit()
        self.base_panel.enter_edit()

    def enter_unify(self):
        self.front_panel.enter_unify()
        self.base_panel.enter_unify()

    def enter_mark_lip(self):
        self.front_panel.enter_mark_lip()
        self.base_panel.enter_mark_lip()

    def enter_mark_teeth(self):
        self.front_panel.enter_mark_teeth()
        self.base_panel.enter_mark_teeth()

    def enter_adjust(self):
        # 把标记牙位同步进调整面板（增量：只添加新标记的牙，保留已有调整）
        for panel, prev_key in ((self.base_panel, "base"), (self.front_panel, "front")):
            marked = panel.get_marked_teeth_data()
            prev = self._prev_marked.get(prev_key, [])
            prev_ids = {t.site for t in prev}
            existing = panel.adjust_panel.get_current_teeth_data()
            existing_ids = {t.site for t in existing}
            new_teeth = [t for t in marked if t.site not in prev_ids and t.site not in existing_ids]
            if new_teeth:
                panel.adjust_panel.set_teeth(existing + new_teeth)
        self._prev_marked = {"base": self.base_panel.get_marked_teeth_data(),
                             "front": self.front_panel.get_marked_teeth_data()}
        self.front_panel.enter_adjust()
        self.base_panel.enter_adjust()

    def enter_adjust_with(self, base_teeth: List[ToothData], front_teeth: List[ToothData]):
        self.base_panel.adjust_panel.set_teeth(base_teeth)
        self.front_panel.adjust_panel.set_teeth(front_teeth)
        self.front_panel.enter_adjust()
        self.base_panel.enter_adjust()

    # ---------- 图像 ----------
    def set_image(self, view_id: int, img):
        (self.base_panel if view_id == VIEW_BASE else self.front_panel).set_image(img)

    def get_image_np(self, view_id: int):
        p = self.base_panel if view_id == VIEW_BASE else self.front_panel
        return p.render_pre_np()

    # ---------- 标记/调整数据 ----------
    def set_marked_teeth(self, view_id: int, data: List[ToothData]):
        (self.base_panel if view_id == VIEW_BASE else self.front_panel).set_marked_teeth(data)

    def get_marked_teeth_data(self, view_id: int) -> List[ToothData]:
        return (self.base_panel if view_id == VIEW_BASE else self.front_panel).get_marked_teeth_data()

    def set_adjusted_teeth(self, view_id: int, data: List[ToothData]):
        (self.base_panel if view_id == VIEW_BASE else self.front_panel).set_adjusted_teeth(data)

    def get_adjusted_teeth_data(self, view_id: int) -> List[ToothData]:
        return (self.base_panel if view_id == VIEW_BASE else self.front_panel).get_adjusted_teeth_data()

    def set_lip_points(self, points):
        self.front_panel.set_lip_points(points)

    def get_lip_points(self):
        return self.front_panel.get_lip_points()

    def get_lip_closed(self) -> bool:
        return self.front_panel.is_lip_closed()

    def set_lip_closed(self, closed: bool):
        self.front_panel.set_lip_closed(closed)

    def set_bright_yellow(self, view_id: int, bright: int, yellow: int):
        (self.base_panel if view_id == VIEW_BASE else self.front_panel).adjust_panel.set_bright_yellow(bright, yellow)

    def get_bright_yellow(self, view_id: int) -> Tuple[int, int]:
        return (self.base_panel if view_id == VIEW_BASE else self.front_panel).adjust_panel.get_bright_yellow()

    # ---------- 中轴线（正面视图） ----------
    def set_sym_axis(self, axis_x):
        self.front_panel.set_sym_axis(axis_x)

    def get_sym_axis(self):
        return self.front_panel.get_sym_axis()

    # ---------- 撤销/重做（标记牙位快照） ----------
    def _snapshot(self):
        self._undo_stack.append({"base": [t.to_dict() for t in self.base_panel.get_marked_teeth_data()],
                                 "front": [t.to_dict() for t in self.front_panel.get_marked_teeth_data()]})
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _mark_changed(self):
        """标记面板变化回调：立即记录一次撤销快照"""
        self._snapshot()

    def record_mark_snapshot(self):
        """供外部（如 AI 检测自动标记后）手动记录快照"""
        self._snapshot()

    def flush_snapshot(self):
        pass

    def undo(self):
        if not self._undo_stack:
            return
        cur = {"base": [t.to_dict() for t in self.base_panel.get_marked_teeth_data()],
               "front": [t.to_dict() for t in self.front_panel.get_marked_teeth_data()]}
        snap = self._undo_stack.pop()
        self._redo_stack.append(cur)
        self._apply_mark_snapshot(snap)

    def redo(self):
        if not self._redo_stack:
            return
        cur = {"base": [t.to_dict() for t in self.base_panel.get_marked_teeth_data()],
               "front": [t.to_dict() for t in self.front_panel.get_marked_teeth_data()]}
        snap = self._redo_stack.pop()
        self._undo_stack.append(cur)
        self._apply_mark_snapshot(snap)

    def _apply_mark_snapshot(self, snap: dict):
        self.base_panel.set_marked_teeth([ToothData.from_dict(d) for d in snap.get("base", [])])
        self.front_panel.set_marked_teeth([ToothData.from_dict(d) for d in snap.get("front", [])])

    # ---------- 自动优化 / 对齐 / 重新设计 ----------
    def auto_adjust(self):
        """口内自动优化 + 正面自动对齐"""
        base = self.base_panel.adjust_panel.get_current_teeth()
        if base:
            img = self.base_panel.render_pre_np()
            h, w = img.shape[:2] if img is not None else (1000, 1000)
            out = optimize_base(base, w, h)
            self.base_panel.adjust_panel.set_teeth([t.to_data() for t in out])
        front = self.front_panel.adjust_panel.get_current_teeth()
        if front:
            img = self.front_panel.render_pre_np()
            h, w = img.shape[:2] if img is not None else (1000, 1000)
            out = align_front(front, w, h)
            self.front_panel.adjust_panel.set_teeth([t.to_data() for t in out])

    def re_gen_adjust(self):
        """重新设计：清除调整面板，按当前标记重建"""
        self.base_panel.adjust_panel.clear()
        self.front_panel.adjust_panel.clear()
        self.enter_adjust()

    # ---------- 缩放联动（平行合平面） ----------
    def sync_zoom(self, src_panel, dst_panel):
        iv = src_panel.image_view
        dv = dst_panel.image_view
        dv.scale = iv.scale
        dv.offset_x = iv.offset_x
        dv.offset_y = iv.offset_y
        dv._auto_fit = iv._auto_fit
        dst_panel.sync_overlays_zoom()
        dst_panel.update()

    # ---------- 导出 ----------
    def gen_design_np(self, mode: int = 1) -> Optional[np.ndarray]:
        """口内视图：设计图（含牙齿模板）"""
        return self.base_panel.render_to_np(with_overlay=True)

    def gen_pre_np(self, view_id: int):
        p = self.base_panel if view_id == VIEW_BASE else self.front_panel
        return p.render_pre_np()

    def gen_after_np(self, view_id: int):
        p = self.base_panel if view_id == VIEW_BASE else self.front_panel
        return p.render_to_np(with_overlay=True)
