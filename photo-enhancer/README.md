# photo-enhancer

Makes phone photos of far-away, brightly lit shows look more like DSLR shots.
Runs locally, no account or upload.

    pip install -r requirements.txt
    python enhance.py photo.jpg -p concert --compare
    python enhance.py my_show_folder/ -p night

Presets: `concert` (default), `night`, `dslr`, `warm`, `film`. Every setting can be
overridden, e.g. `--denoise 0.9 --highlights 0.7 --upscale 2`.

What it does: separate luma/chroma denoise, mid-tone white balance (ignores colored
stage lights), highlight pull-down and shadow lift on a base/detail split, filmic curve,
vibrance, clarity, thresholded sharpening, grain and vignette.

Limits: this is classical processing. It can't invent detail that the phone never
captured (a performer's face from 50 m). For that, add a learned model (Real-ESRGAN,
SwinIR) or a generative edit API as an optional step after denoising.
