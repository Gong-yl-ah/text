# -*- coding: utf-8 -*-
"""工程文件读写 —— 对应原 DEDD 项目的 ProjDataHelper.java

本程序格式 (.deddp)：zip 包
  project.json  工程数据（基本信息 / 牙齿标记 / 调整 / 唇线）
  base.jpg      口内视图原图
  front.jpg     正面视图原图

同时支持导入原 Java 版工程 (.depx)：zip 包内为
  dedd.xml + base.jpg + front.jpg
"""
from __future__ import annotations

import io
import json
import os
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

from .models import BasicInfo, ProjData, ToothData, ViewData

PROJ_JSON = "project.json"
BASE_IMG = "base.jpg"
FRONT_IMG = "front.jpg"
DEPX_XML = "dedd.xml"


def _np_to_jpg_bytes(arr: np.ndarray) -> bytes:
    if arr is None:
        return b""
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def _jpg_bytes_to_np(data: bytes) -> np.ndarray:
    if not data:
        return None
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return np.asarray(img)


def save_project(proj: ProjData, base_image: np.ndarray, front_image: np.ndarray, path: str) -> bool:
    """保存 .deddp 工程文件"""
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(PROJ_JSON, json.dumps(proj.to_dict(), ensure_ascii=False, indent=2))
            if base_image is not None:
                zf.writestr(BASE_IMG, _np_to_jpg_bytes(base_image))
            if front_image is not None:
                zf.writestr(FRONT_IMG, _np_to_jpg_bytes(front_image))
        return True
    except Exception:
        return False


def load_project(path: str) -> tuple:
    """读取 .deddp 工程文件，返回 (ProjData, base_image, front_image)"""
    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())
        if PROJ_JSON not in names:
            raise ValueError("不是有效的工程文件（缺少 project.json）")
        proj = ProjData.from_dict(json.loads(zf.read(PROJ_JSON).decode("utf-8")))
        base_img = _jpg_bytes_to_np(zf.read(BASE_IMG)) if BASE_IMG in names else None
        front_img = _jpg_bytes_to_np(zf.read(FRONT_IMG)) if FRONT_IMG in names else None
    return proj, base_img, front_img


# ---------------- 原 Java 版 (.depx) 导入 ----------------

def import_depx(path: str) -> tuple:
    """导入原版 .depx：解析 dedd.xml + base.jpg + front.jpg

    原版 dedd.xml 结构（DOM）：
      <dedd_data>
        <basic_info><name>..</name><age>..</age><gender>..</gender><phone>..</phone></basic_info>
        <lip_points><point id="0"><x>..</x><y>..</y></point>...</lip_points>
        <closed>false</closed>
        <workpanel id="front">
          <mark_teeth><tooth><id>11</id><x1>..</x1><y1>..</y1><x2>..</x2><y2>..</y2><length>..</length></tooth>...</mark_teeth>
          <adjust_teeth>...</adjust_teeth>
          <bright>0</bright><yellow>0</yellow>
        </workpanel>
        <workpanel id="base">...</workpanel>
      </dedd_data>
    """
    proj = ProjData()
    with zipfile.ZipFile(path, "r") as zf:
        names = set(zf.namelist())
        if DEPX_XML not in names:
            raise ValueError("不是原版 DEDD 工程文件（缺少 dedd.xml）")
        root = ET.fromstring(zf.read(DEPX_XML))

        # 基本信息
        info_elm = root.find("basic_info")
        if info_elm is not None:
            m = {c.tag: (c.text or "") for c in info_elm}
            proj.basic = BasicInfo(name=m.get("name", ""),
                                   age=_safe_int(m.get("age", 0)),
                                   gender=m.get("gender", ""),
                                   phone=m.get("phone", ""))

        # 唇线
        lip_elm = root.find("lip_points")
        if lip_elm is not None:
            for p in lip_elm.findall("point"):
                x = _safe_float(p.findtext("x", "0"))
                y = _safe_float(p.findtext("y", "0"))
                proj.lip_points.append((x, y))
        proj.lip_closed = (root.findtext("closed") or "").lower() == "true"

        # 视图数据
        for wp in root.findall("workpanel"):
            wid = wp.get("id", "")
            vd = ViewData()
            vd.marked = _parse_teeth(wp.find("mark_teeth"))
            vd.adjusted = _parse_teeth(wp.find("adjust_teeth"))
            vd.bright = _safe_int(wp.findtext("bright", "0"))
            vd.yellow = _safe_int(wp.findtext("yellow", "0"))
            if wid == "base":
                proj.base = vd
            elif wid == "front":
                proj.front = vd

        base_img = _jpg_bytes_to_np(zf.read(BASE_IMG)) if BASE_IMG in names else None
        front_img = _jpg_bytes_to_np(zf.read(FRONT_IMG)) if FRONT_IMG in names else None
    return proj, base_img, front_img


def _parse_teeth(node) -> list:
    result = []
    if node is None:
        return result
    for t in node.findall("tooth"):
        td = ToothData(
            site=_safe_int(t.findtext("id", "0")),
            x1=_safe_float(t.findtext("x1", "0")),
            y1=_safe_float(t.findtext("y1", "0")),
            x2=_safe_float(t.findtext("x2", "0")),
            y2=_safe_float(t.findtext("y2", "0")),
            length=_safe_float(t.findtext("length", "0")),
        )
        result.append(td)
    return result


def _safe_int(v, default=0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _safe_float(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
