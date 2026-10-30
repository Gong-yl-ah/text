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
from PySide6.QtWidgets import (QDialog, QFileDialog, QLabel, QMainWindow,
                               QMessageBox, QStackedWidget, QTabWidget,
                               QToolBar, QVBoxLayout, QWidget)

from .. import constants as C
from ..image_utils import crop, np_to_qimage, qimage_bytes
from ..models import BasicInfo, ProjData, ToothData, mirror_teeth
from ..project_io import import_depx, load_project, save_project
from .new_project_dialog import NewProjectDialog
from .result_panel import ResultPanel
from .welcome_panel import WelcomePanel
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
        self._apply_toolbar(None)
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
        self.act_import_photo = QAction(C.IMPORT_PHOTO, self)
        self.act_export_all = QAction("导出全部图（设计图 / 两向对比 / 总图）", self)
        self.act_close = QAction(C.CLOSE, self)
        self.act_exit = QAction(C.EXIT, self)
        for a in (self.act_new, self.act_open, self.act_save, self.act_import,
                  self.act_import_photo, self.act_export_all, self.act_close, self.act_exit):
            m_file.addAction(a)
        self.act_new.triggered.connect(self.new_project)
        self.act_open.triggered.connect(self.open_project)
        self.act_save.triggered.connect(self.save_project)
        self.act_import.triggered.connect(self.import_depx)
        self.act_import_photo.triggered.connect(self.import_photo)
        self.act_export_all.triggered.connect(self.export_all_images)
        self.act_close.triggered.connect(self.close_project)
        self.act_exit.triggered.connect(self.close)
        self.act_save.setEnabled(False)
        self.act_close.setEnabled(False)
        self.act_export_all.setEnabled(False)

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
        self.toolbar = tb
        self.act_face = QAction(C.FACE_ANALYSIS, self)
        self.act_detect = QAction(C.AI_DETECTION, self)
        self.act_export = QAction(C.EXPORT_TO_FILE, self)
        self.act_import_photo_tb = QAction(C.IMPORT_PHOTO, self)
        self.act_onestep = QAction("一键完成", self)
        self.act_onestep.setToolTip(
            "载入照片后：自动检测两视图牙位 → 进入美学设计 → 自动优化\n（之后只需微调即可导出）")
        self.act_sym = QAction("中轴线", self)
        self.act_mirror = QAction("镜像复制", self)
        self.act_esthetics = QAction("美学参数", self)
        self.act_face.triggered.connect(self.face_analysis)
        self.act_detect.triggered.connect(self.detect_teeth)
        self.act_onestep.triggered.connect(self.one_click_flow)
        self.act_export.triggered.connect(self.save_design_to_file)
        self.act_import_photo_tb.triggered.connect(self.import_photo)
        self.act_sym.triggered.connect(self.toggle_sym_axis)
        self.act_mirror.triggered.connect(self.mirror_front)
        self.act_esthetics.triggered.connect(self.open_esthetics_dialog)
        self.act_sym.setEnabled(False)
        self.act_mirror.setEnabled(False)
        self.act_esthetics.setEnabled(False)
        self.act_onestep.setEnabled(False)
        self._est_dlg = None

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

        # 启动引导页（没有项目时显示，避免一片空白无从下手）
        self.welcome = WelcomePanel(self)
        self.stack.addWidget(self.welcome)
        self.stack.setCurrentWidget(self.welcome)
        self.welcome.new_requested.connect(self.new_project)
        self.welcome.open_requested.connect(self.open_project)
        self.welcome.sample_requested.connect(self.open_sample_project)

    # ---------- 工具栏按流程分发 ----------
    def _toolbar_groups(self, tab_index: int):
        """每个步骤只显示这一步用得上的按钮（每组之间自动加分隔线）"""
        if tab_index == 0:          # 编辑照片
            return [[self.act_onestep],
                    [self.act_import_photo_tb, self.act_face]]
        if tab_index in (1, 2):     # 平行合平面 / 标记唇线（旋转、画点都在面板与图上完成）
            return [[self.act_undo, self.act_redo]]
        if tab_index == 3:          # 标记牙位
            return [[self.act_detect],
                    [self.act_undo, self.act_redo],
                    [self.act_sym, self.act_mirror]]
        if tab_index == 4:          # 美学设计
            return [[self.act_auto, self.act_regen],
                    [self.act_undo, self.act_redo],
                    [self.act_sym, self.act_mirror, self.act_esthetics],
                    [self.act_onestep]]
        if tab_index == 5:          # 导出设计
            return [[self.act_export, self.act_export_all]]
        return []

    def _apply_toolbar(self, tab_index):
        """按当前步骤重排工具栏；tab_index=None 表示没打开工程（引导页）"""
        tb = getattr(self, "toolbar", None)
        if tb is None:
            return
        tb.clear()
        if tab_index is None:
            tb.addAction(self.act_import_photo_tb)
            return
        for i, group in enumerate(self._toolbar_groups(tab_index)):
            if i:
                tb.addSeparator()
            for a in group:
                tb.addAction(a)

    def _clear_workspace_widgets(self):
        """移除当前项目的视图（保留启动引导页）"""
        for w in (self.workspace, self.result_panel):
            if w is not None:
                self.stack.removeWidget(w)
                w.deleteLater()
        self.workspace = None
        self.result_panel = None

    # ---------- 项目生命周期 ----------
    def _new_workspace(self):
        # 清理旧内容（保留引导页）
        self._clear_workspace_widgets()
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
        self._apply_toolbar(0)
        # 修改即标记未保存 + 标记快照
        for panel in (self.workspace.base_panel, self.workspace.front_panel):
            panel.image_view.mouseDoubleClickEvent = lambda e, p=panel: self._load_photo(p)
            panel.on_load_photo = self._load_photo
            panel.on_teeth_cleared = lambda: self._on_teeth_cleared()
            panel.mark_panel.on_change = self._on_mark_changed
            panel.adjust_panel.on_change = self._on_adjust_changed
            panel.adjust_panel.on_status = self._show_teeth_status
            panel.lip_panel.on_change = lambda: setattr(self, "dirty", True)
        self.workspace.reset_history()
        self.act_save.setEnabled(True)
        self.act_close.setEnabled(True)
        self.act_export_all.setEnabled(True)
        self.act_face.setEnabled(True)
        self.act_detect.setEnabled(True)
        self.act_sym.setEnabled(True)
        self.act_mirror.setEnabled(True)
        self.act_esthetics.setEnabled(True)
        self.act_onestep.setEnabled(True)
        self.act_export.setEnabled(False)
        self.statusBar().showMessage("点『载入照片』按钮或双击图像区域载入照片（左=正面视图，右=口内视图）")
        self.dirty = False

    def new_project(self):
        if not self._confirm_save_if_dirty():
            return
        dlg = NewProjectDialog(default_dir=os.path.expanduser("~/Documents"), parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
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
        self._load_project_path(path)

    def open_sample_project(self):
        """打开随程序附带的示例工程，便于第一次上手

        示例工程按“只读模板”处理：保存时会要求另存为新文件，避免把
        随程序附带的示例改坏。
        """
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sample = os.path.join(here, f"示例工程.{C.PROJ_FILE_SUFFIX}")
        if not os.path.exists(sample):
            QMessageBox.information(self, "打开示例工程", f"没找到示例工程：\n{sample}")
            return
        if not self._confirm_save_if_dirty():
            return
        self._load_project_path(sample)
        if self.workspace is not None:
            self.proj_file = None          # 模板：保存时另存
            self.dirty = False
            self.statusBar().showMessage("已打开示例工程（模板，保存时会让你另存为新文件）", 6000)

    def _load_project_path(self, path: str):
        """读取工程（.deddp）或原版工程（.depx）并填入界面"""
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
        if proj.lip_upper_points:
            self.workspace.set_lip_upper_points(proj.lip_upper_points)
            self.workspace.set_lip_upper_closed(proj.lip_upper_closed)
        self.workspace.set_sym_axis(proj.sym_axis)
        self.workspace.reset_history()
        self.act_undo.setEnabled(True)
        self.act_redo.setEnabled(True)
        self._update_info_bar()
        self.statusBar().showMessage(f"已打开：{os.path.basename(path)}")

    def import_depx(self):
        self.open_project()

    def import_photo(self):
        """导入照片：若还没有项目则先自动新建，再选择导入到正面/口内视图"""
        if self.workspace is None or not self.tabs.isEnabled():
            dlg = NewProjectDialog(default_dir=os.path.expanduser("~/Documents"), parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            self.basic_info = dlg.basic_info
            self.proj_file = dlg.save_path
            self._close_workspace(silent=True)
            self._new_workspace()
            self._update_info_bar()
        box = QMessageBox(self)
        box.setWindowTitle(C.IMPORT_PHOTO)
        box.setText("照片导入到哪个视图？")
        b_front = box.addButton(C.VIEW_FRONT, QMessageBox.AcceptRole)
        b_base = box.addButton(C.VIEW_BASE, QMessageBox.AcceptRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is None:
            return
        panel = self.workspace.front_panel if clicked is b_front else self.workspace.base_panel
        self._load_photo(panel)

    def save_project(self):
        if self.proj_file is None:
            # 示例工程等“模板”场景：保存时先问存到哪里
            path, _ = QFileDialog.getSaveFileName(
                self, C.SAVE, f"{C.UNNAMED}.{C.PROJ_FILE_SUFFIX}",
                f"DEDD工程 (*.{C.PROJ_FILE_SUFFIX})")
            if not path:
                return
            if not path.lower().endswith(f".{C.PROJ_FILE_SUFFIX}"):
                path += f".{C.PROJ_FILE_SUFFIX}"
            self.proj_file = path
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
        proj.lip_upper_points = self.workspace.get_lip_upper_points()
        proj.lip_upper_closed = self.workspace.get_lip_upper_closed()
        proj.sym_axis = self.workspace.get_sym_axis()
        return proj

    # ---------- 对称辅助线 ----------
    def toggle_sym_axis(self):
        """切换正面视图中轴线显示（未设置时默认放在图像水平中心）"""
        if self.workspace is None:
            return
        cur = self.workspace.get_sym_axis()
        if cur is not None:
            self.workspace.set_sym_axis(None)
            self.statusBar().showMessage("中轴线已隐藏")
        else:
            img = self.workspace.front_panel.get_image()
            w = img.width() if img is not None else 500
            self.workspace.set_sym_axis(w / 2.0)
            self.statusBar().showMessage(
                "中轴线已显示（红色虚线）：在『标记牙位』或『美学设计』视图上可直接左右拖动，对准面部/牙列中线")
        self.dirty = True

    def mirror_front(self):
        """一键镜像复制：把正面视图已标记/调整的牙齿按中轴线对称复制到对侧（11↔21 等）"""
        if self.workspace is None:
            return
        axis = self.workspace.get_sym_axis()
        if axis is None:
            QMessageBox.information(
                self, "镜像复制",
                "请先点击工具栏『中轴线』按钮，把红色中线对准面部/牙列中线，再执行镜像复制。")
            return
        marked = self.workspace.get_marked_teeth_data(VIEW_FRONT)
        adjusted = self.workspace.get_adjusted_teeth_data(VIEW_FRONT)
        if not marked and not adjusted:
            QMessageBox.information(
                self, "镜像复制",
                "正面视图还没有标记牙位。请先在『标记牙位』步骤标记一侧牙齿（如 11/12/13），再执行镜像复制。")
            return
        new_m = mirror_teeth(marked, axis)
        new_a = mirror_teeth(adjusted, axis)
        merged_m = _merge_mirrored(marked, new_m)
        merged_a = _merge_mirrored(adjusted, new_a)
        self.workspace.set_marked_teeth(VIEW_FRONT, merged_m)
        self.workspace.set_adjusted_teeth(VIEW_FRONT, merged_a)
        self.workspace.record_mark_snapshot()
        self.dirty = True
        cnt = len(merged_m) - len(marked)
        self.statusBar().showMessage(f"镜像复制完成：新增 {cnt} 颗（轴线 x≈{axis:.0f}）")

    def open_esthetics_dialog(self):
        """打开美学参数分析窗口（非模态，随操作自动刷新）"""
        if self.workspace is None:
            return
        if self._est_dlg is None:
            from .esthetics_panel import EstheticsDialog
            self._est_dlg = EstheticsDialog(self.workspace, self)
        self._est_dlg.refresh()
        self._est_dlg.show()
        self._est_dlg.raise_()
        self._est_dlg.activateWindow()

    def _on_teeth_cleared(self):
        """合平面旋转等导致图像变化、标记被清除时：记录快照并标记未保存"""
        if self.workspace:
            self.workspace.record_mark_snapshot()
        self.dirty = True

    def _on_mark_changed(self):
        """标记牙位变化：记一步撤销 + 标记未保存"""
        self.dirty = True
        if self.workspace is not None:
            self.workspace._mark_changed()
        self.act_undo.setEnabled(True)

    def _on_adjust_changed(self):
        """美学设计面板变化（拖动/缩放/亮度黄度/切换显示）：同样可撤销"""
        self.dirty = True
        if self.workspace is not None:
            self.workspace.mark_changed()
        self.act_undo.setEnabled(True)

    def _show_teeth_status(self, text: str):
        """选中牙时的状态栏读数"""
        if text:
            self.statusBar().showMessage(text)
        else:
            self._update_info_bar()

    def _close_workspace(self, silent=False):
        self._clear_workspace_widgets()
        self.stack.setCurrentWidget(self.welcome)
        self.tabs.setEnabled(False)
        self._tab_enabled = False
        self._apply_toolbar(None)
        self.act_save.setEnabled(False)
        self.act_close.setEnabled(False)
        self.act_export_all.setEnabled(False)
        self.act_face.setEnabled(False)
        self.act_detect.setEnabled(False)
        self.act_sym.setEnabled(False)
        self.act_mirror.setEnabled(False)
        self.act_esthetics.setEnabled(False)
        self.act_onestep.setEnabled(False)
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
        self._apply_toolbar(index)
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
            self.act_undo.setEnabled(True)
            self.act_redo.setEnabled(True)
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
        try:
            from .esthetics_panel import build_esthetics_summary
            self.result_panel.set_esthetics(build_esthetics_summary(self.workspace))
        except Exception:
            self.result_panel.set_esthetics("")
        self.act_export.setEnabled(True)

    # ---------- 操作 ----------
    def _undo(self):
        if self.workspace and self.workspace.undo():
            self.dirty = True
            self.act_redo.setEnabled(True)
            self._show_teeth_status("")
            self.statusBar().showMessage("已撤销", 1500)

    def _redo(self):
        if self.workspace and self.workspace.redo():
            self.dirty = True
            self.act_undo.setEnabled(True)
            self._show_teeth_status("")
            self.statusBar().showMessage("已重做", 1500)

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

    def detect_teeth(self, checked=False, silent: bool = False):
        """AI 检测（本地启发式增强）：
        口内视图：亮度分割 + 牙间谷分牙自动生成 6 个牙位框；
        正面视图：Haar 嘴部定位 + 亮度分牙自动生成 6 个牙位框。
        两个视图各自独立检测，已有图则生成；结果需手动微调。
        返回 {"base": 口内框数, "front": 正面框数}。"""
        counts = {"base": 0, "front": 0}
        if self.workspace is None:
            return counts
        from ..optimizer import detect_teeth_intraoral, detect_teeth_front
        done = []
        # 口内视图
        bp = self.workspace.base_panel
        if bp.has_image():
            boxes = detect_teeth_intraoral(bp.render_pre_np())
            if boxes:
                bp.set_marked_teeth([ToothData(site=s, x1=a, y1=b, x2=c, y2=d, length=0)
                                     for s, a, b, c, d in boxes])
                counts["base"] = len(boxes)
                done.append("口内")
        # 正面视图
        fp = self.workspace.front_panel
        if fp.has_image():
            boxes = detect_teeth_front(fp.render_pre_np())
            if boxes:
                fp.set_marked_teeth([ToothData(site=s, x1=a, y1=b, x2=c, y2=d, length=0)
                                     for s, a, b, c, d in boxes])
                counts["front"] = len(boxes)
                done.append("正面")
        if not done:
            if not silent:
                QMessageBox.information(self, C.AI_DETECTION,
                                        "未检测到可识别的牙列区域：\n"
                                        "口内照请拍摄上颌前牙清晰正面照（牙齿亮、对焦准）；\n"
                                        "正面照请保持露齿微笑。也可以手动标记牙位。")
            return counts
        self.workspace.record_mark_snapshot()
        self.dirty = True
        self.statusBar().showMessage(
            f"AI检测完成：{'、'.join(done)}视图已生成牙位框，请手动微调", 4000)
        return counts

    def one_click_flow(self, checked=False):
        """一键完成：两视图自动 AI 检测 → 进入『美学设计』→ 自动优化

        之后只剩微调与导出，省掉六步里手动来回切标签的操作。
        """
        if self.workspace is None:
            return
        has_base = self.workspace.base_panel.has_image()
        has_front = self.workspace.front_panel.has_image()
        if not has_base and not has_front:
            QMessageBox.information(
                self, "一键完成",
                "还没有照片。请双击左边视图载入正面照、右边视图载入口内照，再点『一键完成』。")
            return
        counts = self.detect_teeth(silent=True)
        if not counts["base"] and not counts["front"]:
            QMessageBox.information(
                self, "一键完成",
                "AI 没能识别出牙列，已为你切到『标记牙位』步骤，可手动拖框标记。\n"
                "（口内照要牙齿亮、对焦准；正面照请露齿微笑）")
            self.tabs.setCurrentIndex(3)
            return
        # 进入美学设计（会自动把刚检测到的牙位同步进调整面板）
        self.tabs.setCurrentIndex(4)
        self.act_auto.setEnabled(True)
        self.act_regen.setEnabled(True)
        try:
            self.workspace.auto_adjust()
        except Exception as ex:  # 优化失败不应阻断流程
            self.statusBar().showMessage(f"自动优化跳过：{ex}", 5000)
            return
        self.dirty = True
        self.statusBar().showMessage(
            f"一键完成：口内 {counts['base']} 框、正面 {counts['front']} 框，已自动优化。"
            "可微调后到『导出设计』保存。", 9000)

    def _export_stem(self) -> str:
        from datetime import date
        name = (self.basic_info.name or "").strip() or C.UNNAMED
        return f"{name}_{date.today().strftime('%Y%m%d')}"

    def save_design_to_file(self):
        """保存设计图：按原始图像分辨率合成（不再截界面，窗口再小也不糊）"""
        if self.result_panel is None or self.workspace is None:
            return
        default = os.path.join(os.path.expanduser("~/Documents"), f"{self._export_stem()}_设计图.jpg")
        path, _ = QFileDialog.getSaveFileName(self, C.EXPORT_TO_FILE, default, "图片 (*.jpg)")
        if not path:
            return
        if not path.lower().endswith(".jpg"):
            path += ".jpg"
        try:
            from ..export_render import export_design_only
            out = export_design_only(self.workspace, self.basic_info, path)
            if out:
                self.statusBar().showMessage(f"设计图已保存（原图分辨率）：{out}", 6000)
        except Exception as ex:
            QMessageBox.warning(self, C.ERROR, f"保存失败：{ex}")

    def export_all_images(self):
        """一键导出：设计图 + 口内对比 + 正面对比 + 总图（文件名带患者名与日期）"""
        if self.workspace is None:
            QMessageBox.information(self, "导出全部图", "请先打开或新建工程。")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "选择导出目录",
                                                   os.path.expanduser("~/Documents"))
        if not out_dir:
            return
        try:
            from ..export_render import export_case
            files = export_case(self.workspace, self.basic_info, out_dir,
                                stem=self._export_stem())
        except Exception as ex:
            QMessageBox.warning(self, C.ERROR, f"导出失败：{ex}")
            return
        if not files:
            QMessageBox.information(self, "导出全部图", "当前工程没有可导出的图像（两张视图都没载入照片）。")
            return
        self.statusBar().showMessage(f"已导出 {len(files)} 张图：{out_dir}", 9000)
        QMessageBox.information(self, "导出全部图",
                                "已按原图分辨率导出：\n" +
                                "\n".join(os.path.basename(f) for f in files) +
                                f"\n\n目录：{out_dir}")

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


def _merge_mirrored(orig, mirrored):
    """把镜像结果并入原数据：原侧保留，对侧同牙位被镜像覆盖"""
    by_site = {t.site: t for t in orig}
    for t in mirrored:
        by_site[t.site] = t
    return list(by_site.values())
