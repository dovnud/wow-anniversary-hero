#!/usr/bin/env python3
"""Web app: upload a photo, get an enhanced one back.

    python app.py            # then open http://localhost:8000  (add --host 0.0.0.0 to use from a phone on your Wi-Fi)
"""
import argparse
import io
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path
from queue import Queue

import cv2
import numpy as np
from flask import Flask, abort, jsonify, request, send_file, send_from_directory
from PIL import Image, ImageOps

import enhance as core

try:  # iPhone HEIC photos
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

MAX_SIDE = 4096          # bounds processing time/memory; phone photos are usually below this anyway
JOB_TTL = 3600
app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024
jobs: dict[str, dict] = {}
queue: Queue = Queue()


def worker():
    while True:
        jid = queue.get()
        job = jobs.get(jid)
        if not job:
            continue
        try:
            job["status"] = "processing"
            job["started"] = time.time()
            out = core.enhance(job["rgb"], job["settings"])
            buf = io.BytesIO()
            Image.fromarray(out).save(buf, "JPEG", quality=95, subsampling=0)
            job["result"] = buf.getvalue()
            job["status"] = "done"
        except Exception as e:  # report to the page instead of dying silently
            job["status"], job["error"] = "error", str(e)
        finally:
            job.pop("rgb", None)
            job["finished"] = time.time()


threading.Thread(target=worker, daemon=True).start()


def sweep():
    now = time.time()
    for k in [k for k, j in jobs.items() if now - j["created"] > JOB_TTL]:
        jobs.pop(k, None)


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/presets")
def presets():
    return jsonify(list(core.PRESETS))


@app.post("/api/enhance")
def enhance_api():
    sweep()
    f = request.files.get("photo")
    if not f:
        abort(400, "no photo")
    try:
        img = ImageOps.exif_transpose(Image.open(f.stream)).convert("RGB")
    except Exception:
        abort(400, "could not read that image")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    preset = request.form.get("preset", "concert")
    if preset not in core.PRESETS:
        abort(400, "unknown preset")
    s = core.PRESETS[preset]
    if request.form.get("quality") == "fast":
        s = replace(s, ai=0.0)
    jid = uuid.uuid4().hex
    orig = io.BytesIO()
    img.save(orig, "JPEG", quality=92)
    jobs[jid] = {"status": "queued", "created": time.time(), "rgb": np.asarray(img, np.uint8),
                 "settings": s, "original": orig.getvalue()}
    queue.put(jid)
    return jsonify(id=jid)


@app.get("/api/jobs/<jid>")
def job_status(jid):
    j = jobs.get(jid) or abort(404)
    pos = sum(1 for k, v in jobs.items() if v["status"] in ("queued", "processing") and v["created"] <= j["created"])
    return jsonify(status=j["status"], error=j.get("error"), ahead=max(pos - 1, 0))


@app.get("/api/jobs/<jid>/<kind>.jpg")
def job_image(jid, kind):
    j = jobs.get(jid) or abort(404)
    data = j.get("result") if kind == "result" else j.get("original") if kind == "original" else None
    if not data:
        abort(404)
    return send_file(io.BytesIO(data), mimetype="image/jpeg", download_name=f"enhanced_{jid[:6]}.jpg" if kind == "result" else None,
                     as_attachment=request.args.get("dl") == "1")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args()
    app.run(a.host, a.port, threaded=True)
