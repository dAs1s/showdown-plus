"""
Animated pixel-art battle background: swaying trees and grass, drifting clouds, shining sun.

Usage:  python animate.py <background.png> <out_prefix>
Writes <out_prefix>.gif (350x250, for the style), <out_prefix>-preview.gif (2x, for viewing)
and <out_prefix>.webp (lossless, same size as the .gif).

Every frame only moves or re-tints pixels that are already in the picture, snapped to the
picture's own pixel grid and palette, so it stays crisp pixel art. All motions repeat a whole
number of times per loop, so the last frame flows straight back into the first.
"""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from masks import build

# ---------------- settings ----------------
FRAMES = 200           # frames per loop
DELAY_MS = 100         # 100 ms per frame = 10 fps, a 20 second loop (long enough for slow clouds)
COLORS = 240           # palette size (GIF allows up to 256; a few more are added below)

TREE_SWAY = 1.3        # tree tops move up to this many pixels each way (less now: the leaves rustle instead)
BUSH_SWAY = 1.0
TREE_CYCLES = 5        # sways per loop (5 in 20 s = one sway every 4 s)
GRASS_SWAY = 1.4       # thin grass along the horizon
GRASS_FRONT_SWAY = 3.0 # the big clump in the front corner
GRASS_CYCLES = 10      # grass moves faster than trees (one sway every 2 s)
CLOUD_DRIFT = 1.84     # clouds drift up to this many pixels each way (high clouds a bit more);
                       # 1.84 = another 25% slower than 2.45, over the same 20 s
CLOUD_CYCLES = 1       # one slow drift out and back per 20 s
SUN_PULSE_CYCLES = 5   # one glow pulse every 4 s
SUN_GLOW = (255, 196, 150)   # peach light: brighter than the sky, but clearly not the sun's yellow
SPARKLE = (255, 250, 232)
SUN_SPARKLE = False    # the little twinkle on the sun
CLOUD_LINING = True    # golden lining along the bottom of the clouds, lit by the low sun
LINING_GOLD = (255, 206, 112)
LINING_SOFT = (250, 186, 104)
LINING_CYCLES = 10     # shimmer: how many glints travel along the lining per loop (10 = one every 2 s)
LINING_TOPRIGHT_CALM = 0.75   # how much the shimmer eases off on the top-right clouds (0 = not at all)
LINING_REACH = 150     # how far from the sun the lining stays strong and shimmering (pixels)
SUN_RAYS = False       # slowly turning rays of light around the sun
RAY_COUNT = 12
SUN_BEAMS = True       # soft, realistic shafts of light fanning out from the sun over the mountain
BEAM_STRENGTH = 0.62   # how bright the shafts get at their brightest (0 = off)
BEAM_LIGHT = (255, 212, 168)  # warm sunset light
BEAM_BREATHE = 0.6     # each shaft fades between 40% and 100% on its own rhythm
BEAM_CYCLES = 1        # (each shaft's own breaths per loop are set in BEAMS below)
BEAM_SWAY = 1.6        # degrees each shaft drifts side to side, once per loop
DISTANT_SWAY = 1.4     # the trees far behind the field sway a little, less than the big ones
LEAF_RUSTLE = True     # little clusters of leaves catch the light and flicker, like wind in leaves
RIM_LIGHT = True       # warm edge on the side of each big tree that faces the sun
RIM_GOLD = (255, 196, 112)
RIM_STRENGTH = 0.6
SHADOW_SWAY = True     # the trees' shadows on the field sway with the branches
DUST_MOTES = True      # golden specks floating in the shafts of light
MOTE_COUNT = 26
LEAF_LIGHT = (255, 214, 140)
SUN_SHIMMER = True     # heat shimmer: the sun's rows ripple sideways by a pixel, more toward the horizon
SHIMMER_CYCLES = 12    # ripple speed (12 per loop = one wave every 1.7 s; was 20, now 40% slower)
RIPPLE_STRENGTH = 2.2  # how far the rows swing (1 = a pixel at most; 2.2 = up to 2 px near the hills)
SUN_LIGHT_BANDS = False   # pale bands drifting up across the disc (off: they read as scanlines)
BAND_CYCLES = 10       # how often a light band rises across the disc
SUN_RECOLOR = True     # repaint the sun with a proper gradient (same size and shape as drawn)
SUN_SIZE = 0.945       # the sun's size compared with the drawing (0.945 = the 10%-smaller sun made 5% bigger)
SUN_DROP = 2           # pixels the sun sits lower than drawn (more of it behind the hills)
SUN_SOLID = (255, 212, 128)   # one solid sunset gold for the whole disc (None = the banded gradient)
SUN_COLORS = [(255, 249, 222), (255, 230, 152), (255, 203, 102), (252, 168, 74)]
#             pale core        gold             amber            orange rim
SUN_BANDS = [0.42, 0.70]   # where core -> gold -> amber change (fraction of the radius); clean steps
SUN_DITHER = False     # checker dithering where the bands meet (busy at this size)
SUN_WARM_BOTTOM = 0.22 # the lower part of the sun is warmer, as a setting sun reddens near the horizon
SUN_GLOW_COLOR = (255, 210, 156)
SUN_GLOW_STRENGTH = 0.42   # the bright glow hugging the sun
SUN_GLOW_REACH = 3.5
SUN_BLOOM = 0.12           # plus a faint wide bloom
SUN_BLOOM_REACH = 12.0
DEPTH_FADE = 0.30      # distance haze: how much the farthest things fade (0 = none)
NEAR_SATURATE = 0.25   # the closest things get this much richer color (0.25 = +25% at the very front)
NEAR_CONTRAST = 0.12   # ...and this much more contrast
NEAR_DARKEN = 0.06     # ...and this much darker (a darker foreground pushes the background back)
TREELINE_FADE = 0.12   # extra haze on the trees along the horizon (so they sit further back)
TREELINE_SOFTEN = 0.22 # ...and that much less contrast, so their dark shapes are less crisp
SATURATION = 0.90      # overall color strength of the finished GIF (0.9 = 10% less saturated)
DEPTH_HAZE = (222, 150, 170)  # the dusky pink-lavender they fade toward
HORIZON_Y = 108        # where the field meets the distant trees
LEAF_PERSPECTIVE = True  # fallen leaves get smaller toward the horizon, bigger toward the front
LEAF_REF_Y = 150       # reference height for the size curve
LEAF_SIZE = 0.9        # overall leaf size (0.9 = 10% smaller on average)
LEAF_DEPTH = 30        # lower = stronger size difference between near and far leaves
LEAF_REMOVE_EVERY = 4  # take away every 4th fallen leaf (25%), spread evenly over the field (0 = keep all)
REMOVE_CORNER_LEAF = True  # the red leaf at the foot of the front grass clump
DEBUG_LEAVES = False
# ------------------------------------------

def snap_to_grid(path):
    """Average each 2x2 block: the picture's soft 2-pixel 'pixels' become real pixels."""
    a = np.array(Image.open(path).convert('RGB')).astype(float)
    if a.shape[0] % 2: a = np.vstack([a, a[-1:]])
    if a.shape[1] % 2: a = np.hstack([a, a[:, -1:]])
    H, W = a.shape[0] // 2, a.shape[1] // 2
    return a.reshape(H, 2, W, 2, 3).mean(axis=(1, 3))

def sky_plate(art, clouds, sky_zone):
    """The sky with the clouds removed: fill each cloud from the sky on either side of it."""
    plate = art.copy()
    for y in range(art.shape[0]):
        known = np.where(sky_zone[y] & ~clouds[y])[0]
        hole = np.where(clouds[y])[0]
        if known.size < 2 or hole.size == 0: continue
        for c in range(3):
            plate[y, hole, c] = np.interp(hole, known, art[y, known, c])
    return plate

def height_weight(H, W, base, top, power):
    yy = np.mgrid[0:H, 0:W][0]
    return np.clip((base - yy) / float(base - top), 0, 1) ** power

def soft(mask, sigma):
    w = ndi.gaussian_filter(mask.astype(float), sigma)
    return np.clip(w / max(w[mask].mean(), 1e-6), 0, 1) if mask.any() else w

def save_gif(frames, path):
    """GIF where each frame only stores the pixels that changed (the rest is see-through),
    which shrinks the file a lot for a mostly-still picture."""
    TR = 255
    idx = [np.array(f) for f in frames]
    pal = frames[0].getpalette()
    out = []
    for i, a in enumerate(idx):
        b = a.copy()
        if i:
            b[a == idx[i - 1]] = TR
        im = Image.fromarray(b.astype(np.uint8), 'P'); im.putpalette(pal)
        out.append(im)
    out[0].save(path, save_all=True, append_images=out[1:], duration=DELAY_MS, loop=0,
                disposal=1, transparency=TR, optimize=False)

def perspective_leaves(art, m):
    """Resize each group of fallen leaves for its distance: on a flat field, things look
    bigger the lower they sit on the screen. Each group is lifted off the ground (the gap is
    filled with the ground texture beside it), resized around the spot where it touches the
    ground, and put back."""
    from masks import hsv
    H, W = art.shape[:2]
    h, s, v = hsv(art)
    yy, xx = np.mgrid[0:H, 0:W]
    red = (s > 0.62) & ((h > 330) | (h < 8)) & (v > 0.45)
    yellow = (h > 22) & (h < 58) & (s > 0.55) & (v > 0.62)
    core = (yy >= HORIZON_Y) & (red | yellow)
    core &= ~((xx >= 268) & (yy >= 196))                         # the front grass clump
    opened = ndi.binary_opening(core, structure=np.ones((2, 2)))
    core = opened | (core & ndi.binary_dilation(opened, iterations=1))
    grass = m['grass_band'] | m['grass_left']
    labels, n = ndi.label(ndi.binary_dilation(core, iterations=2))

    # 1. the leaf groups (grass tufts along the horizon look similar; skip those)
    groups = []
    erase = np.zeros((H, W), bool)
    for i, sl in enumerate(ndi.find_objects(labels)):
        region = labels[sl] == i + 1
        c = core[sl] & region
        if not c.any() or (c & grass[sl]).sum() > 0.5 * c.sum():
            continue
        e = ndi.binary_dilation(c, iterations=2) & region
        erase[sl] |= e
        groups.append((sl, c, e))

    if REMOVE_CORNER_LEAF:
        zone = np.zeros((H, W), bool); zone[229:250, 283:318] = True
        reddish = zone & (s > 0.62) & (v > 0.5) & ((h > 345) | (h < 12))     # true red, not the purple shade
        reddish = ndi.binary_dilation(ndi.binary_opening(reddish), iterations=1) & zone \
            & ~((h > 18) & (s > 0.6) & (v > 0.6))
        for Y, X in zip(*np.where(reddish)):
            for dx in (24, 30, 36):
                if X - dx >= 0 and not reddish[Y, X - dx]:
                    art = art.copy() if not art.flags.writeable else art
                    art[Y, X] = art[Y, X - dx]; break

    # 2. lift them all off. The gap gets the ground's tone blended in from both sides of the
    # row, plus the ground's fine grain copied from a little further along, so it blends in
    ground = art.copy()
    smooth = ndi.gaussian_filter(art, sigma=(1.5, 1.5, 0))
    grain = art - smooth
    for y in np.where(erase.any(axis=1))[0]:
        known = np.where(~erase[y])[0]
        holes = np.where(erase[y])[0]
        for k in range(3):
            ground[y, holes, k] = np.interp(holes, known, smooth[y, known, k])
    for sl, c, e in groups:
        w = sl[1].stop - sl[1].start + 3
        y0, x0 = sl[0].start, sl[1].start
        for py, px in zip(*np.where(e)):
            Y, X = py + y0, px + x0
            for dx in (-w, w, -2 * w, 2 * w):
                sx = X + dx
                if 0 <= sx < W and not erase[Y, sx]:
                    ground[Y, X] += grain[Y, sx]; break

    # 3. thin them out: list every single leaf (red and yellow ones are told apart by color),
    # in order down the field, and drop every Nth one
    leaves = []
    for gi, (sl, c, e) in enumerate(groups):
        for cls in (red[sl], yellow[sl]):
            lab, k = ndi.label(c & cls)
            for j in range(1, k + 1):
                comp = lab == j
                if comp.sum() >= 6:                      # real leaves; tiny flecks always stay
                    ys_, xs_ = np.where(comp)
                    leaves.append((ys_.mean() + sl[0].start, xs_.mean() + sl[1].start, gi, comp))
    leaves.sort(key=lambda t: (round(t[0] / 12), t[1]))
    dropped = set()
    if LEAF_REMOVE_EVERY:
        # every Nth leaf, but never the last leaf of a group (each group keeps at least one)
        left_in_group = {}
        for _, _, gi, _ in leaves:
            left_in_group[gi] = left_in_group.get(gi, 0) + 1
        target = round(len(leaves) / LEAF_REMOVE_EVERY)
        order = [i for i in range(len(leaves)) if i % LEAF_REMOVE_EVERY == 1] + \
                [i for i in range(len(leaves)) if i % LEAF_REMOVE_EVERY != 1]
        for i in order:
            gi = leaves[i][2]
            if len(dropped) < target and left_in_group[gi] > 1:
                dropped.add(i); left_in_group[gi] -= 1
    kept_core = [c.copy() for sl, c, e in groups]
    for i in dropped:
        _, _, gi, comp = leaves[i]
        kept_core[gi] &= ~comp

    # sizes: every group is resized so its biggest leaf matches the size for its distance,
    # so leaves always get bigger the lower they are (the lowest ones are the biggest)
    biggest = {}
    for i, (_, _, gi, comp) in enumerate(leaves):
        if i not in dropped:
            biggest[gi] = max(biggest.get(gi, 0), np.sqrt(comp.sum()))
    # one size curve for the whole field, set so that on average the leaves come out
    # LEAF_SIZE times the size they had before this step
    def depth_of(gi):
        sl, c, e = groups[gi]
        foot = np.where(kept_core[gi])[0].max() + sl[0].start if kept_core[gi].any() else sl[0].stop
        return (foot - HORIZON_Y + LEAF_DEPTH) / float(LEAF_REF_Y - HORIZON_Y + LEAF_DEPTH)
    if biggest:
        before = sum(biggest[g] * depth_of(g) for g in biggest)
        typical = before / sum(depth_of(g) for g in biggest)
    else:
        typical = 1.0
    print(f'fallen leaves: {len(leaves)}, removed {len(dropped)}')
    if DEBUG_LEAVES:
        for gi, (sl, c, e) in enumerate(groups):
            n_all = sum(1 for t in leaves if t[2] == gi)
            n_drop = sum(1 for i in dropped if leaves[i][2] == gi)
            print(f'  group {gi}: x {sl[1].start}-{sl[1].stop} y {sl[0].start}-{sl[0].stop}  leaves {n_all}, removed {n_drop}')

    # 4. resize each group and put it back, standing on the same spot
    out = ground.copy()
    for (sl, c, e), kc in zip(groups, kept_core):
        if not kc.any():
            continue
        y0, x0 = sl[0].start, sl[1].start
        diff = np.abs(art[sl] - ground[sl]).sum(-1)
        # the kept leaves, their edges and their little shadows (not the shadows of removed ones)
        mask = kc | (e & (diff > 40) & ndi.binary_dilation(kc, iterations=2) & ~(c & ~kc))
        ys, xs = np.where(mask)
        foot_y, foot_x = ys.max() + y0, xs.mean() + x0
        depth = (foot_y - HORIZON_Y + LEAF_DEPTH) / float(LEAF_REF_Y - HORIZON_Y + LEAF_DEPTH)
        gi = next(i for i, g in enumerate(groups) if g[0] == sl)
        scale = LEAF_SIZE * typical * depth / biggest.get(gi, typical)
        if DEBUG_LEAVES:
            print(f'  group {gi}: foot y {foot_y}, biggest leaf {biggest.get(gi, 0):.1f}px -> {biggest.get(gi, 0) * scale:.1f}px (x{scale:.2f})')
        hh, ww = mask.shape
        nw, nh = max(2, int(round(ww * scale))), max(2, int(round(hh * scale)))
        # spread the leaves' own colors into the empty space around them before resizing,
        # so the edges can't pick up a light or dark fringe
        idx = ndi.distance_transform_edt(~mask, return_distances=False, return_indices=True)
        filled = art[sl][idx[0], idx[1]]
        method = Image.BOX if scale < 1 else Image.BICUBIC
        col = np.stack([np.array(Image.fromarray(filled[..., k].astype(np.float32), 'F')
                                 .resize((nw, nh), method)) for k in range(3)], -1).clip(0, 255)
        alpha = np.array(Image.fromarray(mask.astype(np.float32) * 255, 'F').resize((nw, nh), Image.BILINEAR))
        keep = alpha > (80 if scale < 1 else 120)   # shrunk leaves keep their thin points
        oy = int(round(foot_y - (foot_y - y0) * nh / hh))
        ox = int(round(foot_x - (foot_x - x0) * nw / ww))
        for py, px in zip(*np.where(keep)):
            Y, X = py + oy, px + ox
            if HORIZON_Y <= Y < H and 0 <= X < W:
                out[Y, X] = col[py, px]
    return out

def near_objects(m):
    """The things close to us: the two big trees, their trunks, bushes, rocks, front grass."""
    near = m['left_tree'] | m['right_tree'] | m['bushes'] | m['grass_br']
    for x0, y0, x1, y1 in [(6, 56, 44, 112),      # big tree's trunk
                           (300, 50, 348, 110),   # birch trunks
                           (38, 94, 64, 110),     # left rock
                           (298, 96, 322, 110)]:  # right rock
        near[y0:y1, x0:x1] = True
    return near

# shafts of light: (direction in degrees: 180 = straight left, 270 = straight up),
# width in degrees, brightness, length in pixels, and how they slowly breathe
BEAMS = [
    (184, 4.5, 0.90, 120, 2, 0.00),   # low, skimming the mountain ridge
    (195, 3.0, 0.60, 105, 3, 0.35),
    (206, 6.5, 1.00, 135, 2, 0.55),   # the broad one over the mountain
    (220, 3.5, 0.65, 115, 3, 0.15),
    (236, 6.0, 0.80, 120, 2, 0.80),
    (254, 3.0, 0.50, 95, 3, 0.60),
    (270, 5.0, 0.60, 100, 2, 0.30),   # straight up, fainter
]

def beam_field(xx, yy, cx, cy, r, p, tau):
    """Brightness (0-1) of the light shafts at every pixel for loop position p."""
    ang = (np.degrees(np.arctan2(yy - cy, xx - cx)) + 360) % 360
    dist = np.hypot(xx - cx, yy - cy)
    field = np.zeros_like(dist)
    for k, (deg, width, power, length, cycles, phase) in enumerate(BEAMS):
        sway = BEAM_SWAY * np.sin(tau * (p + phase))
        breathe = (1 - BEAM_BREATHE) + BEAM_BREATHE * (0.5 + 0.5 * np.sin(tau * (cycles * p + phase)))
        dd = (ang - (deg + sway) + 180) % 360 - 180
        across = np.exp(-(dd / width) ** 2)
        along = np.clip(1 - dist / length, 0, 1) ** 1.0
        field = np.maximum(field, power * breathe * across * along)
    start = np.clip((dist - r + 1) / 5.0, 0, 1)                    # starts right at the sun's edge
    return field * start

def depth_map(art, m):
    """How far away each pixel is: 0 = right in front of us, 1 = the far distance."""
    H, W = art.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    # the field: from the bottom edge (right in front) back to the horizon
    d = np.clip((H - yy) / float(H - HORIZON_Y), 0, 1) ** 1.4 * 0.85
    # above the horizon: distant trees, hills and mountain
    d[yy < HORIZON_Y] = 0.92
    # the big trees, their trunks, bushes and rocks stand much closer, at the sides of the field
    near = soft(near_objects(m) & ~m['grass_br'], 2.0)
    d = d * (1 - near) + 0.25 * near
    # the grass clump in the front corner is the closest thing of all
    front = soft(m['grass_br'], 1.5)
    d = d * (1 - front) + 0.02 * front
    return ndi.gaussian_filter(d, 0.8)

def depth_pass(art, m):
    """Aerial perspective in both directions: far things fade into a dusky haze and lose
    contrast; near things get richer color, a bit more contrast and a slightly darker tone.
    The open sky, clouds and sun are left alone."""
    H, W = art.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    d = depth_map(art, m)
    lum = 0.299 * art[..., 0] + 0.587 * art[..., 1] + 0.114 * art[..., 2]
    # keep the open sky as it is (fading in gradually toward the hills, so no line appears)
    ramp = np.clip((yy - 54) / 30.0, 0, 1)
    keep = np.where(yy < HORIZON_Y, ramp, 1.0)
    sky = m['clouds'] | ndi.binary_dilation(m['sun'], iterations=2) | ((lum > 175) & (yy < HORIZON_Y))
    keep = keep * (1 - soft(sky, 1.0))
    far_amt = DEPTH_FADE * np.clip((d - 0.3) / 0.7, 0, 1) ** 1.2 * keep
    near_amt = np.clip((0.6 - d) / 0.6, 0, 1) ** 1.5 * keep
    out = art.copy()
    g = lum[..., None]
    out = g + (out - g) * (1 + NEAR_SATURATE * near_amt)[..., None]          # richer color up close
    out = 128 + (out - 128) * (1 + NEAR_CONTRAST * near_amt)[..., None]       # more contrast up close
    out = out * (1 - NEAR_DARKEN * near_amt)[..., None]                       # a touch darker up close
    haze = np.array(DEPTH_HAZE, float)
    out = out + (haze - out) * far_amt[..., None]                             # far away fades into haze

    # the trees along the horizon: a little more haze and softer contrast, ever so slightly
    zone_ = np.zeros((H, W), bool); zone_[40:HORIZON_Y, 0:W] = True
    solid = ndi.binary_dilation(near_objects(m) | m['sun'], iterations=2)
    treeline = zone_ & ~solid & ~m['clouds'] & (lum < 160) & (yy > 60)
    tw = ndi.gaussian_filter(treeline.astype(float), 1.2)
    local = ndi.gaussian_filter(out, sigma=(2, 2, 0))
    out = local + (out - local) * (1 - TREELINE_SOFTEN * tw)[..., None]
    out = out + (haze - out) * (TREELINE_FADE * tw)[..., None]
    return out.clip(0, 255), d

def sun_geometry(m):
    """The drawn sun is a circle partly hidden by the hills: fit its true center and radius
    from the visible rows (top edge and widest row)."""
    if 'sun_fit' in m:
        return m['sun_fit']
    ys, xs = np.where(m['sun'])
    widths = {y: (xs[ys == y].min(), xs[ys == y].max()) for y in np.unique(ys)}
    wide = max(widths.values(), key=lambda a: a[1] - a[0])
    R = (wide[1] - wide[0] + 1) / 2.0
    cx = (wide[0] + wide[1]) / 2.0
    cy = ys.min() - 0.5 + R
    return cx, cy, R

def recolor_sun(art, m):
    """Repaint the sun, same shape and size as drawn: a near-white hot center, through pale
    gold and amber to a crisp orange rim, with checker dithering where bands meet. The lower
    part runs warmer, like a real setting sun."""
    H, W = art.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    cx, cy, R = sun_geometry(m)
    sun = m['sun']
    art = art.copy()
    if SUN_SIZE != 1 or SUN_DROP:
        # shrink around the sun's true center and lower it; the hills still hide its bottom
        R = R * SUN_SIZE
        cy = cy + SUN_DROP
        new = sun & (np.hypot(xx - cx, yy - cy) <= R)
        gone = sun & ~new
        warm_sky = (art[..., 0] - art[..., 2] > 55) & ~sun
        # fill where the sun used to be with the sky on either side of it, row by row
        for y in np.unique(np.where(gone)[0]):
            cols = np.where(sun[y])[0]; x0, x1 = cols.min(), cols.max()
            lft = [x for x in range(x0 - 3, x0) if warm_sky[y, x]]
            rgt = [x for x in range(x1 + 1, x1 + 4) if warm_sky[y, x]]
            L = art[y, lft].mean(0) if lft else None
            Rc = art[y, rgt].mean(0) if rgt else None
            if L is None: L = Rc
            if Rc is None: Rc = L
            if L is None: continue
            for x in np.where(gone[y])[0]:
                t = (x - x0 + 1) / (x1 - x0 + 2)
                art[y, x] = L + (Rc - L) * t
        sun = new
        m['sun'] = new
        m['sun_r'] = m['sun_r'] * SUN_SIZE
        ys, xs = np.where(new)
        m['sun_c'] = (xs.mean(), ys.mean())
        m['sun_fit'] = (cx, cy, R)
    t = np.hypot(xx - cx, yy - cy) / R + SUN_WARM_BOTTOM * np.clip((yy - cy + 0.25 * R) / R, 0, None)
    idx = np.searchsorted(SUN_BANDS, t)                      # 0 core, 1 gold, 2 amber
    if SUN_DITHER:
        checker = (xx + yy) % 2 == 0
        for i, e in enumerate(SUN_BANDS):
            near = np.abs(t - e) < 0.05
            idx = np.where(near & checker, np.where(t <= e, i + 1, i), idx)
    sky = (art[..., 0] - art[..., 2] > 55) & ~sun             # warm sky, not the purple hills
    edge = sun & (np.roll(sky, 1, 0) | np.roll(sky, -1, 0) | np.roll(sky, 1, 1) | np.roll(sky, -1, 1))
    rim = len(SUN_COLORS) - 1
    idx = np.where(edge, rim, np.clip(idx, 0, rim - 1))
    out = art.copy()
    if SUN_SOLID:
        out[sun] = SUN_SOLID
        return out
    for i, c in enumerate(SUN_COLORS):
        out[sun & (idx == i)] = c
    return out

def main(src, out):
    art = snap_to_grid(src)
    H, W = art.shape[:2]
    m = build(art.round().astype(np.uint8))
    if LEAF_PERSPECTIVE:
        art = perspective_leaves(art, m)
    if DEPTH_FADE or NEAR_SATURATE:
        art, depth = depth_pass(art, m)
    if SUN_RECOLOR:
        m = dict(m)
        art = recolor_sun(art, m)
    tau = 2 * np.pi
    yy, xx = np.mgrid[0:H, 0:W]
    # where the light shafts can show: the sky and far-away things, not the near trees
    beam_zone = (1 - soft(near_objects(m), 1.5)) * (yy < HORIZON_Y + 2)

    # palette taken from the still picture, so every frame uses exactly the same colors
    pal_src = art
    if SUN_BEAMS:
        bcx, bcy, bR = sun_geometry(m)          # the shafts come from the sun's true center
        fullbeam = np.zeros((H, W))
        for q in np.linspace(0, 1, 16, endpoint=False):
            fullbeam = np.maximum(fullbeam, beam_field(xx, yy, bcx, bcy, bR, q, tau))
        lit = [art + (np.array(BEAM_LIGHT, float) - art) * (BEAM_STRENGTH * fullbeam * lv)[..., None]
               for lv in (0.35, 0.7, 1.0)]
        pal_src = np.vstack([art] + lit)
    if SUN_RECOLOR:
        gcx, gcy, gR = sun_geometry(m)
        dsun = np.hypot(xx - gcx, yy - gcy) - gR
        ring = (dsun > -1) & (dsun < SUN_BLOOM_REACH * 2)
        for lv in np.arange(0.05, SUN_GLOW_STRENGTH + SUN_BLOOM + 0.01, 0.05):
            v = art.copy(); v[ring] += (np.array(SUN_GLOW_COLOR, float) - v[ring]) * lv
            pal_src = np.vstack([pal_src, v])
    canopy0 = m['left_tree'] | m['right_tree'] | m['bushes']
    up = art.copy(); up[canopy0] += (np.array(LEAF_LIGHT, float) - up[canopy0]) * 0.24
    down = art.copy(); down[canopy0] *= 0.86
    rimmed = art.copy(); rimmed[canopy0] += (np.array(RIM_GOLD, float) - rimmed[canopy0]) * RIM_STRENGTH
    pal_src = np.vstack([pal_src, up, down, rimmed])
    base_pal = Image.fromarray(pal_src.round().clip(0, 255).astype(np.uint8)).quantize(
        colors=COLORS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    # add a few light colors the picture doesn't have (sparkle, sun glow)
    pal = base_pal.getpalette()[:3 * COLORS]
    glow = np.array(SUN_GLOW, float)
    extras = [SPARKLE, SUN_GLOW, LINING_GOLD, LINING_SOFT,
              tuple(int((a + b) / 2) for a, b in zip(LINING_GOLD, SPARKLE))] + [tuple(int(v) for v in (np.array([250, 140, 90]) * (1 - a) + glow * a))
                                    for a in (0.35, 0.6, 0.8)]
    if SUN_RECOLOR:
        extras += [tuple(SUN_SOLID)] if SUN_SOLID else [tuple(c) for c in SUN_COLORS]
    for c in extras: pal += list(c)
    pal_img = Image.new('P', (1, 1)); pal_img.putpalette(pal + [0] * (768 - len(pal)))

    # --- clouds
    plate = sky_plate(art, m['clouds'], m['sky_zone'])
    labels, n = ndi.label(m['clouds'], structure=np.ones((3, 3)))
    comps = []
    for i in range(1, n + 1):
        ys, xs = np.where(labels == i)
        cy, cx = ys.mean(), xs.mean()
        amp = CLOUD_DRIFT * (1.15 - 0.5 * cy / 64.0)          # high clouds look closer: move more
        phase = 0.15 * cx / W + 0.05 * np.sin(i * 2.3)         # all drift together, very slightly out of step
        comps.append((ys, xs, amp, phase))

    # --- sway weights (smooth, so the motion fades out instead of tearing)
    tree_w = (soft(m['left_tree'], 2.0) * height_weight(H, W, 80, 18, 1.3) +
              soft(m['right_tree'], 2.0) * height_weight(H, W, 80, 26, 1.3)) * TREE_SWAY
    tree_w *= ~ndi.binary_dilation(m['clouds'], iterations=1)
    far_w = np.clip(m['mid_trees'] * 1.8, 0, 1) * height_weight(H, W, 100, 45, 1.2) * DISTANT_SWAY
    bush_w = soft(m['bushes'], 1.2) * height_weight(H, W, 108, 80, 1.0) * BUSH_SWAY
    blades = lambda mk: soft(ndi.binary_dilation(mk, iterations=1), 0.8)
    grass_w = (blades(m['grass_band']) * height_weight(H, W, 112, 97, 1.2) * GRASS_SWAY +
               blades(m['grass_left']) * height_weight(H, W, 121, 104, 1.2) * GRASS_SWAY +
               blades(m['grass_br']) * height_weight(H, W, 250, 196, 1.3) * GRASS_FRONT_SWAY)

    # --- sun: a dithered ring of light that breathes in and out, starting just outside the
    # disc so the sun keeps its crisp round edge
    scx, scy = m['sun_c']; sr = m['sun_r']
    dist = np.hypot(xx - scx, yy - scy)
    warm = (art[..., 0] - art[..., 2] > 55)                     # sky near the sun, not the purple hills
    halo_zone = warm & ~m['sun'] & (dist > sr + 0.8) & (dist < sr + 11) & (yy < scy + sr * 0.6) & ~m['left_tree'] & ~m['right_tree']
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0 + 1 / 32.0
    thresh = bayer[yy % 4, xx % 4]
    lit = art + (glow - art) * 0.55                             # the color a "lit" pixel takes
    ang = np.arctan2(yy - scy, xx - scx)
    rays_zone = warm & ~m['sun'] & (dist > sr + 1) & (dist < sr + 30) & (yy < scy + sr * 0.6) \
        & ~m['left_tree'] & ~m['right_tree']
    gcx, gcy, gR = sun_geometry(m)
    sun_bottom = np.where(m['sun'])[0].max()
    gdist = np.hypot(xx - gcx, yy - gcy)
    glow_zone = warm & ~m['sun'] & (yy <= sun_bottom) & ~ndi.binary_dilation(m['left_tree'] | m['right_tree'], iterations=1)
    dd = np.maximum(gdist - gR, 0)
    glow_base = SUN_GLOW_STRENGTH * np.exp(-dd / SUN_GLOW_REACH) + SUN_BLOOM * np.exp(-dd / SUN_BLOOM_REACH)
    glow_col = np.array(SUN_GLOW_COLOR, float)
    core_col = np.array(SUN_COLORS[1], float)
    # the ripple: nothing at the top of the sun, growing smoothly toward the hills
    shimmer_zone = (m['sun'] | warm) & (np.abs(xx - scx) <= sr + 3 + int(np.ceil(RIPPLE_STRENGTH))) \
        & (yy >= scy - sr - 1) & (yy <= scy + sr * 0.75)
    band_tint = np.array([255, 236, 178], float)

    lining_gold = np.array(LINING_GOLD, float); lining_soft = np.array(LINING_SOFT, float)
    lining_glint = (lining_gold + np.array(SPARKLE, float)) / 2
    beam_light = np.array(BEAM_LIGHT, float)
    smoothstep = lambda t: (lambda c: c * c * (3 - 2 * c))(np.clip(t, 0, 1))
    topright = smoothstep((xx - 215) / 120.0) * smoothstep((48 - yy) / 42.0)   # 0 elsewhere, 1 in the corner
    # --- leaf rustle: clusters of a few pixels flicker together, each on its own rhythm
    rng = np.random.default_rng(7)
    def cluster_noise(seed_rng):
        n = ndi.gaussian_filter(seed_rng.random((H, W)), 1.3)
        return (n - n.min()) / (n.max() - n.min())
    n1, n2 = cluster_noise(rng), cluster_noise(rng)
    lum0 = 0.299 * art[..., 0] + 0.587 * art[..., 1] + 0.114 * art[..., 2]
    big_canopy = m['left_tree'] | m['right_tree']
    rustle_amt = big_canopy * 1.0 + m['bushes'] * 0.6 + (m['mid_trees'] > 0.35) * 0.35
    lit_leaves = lum0 > np.percentile(lum0[big_canopy], 45)
    leaf_light = np.array(LEAF_LIGHT, float)

    # --- rim light: canopy pixels whose next step toward the sun is open air
    toward_x = (scx - xx) / np.maximum(dist, 1); toward_y = (scy - yy) / np.maximum(dist, 1)
    def open_at(step):
        sx_ = np.clip(np.rint(xx + toward_x * step).astype(int), 0, W - 1)
        sy_ = np.clip(np.rint(yy + toward_y * step).astype(int), 0, H - 1)
        return ~big_canopy[sy_, sx_]
    rim1 = big_canopy & open_at(1)
    rim2 = big_canopy & ~rim1 & open_at(2)
    rim_w = RIM_STRENGTH * (0.55 + 0.45 * np.exp(-dist / 150.0))   # brighter on the tree nearer the sun
    rim_gold = np.array(RIM_GOLD, float)

    # --- the trees' shadows on the field (the dark purple patches near their feet)
    from masks import hsv
    h0, s0, v0 = hsv(art)
    ground_med = np.median(lum0[(yy > HORIZON_Y + 2) & (yy < 140)])
    shade = (yy >= HORIZON_Y - 2) & (yy < 132) & (lum0 < ground_med - 10) & ((h0 > 280) | (h0 < 10)) \
        & ((xx < 115) | (xx > 268)) & ~near_objects(m)
    shade = ndi.binary_opening(shade)
    lab_s, n_s = ndi.label(shade)
    sizes = np.bincount(lab_s.ravel()); sizes[0] = 0
    shade = np.isin(lab_s, np.where(sizes >= 60)[0])               # big tree shadows, not the leaves' little ones
    shadow_w = soft(shade, 1.5) * 1.0

    # --- dust motes: each floats on its own slow little loop near the light shafts
    rng2 = np.random.default_rng(11)
    motes = []
    near0 = ndi.binary_dilation(near_objects(m), iterations=1)
    bcx, bcy, bR = sun_geometry(m)
    beam_zone = beam_zone * ~m['sun']
    beam_avg = np.mean([beam_field(xx, yy, bcx, bcy, bR, q, tau) for q in (0, 0.25, 0.5, 0.75)], axis=0) * beam_zone
    tries = 0
    while len(motes) < MOTE_COUNT and tries < 20000:
        tries += 1
        a_ = np.radians(rng2.uniform(182, 280)); d_ = rng2.uniform(16, 95)
        x0, y0 = scx + d_ * np.cos(a_), scy + d_ * np.sin(a_)
        if not (2 <= x0 < W - 2 and 2 <= y0 < HORIZON_Y - 6) or near0[int(y0), int(x0)]:
            continue
        if beam_avg[int(y0), int(x0)] < 0.25:                    # start inside a shaft of light
            continue
        motes.append(dict(x0=x0, y0=y0, ax=rng2.uniform(3, 7), ay=rng2.uniform(1.5, 4),
                          px=rng2.random(), py=rng2.random(), cy=int(rng2.integers(1, 3)),
                          tc=int(rng2.integers(2, 6)), tp=rng2.random()))

    frames = []
    for t in range(FRAMES):
        p = t / FRAMES
        f = art.copy()

        # clouds drift
        f[m['clouds']] = plate[m['clouds']]
        cloud_now = np.zeros((H, W), bool)
        for ys, xs, amp, phase in comps:
            dx = int(np.rint(amp * np.sin(tau * (CLOUD_CYCLES * p + phase))))
            nx = xs + dx
            ok = (nx >= 0) & (nx < W)
            ok[ok] &= m['sky_zone'][ys[ok], nx[ok]]
            f[ys[ok], nx[ok]] = art[ys[ok], xs[ok]]
            cloud_now[ys[ok], nx[ok]] = True

        if CLOUD_LINING:
            # the cloud's bottom row (sky right below it) catches the sun; the row above gets a
            # softer touch. Glints travel along it, and clouds nearer the sun glow a bit more.
            below_open = np.zeros((H, W), bool)
            below_open[:-1] = ~cloud_now[1:]
            rim = cloud_now & below_open
            above_rim = np.zeros((H, W), bool)
            above_rim[:-1] = rim[1:]
            inner = cloud_now & above_rim & ~rim
            # how close each cloud is to the sun: the lining and its glints fade with distance,
            # so clouds far from the sun keep only a faint, steady glow
            near_sun = np.exp(-np.hypot(xx - scx, yy - scy) / LINING_REACH)
            wave = 0.5 + 0.5 * np.sin(tau * (xx / 11.0 + yy / 5.0 - LINING_CYCLES * p))
            # calmer toward the top-right corner: the shimmer eases off gradually there
            calm = 1 - LINING_TOPRIGHT_CALM * topright
            k = near_sun * (0.45 + 0.55 * wave) * calm
            bright = rim & (k > 0.42)
            f[rim] += (lining_gold - f[rim]) * ((0.42 + 0.43 * near_sun[rim]) * (1 - 0.25 * topright[rim]))[:, None]
            f[bright] = lining_glint
            f[inner] += (lining_soft - f[inner]) * ((0.18 + 0.3 * near_sun[inner]) *
                                                  (0.6 + 0.4 * wave[inner] * calm[inner]))[:, None]

        if SUN_BEAMS:
            # smooth light; the palette holds the lit shades, so the shafts come out as soft
            # stepped bands (the pixel-art way of drawing a gradient)
            beam_now = beam_field(xx, yy, bcx, bcy, bR, p, tau) * beam_zone
            a = BEAM_STRENGTH * beam_now
            f += (beam_light - f) * a[..., None]

        # sun shines: a soft pulsing glow, the disc brightens with it, and a little sparkle
        pulse = 0.5 + 0.5 * np.sin(tau * SUN_PULSE_CYCLES * p)
        if SUN_RECOLOR:
            # smooth glow that breathes; fine dithering between close shades keeps it soft
            k = glow_base * (0.85 + 0.15 * pulse)
            q = 0.05
            lo = np.floor(k / q) * q
            k = np.where((k - lo) / q > thresh, lo + q, lo)
            f[glow_zone] += (glow_col - f[glow_zone]) * k[glow_zone, None]
        else:
            reach = 5.0 + 4.0 * pulse                                    # the glow spreads out, then pulls back
            k = np.clip(1 - (dist - sr - 0.8) / reach, 0, 1) ** 1.6 * (0.42 + 0.22 * pulse)
            on = halo_zone & (k > thresh)
            f[on] = lit[on]
            f[m['sun']] += (255 - f[m['sun']]) * (0.04 + 0.08 * pulse)

        if SUN_RAYS:   # spokes of light, alternating long and short, turning one spoke per loop
            rot = 2 * tau / RAY_COUNT * p   # two spokes per loop, so long and short spokes line up at the loop point
            spoke = np.cos(RAY_COUNT * (ang - rot))
            width = np.clip((spoke - 0.72) / 0.28, 0, 1)
            longer = 0.5 + 0.5 * np.cos(RAY_COUNT / 2 * (ang - rot))
            length = 12 + 14 * longer + 3 * pulse
            kr = width * np.clip(1 - (dist - sr - 1) / length, 0, 1) ** 1.2 * (0.45 + 0.2 * pulse)
            on = rays_zone & (kr > thresh)
            f[on] = lit[on]

        if SUN_SHIMMER:
            if SUN_LIGHT_BANDS:   # light bands drifting up across the disc
                phase = (yy + 6 * BAND_CYCLES * p) % 6
                band = m['sun'] & (phase < 1.0)
                f[band] += (band_tint - f[band]) * 0.45
            # heat shimmer: rows ripple sideways by a pixel, more toward the horizon
            amp = np.clip((yy - (scy - sr)) / (2 * sr), 0.35, 1.0) * RIPPLE_STRENGTH
            sdx = np.rint(amp * np.sin(tau * (yy / 4.0 - SHIMMER_CYCLES * p))).astype(int)
            sx_src = np.clip(xx - sdx, 0, W - 1)
            take = shimmer_zone & (sdx != 0) & shimmer_zone[yy, sx_src]
            g = f.copy(); g[take] = f[yy[take], sx_src[take]]; f = g
        sp = (t % (FRAMES // SUN_PULSE_CYCLES))                   # sparkle near the peak of each pulse
        size = {8: 1, 9: 2, 10: 2, 11: 1}.get(sp, 0) if SUN_SPARKLE else 0
        if size:
            sx, sy = int(round(scx - sr * 0.45)), int(round(scy - sr * 0.55))
            for d in range(-size, size + 1):
                f[sy, sx + d] = f[sy + d, sx] = SPARKLE

        # wind: trees and bushes sway, grass flutters faster, a gust rolls left to right
        gust = 0.85 + 0.15 * np.sin(tau * p)
        wind_t = np.sin(tau * (TREE_CYCLES * p) - tau * 0.7 * xx / W) * gust

        if LEAF_RUSTLE or RIM_LIGHT:
            # leaves turning in the wind: some catch the light, some turn into shade; it's
            # livelier while a gust passes
            r = (0.6 * np.sin(tau * (4 * p + 3 * n1)) + 0.4 * np.sin(tau * (7 * p + 3 * n2))) \
                * (0.7 + 0.3 * np.abs(wind_t))
        if RIM_LIGHT:
            k1 = (rim_w * (0.85 + 0.15 * r))[rim1]
            f[rim1] += (rim_gold - f[rim1]) * k1[:, None]
            f[rim2] += (rim_gold - f[rim2]) * (0.4 * rim_w[rim2])[:, None]
        if LEAF_RUSTLE:
            up = (rustle_amt > 0) & lit_leaves & (r * rustle_amt > 0.5)
            dn = (rustle_amt > 0) & (r * rustle_amt < -0.58)
            f[up] += (leaf_light - f[up]) * 0.24
            f[dn] *= 0.86
        wind_g = np.sin(tau * (GRASS_CYCLES * p) - tau * 1.6 * xx / W) * gust
        wind_far = np.sin(tau * (TREE_CYCLES * p) - tau * 0.7 * xx / W - 0.6) * gust   # the gust reaches them a moment later
        sway_t = tree_w + bush_w + (shadow_w if SHADOW_SWAY else 0)
        dx = np.rint(sway_t * wind_t + far_w * wind_far + grass_w * wind_g).astype(int)
        moving = dx != 0
        src_x = np.clip(xx - dx, 0, W - 1)
        warped = f.copy()
        warped[moving] = f[yy[moving], src_x[moving]]

        if DUST_MOTES and SUN_BEAMS:
            # specks drift on slow loops and show only where a shaft of light catches them
            for mo in motes:
                mx = int(round(mo['x0'] + mo['ax'] * np.sin(tau * (p + mo['px']))))
                my = int(round(mo['y0'] + mo['ay'] * np.sin(tau * (mo['cy'] * p + mo['py']))))
                if not (1 <= mx < W - 1 and 1 <= my < H - 1) or near0[my, mx]:
                    continue
                twinkle = 0.5 + 0.5 * np.sin(tau * (mo['tc'] * p + mo['tp']))
                v = min(1.0, beam_now[my, mx] * 2.2) * (0.35 + 0.65 * twinkle)
                if v > 0.6:
                    warped[my, mx] = lining_glint
                    if v > 0.85:
                        for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            warped[my + ddy, mx + ddx] += (lining_gold - warped[my + ddy, mx + ddx]) * 0.35
                elif v > 0.22:
                    warped[my, mx] += (lining_gold - warped[my, mx]) * 0.55
        frames.append(Image.fromarray(warped.round().clip(0, 255).astype(np.uint8))
                      .quantize(palette=pal_img, dither=Image.Dither.NONE))

    if SATURATION != 1:
        # overall saturation: applied to the finished palette, so nothing else changes
        pal_arr = np.array(frames[0].getpalette()[:768], float).reshape(-1, 3)
        L = (0.299 * pal_arr[:, 0] + 0.587 * pal_arr[:, 1] + 0.114 * pal_arr[:, 2])[:, None]
        newpal = np.clip(L + (pal_arr - L) * SATURATION, 0, 255).round().astype(int).ravel().tolist()
        for fr in frames:
            fr.putpalette(newpal)
    save_gif(frames, out + '.gif')
    save_gif([fr.resize((W * 2, H * 2), Image.NEAREST) for fr in frames], out + '-preview.gif')
    rgb = [fr.convert('RGB') for fr in frames]
    rgb[0].save(out + '.webp', save_all=True, append_images=rgb[1:], duration=DELAY_MS, loop=0,
                lossless=True, method=6)
    return frames, art, m

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
