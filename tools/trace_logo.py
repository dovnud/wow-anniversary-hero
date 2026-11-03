#!/usr/bin/env python3
"""Trace the WOW logo (assets/wow-logo.webp) into the compact JSON embedded in wow-logo.html.

    pip install opencv-python-headless pillow numpy
    python3 tools/trace_logo.py assets/wow-logo.webp > trace.json

Output: {"L": [{"o": [x,y,...], "h": [[x,y,...], ...]}, ...], "B": [[x, y, letterIndex], ...]}
  L = the three letter faces (W, O, W) as polygons in image pixels, plus holes (the O's counter)
  B = bulb socket centres, in image pixels
Paste the result over `var TRACE = ...` in wow-logo.html.

How it works
  1. The cyan neon outline is isolated by colour and sealed with a small dilation.
  2. The regions it encloses are labelled; the big opaque ones are the letter faces.
     Each face is grown by 7px so its polygon sits on the neon centre line.
  3. Bulb sockets are found with a circle Hough transform inside the faces, then filtered by
     distance to the face edge (drops false hits on the neon) and de-duplicated.
     Expect to miss a few dim bulbs; the O usually comes up a few short.
"""
import sys, json
import cv2, numpy as np
from PIL import Image

src = sys.argv[1] if len(sys.argv) > 1 else 'assets/wow-logo.webp'
im = np.array(Image.open(src).convert('RGBA'))
H, W = im.shape[:2]
rgb = im[..., :3].astype(int); al = im[..., 3]
SUBTITLE_Y = int(H * 0.675)                      # ignore "The Vegas Spectacular"

cy = ((rgb[..., 0] < 130) & (rgb[..., 1] > 170) & (rgb[..., 2] > 190) & (al > 150)).astype(np.uint8)
cy[SUBTITLE_Y:] = 0
seal = cv2.dilate(cy, np.ones((5, 5), np.uint8))
n, lab, st, _ = cv2.connectedComponentsWithStats((seal == 0).astype(np.uint8), connectivity=4)
faces = sorted((i for i in range(1, n) if st[i, 4] > 100000 and st[i, 0] > 0), key=lambda i: st[i, 0])

def simplify(pts, eps):
    a = np.array(pts, np.float32).reshape(-1, 1, 2)
    return cv2.approxPolyDP(a, eps, True)[:, 0, :]

def smooth(c, sig=3.0):
    p = c[:, 0, :].astype(np.float32); k = int(sig * 3) * 2 + 1
    ext = np.vstack([p[-k:], p, p[:k]])
    x = cv2.GaussianBlur(ext[:, 0].reshape(-1, 1), (1, k), sig)[:, 0]
    y = cv2.GaussianBlur(ext[:, 1].reshape(-1, 1), (1, k), sig)[:, 0]
    return np.stack([x, y], 1)[k:-k]

letters = []
for i in faces:
    m = cv2.dilate((lab == i).astype(np.uint8), np.ones((7, 7), np.uint8))
    cs, h = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    outer, holes = [], []
    for c, hh in zip(cs, h[0]):
        if cv2.contourArea(c) < 800: continue
        (holes if hh[3] >= 0 else outer).append(smooth(c))
    outer.sort(key=lambda p: -cv2.contourArea(p.reshape(-1, 1, 2)))
    letters.append((outer[0], holes))

face = np.zeros((H, W), np.uint8)
for o, hs in letters:
    cv2.fillPoly(face, [np.round(o).astype(np.int32)], 255)
    for h in hs: cv2.fillPoly(face, [np.round(h).astype(np.int32)], 0)
g = cv2.GaussianBlur(cv2.cvtColor(im[..., :3], cv2.COLOR_RGB2GRAY), (0, 0), 2.2)
circles = []
for p2 in (22, 18, 15):                          # loosen until we have ~70 candidates
    c = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT, dp=1, minDist=38, param1=90, param2=p2, minRadius=24, maxRadius=36)
    circles = [] if c is None else [(x, y) for x, y, r in c[0] if face[int(y), int(x)] > 0]
    if len(circles) >= 70: break
dt = cv2.distanceTransform(face, cv2.DIST_L2, 5)
cands = sorted((c for c in circles if dt[int(c[1]), int(c[0])] >= 27), key=lambda c: -dt[int(c[1]), int(c[0])])
bulbs = []
for x, y in cands:
    if all((x - ox) ** 2 + (y - oy) ** 2 > 44 ** 2 for ox, oy, _ in bulbs):
        li = next((k for k, (o, _) in enumerate(letters) if cv2.pointPolygonTest(o.astype(np.float32), (x, y), False) >= 0), -1)
        bulbs.append((x, y, li))

print(json.dumps(dict(
    L=[dict(o=[int(round(v)) for p in simplify(o, 3.6) for v in p],
            h=[[int(round(v)) for p in simplify(h, 3.6) for v in p] for h in hs]) for o, hs in letters],
    B=[[int(round(x)), int(round(y)), li] for x, y, li in bulbs]), separators=(',', ':')))
