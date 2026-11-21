"""Builds the motion masks for the autumn background (all coordinates in art pixels, 350x250)."""
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

def hsv(a):
    r, g, b = [a[..., i] / 255.0 for i in range(3)]
    mx = np.max(a, -1) / 255.0; mn = np.min(a, -1) / 255.0
    v = mx; s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    d = np.maximum(mx - mn, 1e-6)
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    return h, s, v

def zone(shape, x0, y0, x1, y1):
    m = np.zeros(shape, bool); m[y0:y1, x0:x1] = True; return m

def build(a):
    H, W = a.shape[:2]
    h, s, v = hsv(a.astype(float))
    yy, xx = np.mgrid[0:H, 0:W]
    lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]

    # --- sun: the bright yellow disc
    sun = (a[..., 0] > 235) & (a[..., 1] > 150) & (a[..., 2] < 160) & zone((H, W), 220, 60, 270, 95)
    sun = ndi.binary_opening(sun, iterations=1)
    cy, cx = ndi.center_of_mass(sun); r = np.sqrt(sun.sum() / np.pi)

    # --- tree canopies: strongly saturated leaves inside each tree's area, holes filled
    leaves = (s > 0.70) & (v > 0.30)
    def canopy(z):
        m = leaves & z
        m = ndi.binary_closing(m, iterations=2) & z
        m = ndi.binary_fill_holes(m)
        return ndi.binary_opening(m, iterations=1)
    left_tree = canopy(zone((H, W), 0, 16, 106, 80))
    right_tree = canopy(zone((H, W), 270, 24, 350, 80))
    # distant trees behind the field: their colors match the sky, so they're found by their
    # leafy texture instead (the sky and the mountain are smooth); returned as a 0-1 weight
    # side-to-side detail only: leaves have it, the sky's horizontal bands don't
    gx = np.zeros_like(lum); gx[:, 1:] = np.abs(lum[:, 1:] - lum[:, :-1])
    texture = ndi.uniform_filter(gx, 3)
    tex = np.clip((texture - 4.0) / 8.0, 0, 1)
    tex = ndi.grey_closing(tex, size=(3, 3))
    far_zone = zone((H, W), 92, 40, 274, 103).astype(float)
    far_zone[70:103, 172:262] = 0.0                     # the mountain stays put
    far_zone = ndi.gaussian_filter(far_zone, 2.0)
    mid_trees = ndi.gaussian_filter(tex, 1.0) * far_zone
    mid_trees[(left_tree | right_tree)] = 0
    bushes = ((s > 0.62) & (v > 0.35)) & (zone((H, W), 28, 78, 126, 106) | zone((H, W), 268, 88, 350, 110))
    bushes = ndi.binary_opening(ndi.binary_closing(bushes, iterations=1))

    # --- grass: golden blades
    golden = (h > 15) & (h < 50) & (s > 0.55) & (v > 0.50)
    grass_band = golden & zone((H, W), 0, 96, 350, 113)
    grass_left = golden & zone((H, W), 0, 104, 30, 122)
    grass_br = ((h > 18) & (h < 52) & (s > 0.6) & (v > 0.5)) & zone((H, W), 270, 196, 350, 250)
    grass_br = ndi.binary_closing(grass_br, iterations=1)

    # --- clouds: brighter than the sky behind them, in the open sky only
    sky_zone = (yy < 64) & ~ndi.binary_dilation(left_tree | right_tree, iterations=2)
    sky_zone &= ~ndi.binary_dilation(sun, iterations=6)
    base = np.zeros(H)
    for y in range(64):
        row = lum[y][sky_zone[y]]
        base[y] = np.percentile(row, 35) if row.size else 0
    clouds = sky_zone & (lum > base[:, None] + 22)
    clouds = ndi.binary_opening(clouds, iterations=1)
    clouds = ndi.binary_dilation(clouds, iterations=1) & sky_zone   # include the soft cloud edge
    mid_trees = mid_trees * ~ndi.binary_dilation(sun, iterations=4) * ~ndi.binary_dilation(clouds, iterations=1)
    return dict(sun=sun, sun_c=(cx, cy), sun_r=r, left_tree=left_tree, right_tree=right_tree,
                mid_trees=mid_trees, bushes=bushes, grass_band=grass_band, grass_left=grass_left,
                grass_br=grass_br, clouds=clouds, sky_zone=sky_zone)
