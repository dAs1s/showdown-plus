"""
The lava for beach640.py's lava scenes: a rebuild of lava.py (the animator behind old map 2, lava4),
made from lava.py's tuned settings (lava.py itself was not kept).

What it does, per frame:
  - the lava is re-drawn from a heat map (how hot each pixel is, from the painting's own brightness) through a
    colour ramp built from the painting's own lava colours, so every colour is the painting's;
  - rivers and falls flow: the heat map slides along the flow (two copies half a cycle apart, crossfaded: a
    seamless loop); pools swirl round their centre, faster near it, at POOL_SPEED battle px/s;
  - dark crust lines (wavy streaks) form, drift with the flow and break up on the rivers; on the pools,
    curved crust forms and unforms as it rides the swirl (kept light: the front lava had too much black);
  - bubbles on the pools: lava.py's own bubble code (its last version, lava_v32 / lava4), recovered line by
    line and ported: a low dome (round top, flat foot) swells for 3.6 s, coloured yellow on top,
    orange through the middle, red low down, varied by the lava it mirrors, with a dark band at its foot, a glow
    spot and a 1-2 px shine near its top and a thin broken outline; it pops in 0.8 s (a flash, torn skin), heavy
    gobs of lava tear off 4/5 of the way up, just reach its peak and drop a little outside; it leaves a ring of
    darker lava with churned yellow-orange-red lava inside that drifts with the swirl and fades over 2.6 s;
  - embers rise off the lava; far streams fade toward the haze (falls don't).
All distances here are battle px (the 640x410 picture's px).
"""
import numpy as np
from scipy import ndimage as ndi

POOL_SPEED = 3.6          # battle px/s the pools swirl (as tuned: 3.6)
FAR_POOL_K = 0.6          # pools nearer the horizon swirl slower
RIVER_SPEED = 4.0         # battle px/s the rivers flow (the old map's crust drifted 3-5 px/s)
FALL_SPEED = 8.0          # lava falls pour faster
FLOW_CYCLES = 4           # crossfade cycles per loop for the pools (each copy turns for 5 s)
STREAM_CYCLES = 8         # rivers: each copy slides 2.5 s (so it never pulls from far outside the stream)
FALL_CYCLES = 10          # falls: 2 s
CRUST_DENSITY = 380 / 6000.0   # crust lines per battle px^2 of river (380 on the old far rivers)
CRUST = dict(length=(8.0, 22.0), width=(1.0, 1.7), wobble=(0.5, 1.4), wave=(6.0, 14.0), dark=(0.75, 1.0))
CRUST_LIFE_CYCLES = 4     # a line forms and breaks up this many times a loop
POOL_CRUST = 70           # dark crust patches per 10,000 px^2 of pool, swirling with it
POOL_CRUST_DARK = 0.6     # (lighter than the first try: the front lava had too much black)
# bubbles: lava.py's own final settings (lava2/lava4), in its units (px of the battle
# picture, frames at 10 fps; FRAMES=200 a loop)
FRAMES = 200
B = dict(FRAMES=(36, 8), SQUASH=3.0, HEIGHT=0.82, EASE_POWER=2.2, GLOW=0.42, OPACITY=0.92, REFLECT=0.45,
         DEEP=0.85, BANDS=(0.84, 0.62, 0.36), MAX_HEAT=0.92, GLOW_SPOT=1.0,
         OUTLINE=((74, 20, 30), 0.5, 0.55, 0.85), SCAR=(26, 0.6, 0.38), SHINE=1.7, CONTRAST=0.95,
         DROPS=(7, 11), GRAVITY=0.36, DROP_SPEED=1.66, DROP_SIZE=1.6, DROP_LAND=(1.22, 1.42), DROP_START=0.8,
         DROP_START_R=0.72, DROP_APEX=(0.84, 0.9), DROP_HEAT=(0.42, 0.88), DROP_COOL=0.25)
W3 = np.array([0.299, 0.587, 0.114])
EMBERS = 22               # per loop, rising off the lava
FAR_FADE = 0.35           # far streams: this much toward the haze at the horizon


def smooth01(v):
    v = np.clip(v, 0, 1)
    return v * v * (3 - 2 * v)


class Lava:
    def __init__(self, art, m, S, s, A, rng):
        self.S, self.s, self.A = S, s, A
        H, W = art.shape[:2]
        self.H, self.W = H, W
        self.yy, self.xx = np.mgrid[0:H, 0:W].astype(float)
        lav = m['lava']
        self.lava = lav
        L = 0.299 * art[..., 0] + 0.587 * art[..., 1] + 0.114 * art[..., 2]
        lo, hi = np.percentile(L[lav], 3), np.percentile(L[lav], 99.5)
        h0 = np.clip((L - lo) / max(hi - lo, 1), 0, 1)
        # outside the lava, the heat of the nearest lava pixel (so flow near an edge samples lava, not rock)
        # (a soft fill, wider and wider, not nearest-pixel: that drew streaky fans where flow pulls from outside)
        fill = h0 * lav; wsum = lav.astype(float); out = np.where(lav, h0, 0.0); have = lav.copy()
        for sg in (1.5, 3, 6, 12, 24):
            num = ndi.gaussian_filter(fill, sg / s); den = ndi.gaussian_filter(wsum, sg / s)
            new = (den > 1e-3) & ~have
            out[new] = num[new] / den[new]; have |= new
        out[~have] = h0[lav].mean()
        self.h0 = out
        # the colour ramp: the painting's own lava colours by heat, continued down to crust and up to white heat
        bins = np.linspace(0, 1, 33)
        cols = []
        for i in range(32):
            sel = lav & (h0 >= bins[i]) & (h0 < bins[i + 1] + (1 if i == 31 else 0))
            cols.append(np.median(art[sel], axis=0) if sel.sum() >= 3 else np.full(3, np.nan))
        cols = np.array(cols)
        ok = ~np.isnan(cols[:, 0])
        xs = (bins[:-1] + bins[1:]) / 2
        for c in range(3):
            cols[:, c] = np.interp(xs, xs[ok], cols[ok, c])
        near = ndi.binary_dilation(lav, iterations=4 * A) & ~lav
        crust = np.percentile(art[near], 15, axis=0) if near.any() else np.array([50, 25, 35.0])
        self.rx = np.concatenate([[-1.0], xs, [1.35]])
        self.rc = np.vstack([crust, cols, [255, 246, 210]])
        self.haze = np.array(S.get('haze', (120, 90, 120)), float)
        hz = m['hz']
        self.far = np.clip(1 - (self.yy - hz) / (60.0 / s), 0, 1) * FAR_FADE
        # zones
        self.parts = []
        self.bubbles, self.arcs, self.lines = [], [], []
        self.brng = np.random.default_rng(1000)          # (the bubbles own; rng left untouched)
        for z in m['lava_zones']:
            zm = z['mask']
            if not zm.any() or z.get('kind', 'river') == 'crack':
                continue
            kind = z.get('kind', 'river')
            P = dict(kind=kind, mask=zm, fade=(kind == 'river'))
            if kind == 'pool':
                cx, cy = z['centre'][0] / s, z['centre'][1] / s
                sq = z.get('squash', 2.0)
                dx, dy = self.xx - cx, (self.yy - cy) * sq
                P.update(cx=cx, cy=cy, sq=sq, r=np.hypot(dx, dy) + 1e-6, th=np.arctan2(dy, dx),
                         speed=POOL_SPEED * (FAR_POOL_K if cy * s < hz * s + 70 else 1.0) / s * z.get('spin', 1))
                self._pool_extras(P, z, rng)
            else:
                d = np.array(z.get('dir', (-1.0, 0.0) if kind == 'river' else (0.0, 1.0)), float)
                d /= np.linalg.norm(d)
                P.update(d=d, speed=(RIVER_SPEED if kind == 'river' else FALL_SPEED) / s)
                if kind == 'river':
                    self._river_lines(P, rng)
            sw = ndi.gaussian_filter(zm.astype(float), 3.0 / s)
            P['soft'] = np.clip(sw * 2.0, 0, 1) * ndi.binary_dilation(zm, iterations=max(1, int(6 / s)))
            self.parts.append(P)
        # embers: off the lava's hottest pixels
        ys, xs_ = np.where(lav & (h0 > 0.55))
        self.embers = []
        for i in range(EMBERS if len(ys) else 0):
            j = int(rng.integers(len(ys)))
            self.embers.append(dict(x=xs_[j], y=ys[j], ph=rng.random(), cyc=int(rng.integers(3, 6)),
                                    rise=rng.uniform(18, 34) / s, sway=rng.uniform(1.0, 2.5) / s))

    # ---- set-up of crust and bubbles
    def _river_lines(self, P, rng):
        zm = P['mask']
        n = int(CRUST_DENSITY * zm.sum() * self.s ** 2)
        ys, xs = np.where(zm)
        for _ in range(n):
            j = int(rng.integers(len(ys)))
            self.lines.append(dict(P=P, x=xs[j], y=ys[j], ph=rng.random(),
                                   len=rng.uniform(*CRUST['length']) / self.s, w=rng.uniform(*CRUST['width']) / self.s,
                                   wob=rng.uniform(*CRUST['wobble']) / self.s, wave=rng.uniform(*CRUST['wave']) / self.s,
                                   dark=rng.uniform(*CRUST['dark']), wph=rng.random() * 6.28))

    def _pool_extras(self, P, z, rng):
        zm = P['mask']
        area = zm.sum() * self.s ** 2
        rr = P['r'][zm]
        for _ in range(int(POOL_CRUST * area / 10000.0) + 2):
            self.arcs.append(dict(P=P, r=rng.uniform(np.percentile(rr, 20), np.percentile(rr, 90)),
                                  th=rng.uniform(-np.pi, np.pi), span=rng.uniform(0.15, 0.6),
                                  w=rng.uniform(1.5, 3.5) / self.s, ph=rng.random()))
        # bubbles in the open lava (hot enough, away from the edge and from each other)
        sizes = z.get('bubbles', [])
        rq = P['r'][zm]
        open_ = (zm & (ndi.distance_transform_edt(zm) > 6 / self.s) & (self.h0 > 0.25)
                 & (P['r'] > np.percentile(rq, 12)) & (P['r'] < np.percentile(rq, 80)))
        ys, xs = np.where(open_)
        placed = []
        for k, wpx in enumerate(sizes):
            R = wpx / 2.0 / self.s
            for _try in range(3000):
                j = int(rng.integers(len(ys))) if len(ys) else None
                if j is None:
                    break
                x, y = xs[j], ys[j]
                if all(np.hypot(x - a, (y - b) * 1.6) > R + r2 + 1 / self.s for a, b, r2 in placed):
                    placed.append((x, y, R))
                    # (the draws the first version made here, so the crust and embers made after stay where they were)
                    for _ in range(int(rng.integers(7, 12))):
                        rng.uniform(-1, 1); rng.uniform(0.8, 1.2)
                    br = self.brng                       # the bubbles' own random numbers, as lava.py drew them
                    nd = int(br.integers(*B['DROPS']))
                    t0 = (k + br.uniform(0, 0.3)) / max(len(sizes), 1) + z.get('bub_offset', 0.0) / 20.0
                    angs = br.uniform(0, 2 * np.pi, nd)
                    self.bubbles.append(dict(P=P, x=x, y=y, R=R, t0=t0 % 1.0, tear=br.uniform(0, 2 * np.pi, 3),
                                             drops=[(a_, br.uniform(*B['DROP_LAND']), br.uniform(*B['DROP_APEX']),
                                                     br.uniform(*B['DROP_HEAT'])) for a_ in angs]))
                    break

    # ---- per frame
    def heat(self, p):
        """the flowing heat map for this moment (p: 0..1 through the loop)"""
        h = self.h0.copy()
        T = 20.0
        for P in self.parts:
            zm = P['mask']
            acc = np.zeros(self.h0.shape);
            kc = {'pool': FLOW_CYCLES, 'river': STREAM_CYCLES, 'fall': FALL_CYCLES}[P['kind']]
            phs = [(kc * p) % 1.0, (kc * p + 0.5) % 1.0]
            ws = [1 - abs(1 - 2 * q) for q in phs]
            for q, w in zip(phs, ws):
                tau = q * T / kc
                if P['kind'] == 'pool':
                    dth = P['speed'] * tau / np.maximum(P['r'], 6.0 / self.s)
                    th = P['th'] - dth
                    sx = P['cx'] + P['r'] * np.cos(th); sy = P['cy'] + P['r'] * np.sin(th) / P['sq']
                else:
                    D = P['speed'] * tau
                    sx = self.xx - P['d'][0] * D; sy = self.yy - P['d'][1] * D
                acc += w * ndi.map_coordinates(self.h0, [sy, sx], order=1, mode='nearest')
            mean = self.h0[zm].mean()
            # (crossfading two copies flattens contrast mid-way: put it back)
            hv = mean + (acc - mean) / np.sqrt(ws[0] ** 2 + ws[1] ** 2)
            # blended in softly across its edge, so where a fall meets a river there's no straight seam
            wz = P['soft']
            h = h + (hv - h) * wz
        return h

    def colour(self, h):
        return np.stack([np.interp(h, self.rx, self.rc[:, c]) for c in range(3)], -1)

    def draw(self, f, p):
        lav = self.lava
        if not lav.any():
            return f
        tau2 = 2 * np.pi
        h = self.heat(p)
        dark = np.zeros(h.shape)
        # crust lines on the rivers: form, drift with the flow, break up
        for ln in self.lines:
            P = ln['P']
            q = (CRUST_LIFE_CYCLES * p + ln['ph']) % 1.0
            life = 20.0 / CRUST_LIFE_CYCLES
            alpha = np.sin(np.pi * q) ** 2
            if alpha < 0.05:
                continue
            D = P['speed'] * q * life
            d = P['d']; nrm = np.array([-d[1], d[0]])
            cx, cy = ln['x'] + d[0] * D, ln['y'] + d[1] * D
            for t in np.arange(-ln['len'] / 2, ln['len'] / 2, 0.5):
                off = ln['wob'] * np.sin(tau2 * t / ln['wave'] + ln['wph'] + tau2 * q)
                px, py = cx + d[0] * t + nrm[0] * off, cy + d[1] * t + nrm[1] * off
                ix, iy = int(round(px)), int(round(py))
                taper = np.cos(np.pi * t / ln['len'])
                r = max(1, int(np.ceil(ln['w'])))
                y0, y1, x0, x1 = max(0, iy - r), min(self.H, iy + r + 1), max(0, ix - r), min(self.W, ix + r + 1)
                if y0 >= y1 or x0 >= x1:
                    continue
                gy, gx = self.yy[y0:y1, x0:x1], self.xx[y0:y1, x0:x1]
                k = np.clip(1 - np.hypot(gx - px, gy - py) / (ln['w'] + 0.5), 0, 1) * taper * alpha * ln['dark']
                dark[y0:y1, x0:x1] = np.maximum(dark[y0:y1, x0:x1], k)
        # curved crust on the pools: rides the swirl, forms and unforms
        for ar in self.arcs:
            P = ar['P']
            q = (2 * p + ar['ph']) % 1.0
            alpha = np.sin(np.pi * q) ** 2 * POOL_CRUST_DARK
            if alpha < 0.03:
                continue
            th0 = ar['th'] + P['speed'] * q * 10.0 / max(ar['r'], 6.0 / self.s)
            for th in np.linspace(th0, th0 + ar['span'], max(4, int(ar['r'] * ar['span'] * 2))):
                rr_ = ar['r'] * (1 + 0.04 * np.sin(th * 5 + ar['ph'] * 6))
                px, py = P['cx'] + rr_ * np.cos(th), P['cy'] + rr_ * np.sin(th) / P['sq']
                ix, iy = int(round(px)), int(round(py))
                if 0 <= iy < self.H and 0 <= ix < self.W:
                    taper = np.sin(np.pi * (th - th0) / ar['span'])
                    r = max(1, int(np.ceil(ar['w'])))
                    y0, y1, x0, x1 = max(0, iy - r), min(self.H, iy + r + 1), max(0, ix - r), min(self.W, ix + r + 1)
                    gy, gx = self.yy[y0:y1, x0:x1], self.xx[y0:y1, x0:x1]
                    k = np.clip(1 - np.hypot(gx - px, gy - py) / (ar['w'] + 0.5), 0, 1) * taper * alpha
                    dark[y0:y1, x0:x1] = np.maximum(dark[y0:y1, x0:x1], k)
        h = h - 1.6 * dark * (h + 0.5)
        h, domes, splash = self._bubbles(h, p)
        col = self.colour(h)
        # far streams fade toward the haze
        for P in self.parts:
            if P['fade']:
                zm = P['mask']
                col[zm] += (self.haze - col[zm]) * self.far[zm][:, None]
        f = np.where(lav[..., None], col, f)
        f = self._draw_domes(f, domes)
        f = self._draw_splash(f, splash)
        # embers rise off the lava, flicker and fade
        for e in self.embers:
            q = (e['cyc'] * p + e['ph']) % 1.0
            x = e['x'] + e['sway'] * np.sin(tau2 * q * 1.5 + e['ph'] * 6)
            y = e['y'] - e['rise'] * q
            ix, iy = int(round(x)), int(round(y))
            if 0 <= ix < self.W and 0 <= iy < self.H:
                k = np.sin(np.pi * q) * (0.7 + 0.3 * np.sin(tau2 * 3 * q + e['ph']))
                c = np.array([255, 190 - 90 * q, 80 - 50 * q])
                f[iy, ix] += (c - f[iy, ix]) * k
        return f

    # ---- bubbles: lava.py's code (lava_v32 onward), ported
    def ramp(self, t):
        """lava.py's lava_ramp: its heat (0 dark crust .. ~0.9 yellow .. 1 pale) through this painting's colours"""
        t = np.asarray(t, float)
        return np.stack([np.interp(t, self.rx, self.rc[:, c]) for c in range(3)], -1)

    def drop_tl(self, kick, R):
        Hp = kick * B['HEIGHT'] * R; h0_ = B['DROP_START'] * B['HEIGHT'] * R
        v0 = np.sqrt(2 * B['GRAVITY'] * max(Hp - h0_, 0.01))
        return v0 / B['GRAVITY'] + np.sqrt(2 * Hp / B['GRAVITY'])

    def _bubbles(self, h, p):
        H, W = self.H, self.W
        T = h.copy()                                  # the lava's heat the domes' skin keeps (its swirl)
        bub = np.zeros((H, W)); dome_t = np.zeros((H, W)); dome_w = np.zeros((H, W))
        domes, splash = [], []
        S_, P_ = B['FRAMES']; sq_ = B['SQUASH']; G = B['GRAVITY']
        sf_, sdk, sgl = B['SCAR']
        for bb in self.bubbles:
            Pz = bb['P']
            u = np.mod(p - bb['t0'], 1.0) * FRAMES
            R = bb['R']
            dlife = max(self.drop_tl(d_[2], R) for d_ in bb['drops']) / B['DROP_SPEED'] if bb['drops'] else 0
            if u >= S_ + max(P_, dlife, sf_):
                continue
            # carried round the pool with the lava
            r0p = np.hypot(bb['x'] - Pz['cx'], (bb['y'] - Pz['cy']) * Pz['sq'])
            th0 = np.arctan2((bb['y'] - Pz['cy']) * Pz['sq'], bb['x'] - Pz['cx'])
            dth = Pz['speed'] * (u / 10.0) / max(r0p, 6.0 / self.s)
            bxc = Pz['cx'] + r0p * np.cos(th0 + dth); byc = Pz['cy'] + r0p * np.sin(th0 + dth) / Pz['sq']
            x0, x1 = int(bxc - 2.8 * R) - 2, int(bxc + 2.8 * R) + 3
            y0, y1 = int(byc - 1.6 * R) - 2, int(byc + 2.8 * R / sq_) + 3
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
            if x0 >= x1 or y0 >= y1:
                continue
            gy, gx = self.yy[y0:y1, x0:x1], self.xx[y0:y1, x0:x1]
            dx_, dy_ = gx - bxc, (gy - byc) * sq_
            dyb = gy - byc
            rr = np.hypot(dx_, dy_); th = np.arctan2(dy_, dx_)
            if u < S_:                                    # the dome swells
                g_ = u / S_; g_ = 1 - (1 - g_) ** B['EASE_POWER']
                rad = R * (0.12 + 0.88 * g_); hgt = rad * B['HEIGHT']
                nx = dx_ / rad; ny = np.where(dyb < 0, dyb / hgt, dyb * sq_ / rad)
                r1 = np.sqrt(nx * nx + ny * ny); nz = np.sqrt(np.clip(1 - r1 * r1, 0, 1))
                sk = ndi.map_coordinates(T, [byc + ny * rad * 0.8, bxc + nx * rad * 0.8], order=1, mode='nearest')
                cov = np.clip((1 - r1) * rad + 0.5, 0, 1)
                oc_, ota, oba, ow = B['OUTLINE']
                rim = np.clip(1 - np.abs(r1 - 1) * rad / ow, 0, 1) * np.where(ny < 0, ota, oba)
                ta_ = np.arctan2(ny, nx)
                brk_ = 0.5 + 0.5 * np.sin(5 * ta_ + bb['tear'][0]) * np.cos(3 * ta_ + bb['tear'][1])
                rim = rim * np.clip(0.15 + 1.25 * brk_, 0.12, 1)
                halo = B['GLOW'] * (0.4 + 0.6 * g_) * np.exp(-np.clip(r1 - 1, 0, None) * 2.2) * (r1 > 0.98)
                k2 = 1.4 + 4.0 * (1 - nz)
                refl_at = (gy + (gy - byc) * k2, gx + (gx - bxc) * k2)
                hot_ = np.clip((sk - 0.6) / 0.25, 0, 1) * np.sqrt(nz)
                gl_ = np.clip(1 - np.hypot(nx + 0.38, ny + 0.5) / 0.22, 0, 1) ** 1.5 * cov
                dpx = np.hypot((nx + 0.3) * rad, (np.minimum(ny, 0) + 0.62) * hgt + np.maximum(ny, 0) * rad)
                gl_ = np.maximum(gl_, np.clip(B['SHINE'] - dpx, 0, 1) * np.clip((rad - 3) / 3, 0, 1) * cov)
                domes.append((y0, y1, x0, x1, cov, rim, halo, refl_at, hot_, nz, gl_, ny, sk, nx))
                v_ = np.zeros_like(rr)
            else:                                         # it bursts
                tt = u - S_; k_ = min(tt / P_, 1.0)
                flash = 0.8 * np.clip(1 - tt / 2.0, 0, 1) * np.clip(1 - rr / R, 0, 1)
                torn = sum(np.cos((j + 3) * th + bb['tear'][j]) for j in range(3)) > 0.3
                rs_ = R * (1 - 0.25 * k_)
                skin = -0.5 * np.clip(1 - k_ / 0.6, 0, 1) * np.clip(1 - np.abs(rr - rs_) / 1.3, 0, 1) * torn
                # where it stood: a ring of darker lava with churned lava of every colour inside, fading
                fd_ = np.clip(1 - tt / sf_, 0, 1) ** 1.2
                ring_ = -sdk * fd_ * np.clip(1 - np.abs(rr - 0.95 * R) / 2.0, 0, 1)
                sw_ = 1.2 * (1 - np.clip(rr / R, 0, 1))
                ca_, sa_ = np.cos(sw_), np.sin(sw_)
                qx_ = bxc + (dx_ * ca_ - (dy_ / sq_) * sa_ * sq_) * 1.6
                qy_ = byc + (dx_ * sa_ / sq_ + (dy_ / sq_) * ca_) * 1.6
                tex_ = ndi.map_coordinates(T, [qy_, qx_], order=1, mode='nearest')
                rq_ = np.clip(rr / R, 0, 1)
                tgt_ = np.clip(np.interp(rq_, [0.0, 0.45, 0.9], [0.82, 0.62, 0.38]) + 0.55 * (tex_ - 0.5), 0.15, 0.88)
                win = fd_ * np.clip(1 - rr / (0.88 * R), 0, 1) ** 0.5
                dome_t[y0:y1, x0:x1] = np.where(win > dome_w[y0:y1, x0:x1], tgt_, dome_t[y0:y1, x0:x1])
                dome_w[y0:y1, x0:x1] = np.maximum(dome_w[y0:y1, x0:x1], 0.9 * win)
                v_ = (flash + skin) * (tt < P_) + ring_
                # droplets: torn from the dome 4/5 of the way up, just reaching its peak, landing a little outside
                ts = tt * B['DROP_SPEED']
                for (ang, vr, kick, h0) in bb['drops']:
                    tl = self.drop_tl(kick, R)
                    if ts < tl:
                        pts_ = []
                        for tq in (ts, max(ts - 0.4, 0.0)):
                            Hp = kick * B['HEIGHT'] * R; h0_ = B['DROP_START'] * B['HEIGHT'] * R
                            v0 = np.sqrt(2 * G * max(Hp - h0_, 0.01))
                            r0 = B['DROP_START_R']
                            f_ = tq / tl
                            rd_ = (r0 + (vr - r0) * f_) * R
                            up = -(h0_ + v0 * tq - 0.5 * G * tq * tq)
                            pts_.append((bxc + np.cos(ang) * rd_, byc + np.sin(ang) * rd_ / sq_ + up))
                        hh = h0 - B['DROP_COOL'] * ts / tl
                        vel = (pts_[0][0] - pts_[1][0], pts_[0][1] - pts_[1][1])
                        splash.append((pts_[0][0], pts_[0][1], 1 - 0.35 * ts / tl, hh, vel))
            reg = bub[y0:y1, x0:x1]
            bub[y0:y1, x0:x1] = np.where(np.abs(v_) > np.abs(reg), v_, reg)
        lav = self.lava
        h = np.where(lav, h + bub, h)
        h = np.where(lav, h * (1 - dome_w) + dome_t * dome_w, h)
        return h, domes, splash

    def _draw_domes(self, f, domes):
        self.keep = np.zeros(f.shape[:2])
        if not domes:
            return f
        fs = f.copy()                                     # (what the domes mirror)
        self.keep = np.zeros(f.shape[:2])                 # outline and glint: kept when brought down to the grid
        op = B['OPACITY']; RF = B['REFLECT']; DP = B['DEEP']
        for (y0, y1, x0, x1, cov, rim, halo, refl_at, hot_, nz_, gl_, ny_, sk_, nxs_) in domes:
            rc = np.stack([ndi.map_coordinates(fs[..., ch], [refl_at[0], refl_at[1]], order=1, mode='nearest')
                           for ch in range(3)], -1)
            rl = (rc @ W3) / 255.0
            wb = np.clip((ny_ + 1) / 1.25, 0, 1); wt = 1 - wb
            refl = RF * 2.6 * (rl - 0.62) * (0.6 + 0.4 * nz_)
            refl = np.where(refl < 0, refl * (0.3 + 0.7 * wb), refl * (1 + 0.5 * wt))
            # yellow on top, orange through the middle, red low down; the mirrored lava and hot patches vary it
            td = np.interp(wb, [0.0, 0.45, 1.0], list(B['BANDS'])) - 0.12 * (1 - nz_) ** 1.5
            td = td + 0.6 * refl + 0.14 * hot_ * (0.6 + 0.4 * wt)
            band = np.exp(-((ny_ - 0.5) / 0.14) ** 2) * np.clip((0.62 - sk_) / 0.25, 0, 1) * (np.abs(ny_) < 0.9)
            td = td - DP * 0.75 * band - DP * 0.5 * np.clip((0.42 - rl) / 0.2, 0, 1) * (0.25 + 0.75 * wb)
            td = np.clip(td, 0, B['MAX_HEAT'])
            gsp = np.exp(-((nxs_ + 0.22) ** 2 + (ny_ + 0.55) ** 2) / 0.07)          # glow spot near its top
            up_ = np.clip(-ny_, 0, 1)
            td = np.maximum(td, B['GLOW_SPOT'] * (0.5 * up_ * nz_))
            gsp2 = np.exp(-((nxs_ + 0.2) ** 2 + (ny_ + 0.6) ** 2) / 0.025)
            td = td + (0.86 - td) * np.clip(B['GLOW_SPOT'] * gsp, 0, 1)
            td = td + (0.98 - td) * np.clip(B['GLOW_SPOT'] * gsp2, 0, 1)
            td = np.clip(td, 0, max(B['MAX_HEAT'], 0.98))
            col = self.ramp(td)
            reg = f[y0:y1, x0:x1]
            reg += (np.array([255, 214, 120], float) - reg) * (op * halo)[..., None]
            reg += (col - reg) * (op * 0.94 * cov)[..., None]
            reg += (np.array(B['OUTLINE'][0], float) - reg) * (min(1.0, op * 1.4) * rim)[..., None]
            reg += (np.array([255, 250, 228], float) - reg) * (np.clip(0.9 * gl_ * 1.1, 0, 1))[..., None]
            kp = self.keep[y0:y1, x0:x1]
            kp[:] = np.maximum(kp, np.maximum(min(1.0, op * 1.4) * rim, np.clip(0.9 * gl_ * 1.1, 0, 1)))
            wd_ = np.clip(np.maximum(cov, rim * 2), 0, 1)
            if wd_.sum() > 0:
                M_ = (reg * wd_[..., None]).sum((0, 1)) / wd_.sum()
                reg += ((M_ + (reg - M_) * B['CONTRAST']) - reg) * wd_[..., None]
        return f

    def _draw_splash(self, f, splash):
        H, W = self.H, self.W
        for (sx_, sy_, sa_, sh_, vel_) in splash:
            xi, yi = int(round(sx_)), int(round(sy_))
            if not (4 <= xi < W - 4 and 4 <= yi < H - 4):
                continue
            # a gob of lava: dark crusted underside, orange body, a hot yellow spot, stretched a little along its flight
            gy_, gx_ = self.yy[yi - 4:yi + 5, xi - 4:xi + 5], self.xx[yi - 4:yi + 5, xi - 4:xi + 5]
            ddx, ddy = gx_ - sx_, gy_ - sy_
            vn = np.hypot(*vel_)
            ux_, uy_ = (vel_[0] / vn, vel_[1] / vn) if vn > 1e-6 else (1.0, 0.0)
            al_ = ddx * ux_ + ddy * uy_; ac_ = -ddx * uy_ + ddy * ux_
            stretch = 1 + min(vn, 1.5) * 0.3
            pt = f[yi - 4:yi + 5, xi - 4:xi + 5]
            rd = B['DROP_SIZE']
            dist_ = np.sqrt((al_ / stretch) ** 2 + ac_ ** 2)
            cov_ = np.clip(rd - dist_ + 0.5, 0, 1) * min(1.0, sa_ * 1.4)
            c_body, c_dark, c_hot = self.ramp(np.clip([sh_, sh_ - 0.3, sh_ + 0.22], 0, 1))
            shade = np.clip((ddx * 0.45 + ddy * 0.9) / rd, 0, 1)[..., None]
            hot = np.clip(1 - np.hypot(ddx + 0.45 * rd, ddy + 0.5 * rd) / (0.55 * rd), 0, 1)[..., None]
            col_ = c_body + (c_dark - c_body) * 0.85 * shade
            col_ = col_ + (c_hot - col_) * hot
            pt += (col_ - pt) * cov_[..., None]
        return f


class GridLava:
    """Draws the full-detail lava and brings it down to the 320x205 grid (each grid pixel: the colour most
    of its four full-detail pixels share, else their average), only where the lava drew something."""
    def __init__(self, full, fart):
        self.full, self.fart = full, fart

    def draw(self, f, p):
        F = self.full.draw(self.fart.copy(), p)
        H2, W2 = F.shape[0] // 2, F.shape[1] // 2
        c = F.reshape(H2, 2, W2, 2, 3).transpose(0, 2, 1, 3, 4).reshape(H2, W2, 4, 3)
        same = (np.abs(c[:, :, :, None, :] - c[:, :, None, :, :]).max(-1) < 10).sum(-1)    # how many agree with each
        best = np.argmax(same, axis=-1)
        pick = np.take_along_axis(c, best[..., None, None], 2)[:, :, 0]
        down = np.where((same.max(-1) >= 2)[..., None], pick, c.mean(2))
        # a bubble's thin outline and its glint would lose the vote: where one is drawn, it wins its grid pixel
        kp = getattr(self.full, 'keep', None)
        if kp is not None and kp.shape == F.shape[:2]:
            k4 = kp.reshape(H2, 2, W2, 2).transpose(0, 2, 1, 3).reshape(H2, W2, 4)
            kb = np.argmax(k4, axis=-1)
            kpick = np.take_along_axis(c, kb[..., None, None], 2)[:, :, 0]
            down = np.where((k4.max(-1) > 0.35)[..., None], kpick, down)
        ch = (np.abs(F - self.fart).max(-1) > 0).reshape(H2, 2, W2, 2).any(axis=(1, 3))
        return np.where(ch[..., None], down, f)
