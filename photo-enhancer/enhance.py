#!/usr/bin/env python3
"""Make phone photos (esp. distant, low-light, stage-lit shows) look closer to DSLR.

Pipeline: denoise -> (upscale) -> white balance -> tone map (recover highlights,
lift shadows) -> filmic curve -> color grade -> clarity/sharpen -> lens look.

    python enhance.py photo.jpg                  # -> photo_enhanced.jpg
    python enhance.py shows/ -p concert --compare
"""
import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}


@dataclass
class Settings:
    denoise: float = 0.6      # 0..1 luma noise reduction (chroma is always stronger)
    upscale: float = 1.0      # output scale factor
    wb: float = 0.5           # 0 = keep stage color cast, 1 = fully neutralize
    exposure: float = 0.0     # EV before tone mapping
    shadows: float = 0.5      # 0..1 lift dark areas
    highlights: float = 0.5   # 0..1 pull bright lights back (saves color in blown LEDs)
    contrast: float = 0.35    # filmic S-curve strength
    vibrance: float = 0.3     # boosts muted colors more than saturated ones
    clarity: float = 0.35     # local contrast
    sharpen: float = 0.5
    grain: float = 0.15       # film-ish grain hides plastic denoise look
    vignette: float = 0.2
    warmth: float = 0.0       # -1 cool .. +1 warm


PRESETS = {
    "concert": Settings(),
    "dslr": Settings(denoise=0.4, wb=0.8, shadows=0.3, highlights=0.3, contrast=0.3,
                     vibrance=0.2, clarity=0.3, grain=0.08, vignette=0.15),
    "night": Settings(denoise=0.85, exposure=0.6, shadows=0.75, highlights=0.65,
                      clarity=0.4, grain=0.2, vignette=0.25),
    "warm": Settings(wb=0.4, warmth=0.35, vibrance=0.35, contrast=0.4, vignette=0.25),
    "film": Settings(wb=0.3, contrast=0.5, vibrance=0.15, grain=0.35, vignette=0.35,
                     warmth=0.15, clarity=0.2),
}


def load(path):
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    return np.asarray(img, dtype=np.uint8)


def save(path, rgb, quality=95):
    Image.fromarray(rgb).save(path, quality=quality, subsampling=0)


def srgb_to_lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055)


def luma(lin):
    return lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)


def denoise(rgb, s):
    """Chroma gets heavy smoothing (the ugly blotchy color noise); luma stays gentler."""
    if s.denoise <= 0:
        return rgb
    ycc = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb)
    h_luma = 2 + 9 * s.denoise
    h_chroma = 6 + 14 * s.denoise
    y = cv2.fastNlMeansDenoising(ycc[..., 0], None, h_luma, 7, 21)
    cr = cv2.fastNlMeansDenoising(ycc[..., 1], None, h_chroma, 7, 21)
    cb = cv2.fastNlMeansDenoising(ycc[..., 2], None, h_chroma, 7, 21)
    return cv2.cvtColor(np.dstack([y, cr, cb]), cv2.COLOR_YCrCb2RGB)


def upscale(rgb, s):
    if s.upscale <= 1.0:
        return rgb
    h, w = rgb.shape[:2]
    return cv2.resize(rgb, (round(w * s.upscale), round(h * s.upscale)), interpolation=cv2.INTER_LANCZOS4)


def white_balance(lin, s):
    """Gray-world on the mid-tones only, so bright colored stage lights don't skew it."""
    if s.wb > 0:
        y = luma(lin)
        lo, hi = np.percentile(y, [20, 85])
        m = (y > lo) & (y < hi)
        if m.sum() > 100:
            mean = lin[m].mean(0)
            gain = mean.mean() / np.maximum(mean, 1e-4)
            gain = np.clip(gain, 0.6, 1.8) ** s.wb
            lin = lin * gain
    if s.warmth:
        lin = lin * np.array([1 + 0.12 * s.warmth, 1, 1 - 0.15 * s.warmth], np.float32)
    return lin


def tone_map(lin, s):
    """Split luminance into base + detail; compress only the base, so shadows come up and
    highlights come down while texture stays intact (avoids the flat 'HDR' look)."""
    lin = lin * (2.0 ** s.exposure)
    y = np.maximum(luma(lin), 1e-5)
    logy = np.log2(y)
    # edge-preserving base layer, computed on a small copy for speed
    h, w = logy.shape
    k = min(1.0, 480 / max(h, w))
    small = cv2.resize(logy.astype(np.float32), (max(int(w * k), 1), max(int(h * k), 1)), interpolation=cv2.INTER_AREA)
    small = cv2.bilateralFilter(small, 0, 1.0, 0.04 * max(small.shape))
    base = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    detail = logy - base
    pivot = np.median(base)
    lift = np.clip(pivot - base, 0, None) * (0.55 * s.shadows)      # dark areas up
    pull = np.clip(base - pivot, 0, None) * (-0.45 * s.highlights)  # bright areas down
    new_y = 2.0 ** (base + lift + pull + detail)
    ratio = (new_y / y)[..., None]
    out = lin * ratio
    # desaturate toward white only as light approaches clipping, then roll off smoothly
    peak = out.max(-1, keepdims=True)
    out = out / (1 + np.maximum(peak - 0.8, 0) * 0.8)
    return out


def filmic(srgb, s):
    if s.contrast <= 0:
        return srgb
    k = 1 + 4 * s.contrast
    sig = 1 / (1 + np.exp(-k * (srgb - 0.5)))
    lo, hi = 1 / (1 + np.exp(k * 0.5)), 1 / (1 + np.exp(-k * 0.5))
    return srgb * (1 - 0.8) + ((sig - lo) / (hi - lo)) * 0.8


def vibrance(srgb, s):
    if s.vibrance <= 0:
        return srgb
    hsv = cv2.cvtColor(srgb.astype(np.float32), cv2.COLOR_RGB2HSV)
    sat = hsv[..., 1]
    hsv[..., 1] = np.clip(sat + s.vibrance * (1 - sat) * sat ** 0.5 * 1.5, 0, 1)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)


def clarity_sharpen(srgb, s):
    out = srgb
    if s.clarity > 0:
        r = max(srgb.shape[:2]) * 0.01
        blur = cv2.GaussianBlur(out, (0, 0), r)
        y = luma(out)[..., None]
        mid = 1 - np.abs(y * 2 - 1) ** 2   # protect deep shadows and highlights
        out = out + (out - blur) * s.clarity * 0.8 * mid
    if s.sharpen > 0:
        blur = cv2.GaussianBlur(out, (0, 0), 1.2)
        detail = out - blur
        # core the threshold so remaining noise is not amplified
        mask = (np.abs(detail) > 0.004).astype(np.float32)
        out = out + detail * s.sharpen * 1.2 * mask
    return out


def lens_look(srgb, s, seed=0):
    h, w = srgb.shape[:2]
    if s.vignette > 0:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        d = ((xx - w / 2) ** 2 + (yy - h / 2) ** 2) / ((w / 2) ** 2 + (h / 2) ** 2)
        srgb = srgb * (1 - s.vignette * d ** 1.5)[..., None]
    if s.grain > 0:
        rng = np.random.default_rng(seed)
        g = rng.normal(0, 1, (h, w)).astype(np.float32)
        g = cv2.GaussianBlur(g, (0, 0), 0.7)
        y = luma(srgb)
        weight = 1 - np.abs(y * 2 - 1)   # grain lives in the mid-tones
        srgb = srgb + (g * 0.025 * s.grain * (0.4 + weight))[..., None]
    return srgb


def enhance(rgb, s):
    rgb = denoise(rgb, s)
    rgb = upscale(rgb, s)
    lin = srgb_to_lin(rgb.astype(np.float32) / 255)
    lin = white_balance(lin, s)
    lin = tone_map(lin, s)
    srgb = lin_to_srgb(lin).astype(np.float32)
    srgb = filmic(srgb, s)
    srgb = vibrance(np.clip(srgb, 0, 1), s)
    srgb = clarity_sharpen(srgb, s)
    srgb = lens_look(srgb, s)
    return (np.clip(srgb, 0, 1) * 255 + 0.5).astype(np.uint8)


def side_by_side(before, after):
    if before.shape != after.shape:
        before = cv2.resize(before, (after.shape[1], after.shape[0]), interpolation=cv2.INTER_CUBIC)
    return np.hstack([before, after])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", type=Path, help="image file or folder")
    p.add_argument("-o", "--out", type=Path, help="output file or folder")
    p.add_argument("-p", "--preset", choices=PRESETS, default="concert")
    p.add_argument("--compare", action="store_true", help="also write a before|after image")
    for f in Settings.__dataclass_fields__:
        p.add_argument("--" + f, type=float, help=f"override preset value for {f}")
    a = p.parse_args(argv)

    s = replace(PRESETS[a.preset], **{f: getattr(a, f) for f in Settings.__dataclass_fields__
                                      if getattr(a, f) is not None})
    if a.input.is_dir():
        files = sorted(f for f in a.input.iterdir() if f.suffix.lower() in EXTS and "_enhanced" not in f.stem)
        outdir = a.out or a.input / "enhanced"
        outdir.mkdir(parents=True, exist_ok=True)
        jobs = [(f, outdir / (f.stem + "_enhanced.jpg")) for f in files]
    else:
        jobs = [(a.input, a.out or a.input.with_name(a.input.stem + "_enhanced.jpg"))]
    if not jobs:
        sys.exit("no images found")

    for src, dst in jobs:
        before = load(src)
        after = enhance(before, s)
        save(dst, after)
        if a.compare:
            save(dst.with_name(dst.stem + "_compare.jpg"), side_by_side(before, after), 90)
        print(f"{src} -> {dst}")


if __name__ == "__main__":
    main()
