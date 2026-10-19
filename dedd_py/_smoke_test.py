# -*- coding: utf-8 -*-
"""离屏冒烟测试：验证主流程可运行（无需显示窗口）"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtWidgets import QApplication

app = QApplication([])

from dedd.image_utils import np_to_qimage
from dedd.models import BasicInfo, ToothData
from dedd.widgets.main_window import MainWindow


def make_test_image(w=800, h=600, kind="base"):
    """生成模拟照片"""
    img = np.full((h, w, 3), (210, 205, 200), np.uint8)
    if kind == "front":
        # 模拟人脸区域
        img[60:480, 200:600] = (235, 200, 180)
        # 模拟嘴部
        img[300:380, 300:500] = (180, 120, 110)
    else:
        # 模拟牙龈和牙齿
        img[150:450, 200:600] = (225, 160, 150)
        for i in range(6):
            x = 230 + i * 60
            img[200:380, x:x + 45] = (245, 245, 245)
    return img


def main():
    w = MainWindow()
    w.basic_info = BasicInfo(name="测试患者", age=32, gender="男", phone="13800000000")
    proj_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_smoke_test.deddp")
    w.proj_file = proj_path
    w._new_workspace()
    w.show()
    app.processEvents()

    # 载入两张测试图
    w.workspace.base_panel.set_image(np_to_qimage(make_test_image(kind="base")))
    w.workspace.front_panel.set_image(np_to_qimage(make_test_image(kind="front")))

    # 标记牙位（口内 + 正面）
    base_teeth = [
        ToothData(site=13, x1=200, y1=160, x2=255, y2=330, length=9.5),
        ToothData(site=12, x1=265, y1=165, x2=318, y2=332, length=8.8),
        ToothData(site=11, x1=328, y1=160, x2=382, y2=335, length=9.2),
        ToothData(site=21, x1=392, y1=162, x2=446, y2=334, length=9.0),
        ToothData(site=22, x1=456, y1=166, x2=508, y2=330, length=8.7),
        ToothData(site=23, x1=518, y1=162, x2=572, y2=328, length=9.3),
    ]
    front_teeth = [
        ToothData(site=13, x1=310, y1=300, x2=360, y2=390, length=9.5),
        ToothData(site=12, x1=368, y1=302, x2=414, y2=392, length=8.8),
        ToothData(site=11, x1=424, y1=300, x2=472, y2=395, length=9.2),
        ToothData(site=21, x1=480, y1=301, x2=528, y2=394, length=9.0),
        ToothData(site=22, x1=536, y1=303, x2=580, y2=390, length=8.7),
        ToothData(site=23, x1=588, y1=300, x2=636, y2=388, length=9.3),
    ]
    w.workspace.base_panel.set_marked_teeth(base_teeth)
    w.workspace.front_panel.set_marked_teeth(front_teeth)

    # 唇线
    w.workspace.set_lip_points([(350, 260), (410, 250), (470, 250), (530, 255), (600, 265)])
    w.workspace.set_lip_closed(False)

    # 进入美学设计
    w.workspace.enter_adjust()
    assert len(w.workspace.base_panel.adjust_panel.items) == 6
    assert len(w.workspace.front_panel.adjust_panel.items) == 6

    # 自动优化
    w.workspace.auto_adjust()

    # 调整亮度/黄度
    w.workspace.set_bright_yellow(0, 15, 5)

    # 生成导出图
    base_after = w.workspace.base_panel.render_to_np(with_overlay=True)
    front_after = w.workspace.front_panel.render_to_np(with_overlay=True)
    assert base_after is not None and base_after.shape[0] > 50
    assert front_after is not None

    # 导出设计面板
    w._show_export()

    # 保存工程
    ok = w.save_project()
    assert ok is None  # save_project 无返回值，成功则无异常

    # 重新读取工程
    from dedd.project_io import load_project
    proj, bimg, fimg = load_project(proj_path)
    assert proj.basic.name == "测试患者"
    assert len(proj.base.marked) == 6
    assert bimg is not None and fimg is not None
    print("=== SMOKE TEST PASSED ===")
    print(f"project file: {proj_path} ({os.path.getsize(proj_path)} bytes)")
    print("base after shape:", base_after.shape)
    print("front after shape:", front_after.shape)


if __name__ == "__main__":
    main()
