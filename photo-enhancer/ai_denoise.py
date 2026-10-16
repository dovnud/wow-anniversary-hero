"""Learned denoising with SCUNet (Apache-2.0, https://github.com/cszn/SCUNet).

Chosen on purpose: it is a *regression* denoiser (trained to match the clean image),
not a GAN or diffusion model, so it removes noise without inventing new facial features.
Weights (72 MB) are downloaded on first use to ~/.cache/photo-enhancer.
"""
import urllib.request
from pathlib import Path

import numpy as np

WEIGHTS_URL = "https://github.com/cszn/KAIR/releases/download/v1.0/scunet_color_real_psnr.pth"
CACHE = Path.home() / ".cache" / "photo-enhancer" / "scunet_color_real_psnr.pth"
_model = None


def _load():
    global _model
    if _model is None:
        import torch
        from models.network_scunet import SCUNet
        if not CACHE.exists():
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            print("downloading denoise model (72 MB, once)...")
            urllib.request.urlretrieve(WEIGHTS_URL, CACHE)
        m = SCUNet(in_nc=3, config=[4, 4, 4, 4, 4, 4, 4], dim=64)
        m.load_state_dict(torch.load(CACHE, map_location="cpu"), strict=True)
        _model = m.eval()
    return _model


def denoise(rgb, tile=512, overlap=48):
    """rgb uint8 HxWx3 -> uint8, processed in overlapping tiles with feathered blending."""
    import torch
    m = _load()
    h, w = rgb.shape[:2]
    x = torch.from_numpy(rgb.astype(np.float32) / 255).permute(2, 0, 1)[None]
    out = torch.zeros_like(x)
    wsum = torch.zeros(1, 1, h, w)
    step = tile - overlap
    ramp = torch.ones(tile)
    ramp[:overlap] = torch.linspace(0.05, 1, overlap)
    ramp[-overlap:] = torch.minimum(ramp[-overlap:], torch.linspace(1, 0.05, overlap))
    win = (ramp[:, None] * ramp[None, :])
    ys = list(range(0, max(h - tile, 0) + 1, step)); ys += [h - tile] if h > tile and ys[-1] != h - tile else []
    xs = list(range(0, max(w - tile, 0) + 1, step)); xs += [w - tile] if w > tile and xs[-1] != w - tile else []
    with torch.no_grad():
        for y0 in ys:
            for x0 in xs:
                t = x[:, :, y0:y0 + tile, x0:x0 + tile]
                th, tw = t.shape[2:]
                ph, pw = (-th) % 64, (-tw) % 64          # SCUNet needs sizes divisible by 64
                t = torch.nn.functional.pad(t, (0, pw, 0, ph), mode="reflect")
                r = m(t)[:, :, :th, :tw]
                wt = win[:th, :tw]
                out[:, :, y0:y0 + th, x0:x0 + tw] += r * wt
                wsum[:, :, y0:y0 + th, x0:x0 + tw] += wt
    out = (out / wsum).clamp(0, 1)[0].permute(1, 2, 0).numpy()
    return (out * 255 + 0.5).astype(np.uint8)
