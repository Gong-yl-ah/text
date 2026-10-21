# -*- coding: utf-8 -*-
"""图像工具 —— 对应原 DEDD 项目的 ImageUtils.java（numpy 向量化加速）"""
from __future__ import annotations

import numpy as np


def adjust_bright_yellow(image: np.ndarray, bright: int, yellow: int) -> np.ndarray:
    """亮度/黄度调整。

    与原版算法一致：
      R = R + bright + yellow
      G = G + bright + yellow
      B = B + bright - 2*yellow
    支持 3 通道 RGB 和 4 通道 RGBA（alpha 为 0 的像素不变）。
    """
    if image is None or (bright == 0 and yellow == 0):
        return image
    arr = np.asarray(image)
    if arr.dtype != np.uint8:
        return image
    out = arr.copy().astype(np.int16)
    if arr.ndim == 3 and arr.shape[2] >= 3:
        out[..., 0] += bright + yellow      # R
        out[..., 1] += bright + yellow      # G
        out[..., 2] += bright - 2 * yellow  # B
        if arr.shape[2] == 4:
            alpha = arr[..., 3]
            mask = alpha == 0
            # 透明像素保持原样
            out[..., :3] = np.where(mask[..., None], arr[..., :3], out[..., :3])
    out = np.clip(out, 0, 255).astype(np.uint8)
    return out


def lum_adjustment(image: np.ndarray, param: int) -> np.ndarray:
    """仅亮度调整（R/G/B 同时 +param）"""
    return adjust_bright_yellow(image, param, 0)


def rotate90(image: np.ndarray, direction: str = "right") -> np.ndarray:
    """顺时针(right)/逆时针(left)旋转 90°"""
    if image is None:
        return None
    k = 1 if direction == "right" else -1
    return np.rot90(image, k)


def rotate_align_horizontal(image: np.ndarray, p1, p2, bg: int = 0) -> np.ndarray:
    """按图像坐标两点（如合平面两点）旋转图像，使两点连线变为水平。

    返回扩大画布后的旋转图（背景填充 bg，默认黑）。p1/p2 为 (x, y) 元组。
    """
    if image is None:
        return None
    import math
    try:
        import cv2
    except Exception:            # 无 OpenCV 时退化为不做处理
        return image
    h, w = image.shape[:2]
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    if abs(dx) < 1e-6:
        return image
    # 图像坐标系 y 向下：线方向角 = atan2(dy, dx)；OpenCV getRotationMatrix2D
    # 的角度符号与数学约定相反，直接传该角即可把两点连线旋转到水平（已验证）
    angle = math.degrees(math.atan2(dy, dx))
    if abs(angle) < 0.05:
        return image
    cx, cy = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
    mat = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
    cos = abs(mat[0, 0])
    sin = abs(mat[0, 1])
    nw = int(h * sin + w * cos)
    nh = int(h * cos + w * sin)
    mat[0, 2] += (nw / 2.0) - cx
    mat[1, 2] += (nh / 2.0) - cy
    if image.ndim == 2:
        out = cv2.warpAffine(image, mat, (nw, nh), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=bg)
    else:
        out = cv2.warpAffine(image, mat, (nw, nh), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_CONSTANT,
                             borderValue=(bg, bg, bg) if image.shape[2] == 3 else (bg, bg, bg, 255))
    return out


def crop(image: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
    """裁剪并做边界保护"""
    if image is None:
        return None
    h, w = image.shape[:2]
    x1 = max(0, min(int(x1), w - 1))
    y1 = max(0, min(int(y1), h - 1))
    x2 = max(0, min(int(x2), w))
    y2 = max(0, min(int(y2), h))
    if x2 - x1 < 5 or y2 - y1 < 5:
        return image
    return image[y1:y2, x1:x2]


def np_to_qimage(arr: np.ndarray):
    """numpy 数组转 QImage（RGB/RGBA）"""
    from PySide6.QtGui import QImage
    if arr is None:
        return None
    arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]
    if arr.ndim == 2:
        fmt = QImage.Format_Grayscale8
        return QImage(arr.data, w, h, arr.strides[0], fmt).copy()
    if arr.shape[2] == 3:
        fmt = QImage.Format_RGB888
    elif arr.shape[2] == 4:
        fmt = QImage.Format_RGBA8888
    else:
        return None
    return QImage(arr.data, w, h, arr.strides[0], fmt).copy()


def qimage_bytes(qimg) -> bytes:
    """提取 QImage 像素字节（兼容 PySide6 各版本 bits() 返回类型）"""
    b = qimg.bits()
    n = qimg.sizeInBytes()
    if hasattr(b, "setsize"):
        try:
            b.setsize(n)
        except TypeError:
            pass
        return bytes(b)
    if isinstance(b, memoryview):
        return bytes(b)[:n]
    return bytes(b)


def qimage_bytes_to_rgba(qimg) -> np.ndarray:
    """按当前格式读取像素（不转换），处理行字节对齐"""
    w, h = qimg.width(), qimg.height()
    buf = qimage_bytes(qimg)
    bpl = qimg.bytesPerLine()
    ch = qimg.pixelFormat()  # 每像素字节数
    try:
        bpp = qimg.depth() // 8
    except Exception:
        bpp = 4
    if bpp <= 0:
        bpp = 4
    arr = np.frombuffer(buf, np.uint8).reshape(h, bpl)
    if bpl != w * bpp:
        arr = arr[:, : w * bpp]
    return arr.reshape(h, w, bpp)


def qimage_to_np(qimg) -> np.ndarray:
    """QImage 转 numpy 数组（处理行字节对齐）"""
    if qimg is None:
        return None
    from PySide6.QtGui import QImage
    qimg = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = qimg.width(), qimg.height()
    buf = qimage_bytes(qimg)
    bpl = qimg.bytesPerLine()
    arr = np.frombuffer(buf, np.uint8).reshape(h, bpl)
    if bpl != w * 4:
        arr = arr[:, : w * 4]
    return arr.reshape(h, w, 4)
