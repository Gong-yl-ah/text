# -*- coding: utf-8 -*-
"""美学参数分析面板 —— 实时显示 2D 照片可计算的美学参数
（依据：中华口腔医学杂志 2026;61(9) 刘云松等《口腔美学重建中关键的美学参数及其数字化转移流程》）
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from ..esthetics import (GINGIVAL_LOWER_MM_MAX, GINGIVAL_LOWER_MM_MIN,
                         crown_ratio_status, crown_width_height_ratio,
                         frontal_width_ratios, gingival_analysis,
                         incisal_vs_lip)

_STATUS_TEXT = {
    "ideal": "理想",
    "short": "偏短宽",
    "long": "偏窄长",
    "low": "偏龈方",
    "high": "偏冠方",
    "n/a": "—",
}
_COLOR = {"ideal": "#2e7d32", "short": "#e65100", "long": "#1565c0",
          "low": "#e65100", "high": "#c62828", "n/a": "#888"}


class EstheticsDialog(QDialog):
    """美学参数分析窗口（非模态，打开期间每 0.8s 自动刷新）"""

    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.setWindowTitle("美学参数分析")
        self.resize(520, 620)
        self.setWindowFlag(Qt.Window, True)

        v = QVBoxLayout(self)
        head = QLabel(
            "<b>美学参数分析</b>（依据《中华口腔医学杂志》2026;61(9):1275-1283）<br>"
            "<span style='color:#666;font-size:12px'>实时读取当前标记/调整数据，随操作自动更新</span>")
        head.setWordWrap(True)
        v.addWidget(head)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.RichText)
        self.body.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        v.addWidget(self.body, 1)
        note = QLabel(
            "<span style='color:#888;font-size:11.5px'>说明：①宽长比=框宽/框高（标得准时≈临床冠宽/冠长），"
            "理想带 0.75~0.85 为临床常用参考，文章未给固定值；"
            "②宽度比按原文黄金分割 1.618:1:0.618 与 Preston 1.51:1:0.84（中国人更倾向 Preston）；"
            "③龈缘理想带按原文 0.5~1.0 mm；"
            "④切缘-唇线仅作微笑照近似提示（文章静息位参考为上唇下方 2~4 mm）；"
            "⑤垂直距离、⑥穿龈轮廓需侧貌照或三维数据，超出本软件 2D 范围。</span>")
        note.setWordWrap(True)
        v.addWidget(note)
        btn = QPushButton("关闭")
        btn.clicked.connect(self.hide)
        v.addWidget(btn)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(800)

    def _tick(self):
        if self.isVisible():
            self.refresh()

    def refresh(self):
        ws = self.workspace
        if ws is None:
            return
        try:
            # 优先取调整数据（美学设计阶段），否则取标记数据
            front = ws.front_panel.get_adjusted_teeth_data()
            source = "调整"
            if not front:
                front = ws.front_panel.get_marked_teeth_data()
                source = "标记"
            base = ws.base_panel.get_marked_teeth_data()
            lip = ws.get_lip_points()

            px_per_mm = _calibrate_mm(base)
            ratio_rows = []
            for t in sorted(front, key=lambda x: x.site):
                r = crown_width_height_ratio(t)
                st = crown_ratio_status(r)
                ratio_rows.append(
                    f"<tr><td>{t.site}</td><td>{'—' if r is None else f'{r:.2f}'}</td>"
                    f"<td style='color:{_COLOR[st]}'>{_STATUS_TEXT[st]}</td></tr>")
            ratio_html = "".join(ratio_rows) if ratio_rows else \
                "<tr><td colspan='3' style='color:#888'>正面视图暂无标记牙位</td></tr>"

            fw = frontal_width_ratios(front)
            width_html = ""
            for side, tag in (("left", "左侧 13:12:11"), ("right", "右侧 23:22:21")):
                d = fw.get(side)
                if not d:
                    width_html += (f"<tr><td>{tag}</td><td colspan='3' style='color:#888'>"
                                   f"需标记 中切牙/侧切牙/尖牙 三颗</td></tr>")
                    continue
                r = d["ratio"]
                closer = "黄金分割" if d["closer"] == "golden" else "Preston"
                width_html += (
                    f"<tr><td>{tag}</td><td>{r[0]:.2f} : 1 : {r[2]:.2f}</td>"
                    f"<td>黄金 {d['golden_dev']}%<br>Preston {d['preston_dev']}%</td>"
                    f"<td>{closer}</td></tr>")

            ga = gingival_analysis(front, px_per_mm)
            ging_html = ""
            for side, tag in (("left", "左侧 11/12/13"), ("right", "右侧 21/22/23")):
                d = ga.get(side)
                if not d:
                    ging_html += (f"<tr><td>{tag}</td><td colspan='3' style='color:#888'>"
                                  f"需标记中切牙/侧切牙/尖牙三颗</td></tr>")
                    continue
                mm = d["diff_mm"]
                st = d["verdict"]
                mm_txt = "—" if mm is None else f"{mm:.2f} mm"
                ging_html += (
                    f"<tr><td>{tag}</td><td>侧切牙比连线{'' if d['diff_px'] >= 0 else '（龈方）'}"
                    f"{abs(d['diff_px']):.0f}px</td><td>{mm_txt}</td>"
                    f"<td style='color:{_COLOR[st]}'>{_STATUS_TEXT[st]}</td></tr>")

            ivl = incisal_vs_lip(front, lip)
            lip_note = "（未标记唇线）" if not lip else ""
            ivl_left = "—" if ivl["left"] is None else f"{ivl['left']:.0f}px"
            ivl_right = "—" if ivl["right"] is None else f"{ivl['right']:.0f}px"
            lip_html = (
                f"<tr><td>11 切缘-唇线</td><td colspan='3'>{ivl_left} {lip_note}</td></tr>"
                f"<tr><td>21 切缘-唇线</td><td colspan='3'>{ivl_right} {lip_note}</td></tr>")

            calib = "（已用口内冠长校准）" if px_per_mm else \
                "（未校准：需在口内视图标记牙位并输入冠长，如 11 冠长 9.0）"
            self.body.setText(
                f"<div style='font-size:13px;line-height:1.7'>"
                f"<p><b>② 牙冠宽长比（数据源：{source}）</b>　理想带 0.75~0.85"
                f"<table border='1' cellspacing='0' cellpadding='4' style='border-collapse:collapse;width:100%'>"
                f"<tr style='background:#eef3f9'><th>牙位</th><th>宽长比</th><th>判定</th></tr>{ratio_html}</table></p>"
                f"<p><b>③ 上前牙正面观宽度比</b>　黄金分割 1.618:1:0.618 / Preston 1.51:1:0.84"
                f"<table border='1' cellspacing='0' cellpadding='4' style='border-collapse:collapse;width:100%'>"
                f"<tr style='background:#eef3f9'><th>侧别</th><th>中切牙:侧切牙:尖牙</th>"
                f"<th>与标准偏差</th><th>更接近</th></tr>{width_html}</table></p>"
                f"<p><b>④ 上前牙龈缘位置</b>　理想：侧切牙比中切牙/尖牙连线冠方 0.5~1.0 mm {calib}"
                f"<table border='1' cellspacing='0' cellpadding='4' style='border-collapse:collapse;width:100%'>"
                f"<tr style='background:#eef3f9'><th>侧别</th><th>像素差</th><th>mm</th><th>判定</th></tr>"
                f"{ging_html}</table></p>"
                f"<p><b>① 中切牙切缘位置</b>（微笑照近似提示）"
                f"<table border='1' cellspacing='0' cellpadding='4' style='border-collapse:collapse;width:100%'>"
                f"{lip_html}</table></p>"
                f"<p style='color:#888'>⑤ 垂直距离、⑥ 穿龈轮廓：需要侧貌照片或三维数据，"
                f"本软件（2D 照片设计）暂不支持。</p>"
                f"</div>")
        except Exception:
            pass

def _calibrate_mm(base_teeth) -> Optional[float]:
    """用口内视图 11/21 的冠长校准像素/毫米：px_per_mm = 框高 / 冠长"""
    for t in base_teeth:
        if t.site in (11, 21) and t.length and t.length > 0:
            h = abs(t.y2 - t.y1)
            if h > 0:
                return h / t.length
    return None


def build_esthetics_summary(workspace) -> str:
    """导出页用的紧凑美学参数标尺 HTML（宽长比 / 宽度比 / 龈缘）"""
    try:
        front = workspace.front_panel.get_adjusted_teeth_data()
        if not front:
            front = workspace.front_panel.get_marked_teeth_data()
        base = workspace.base_panel.get_marked_teeth_data()

        dlg = None
        px_per_mm = _calibrate_mm(base)

        # 宽长比（一行）
        ratios = []
        for t in sorted(front, key=lambda x: x.site):
            r = crown_width_height_ratio(t)
            st = crown_ratio_status(r)
            txt = "—" if r is None else f"{r:.2f}"
            color = _COLOR.get(st, "#888")
            ratios.append(f"<b>{t.site}</b> {txt} <span style='color:{color}'>({_STATUS_TEXT[st]})</span>")
        ratio_line = "　".join(ratios) if ratios else "无标记牙位"

        # 宽度比
        fw = frontal_width_ratios(front)
        wparts = []
        for side, tag in (("left", "左13:12:11"), ("right", "右23:22:21")):
            d = fw.get(side)
            if not d:
                wparts.append(f"{tag}: —")
                continue
            r = d["ratio"]
            closer = "黄金分割" if d["closer"] == "golden" else "Preston"
            dev = d["preston_dev"] if d["closer"] == "preston" else d["golden_dev"]
            wparts.append(f"{tag}: {r[0]:.2f}:1:{r[2]:.2f}（近{closer}，偏差{dev}%）")
        width_line = "　".join(wparts)

        # 龈缘
        ga = gingival_analysis(front, px_per_mm)
        gparts = []
        for side, tag in (("left", "左11/12/13"), ("right", "右21/22/23")):
            d = ga.get(side)
            if not d:
                gparts.append(f"{tag}: —")
                continue
            mm = "—" if d["diff_mm"] is None else f"{d['diff_mm']:.2f}mm"
            st = d["verdict"]
            gparts.append(f"{tag}: {mm} <span style='color:{_COLOR.get(st, '#888')}'>({_STATUS_TEXT[st]})</span>")
        ging_line = "　".join(gparts)

        calib = "已校准" if px_per_mm else "未校准(需口内冠长)"
        return (
            f"<div style='font-size:12px;line-height:1.8;text-align:left;'>"
            f"<b>② 牙冠宽长比</b>（理想 0.75~0.85）：{ratio_line}<br>"
            f"<b>③ 正面观宽度比</b>（黄金分割 1.618:1:0.618 / Preston 1.51:1:0.84）：{width_line}<br>"
            f"<b>④ 龈缘位置</b>（理想 0.5~1.0mm，{calib}）：{ging_line}</div>")
    except Exception:
        return "美学参数标尺生成失败"
