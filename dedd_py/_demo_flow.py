# -*- coding: utf-8 -*-
"""用 未命名.deddp 演示完整六步流程，逐步截图（只读演示，不保存工程）"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF

app = QApplication([])

from dedd.widgets.main_window import MainWindow
from dedd.project_io import load_project
from dedd.image_utils import np_to_qimage

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "流程示例")
os.makedirs(OUT, exist_ok=True)

proj, base_img, front_img = load_project(os.path.join(os.path.dirname(os.path.abspath(__file__)), "未命名.deddp"))
w = MainWindow()
w.resize(1280, 800)
w.show()
w._close_workspace(silent=True)
w._new_workspace()
w.basic_info = proj.basic
if base_img is not None:
    w.workspace.base_panel.set_image(np_to_qimage(base_img))
if front_img is not None:
    w.workspace.front_panel.set_image(np_to_qimage(front_img))
w._update_info_bar()

def shot(name):
    app.processEvents()
    w.grab().save(os.path.join(OUT, name))

# ---- 步骤1 编辑照片：初始双视图 ----
w.tabs.setCurrentIndex(0)
app.processEvents()
shot("step01_编辑照片.png")

# ---- 步骤2 平行合平面：两点 → 应用旋转 → 恢复原图 ----
w.tabs.setCurrentIndex(1)
app.processEvents()
bp = w.workspace.base_panel
# 模拟沿合平面点两点（视图坐标，口内图 548x822 显示于视口）
wpx = bp.image_view.width()
hp = bp.image_view.height()
bp.unify_panel.points = [QPointF(wpx * 0.30, hp * 0.62), QPointF(wpx * 0.70, hp * 0.50)]
bp.unify_panel.img_points = [bp.unify_panel._to_img(p) for p in bp.unify_panel.points]
shot("step02_平行合平面_两点.png")
bp.apply_unify_rotation()
app.processEvents()
shot("step02b_平行合平面_已旋转.png")
bp.restore_unify()   # 演示后恢复原图，工程数据不动
app.processEvents()

# ---- 步骤3 标记唇线：正面视图画唇线 ----
w.tabs.setCurrentIndex(2)
app.processEvents()
fp = w.workspace.front_panel
lp = fp.lip_panel
fwpx = fp.image_view.width()
fhp = fp.image_view.height()
pts = [(0.30, 0.62), (0.40, 0.60), (0.50, 0.615), (0.60, 0.60), (0.70, 0.62)]
for i, (rx, ry) in enumerate(pts):
    v = QPointF(fwpx * rx, fhp * ry)
    lp.points.append(v)
    lp.img_points.append(lp._to_img(v))
lp.update()
shot("step03_标记唇线.png")

# ---- 步骤4 标记牙位：AI 检测 ----
w.tabs.setCurrentIndex(3)
app.processEvents()
w.detect_teeth()
app.processEvents()
shot("step04_标记牙位_AI检测.png")

# ---- 步骤5 美学设计：自动优化 + 重新设计 ----
w.tabs.setCurrentIndex(4)
app.processEvents()
w.workspace.enter_adjust()
w.workspace.base_panel.adjust_panel.set_mode(1)   # 牙冠显示模式
app.processEvents()
shot("step05_美学设计.png")

# ---- 步骤6 导出设计：结果页 ----
w.tabs.setCurrentIndex(5)
app.processEvents()
shot("step06_导出设计.png")

w.close()
print("done ->", OUT)
