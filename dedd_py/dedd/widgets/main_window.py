# -*- coding: utf-8 -*-
"""主窗口 —— 对应原 DEDD 项目的 MainUI

布局：
  菜单栏（文件/编辑/设计/关于）
  流程标签（编辑照片 → 平行合平面 → 标记唇线 → 标记牙位 → 美学设计 → 导出设计）
  工具栏（人脸分析/AI检测/撤销/重做/自动优化/重新设计）
  中央区（WorkSpace / ResultPanel）
  状态栏（患者信息）
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QLabel, QMainWindow, QMessageBox,
                               QStackedWidget, QTabWidget, QToolBar,
                               QVBoxLayout, QWidget)

from .. import constants as C
from ..image_utils import crop, np_to_qimage, qimage_bytes
from ..models import BasicInfo, ProjData, ToothData
from ..project_io import import_depx, load_project, save_project
from .new_project_dialog import NewProjectDialog
from .result_panel import ResultPanel
from .work_panel import VIEW_BASE, VIEW_FRONT
from .work_space import WorkSpace


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{C.APP_NAME}  {C.VERSION}")
        self.resize(1280, 800)

        self.proj_file: Optional[str] = None
        self.basic_info = BasicInfo()
        self.workspace: Optional[WorkSpace] = None
        self.result_panel: Optional[ResultPanel] = None
        self.dirty = False

        self._build_menu()
        self._build_toolbar()
        self._build_tabs()
        self.statusBar().showMessage("新建项目后开始设计")

        self._current_tab = 0
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._tab_enabled = False

    # ---------- UI 构建 ----------
    def _build_menu(self):
        mb = self.menuBar()

        m_file = mb.addMenu(C.MENU_FILE)
        self.act_new = QAction(C.NEW, self)
        self.act_open = QAction(C.OPEN, self)
        self.act_save = QAction(C.SAVE, self)
        self.act_import = QAction(C.IMPORT_DEPX, self)
        self.act_close = QAction(C.CLOSE, self)
        self.act_exit = QAction(C.EXIT, self)
        for a in (self.act_new, self.act_open, self.act_save, self.act_import,
                  self.act_close, self.act_exit):
            m_file.addAction(a)
        self.act_new.triggered.connect(self.new_project)
        self.act_open.triggered.connect(self.open_project)
        self.act_save.triggered.connect(self.save_project)
        self.act_import.triggered.connect(self.import_depx)
        self.act_close.triggered.connect(self.close_project)
        self.act_exit.triggered.connect(self.close)
        self.act_save.setEnabled(False)
        self.act_close.setEnabled(False)

        m_edit = mb.addMenu(C.MENU_EDIT)
        self.act_undo = QAction(C.UNDO, self)
        self.act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self.act_redo = QAction(C.REDO, self)
        self.act_redo.setShortcut(QKeySequence("Ctrl+Y"))
        m_edit.addAction(self.act_undo)
        m_edit.addAction(self.act_redo)
        self.act_undo.triggered.connect(self._undo)
        self.act_redo.triggered.connect(self._redo)
        self.act_undo.setEnabled(False)
        self.act_redo.setEnabled(False)

        m_design = mb.addMenu(C.MENU_DESIGN)
        self.act_auto = QAction(C.AUTO_ADJUST, self)
        self.act_regen = QAction(C.RE_ADJUST, self)
        m_design.addAction(self.act_auto)
        m_design.addAction(self.act_regen)
        self.act_auto.triggered.connect(self.auto_adjust)
        self.act_regen.triggered.connect(self.regen_adjust)
        self.act_auto.setEnabled(False)
        self.act_regen.setEnabled(False)

        m_about = mb.addMenu(C.MENU_ABOUT)
        act_about = QAction(C.ABOUT, self)
        m_about.addAction(act_about)
        act_about.triggered.connect(self._show_about)

    def _build_toolbar(self):
        tb = QToolBar("工具", self)
        tb.setMovable(False)
        self.addToolBar(tb)
        self.act_face = QAction(C.FACE_ANALYSIS, self)
        self.act_detect = QAction(C.AI_DETECTION, self)
        self.act_export = QAction(C.EXPORT_TO_FILE, self)
        for a in (self.act_face, self.act_detect, self.act_export):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)
        tb.addSeparator()
        tb.addAction(self.act_auto)
        tb.addAction(self.act_regen)
        self.act_face.triggered.connect(self.face_analysis)
        self.act_detect.triggered.connect(self.detect_teeth)
        self.act_export.triggered.connect(self.save_design_to_file)

    def _build_tabs(self):
        central = QWidget(self)
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.tabs = QTabWidget(central)
        self.stack = QStackedWidget(central)
        v.addWidget(self.tabs)
        v.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        for label in (C.TAB_EDIT, C.TAB_UNIFY, C.TAB_MARK_LIP, C.TAB_MARK_TEETH,
                      C.TAB_ADJUST, C.TAB_EXPORT):
            self.tabs.addTab(QWidget(), label)
        self.tabs.setEnabled(False)

    # ---------- 项目生命周期 ----------
    def _new_workspace(self):
        # 清理旧内容
        while self.stack.count() > 0:
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()
        self.workspace = WorkSpace(self)
        self.result_panel = ResultPanel(self)
        self.stack.addWidget(self.workspace)
        self.stack.addWidget(self.result_panel)
        self.stack.setCurrentWidget(self.workspace)
        self.result_panel.save_btn.clicked.connect(self.save_design_to_file)
        self.tabs.setEnabled(True)
        self._tab_enabled = True
        self.tabs.setCurrentIndex(0)
        self.workspace.enter_edit()
        # 修改即标记未保存 + 标记快照
        for panel in (self.workspace.base_panel, self.workspace.front_panel):
            panel.image_view.mouseDoubleClickEvent = lambda e, p=panel: self._load_photo(p)
            panel.on_load_photo = self._load_photo
            panel.mark_panel.on_change = self.workspace._mark_changed
            panel.adjust_panel.on_change = lambda: setattr(self, "dirty", True)
            panel.lip_panel.on_change = lambda: setattr(self, "dirty", True)
        self.act_save.setEnabled(True)
        self.act_close.setEnabled(True)
        self.act_face.setEnabled(True)
        self.act_detect.setEnabled(True)
        self.act_export.setEnabled(False)
        self.statusBar().showMessage("点『载入照片』按钮或双击图像区域载入照片（左=正面视图，右=口内视图）")
        self.dirty = False

    def new_project(self):
        if not self._confirm_save_if_dirty():
            return
        dlg = NewProjectDialog(default_dir=os.path.expanduser("~/Documents"), parent=self)
        if dlg.exec() != dlg.Accepted:
            return
        self.basic_info = dlg.basic_info
        self.proj_file = dlg.save_path
        self._close_workspace(silent=True)
        self._new_workspace()
        self._update_info_bar()

    def open_project(self):
        if not self._confirm_save_if_dirty():
            return
        path, _ = QFileDialog.getOpenFileName(self, C.OPEN, "", f"DEDD工程 (*.{C.PROJ_FILE_SUFFIX});;原版工程 (*.{C.DEPX_SUFFIX})")
        if not path:
            return
        try:
            if path.lower().endswith(f".{C.DEPX_SUFFIX}"):
                proj, base_img, front_img = import_depx(path)
            else:
                proj, base_img, front_img = load_project(path)
        except Exception as ex:
            QMessageBox.warning(self, C.ERROR, f"{C.DATA_ERROR}\n{ex}")
            return
        self.basic_info = proj.basic
        self.proj_file = path
        self._close_workspace(silent=True)
        self._new_workspace()
        if base_img is not None:
            self.workspace.base_panel.set_image(np_to_qimage(base_img))
        if front_img is not None:
            self.workspace.front_panel.set_image(np_to_qimage(front_img))
        self.workspace.base_panel.set_marked_teeth(proj.base.marked)
        self.workspace.front_panel.set_marked_teeth(proj.front.marked)
        self.workspace.base_panel.set_adjusted_teeth(proj.base.adjusted)
        self.workspace.front_panel.set_adjusted_teeth(proj.front.adjusted)
        self.workspace.set_bright_yellow(VIEW_BASE, proj.base.bright, proj.base.yellow)
        self.workspace.set_bright_yellow(VIEW_FRONT, proj.front.bright, proj.front.yellow)
        if proj.lip_points:
            self.workspace.set_lip_points(proj.lip_points)
            self.workspace.set_lip_closed(proj.lip_closed)
        self._update_info_bar()
        self.statusBar().showMessage(f"已打开：{os.path.basename(path)}")

    def import_depx(self):
        self.open_project()

    def save_project(self):
        if self.proj_file is None:
            return
        proj = self._collect_proj()
        base_img = self.workspace.base_panel.render_pre_np()
        front_img = self.workspace.front_panel.render_pre_np()
        if save_project(proj, base_img, front_img, self.proj_file):
            self.dirty = False
            self.statusBar().showMessage(f"已保存：{os.path.basename(self.proj_file)}")
        else:
            QMessageBox.warning(self, C.ERROR, "保存失败！")

    def close_project(self):
        if not self._confirm_save_if_dirty():
            return
        self._close_workspace(silent=True)

    def _collect_proj(self) -> ProjData:
        proj = ProjData()
        proj.basic = self.basic_info
        proj.base.marked = self.workspace.base_panel.get_marked_teeth_data()
        proj.base.adjusted = self.workspace.base_panel.get_adjusted_teeth_data()
        proj.base.bright, proj.base.yellow = self.workspace.get_bright_yellow(VIEW_BASE)
        proj.front.marked = self.workspace.front_panel.get_marked_teeth_data()
        proj.front.adjusted = self.workspace.front_panel.get_adjusted_teeth_data()
        proj.front.bright, proj.front.yellow = self.workspace.get_bright_yellow(VIEW_FRONT)
        proj.lip_points = self.workspace.get_lip_points()
        proj.lip_closed = self.workspace.get_lip_closed()
        return proj

    def _close_workspace(self, silent=False):
        while self.stack.count() > 0:
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()
        self.workspace = None
        self.result_panel = None
        self.tabs.setEnabled(False)
        self._tab_enabled = False
        self.act_save.setEnabled(False)
        self.act_close.setEnabled(False)
        self.act_face.setEnabled(False)
        self.act_detect.setEnabled(False)
        self.act_export.setEnabled(False)
        self.act_auto.setEnabled(False)
        self.act_regen.setEnabled(False)
        self.act_undo.setEnabled(False)
        self.act_redo.setEnabled(False)
        self.statusBar().showMessage("已关闭项目")

    def _confirm_save_if_dirty(self) -> bool:
        if not self.dirty or self.proj_file is None:
            return True
        r = QMessageBox.question(self, C.SAVE, C.CONFIRM_SAVE,
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Save:
            self.save_project()
        return True

    def _update_info_bar(self):
        info = self.basic_info
        self.statusBar().showMessage(
            f"{C.NAME}:{info.name or C.UNKNOWN}  {C.GENDER}:{info.gender or C.UNKNOWN}  "
            f"{C.AGE}:{info.age or C.UNKNOWN}  {C.PHONE}:{info.phone or C.UNKNOWN}")

    # ---------- 载入照片 ----------
    def _load_photo(self, panel):
        if self.workspace is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, C.LOAD_IMAGE, "",
                                              "图片 (*.jpg *.jpeg *.png *.bmp)")
        if not path:
            return
        from PySide6.QtGui import QImage
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, C.ERROR, "无法读取图片！")
            return
        panel.set_image(img)
        self.dirty = True

    # ---------- 流程标签 ----------
    def _on_tab_changed(self, index: int):
        if not self._tab_enabled or self.workspace is None:
            return
        self._current_tab = index
        labels = (C.TAB_EDIT, C.TAB_UNIFY, C.TAB_MARK_LIP, C.TAB_MARK_TEETH,
                  C.TAB_ADJUST, C.TAB_EXPORT)
        label = labels[index]
        if label == C.TAB_EDIT:
            self.workspace.enter_edit()
        elif label == C.TAB_UNIFY:
            self.workspace.enter_unify()
        elif label == C.TAB_MARK_LIP:
            self.workspace.enter_mark_lip()
        elif label == C.TAB_MARK_TEETH:
            self.workspace.enter_mark_teeth()
            self.act_undo.setEnabled(True)
            self.act_redo.setEnabled(True)
        elif label == C.TAB_ADJUST:
            self.workspace.enter_adjust()
            self.act_auto.setEnabled(True)
            self.act_regen.setEnabled(True)
        elif label == C.TAB_EXPORT:
            self._show_export()
            self.stack.setCurrentWidget(self.result_panel)
            return
        self.stack.setCurrentWidget(self.workspace)

    def _show_export(self):
        if self.workspace is None or self.result_panel is None:
            return
        base_after = self.workspace.base_panel.render_to_np(with_overlay=True)
        front_after = self.workspace.front_panel.render_to_np(with_overlay=True)
        base_before = self.workspace.base_panel.render_pre_np()
        front_before = self.workspace.front_panel.render_pre_np()
        self.result_panel.set_info(self.basic_info)
        self.result_panel.set_design(base_after, self.workspace.base_panel.get_adjusted_teeth_data())
        self.result_panel.set_compare("base", base_before, base_after)
        self.result_panel.set_compare("front", front_before, front_after)
        self.act_export.setEnabled(True)

    # ---------- 操作 ----------
    def _undo(self):
        if self.workspace:
            self.workspace.undo()

    def _redo(self):
        if self.workspace:
            self.workspace.redo()

    def auto_adjust(self):
        if self.workspace:
            self.workspace.auto_adjust()
            self.statusBar().showMessage(C.AUTO_ADJUSTING, 2000)

    def regen_adjust(self):
        if self.workspace:
            self.workspace.re_gen_adjust()

    def face_analysis(self):
        """人脸分析（本地 OpenCV）：旋转眼线至水平 + 裁剪人脸"""
        if self.workspace is None or not self.workspace.front_panel.has_image():
            QMessageBox.information(self, C.FACE_ANALYSIS, C.IMPORT_IMAGE_FIRST)
            return
        from ..optimizer import detect_face_and_eyes
        img = self.workspace.front_panel.render_pre_np()
        res = detect_face_and_eyes(img)
        if res is None:
            QMessageBox.warning(self, C.FACE_ANALYSIS, C.NO_FACE_ERROR)
            return
        rotation, (x, y, w, h) = res
        try:
            import cv2
            out = img
            if abs(rotation) > 0.4:
                hh, ww = img.shape[:2]
                M = cv2.getRotationMatrix2D((ww / 2, hh / 2), -rotation, 1.0)
                cos, sin = abs(M[0, 0]), abs(M[0, 1])
                nw = int(hh * sin + ww * cos)
                nh = int(hh * cos + ww * sin)
                M[0, 2] += nw / 2 - ww / 2
                M[1, 2] += nh / 2 - hh / 2
                out = cv2.warpAffine(img, M, (nw, nh), borderMode=cv2.BORDER_REPLICATE)
                res2 = detect_face_and_eyes(out)
                if res2 is not None:
                    _, (x, y, w, h) = res2
            out = crop(out, x, y, x + w, y + h)
            self.workspace.front_panel.set_image(np_to_qimage(out))
            self.dirty = True
            self.statusBar().showMessage("人脸分析完成：已旋转并对齐人脸", 3000)
        except Exception as ex:
            QMessageBox.warning(self, C.FACE_ANALYSIS, f"{C.ERROR}: {ex}")

    def detect_teeth(self):
        """AI 检测（本地启发式）：正面视图按嘴部区域生成 6 个牙位框；
        口内视图提示手动标记（无本地牙齿检测模型）。"""
        if self.workspace is None or not self.workspace.front_panel.has_image():
            QMessageBox.information(self, C.AI_DETECTION, C.IMPORT_IMAGE_FIRST)
            return
        teeth = self._detect_teeth_front()
        if not teeth:
            QMessageBox.information(self, C.AI_DETECTION, C.NO_TOOTH_ERROR)
            return
        self.workspace.front_panel.set_marked_teeth(teeth)
        self.workspace.record_mark_snapshot()
        self.statusBar().showMessage("AI检测完成：已按嘴部区域生成牙位框，请手动微调", 4000)

    def _detect_teeth_front(self):
        try:
            import cv2
        except ImportError:
            return []
        img = self.workspace.front_panel.render_pre_np()
        if img is None:
            return []
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        smile = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_smile.xml")
        smiles = smile.detectMultiScale(gray, 1.7, 18, minSize=(50, 50))
        if len(smiles) == 0:
            return []
        x, y, w, h = max(smiles, key=lambda s: s[2] * s[3])
        # 在嘴部区域内生成 6 颗前牙框（从左到右：13 12 11 21 22 23）
        sites = [13, 12, 11, 21, 22, 23]
        teeth = []
        tw = w / 6.0
        th = h * 1.05
        ty = y + h * 0.05
        for i, site in enumerate(sites):
            tx = x + i * tw
            teeth.append(ToothData(site=site, x1=tx, y1=ty, x2=tx + tw, y2=ty + th, length=0))
        return teeth

    def save_design_to_file(self):
        if self.result_panel is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, C.EXPORT_TO_FILE, "design.jpg", "图片 (*.jpg)")
        if not path:
            return
        if not path.lower().endswith(".jpg"):
            path += ".jpg"
        try:
            from PIL import Image as PILImage
            # 渲染结果面板整页
            from PySide6.QtGui import QPixmap
            pm = QPixmap(self.result_panel.viewport().size())
            pm.fill(Qt.white)
            self.result_panel.viewport().render(pm)
            img = pm.toImage()
            buf = qimage_bytes(img)
            arr = np.frombuffer(buf, np.uint8).reshape(img.height(), img.width(), 4)
            PILImage.fromarray(arr[:, :, :3]).save(path, "JPEG", quality=92)
            self.statusBar().showMessage(f"设计图已保存：{path}", 4000)
        except Exception as ex:
            QMessageBox.warning(self, C.ERROR, f"保存失败：{ex}")

    def _show_about(self):
        QMessageBox.about(self, C.ABOUT,
                          f"<b>{C.APP_NAME}</b> {C.VERSION}<br>"
                          f"{C.APP_NAME_EN}<br><br>"
                          "参考开源项目 kqstone/Digital-Esthetic-Dentistry-Design 的框架，"
                          "以 Python/PySide6 重新实现，本地运行无需 Java。<br>"
                          "人脸分析/AI检测为本地 OpenCV 启发式实现。")

    # ---------- 关闭 ----------
    def closeEvent(self, e):
        if self._confirm_save_if_dirty():
            e.accept()
        else:
            e.ignore()
