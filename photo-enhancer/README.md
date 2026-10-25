# photo-enhancer

Makes phone photos of far-away, brightly lit shows look more like DSLR shots.
Runs locally, no account or upload.

## Web app (upload a photo, get a better one)

    pip install -r requirements.txt
    python app.py                    # open http://localhost:8000
    python app.py --host 0.0.0.0     # reachable from your phone on the same Wi-Fi

Pick a photo (camera roll works, HEIC too), choose a look, and slide before/after.
"Fast" skips the AI cleanup. Photos are processed in memory and dropped after an hour;
nothing leaves the machine running it.

## Command line

    pip install -r requirements.txt
    python enhance.py photo.jpg -p concert --compare
    python enhance.py my_show_folder/ -p night

Presets: `concert` (default), `night`, `dslr`, `warm`, `film`. Every setting can be
overridden, e.g. `--denoise 0.9 --highlights 0.7 --upscale 2`.

What it does: separate luma/chroma denoise, mid-tone white balance (ignores colored
stage lights), highlight pull-down and shadow lift on a base/detail split, filmic curve,
vibrance, clarity, thresholded sharpening, grain and vignette.

**AI step (face-safe by design):** noise is removed with SCUNet, a *regression* denoiser
(Apache-2.0, https://github.com/cszn/SCUNet, vendored in `models/`; weights download once to
`~/.cache/photo-enhancer`). Unlike GAN/diffusion upscalers (Real-ESRGAN, "AI enhance" apps) it
is trained to reproduce the clean image, so it doesn't invent or reshape facial features.
`--no-ai` skips it (fast); `--ai 0.5` blends it with the original. Expect ~1-3 min per
photo on CPU, seconds on a GPU.

**DSLR lens look:** `dslr_look.py` estimates depth (Depth-Anything-V2) and finds the performers
(DeepLabV3). Performers, and anything at their distance, are never blurred; the backdrop and
foreground fall softly out of focus with round bokeh, and near-clipped stage lights get a soft
glow. `--dslr 0` turns it off, `--dslr 1.4` makes the blur stronger.

Limits: it can't invent detail the phone never captured. It can't invent detail that the phone never
captured (a performer's face from 50 m). For that, add a learned model (Real-ESRGAN,
SwinIR) or a generative edit API as an optional step after denoising.
