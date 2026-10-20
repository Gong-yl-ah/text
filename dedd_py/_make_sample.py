# -*- coding: utf-8 -*-
"""生成完整样板工程 示例工程.deddp：包含每步数据（照片/唇线/牙位/美学调整）"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtWidgets import QApplication

app = QApplication([])

from dedd.models import BasicInfo, ProjData, ToothData
from dedd.project_io import save_project, load_project
from dedd.widgets.main_window import MainWindow
from dedd.image_utils import np_to_qimage


def make_test_image(w=800, h=600, kind="base"):
    img = np.full((h, w, 3), (208, 203, 198), np.uint8)
    if kind == "front":
        img[40:520, 160:640] = (232, 198, 176)
        img[290:400, 280:520] = (176, 118, 108)
        for i in range(6):
            x = 300 + i * 36
            img[300:380, x:x + 30] = (240, 238, 234)
    else:
        img[140:460, 180:620] = (222, 158, 148)
        for i in range(6):
            x = 210 + i * 62
            img[190:390, x:x + 48] = (243, 242, 240)
            img[195:385, x + 5:x + 43] = (250, 249, 247)
    return img


def main():
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "示例工程.deddp")

    base_img = make_test_image(kind="base")
    front_img = make_test_image(kind="front")

    base_teeth = [
        ToothData(site=13, x1=200, y1=150, x2=258, y2=340, length=9.6),
        ToothData(site=12, x1=268, y1=155, x2=322, y2=342, length=8.8),
        ToothData(site=11, x1=332, y1=148, x2=392, y2=348, length=9.3),
        ToothData(site=21, x1=402, y1=150, x2=462, y2=346, length=9.1),
        ToothData(site=22, x1=472, y1=156, x2=524, y2=340, length=8.7),
        ToothData(site=23, x1=534, y1=152, x2=590, y2=338, length=9.4),
    ]
    front_teeth = [
        ToothData(site=13, x1=296, y1=296, x2=330, y2=386, length=9.6),
        ToothData(site=12, x1=336, y1=298, x2=368, y2=388, length=8.8),
        ToothData(site=11, x1=374, y1=294, x2=410, y2=392, length=9.3),
        ToothData(site=21, x1=416, y1=295, x2=452, y2=390, length=9.1),
        ToothData(site=22, x1=458, y1=299, x2=488, y2=386, length=8.7),
        ToothData(site=23, x1=494, y1=297, x2=526, y2=384, length=9.4),
    ]

    # 构造工程数据
    proj = ProjData()
    proj.basic = BasicInfo(name="演示患者", age=30, gender="男", phone="13800000000")
    proj.base.marked = base_teeth
    proj.front.marked = front_teeth
    proj.lip_points = [(300, 262), (360, 250), (420, 246), (480, 250), (530, 262)]
    proj.lip_closed = False
    proj.base.bright, proj.base.yellow = 22, 6
    proj.front.bright, proj.front.yellow = 14, 4

    # 美学设计：进入调整 + 自动优化生成 adjusted 数据
    w = MainWindow()
    w.basic_info = proj.basic
    w._new_workspace()
    w.workspace.base_panel.set_image(np_to_qimage(base_img))
    w.workspace.front_panel.set_image(np_to_qimage(front_img))
    w.workspace.base_panel.set_marked_teeth(base_teeth)
    w.workspace.front_panel.set_marked_teeth(front_teeth)
    w.workspace.set_lip_points(proj.lip_points)
    w.workspace.set_lip_closed(False)
    w.workspace.enter_adjust()
    w.workspace.auto_adjust()
    w.workspace.set_bright_yellow(0, 22, 6)
    w.workspace.set_bright_yellow(1, 14, 4)
    app.processEvents()

    proj.base.adjusted = w.workspace.base_panel.get_adjusted_teeth_data()
    proj.front.adjusted = w.workspace.front_panel.get_adjusted_teeth_data()

    ok = save_project(proj, base_img, front_img, out_path)
    print("save sample project:", ok, "->", out_path)

    # 读回验证
    p2, b2, f2 = load_project(out_path)
    print("== 读回验证 ==")
    print("患者:", p2.basic.name, p2.basic.gender, p2.basic.age)
    print("唇线点:", len(p2.lip_points))
    print("口内标记:", len(p2.base.marked), "颗 | 正面标记:", len(p2.front.marked), "颗")
    print("口内调整:", len(p2.base.adjusted), "颗 | 正面调整:", len(p2.front.adjusted), "颗")
    print("亮度/黄度:", (p2.base.bright, p2.base.yellow), (p2.front.bright, p2.front.yellow))

    # 渲染每步效果截图（给用户参考）
    from PIL import Image
    # 标记牙位效果（标签3）
    w.tabs.setCurrentIndex(3)
    w.workspace.enter_mark_teeth()
    app.processEvents()
    w.grab().save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "样板_标记牙位.png"), "PNG")
    # 美学设计效果（标签4）
    w.tabs.setCurrentIndex(4)
    w.workspace.enter_adjust()
    app.processEvents()
    w.grab().save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "样板_美学设计.png"), "PNG")
    print("样板截图已保存")
    print("=== SAMPLE PROJECT READY ===")


if __name__ == "__main__":
    main()
