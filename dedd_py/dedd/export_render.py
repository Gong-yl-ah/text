# -*- coding: utf-8 -*-
"""高分辨率导出渲染

为什么不直接截界面：`WorkPanel.render_to_np()` 渲染的是**窗口大小**的位图，
窗口一小导出图就糊。这里改为按**原始图像像素**重新合成：
  原图(numpy) → 按 rect 贴牙齿模板（含亮度/黄度）→ 标注牙位/宽长比 → 排版输出
所以窗口多小都不影响导出分辨率。

对外接口：
  build_view_images(panel)             -> (before, after) 两张全分辨率 numpy
  compose_design(...) / compose_compare(...) / compose_sheet(...)   -> PIL.Image
  export_case(...)                     -> 一次导出四张图（设计图/口内对比/正面对比/总图）
  export_design_only(...)              -> 只导出设计图
"""
from __future__ import annotations

import os
from datetime import date
from typing import List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .image_utils import adjust_bright_yellow, qimage_to_np
from .teeth_templates import get_template
from .widgets.adjust_panel import MODE_NONE, MODE_REAL

# ---- 版式常量（像素） ----
MARGIN = 64
HEADER_H = 150
CAPTION_H = 78
LEGEND_H = 64
GAP = 36
MAX_SIDE = 1800          # 单图最长边上限（避免超大原图导出成几十 MB）
JPEG_QUALITY = 95

_FONT_REG = r"C:\Windows\Fonts\msyh.ttc"
_FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
_FONT_FALLBACK = (r"C:\Windows\Fonts\simhei.ttf", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")


def font(size: int, bold: bool = False):
    """中文字体（雅黑优先，失败回退黑体，再失败用默认字体）"""
    for path in ((_FONT_BOLD if bold else _FONT_REG), _FONT_REG) + _FONT_FALLBACK:
        try:
            return ImageFont.truetype(path, int(size))
        except Exception:
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# 1. 全分辨率合成
# ---------------------------------------------------------------------------
def view_before(panel) -> Optional[np.ndarray]:
    """原始照片（设计前），全分辨率"""
    img = panel.get_image()
    if img is None or img.isNull():
        return None
    arr = qimage_to_np(img)
    if arr is None:
        return None
    return np.ascontiguousarray(arr[:, :, :3])


def view_after(panel) -> Optional[np.ndarray]:
    """设计后：原图 + 牙齿模板（全分辨率，含亮度/黄度）"""
    base = view_before(panel)
    if base is None:
        return None
    ap = panel.adjust_panel
    if ap.mode == MODE_NONE or not ap.items:
        return base

    canvas = Image.fromarray(base).convert("RGBA")
    is_front = (ap.view_kind == "front")
    kind = "real_front" if is_front else "real"
    for it in ap.items:
        tpl = get_template(it.site, kind)
        if tpl is None:
            continue
        tpl_arr = qimage_to_np(tpl)
        if tpl_arr is None or tpl_arr.size == 0:
            continue
        rgb = tpl_arr[:, :, :3]
        alpha = tpl_arr[:, :, 3]
        # 亮度/黄度：正面视图或牙冠模式生效（与界面上的规则一致）
        if (is_front or ap.mode == MODE_REAL) and (ap.bright or ap.yellow):
            rgb = adjust_bright_yellow(rgb, ap.bright, ap.yellow)
        patch = Image.fromarray(np.dstack([rgb, alpha]), "RGBA")
        r = it.rect_img
        w = max(1, int(round(r.width)))
        h = max(1, int(round(r.height)))
        patch = patch.resize((w, h), Image.LANCZOS)
        canvas.paste(patch, (int(round(r.x1)), int(round(r.y1))), patch)   # paste 自动裁剪越界
    return np.array(canvas.convert("RGB"))


def build_view_images(panel) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    return view_before(panel), view_after(panel)


# ---------------------------------------------------------------------------
# 2. 标注（牙位号 + 宽长比图例）
# ---------------------------------------------------------------------------
def annotate_teeth(img: np.ndarray, items: Sequence, color=(255, 214, 0)) -> Image:
    """在图上画牙位框与牙位号；宽长比统一放到下方图例里（避免标签互相压字）"""
    pil = Image.fromarray(img).convert("RGB")
    if not items:
        return pil
    draw = ImageDraw.Draw(pil)
    h, w = img.shape[:2]
    line_w = max(2, int(round(min(w, h) / 420)))
    for it in items:
        r = it.rect_img
        x1, y1, x2, y2 = r.x1, r.y1, r.x2, r.y2
        if (x2 - x1) < 2 or (y2 - y1) < 2:
            continue
        draw.rectangle([x1, y1, x2, y2], outline=color, width=line_w)
        # 牙位号：字号按框尺寸自适应并设上限，放在框内左上角，加黑底保证浅色照片上也看得清
        bw, bh = (x2 - x1), (y2 - y1)
        fsize = max(12, min(int(bw * 0.55), int(bh * 0.22), 40))
        f = font(fsize, bold=True)
        label = str(it.site)
        pad = max(2, int(round(fsize * 0.18)))
        try:
            tb = draw.textbbox((0, 0), label, font=f)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
            draw.rectangle([x1 + 2, y1 + 2, x1 + 2 + tw + pad * 2, y1 + 2 + th + pad * 2],
                           fill=(0, 0, 0))
            draw.text((x1 + 2 + pad, y1 + 2 + pad - tb[1]), label, font=f, fill=color)
        except Exception:
            draw.text((x1 + 3, y1 + 2), label, font=f, fill=color)
    return pil


def ratio_legend(items: Sequence) -> str:
    """宽长比图例文本：11 0.32 · 12 0.75 · …（宽长比 = 牙框宽 / 高，与界面读数一致）"""
    parts = []
    for it in items:
        r = it.rect_img
        if (r.x2 - r.x1) < 2 or (r.y2 - r.y1) < 2:
            continue
        parts.append(f"{it.site}  {(r.x2 - r.x1) / (r.y2 - r.y1):.2f}")
    return "宽长比（宽/高）：" + "　·　".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# 3. 排版
# ---------------------------------------------------------------------------
def _fit_height(img: Image, height: int) -> Image:
    ratio = height / img.height
    return img.resize((max(1, int(round(img.width * ratio))), height), Image.LANCZOS)


def _fit_width(img: Image, width: int) -> Image:
    ratio = width / img.width
    return img.resize((width, max(1, int(round(img.height * ratio)))), Image.LANCZOS)


def _clamp_side(img: Image, max_side: int = MAX_SIDE) -> Image:
    if max(img.size) <= max_side:
        return img
    return _fit_height(img, max_side) if img.height >= img.width else _fit_width(img, max_side)


def _text_w(draw: ImageDraw.ImageDraw, text: str, f) -> int:
    try:
        return int(draw.textlength(text, font=f))
    except Exception:
        return len(text) * int(getattr(f, "size", 16)) // 2


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, f, max_w: int) -> List[str]:
    """按字符换行（中文没有空格可断），返回行列表"""
    lines, cur = [], ""
    for ch in text:
        trial = cur + ch
        if not cur or _text_w(draw, trial, f) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def _probe() -> ImageDraw.ImageDraw:
    return ImageDraw.Draw(Image.new("RGB", (8, 8)))


def _wrap_tokens(draw: ImageDraw.ImageDraw, tokens: Sequence[str], sep: str, f,
                 max_w: int) -> List[str]:
    """按“词”换行（如宽长比图例），避免把 22 0.28 拆成 "2" + "2 0.28" """
    lines, cur = [], ""
    for tok in tokens:
        trial = f"{cur}{sep}{tok}" if cur else tok
        if not cur or _text_w(draw, trial, f) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = tok
    if cur:
        lines.append(cur)
    return lines or [""]


def _draw_header(draw: ImageDraw.ImageDraw, width: int, title: str, subtitle: str):
    """标题栏：标题/副标题都按画布宽度自动换行，避免窄图上被裁掉"""
    max_w = width - MARGIN * 2
    y = int(MARGIN * 0.42)
    if title:
        tf = font(44, bold=True)
        for line in _wrap_text(draw, title, tf, max_w)[:2]:
            draw.text((MARGIN, y), line, font=tf, fill=(28, 32, 38))
            y += 52
    if subtitle:
        sf = font(24)
        for line in _wrap_tokens(draw, subtitle.split("　|　"), "　|　", sf, max_w)[:3]:
            draw.text((MARGIN, y + 2), line, font=sf, fill=(90, 96, 105))
            y += 30
    draw.line([(MARGIN, HEADER_H - 18), (width - MARGIN, HEADER_H - 18)],
              fill=(220, 223, 228), width=2)


def compose_design(design: Image, title: str, subtitle: str,
                   legend: str = "", with_header: bool = True,
                   with_caption: bool = True) -> Image:
    """单张设计图（可选标题栏 / 宽长比图例 / 图注；图例按宽度自动换行）"""
    design = _clamp_side(design)
    W = design.width + MARGIN * 2
    probe = _probe()
    legend_f = font(24)
    legend_lines = (_wrap_tokens(probe, legend.split("　·　"), "　·　", legend_f, W - 2 * MARGIN)
                    if legend else [])
    cap = "设计图示（牙位标注 · 宽长比为牙框宽/高）"
    cap_f = font(26, bold=True)
    cap_lines = _wrap_text(probe, cap, cap_f, W - 2 * MARGIN) if with_caption else []
    header_h = HEADER_H if with_header else 0
    legend_h = (len(legend_lines) * 34 + 16) if legend_lines else 0
    cap_h = (len(cap_lines) * 38 + 22) if cap_lines else 16
    H = header_h + design.height + legend_h + cap_h
    sheet = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(sheet)
    if with_header:
        _draw_header(draw, W, title, subtitle)
    y = header_h
    sheet.paste(design, (MARGIN, y))
    y += design.height
    for line in legend_lines:
        draw.text(((W - _text_w(draw, line, legend_f)) / 2, y + 12),
                  line, font=legend_f, fill=(70, 76, 84))
        y += 34
    if legend_lines:
        y += 16
    for line in cap_lines:
        draw.text(((W - _text_w(draw, line, cap_f)) / 2, y + 12),
                  line, font=cap_f, fill=(60, 66, 74))
        y += 38
    return sheet


def compose_compare(before: Image, after: Image, title: str, subtitle: str,
                    labels: Tuple[str, str] = ("设计前", "设计后"),
                    with_header: bool = True) -> Image:
    """左右对比图：等高、中间留缝、可选标题栏 + 图注"""
    target_h = min(max(before.height, after.height), 1200)
    b = _fit_height(before, target_h) if before.height != target_h else before
    a = _fit_height(after, target_h) if after.height != target_h else after
    header_h = HEADER_H if with_header else 0
    W = MARGIN * 2 + b.width + GAP + a.width
    H = header_h + target_h + CAPTION_H
    sheet = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(sheet)
    if with_header:
        _draw_header(draw, W, title, subtitle)
    y = header_h
    x0 = MARGIN
    sheet.paste(b, (x0, y))
    x1 = x0 + b.width + GAP
    sheet.paste(a, (x1, y))
    f_cap = font(26, bold=True)
    for text, x, w in ((labels[0], x0, b.width), (labels[1], x1, a.width)):
        draw.text((x + (w - _text_w(draw, text, f_cap)) / 2, y + target_h + 22),
                  text, font=f_cap, fill=(60, 66, 74))
    draw.line([(x0 + b.width + GAP / 2, y), (x0 + b.width + GAP / 2, y + target_h)],
              fill=(230, 232, 236), width=2)
    return sheet


def compose_sheet(blocks: Sequence[Tuple[str, Image]], title: str, subtitle: str) -> Image:
    """把（小节标题, 图）竖排成一张总图；块内不再重复标题栏，长标题自动换行"""
    blocks = [(t, _clamp_side(img, 1400)) for t, img in blocks if img is not None]
    if not blocks:
        return Image.new("RGB", (900, 500), "white")
    W = max(img.width for _, img in blocks) + MARGIN * 2
    probe = _probe()
    f_cap = font(28, bold=True)
    laid = []
    for cap, img in blocks:
        lines = _wrap_text(probe, cap, f_cap, W - 2 * MARGIN)
        laid.append((lines, img, len(lines) * 38 + 30))
    H = HEADER_H + sum(img.height + h for _, img, h in laid)
    sheet = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(sheet)
    _draw_header(draw, W, title, subtitle)
    y = HEADER_H
    for lines, img, h in laid:
        sheet.paste(img, ((W - img.width) // 2, y))
        ty = y + img.height + 16
        for line in lines:
            draw.text(((W - _text_w(draw, line, f_cap)) / 2, ty),
                      line, font=f_cap, fill=(60, 66, 74))
            ty += 38
        y += img.height + h
    return sheet


def save_jpeg(img: Image, path: str, quality: int = JPEG_QUALITY) -> str:
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    img.convert("RGB").save(path, "JPEG", quality=quality, subsampling=0)
    return path


# ---------------------------------------------------------------------------
# 4. 一次导出
# ---------------------------------------------------------------------------
def _subtitle(info, view_name: str = "") -> str:
    name = getattr(info, "name", "") or "未命名"
    gender = getattr(info, "gender", "") or "未知"
    age = getattr(info, "age", "")
    phone = getattr(info, "phone", "")
    parts = [f"姓名 {name}", f"性别 {gender}"]
    if age:
        parts.append(f"年龄 {age} 岁")
    if phone:
        parts.append(f"电话 {phone}")
    parts.append(f"日期 {date.today().isoformat()}")
    if view_name:
        parts.append(view_name)
    return "　|　".join(parts)


def _pick_items(workspace) -> List:
    base_items = list(workspace.base_panel.adjust_panel.items)
    return base_items if base_items else list(workspace.front_panel.adjust_panel.items)


def export_case(workspace, info, out_dir: str, stem: Optional[str] = None) -> List[str]:
    """导出四张图：设计图 / 口内对比 / 正面对比 / 总图（全部按原图分辨率）"""
    bb, ba = build_view_images(workspace.base_panel)
    fb, fa = build_view_images(workspace.front_panel)
    items = _pick_items(workspace)
    legend = ratio_legend(items)
    name = (getattr(info, "name", "") or "未命名").strip()
    stem = stem or f"{name}_{date.today().strftime('%Y%m%d')}"
    out: List[str] = []

    design_src = ba if ba is not None else fa
    design_pil = annotate_teeth(design_src, items) if design_src is not None else None

    if design_pil is not None:
        out.append(save_jpeg(
            compose_design(design_pil, "美学设计方案", _subtitle(info, "口内设计图"), legend),
            os.path.join(out_dir, f"{stem}_设计图.jpg")))

    base_cmp = None
    if bb is not None and ba is not None:
        base_cmp = compose_compare(Image.fromarray(bb), Image.fromarray(ba),
                                   "口内治疗前后对比", _subtitle(info, "口内视图"))
        out.append(save_jpeg(base_cmp, os.path.join(out_dir, f"{stem}_口内对比.jpg")))

    front_cmp = None
    if fb is not None and fa is not None:
        front_cmp = compose_compare(Image.fromarray(fb), Image.fromarray(fa),
                                    "正面微笑前后对比", _subtitle(info, "正面视图"))
        out.append(save_jpeg(front_cmp, os.path.join(out_dir, f"{stem}_正面对比.jpg")))

    # 总图：块内不要再嵌套标题栏，只在顶部放一次患者信息
    blocks = []
    if design_pil is not None:
        blocks.append(("设计图示（牙位标注）", compose_design(
            design_pil, "", "", legend, with_header=False, with_caption=False)))
    if bb is not None and ba is not None:
        blocks.append(("口内治疗前后", compose_compare(
            Image.fromarray(bb), Image.fromarray(ba), "", "", ("设计前", "设计后"),
            with_header=False)))
    if fb is not None and fa is not None:
        blocks.append(("正面微笑前后", compose_compare(
            Image.fromarray(fb), Image.fromarray(fa), "", "", ("设计前", "设计后"),
            with_header=False)))
    if blocks:
        out.append(save_jpeg(compose_sheet(blocks, "美学设计病历图", _subtitle(info)),
                             os.path.join(out_dir, f"{stem}_总图.jpg")))
    return out


def export_design_only(workspace, info, path: str) -> Optional[str]:
    """只导出设计图（工具栏『保存设计图』用）"""
    bb, ba = build_view_images(workspace.base_panel)
    fb, fa = build_view_images(workspace.front_panel)
    src = ba if ba is not None else fa
    if src is None:
        return None
    items = _pick_items(workspace)
    design = annotate_teeth(src, items)
    return save_jpeg(compose_design(design, "美学设计方案",
                                    _subtitle(info, "口内设计图"), ratio_legend(items)), path)
