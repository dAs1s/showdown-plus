"""Shrink the fallen leaves on the autumn-forest ground by distance (far ones smaller), like the old autumn map.
Each leaf cluster is lifted out, the ground behind it refilled from the neighbouring ground pixels, and the
cluster scaled about its own centre: 0.55 at the far edge of the ground (y 166) to 1.0 by y 320."""
import sys, numpy as np
from PIL import Image
from scipy import ndimage as ndi
src, out = sys.argv[1:3]
a = np.asarray(Image.open(src).convert('RGB')).astype(float)
R, G, B = a[..., 0], a[..., 1], a[..., 2]
H, W = R.shape; yy, xx = np.mgrid[0:H, 0:W]
gm = ndi.median_filter(a, (15, 15, 1))
d = np.linalg.norm(a - gm, axis=-1)
core = (d > 45) & ((R - G > 95) | (G > gm[..., 1] + 40)) & (yy > 164)
core = ndi.binary_closing(core, np.ones((2, 2)))
leaf = core | (ndi.binary_dilation(core, iterations=3) & (d > 14))   # (and their dark outlines and shading)
lab, n = ndi.label(ndi.binary_dilation(core, np.ones((3, 3))), np.ones((3, 3)))
res = a.copy()
jobs = []
lift = np.zeros((H, W), bool)
for i, o in enumerate(ndi.find_objects(lab), start=1):
    y0, y1, x0, x1 = o[0].start, o[0].stop, o[1].start, o[1].stop
    cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
    if (lab == i).sum() < 8 or cy >= 320: continue
    if y0 < 186 and (x0 < 80 or x1 > 520): continue           # the grass and bushes along the far edge
    f = float(np.clip(0.55 + 0.45 * (cy - 166) / (320 - 166), 0.55, 1.0))
    if f > 0.97: continue
    m = ndi.binary_dilation(lab == i, iterations=2) & leaf
    jobs.append((y0, y1, x0, x1, cy, cx, f, m))
    lift |= m
# every leaf being shrunk is lifted at once; the ground behind takes the nearest ground pixel's colour
boxes = np.zeros((H, W), bool)
for (y0, y1, x0, x1, *_r) in jobs:
    boxes[max(y0 - 3, 0):y1 + 3, max(x0 - 3, 0):x1 + 3] = True
lift_all = lift | (ndi.binary_dilation(lift, iterations=3) & (d > 12) & boxes)     # (with their soft shadows, near each leaf only)
lift_all &= yy >= 167                                   # (the grass line along the far edge stays as painted)
idx = ndi.distance_transform_edt(lift_all | (yy < 167), return_distances=False, return_indices=True)   # (refilled from ground, never grass)
res[lift_all] = a[idx[0][lift_all], idx[1][lift_all]]
for (y0, y1, x0, x1, cy, cx, f, m) in jobs:
    py0, py1, px0, px1 = max(y0 - 4, 0), min(y1 + 4, H), max(x0 - 4, 0), min(x1 + 4, W)
    mb = m[py0:py1, px0:px1]; piece = a[py0:py1, px0:px1].copy()
    h_, w_ = py1 - py0, px1 - px0
    nh, nw = max(1, int(round(h_ * f))), max(1, int(round(w_ * f)))
    # smooth resample (premultiplied), then crisp edges and each pixel snapped to the leaf's own colours
    al = mb.astype(float)
    pre = np.dstack([piece * al[..., None], al * 255])
    rs = np.asarray(Image.fromarray(pre.astype(np.uint8), 'RGBA').resize((nw, nh), Image.LANCZOS)).astype(float)
    alp = rs[..., 3] / 255.0
    col = rs[..., :3] / np.maximum(alp, 1e-3)[..., None]
    pal = piece[mb]
    nearest = np.argmin(((col[..., None, :] - pal[None, None, :, :]) ** 2).sum(-1), axis=-1)
    pi = pal[nearest]; pm = alp > 0.5
    oy, ox = int(round(cy - py0 - nh / 2)), int(round(cx - px0 - nw / 2))
    ys_, xs_ = np.where(pm)
    ty, tx = ys_ + oy + py0, xs_ + ox + px0
    ok = (ty >= 0) & (ty < H) & (tx >= 0) & (tx < W)
    res[ty[ok], tx[ok]] = pi[ys_[ok], xs_[ok]]
    print('cluster y %d-%d x %d-%d  scale %.2f' % (y0, y1, x0, x1, f))
print('clusters shrunk:', len(jobs))
Image.fromarray(np.clip(res, 0, 255).astype(np.uint8)).save(out)
if '--debug' in sys.argv:
    v = (a * 0.6).astype(np.uint8); v[lift_all] = [0, 255, 255]; v[lift] = [255, 0, 255]
    Image.fromarray(v).save(out.replace('.png', '-mask.png'))
