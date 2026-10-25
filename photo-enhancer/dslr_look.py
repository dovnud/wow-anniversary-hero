"""DSLR-style optics on top of an enhanced photo.

Phones keep everything in focus, which is the main tell. A real lens at a wide aperture
keeps the performers sharp and lets the rest fall away into soft, round highlights.

  depth (Depth-Anything-V2 small)  -> how far behind the focus plane each pixel is
  person mask (DeepLabV3)          -> performers are NEVER blurred, so faces stay untouched
  disc-shaped blur on linear light -> round bokeh, bright lights bloom the way they do on glass
  highlight glow + light grain     -> soft halation, and blurred areas don't look plastic
"""
import cv2
import numpy as np

_depth = _seg = None


def _load_models():
    global _depth, _seg
    if _depth is None:
        from transformers import pipeline
        _depth = pipeline("depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf", device=-1)
    if _seg is None:
        from torchvision.models.segmentation import deeplabv3_mobilenet_v3_large, DeepLabV3_MobileNet_V3_Large_Weights
        _seg = deeplabv3_mobilenet_v3_large(weights=DeepLabV3_MobileNet_V3_Large_Weights.DEFAULT).eval()


def nearness(rgb):
    """0 (far) .. 1 (near), same size as rgb."""
    from PIL import Image
    _load_models()
    h, w = rgb.shape[:2]
    d = _depth(Image.fromarray(rgb))["predicted_depth"].squeeze().numpy().astype(np.float32)
    d = cv2.resize(d, (w, h), interpolation=cv2.INTER_CUBIC)
    lo, hi = np.percentile(d, [1, 99])
    return np.clip((d - lo) / max(hi - lo, 1e-6), 0, 1)


def person_mask(rgb):
    """0..1 probability of 'person', same size as rgb."""
    import torch
    _load_models()
    h, w = rgb.shape[:2]
    k = 1024 / max(h, w)
    small = cv2.resize(rgb, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
    x = torch.from_numpy(small.astype(np.float32) / 255).permute(2, 0, 1)
    x = (x - torch.tensor([0.485, 0.456, 0.406])[:, None, None]) / torch.tensor([0.229, 0.224, 0.225])[:, None, None]
    with torch.no_grad():
        p = _seg(x[None])["out"].softmax(1)[0, 15].numpy()          # class 15 = person
    return cv2.resize(p, (w, h), interpolation=cv2.INTER_CUBIC).clip(0, 1)


def _disc(r):
    r = max(r, 0.5)
    n = int(np.ceil(r)) * 2 + 1
    yy, xx = np.mgrid[:n, :n] - n // 2
    k = np.clip(r + 0.5 - np.hypot(xx, yy), 0, 1).astype(np.float32)
    return k / k.sum()


def _guided(guide, src, r, eps):
    """Edge-aware smoothing of `src` that snaps to edges in `guide` (He et al. guided filter)."""
    f = lambda x: cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1), borderType=cv2.BORDER_REFLECT)
    mg, ms = f(guide), f(src)
    cov = f(guide * src) - mg * ms
    var = f(guide * guide) - mg * mg
    a = cov / (var + eps)
    b = ms - a * mg
    return f(a) * guide + f(b)


def blur_map(rgb, strength, focus=None):
    h, w = rgb.shape[:2]
    near = nearness(rgb)
    mask = person_mask(rgb)
    hard = mask > 0.5
    if focus is None:
        focus = float(np.median(near[hard])) if hard.mean() > 0.005 else float(np.percentile(near, 70))
    maxr = 0.0075 * max(h, w) * strength            # ~19 px on a 2576 px photo at strength 1
    dist = np.abs(near - focus)
    r = maxr * np.clip((dist - 0.07) / 0.40, 0, 1) ** 1.2
    # performers stay sharp: dilate + feather the mask so hair/costume edges are covered
    prot = cv2.dilate((mask > 0.3).astype(np.uint8), np.ones((17, 17), np.uint8)).astype(np.float32)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    # anything at the performers' distance is also protected, so a missed detection (e.g. a backbend) can't be blurred
    dprot = (np.clip(1 - (dist - 0.05) / 0.08, 0, 1) > 0.5).astype(np.float32)
    dprot = cv2.dilate(dprot, np.ones((9, 9), np.uint8))
    prot = np.maximum(prot, dprot)
    prot = np.clip(_guided(gray, prot, 12, 2e-3), 0, 1)           # snap to hair / finger / costume edges
    prot = cv2.GaussianBlur(prot, (0, 0), 2.0)
    r = r * (1 - prot)
    return cv2.GaussianBlur(r, (0, 0), 2.0), near, mask, focus, prot


def apply(rgb, strength=1.0, glow=0.22, grain=0.012, seed=1):
    h, w = rgb.shape[:2]
    rmap, near, mask, focus, prot = blur_map(rgb, strength)
    lin = (rgb.astype(np.float32) / 255) ** 2.2
    lum = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    hw = (1 + 10 * np.clip(lum - 0.35, 0, 1) ** 1.5)[..., None]       # bright lights bloom into bokeh balls
    maxr = max(float(rmap.max()), 1.0)
    radii = [0.0] + list(np.linspace(maxr / 6, maxr, 6))
    levels = [lin]
    for ri in radii[1:]:
        wb = (np.clip(rmap / (ri * 0.6), 0, 1) * (1 - np.clip(prot * 5, 0, 1)))[..., None]   # sharp pixels and people never leak into the blur
        wgt = hw * wb + 1e-4
        k = _disc(ri)
        num = cv2.filter2D(lin * wgt, -1, k, borderType=cv2.BORDER_REFLECT)
        den = cv2.filter2D(wgt, -1, k, borderType=cv2.BORDER_REFLECT)
        if den.ndim == 2:
            den = den[..., None]
        levels.append(num / np.maximum(den, 1e-4))
    idx = np.interp(rmap, radii, np.arange(len(radii)))
    out = np.zeros_like(lin)
    for i, lv in enumerate(levels):
        out += lv * np.clip(1 - np.abs(idx - i), 0, 1)[..., None]
    # keep sharp pixels exactly as they were (no blur-level resampling softness)
    keep = np.clip(1 - rmap / 0.6, 0, 1)[..., None]
    out = out * (1 - keep) + lin * keep
    if glow > 0:
        # glow comes from real light sources only (very bright pixels), never from performers' skin/costumes
        src = np.clip((lum - 0.88) / 0.08, 0, 1) * (1 - np.clip(prot * 20, 0, 1))   # near-clipped bulbs only; skin never reaches this
        g = cv2.GaussianBlur(lin * src[..., None], (0, 0), 0.012 * max(h, w))
        out = out + glow * g * np.array([1.0, 0.95, 1.05], np.float32)
    out = out / (1 + np.maximum(out.max(-1, keepdims=True) - 0.9, 0) * 0.5)
    srgb = np.clip(out, 0, 1) ** (1 / 2.2)
    if grain > 0:
        g = cv2.GaussianBlur(np.random.default_rng(seed).normal(0, 1, (h, w)).astype(np.float32), (0, 0), 0.7)
        srgb = srgb + (g * grain * (1 - 0.6 * np.clip(1 - rmap / 0.6, 0, 1)))[..., None]
    return (np.clip(srgb, 0, 1) * 255 + 0.5).astype(np.uint8), dict(focus=focus, near=near, mask=mask, rmap=rmap)
