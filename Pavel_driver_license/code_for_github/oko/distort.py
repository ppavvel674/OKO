"""Искажения для стресс-теста и «фото телефоном»."""
from __future__ import annotations

import io
import math
import random

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

KINDS = ["blur", "motion", "rotate", "perspective", "noise", "jpeg", "lowres", "glare", "shadow", "dark", "occlusion", "crumple"]
TITLES = {
    "blur": "Размытие", "motion": "Смаз", "rotate": "Поворот", "perspective": "Перспектива",
    "noise": "Шум", "jpeg": "Сжатие JPEG", "lowres": "Низкое разрешение", "glare": "Блик",
    "shadow": "Тень", "dark": "Темнота", "occlusion": "Перекрытие", "crumple": "Помятость",
}

def apply(img: Image.Image, kind: str, level: int, seed: int = 0) -> Image.Image:
    """Применяет искажение kind силы level (0-4)."""
    if level <= 0:
        return img.copy()
    rng = random.Random(seed + level * 100 + KINDS.index(kind))
    arr = np.array(img.convert("RGB"))
    h, w = arr.shape[:2]
    strength = level / 4.0

    if kind == "blur":
        k = int(1 + strength * 10) * 2 + 1
        arr = cv2.GaussianBlur(arr, (k, k), 0)
    elif kind == "motion":
        k = int(1 + strength * 15)
        kernel = np.zeros((k, k))
        kernel[int((k - 1) / 2), :] = np.ones(k)
        kernel = kernel / k
        arr = cv2.filter2D(arr, -1, kernel)
    elif kind == "rotate":
        angle = strength * 15 * rng.choice([-1, 1])
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        arr = cv2.warpAffine(arr, m, (w, h), borderValue=(230, 230, 230))
    elif kind == "perspective":
        d = int(min(w, h) * 0.2 * strength)
        pts1 = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
        pts2 = np.float32([[d, d], [w - d, 0], [0, h], [w, h - d]])
        m = cv2.getPerspectiveTransform(pts1, pts2)
        arr = cv2.warpPerspective(arr, m, (w, h), borderValue=(230, 230, 230))
    elif kind == "noise":
        noise = np.random.normal(0, 25 * level, arr.shape)
        arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    elif kind == "jpeg":
        quality = max(5, int(90 - level * 20))
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, format="JPEG", quality=quality)
        buf.seek(0)
        arr = np.array(Image.open(buf).convert("RGB"))
    elif kind == "lowres":
        scale = 1.0 - (level * 0.2)
        small = cv2.resize(arr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LINEAR)
        arr = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    elif kind == "glare":
        overlay = np.zeros_like(arr)
        cv2.circle(overlay, (int(w * 0.8), int(h * 0.2)), int(w * 0.3 * strength), (255, 255, 255), -1)
        mask = cv2.GaussianBlur(overlay, (101, 101), 0).astype(float) / 255.0
        arr = np.clip(arr * (1 - mask) + 255 * mask, 0, 255).astype(np.uint8)
    elif kind == "shadow":
        overlay = np.zeros_like(arr)
        cv2.rectangle(overlay, (int(w * 0.2), 0), (int(w * 0.8), h), (0, 0, 0), -1)
        mask = cv2.GaussianBlur(overlay, (151, 151), 0).astype(float) / 255.0
        arr = np.clip(arr * (1 - mask * 0.7), 0, 255).astype(np.uint8)
    elif kind == "dark":
        arr = np.clip(arr * (1.0 - strength * 0.6), 0, 255).astype(np.uint8)
    elif kind == "occlusion":
        overlay = np.zeros_like(arr)
        x = int(w * 0.4)
        y = int(h * 0.3)
        cv2.rectangle(overlay, (x, y), (x + int(w * 0.15 * strength), y + int(h * 0.4 * strength)), (100, 100, 100), -1)
        mask = cv2.GaussianBlur(overlay, (31, 31), 0).astype(float) / 255.0
        arr = np.clip(arr * (1 - mask) + 100 * mask, 0, 255).astype(np.uint8)
    elif kind == "crumple":
        rows, cols = arr.shape[:2]
        map_x, map_y = np.meshgrid(np.arange(cols), np.arange(rows))
        freq = 0.02 * level
        map_x = map_x + np.sin(map_y * freq) * (10 * level)
        map_y = map_y + np.cos(map_x * freq) * (10 * level)
        arr = cv2.remap(arr, map_x.astype(np.float32), map_y.astype(np.float32), cv2.INTER_LINEAR)
    
    return Image.fromarray(arr)

def phone_photo(img: Image.Image, seed: int = 0) -> Image.Image:
    """Имитация «фото телефоном»: 2-4 случайных мягких искажения."""
    rng = random.Random(seed)
    out = img.copy()
    for _ in range(rng.randint(2, 4)):
        kind = rng.choice(["perspective", "rotate", "crumple", "shadow", "glare", "dark", "blur", "noise", "jpeg"])
        out = apply(out, kind, rng.randint(1, 2), seed=rng.randint(0, 10000))
    return out