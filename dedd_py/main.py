# -*- coding: utf-8 -*-
"""数字化美学牙科分析与设计 —— 程序入口

运行：python main.py
"""
import os
import sys


def _install_excepthook():
    """未捕获异常写入 error.log，便于排查界面无响应等运行时问题"""
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error.log")

    def hook(tp, val, tb):
        import traceback
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("=" * 40 + "\n")
                f.write("".join(traceback.format_exception(tp, val, tb)))
        except Exception:
            pass
        sys.__excepthook__(tp, val, tb)

    sys.excepthook = hook


def main():
    _install_excepthook()
    from PySide6.QtWidgets import QApplication
    from dedd.widgets.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("数字化美学牙科分析与设计")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
