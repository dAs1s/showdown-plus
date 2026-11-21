"""
Animated battle backgrounds at the new 640x410 battle size: shipwreck beaches.

Usage:  python beach640.py <scene> <picture 640x410.png> <out_prefix> [--smooth] [--masks]

  grid (default): the picture is snapped to the 320x205 pixel grid (crisp: see snap_grid) and animated
                  there; writes <out>.gif (320x205) and <out>-preview.gif (640x410, 2x nearest).
  --smooth:       animated at the full 640x410 detail; writes <out>.gif (640x410).
  --masks:        writes <out>-masks.png (what was found where) and stops.

Same rules as beach.py (which made the first beach maps on the 350x250 grid): only the
picture's own pixels move or get re-tinted, one fixed palette, and every motion repeats a
whole number of times per loop (20 s at 10 fps). All distances below are in grid pixels
(320x205); the smooth version moves twice as many of its own (finer) pixels, so both look the
same size on screen. Scene boxes are in picture pixels (640x410).

Fixes over beach.py:
  - water is found by colour over the WHOLE picture (no sea_x column range, nothing masked out
    behind the wreck): the sea beside the boat, between the rail posts and behind the rigging
    ripples with the rest, and the shoreline is found in every column where it shows;
  - the surf only ever moves water and sand pixels (never pulls planks into the wash);
  - the sunlit cloud rims: each cloud's own gold rim pixels are traced (bright, warm, at the
    cloud's edge) and a glint runs along that rim; nothing else on the cloud is tinted (the old
    shimmer was one flat diagonal wave over each cloud, which read as straight bands).
"""
import sys
import os
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from animate import save_gif, sky_plate

FRAMES = 200            # 20 s at 10 fps
PALETTE_FROM = None     # --palette-from=<gif>: reuse that GIF's palette
SNAP_FROM = None        # --snap-from=<png>: grid colours learned from this (original) picture
GRID_COLORS = 128       # grid version: colours the picture is snapped to (crisp pixels)
COLORS = 248            # palette size (index 255 stays free for the see-through delta pixels)
CLOUD_DRIFT = 1.84      # clouds drift this many grid px each way, once per loop
RIPPLE_CYCLES = 4       # sea: sideways ripples per loop
SWELL_CYCLES = 5        # sea: swells rolling toward the beach per loop
SWELL_AMP = 0.9         # grid px the near-shore wave lines rise and fall
SURF_CYCLES = 4         # waves washing up the sand per loop (one every 5 s)
LAP_CYCLES = 10         # waterline lap: one sideways slide and back every 2 s
SURF_AMP = 2.6          # grid px the wash runs up the sand
SAIL_SWAY = 2.4         # torn sail: grid px at the ragged ends
SAIL_CYCLES = 8
GRASS_SWAY = 1.1        # grass tufts by the ship / far away
GRASS_FRONT = 2.0       # ...the ones right at the front
GRASS_CYCLES = 10
CREST_CYCLES = 6        # rolling waves (from old map 5): each wave's roll-ins per loop
WAVE_TRAVEL = 0.7 * 8 / 6   # how far each roll carries a wave (map 5's pace: one roll-in every 3.3 s)
WAVE_LEAN_AT = [0.0, 0.2, 0.5, 1.0]      # across the beach: boat ... middle ... far end
WAVE_LEAN = [0.0, 0.08, 0.14, 0.20]      # tilt of a wave's line there (rise per px)
CREST_LINGER = 2.3 * CREST_CYCLES / 20.0 # a crest carries on 2.3 s after its dark part is gone, easing to a stop
CREST_POP = 1.7         # white crests stand out this much more than the bare stroke
RIM_GLOW = 0.10         # cloud rims: steady extra warmth that breathes a little...
RIM_GLINT = 0.30        # ...plus a glint travelling along each rim
RIM_CYCLES = 2          # glint passes per loop, per cloud (each cloud its own phase)
RIM_WIDTH = 5.0         # glint half-width along the rim, grid px
VINE_SWAY = 1.0         # hanging ivy: grid px at the tips (they hang from the top)
VINE_CYCLES = 4         # one slow swing every 5 s
LAVA_CYCLES = 4         # lava: the churn travels downstream this many times a loop
LAVA_AMP = 1.3          # grid px the lava's pixels shift as it churns
LAVA_PULSE = 0.22       # brighter pulses running down the lava
LAVA_PULSE_WL = 40      # grid px between pulses
LAVA_PULSE_CYCLES = 3
LAVA_GLOW = 0.16        # the rock beside the lava glows (breathes twice a loop)
SMOKE_RISE = 1.2        # painted smoke: grid px it bobs up
SMOKE_SWAY = 0.8
HILL_WIND = 0.10        # wind rolling over grassy slopes (brightness)
WATERFALL_CYCLES = 15   # how fast a waterfall's water runs down
SUN_COLOR = (255, 212, 128)   # the sunset sun: one solid colour
BEAMS = [  # sun shafts (old map 9): direction (deg: 180 left, 270 up), width, brightness, length, breaths/loop, phase
    (196, 4.0, 0.80, 150, 2, 0.00), (214, 5.5, 1.00, 170, 3, 0.40), (233, 3.5, 0.65, 140, 2, 0.70),
    (252, 5.0, 0.85, 130, 3, 0.15), (272, 3.5, 0.60, 110, 2, 0.55), (292, 4.5, 0.70, 100, 3, 0.85),
    (318, 3.0, 0.50, 70, 2, 0.30)]
BEAM_STRENGTH = 0.30
BEAM_BREATHE = 0.6
BEAM_SWAY = 1.6
BEAM_LIGHT = (255, 206, 178)
DEPTH_FADE = 0.12       # far things fade a little into the haze
NEAR_SATURATE = 0.14
NEAR_CONTRAST = 0.08

SCENES = {
    'golden': dict(  # golden-hour shipwreck: wreck on the left, sea arch on the right
        horizon=164, cloud_ymax=136, sea_ymax=215,
        ship=(0, 54, 268, 290),                      # the wreck, mast and rigging
        sail=(58, 88, 164, 178), yard=((42, 127), (162, 87)), mast=((92, 80), (110, 180), 9),   # the torn cloth under the yard
        rock=[(372, 40, 640, 168)],                  # the sea arch (above the horizon)
        rock_low=[(548, 168, 640, 240), (372, 164, 452, 192)],   # rocks on the beach / at the arch's foot
        tufts=[(0, 236, 72, 292), (84, 244, 150, 290), (196, 232, 282, 280),
               (0, 334, 60, 400), (580, 344, 640, 404), (548, 218, 610, 236),
               (582, 286, 640, 300), (470, 228, 560, 240)],
        refl=(470, 166, 600, 214),                   # the glow's reflection: the water right under it
        light=(600, 130), light_col=(255, 196, 140),
        refl_glitter=0.16, water_sheen=0.05,
        surf_lr=(1.3, 0.8),                           # surf reaches further by the boat (closer)
        crests=True, surf_cycles=5, ripple=0.6,       # map 5's rolling waves (calmer ripple keeps them whole)
        crest_dir=([0.0, 0.6, 1.0], [0.0, 0.0, 0.5]), # straight in by the boat, a little diagonal by the arch
        wave_local=(3, 31), wave_dark=7,              # this sea darkens toward the horizon: compare along rows
        haze=(200, 140, 190)),

    'blue-hour': dict(  # dusk, dunes, the first stars (old map 7)
        horizon=162, cloud_ymax=140, sea_ymax=225,
        ship=(0, 40, 246, 278), sail=(25, 74, 132, 165), yard=((18, 112), (135, 78)), mast=((66, 60), (110, 210), 8),
        land=[[(325, 212), (360, 204), (400, 190), (440, 175), (480, 158), (520, 141), (560, 128), (600, 118),
               (640, 110), (640, 260), (325, 260)],
              [(370, 193), (377, 185), (391, 182), (400, 186), (412, 181), (426, 183), (435, 190), (431, 197), (371, 198)]],
        tufts=[(0, 222, 62, 272), (62, 238, 125, 270), (192, 232, 252, 266), (395, 110, 640, 250),
               (0, 330, 62, 402), (520, 355, 605, 408), (590, 360, 640, 402), (230, 255, 340, 270)],
        refl=(245, 163, 312, 192), refl_glitter=0.16, water_sheen=0.04,   # no sun: a faint glimmer only
        rims=None, stars=16, star_ymax=110, grass_gb=1.2,
        light=(290, 160), light_col=(236, 150, 210),
        surf_lr=(1.3, 0.8), crests=True, surf_cycles=5, ripple=0.6, far_flick=True,
        crest_dir=([0.0, 1.0], [0.0, 0.3]), wave_local=(3, 31), wave_dark=5, wreck_sea_tol=60,
        waves_behind_wreck=True, waves_avoid_refl=False,
        haze=(150, 120, 190)),
    'dawn': dict(  # the sun on the horizon, a grassy headland (old map 9)
        horizon=164, cloud_ymax=136, sea_ymax=228,
        ship=(0, 40, 252, 282), sail=(45, 76, 154, 168), yard=((42, 117), (150, 80)), mast=((80, 60), (118, 210), 8),
        land=[[(0, 84), (30, 94), (70, 104), (110, 115), (150, 127), (190, 137), (225, 147), (260, 158),
               (290, 170), (300, 177), (240, 181), (0, 184)]],
        hills=[(0, 84, 300, 186)],
        sun=(553, 140, 16), beams=True, sun_glow_k=0.5, sun_color='own', lean_from_shore=True, fill_crest_bits=True, waves_avoid_refl=False, rim_min_L=172, rim_edge=2.0, cloth_land_L=125,
        tufts=[(0, 212, 62, 268), (72, 222, 132, 264), (192, 222, 268, 260), (575, 352, 640, 408)],
        refl=(518, 165, 592, 222), refl_glitter=0.30, water_sheen=0.0,
        light=(553, 140), light_col=(255, 196, 150),
        surf_lr=(1.3, 0.8), crests=True, surf_cycles=5, ripple=0.6, far_flick=True,
        crest_dir=([0.0, 1.0], [0.0, 0.3]), wave_local=(3, 31), wave_dark=7, wreck_sea_tol=60,
        haze=(196, 140, 196)),
    'misty': dict(  # grey-violet evening, overcast (old map 5)
        horizon=163, cloud_ymax=140, sea_ymax=232,
        ship=(0, 35, 268, 286), sail=(30, 58, 154, 175), yard=((28, 122), (150, 62)), mast=((64, 50), (120, 210), 8),
        tufts=[(0, 232, 52, 286), (68, 248, 122, 282), (222, 238, 282, 276), (598, 212, 632, 236), (588, 306, 634, 372)],
        rims=None, cloud_drift=2.6, sea_test='teal',
        sail_poly=[[(98, 120), (118, 111), (142, 100), (140, 150), (132, 158), (122, 148), (110, 150), (100, 145)],
                   [(55, 141), (75, 133), (96, 122), (96, 150), (88, 172), (78, 165), (65, 160), (55, 155)]], fill_crest_bits=True,   # overcast: no sunlit edges, no glitter
        light=(500, 140), light_col=(236, 176, 186),
        surf_lr=(1.3, 0.7), crests=True, surf_cycles=5, ripple=0.6, far_flick=True,
        crest_dir=([0.0, 1.0], [0.0, 1.0]), wave_local=(3, 31), wave_dark=6, wreck_sea_tol=60,
        waves_behind_wreck=True,
        haze=(160, 145, 175)),
    'moonlit': dict(  # night, full moon top left, a sea stack far right
        horizon=165, cloud_ymax=130, sea_ymax=232,
        ship=(0, 70, 272, 286), sail=(60, 68, 182, 172), yard=((60, 120), (175, 72)), mast=((100, 90), (135, 215), 8),
        land=[[(0, 149), (40, 152), (66, 161), (72, 172), (40, 176), (0, 178)],
              [(558, 167), (574, 151), (589, 139), (601, 144), (618, 167)]],
        moon=(85, 30, 17), sea_test='night', wreck_foam=False, sail_dark_L=95,
        sail_poly=[[(118, 130), (140, 122), (164, 110), (162, 148), (155, 152), (145, 145), (135, 158), (122, 155)],
                   [(75, 146), (95, 139), (113, 132), (112, 165), (103, 175), (92, 168), (80, 160)]],
        tufts=[(0, 228, 62, 286), (98, 252, 152, 286), (212, 248, 268, 282), (0, 332, 52, 396), (505, 326, 565, 392)],
        refl=[(58, 165, 142, 212), (0, 174, 66, 202)], refl_warm=False, refl_glitter=0.30,
        glint_col=(236, 240, 255), streak_cycles=6, ripple_cycles=3,     # night: slower glints and ripples
        rims='silver', rim_k=0.6, stars=20, star_ymax=120, water_sheen=0.0,
        light=(85, 30), light_col=(222, 228, 255),
        surf_lr=(1.3, 0.8), crests=True, surf_cycles=5, ripple=0.6, far_flick=True,
        # waves lie along this beach (it runs downhill to the right) and travel straight in toward it
        crest_dir=([0.0, 1.0], [-0.08, -0.08]), lean_from_shore=True,
        wave_min_gap=7, crest_linger=0.9, crest_fade_in=0.4,   # no stacked / doubled crests
        wave_local=(3, 31), wave_dark=6, wreck_sea_tol=50,
        waves_behind_wreck=True,
        haze=(70, 70, 130)),
    'rose-cliff': dict(  # bright day, rose cliffs, a waterfall (old map 8)
        horizon=163, cloud_ymax=140, sea_ymax=232,
        ship=(0, 50, 256, 290), sail=(35, 88, 152, 182), yard=((25, 140), (145, 92)), mast=((70, 70), (112, 215), 8),
        land=[[(395, 168), (420, 150), (450, 140), (480, 134), (500, 120), (520, 104), (545, 94), (570, 70),
               (600, 45), (625, 30), (640, 24), (640, 214), (600, 205), (560, 192), (520, 178), (470, 170), (395, 170)]],
        waterfall=(492, 138, 508, 172), splash=(484, 166, 514, 178),
        tufts=[(0, 238, 62, 286), (72, 248, 138, 282), (198, 244, 258, 276), (585, 210, 640, 236),
               (0, 348, 52, 406), (596, 352, 640, 402)],
        rims=None, glints=34, water_sheen=0.0, sea_test='azure',      # (no sheen: its bands read as light lines)
        light=(300, -80), light_col=(255, 255, 240),
        surf_lr=(1.3, 0.8), crests=True, surf_cycles=5, ripple=0.6, far_flick=True,
        crest_dir=([0.0, 1.0], [0.0, 0.3]), wave_local=(3, 31), wave_dark=7, wreck_sea_tol=60,
        haze=(150, 180, 230)),
'stormlit': dict(  # storm clouds at sunset, basalt columns on the right, no wreck
        horizon=165, cloud_ymax=135, sea_ymax=212, ship=None, sail=None,
        land=[[(250, 201), (300, 184), (330, 180), (380, 168), (420, 140), (465, 108), (505, 90), (525, 60),
               (560, 45), (580, 15), (600, 0), (640, 0), (640, 218), (250, 213)],
              [(158, 165), (172, 151), (220, 145), (262, 148), (300, 140), (350, 134), (400, 139), (432, 146), (432, 166)]],
        tufts=[], sea_test='night', sky_slide=True, rims='lit', refl_force_water=True,
        refl=(0, 163, 150, 200), refl_glitter=0.30, water_sheen=0.0,
        light=(40, 158), light_col=(255, 186, 130),
        surf_lr=(1.0, 0.8), crests=False, surf_cycles=5, ripple=0.8, far_flick=True, swell_floor=0.62,
        breaker_roll=(14, 4),                     # the breakers roll 14 px in to the beach, 4 times a loop
        # big painted breakers: the rolling-piece waves broke their curls into blotches, so here
        # the breakers stay whole and rise and fall with the swell (the older beach maps' way)
        haze=(120, 90, 150)),
    'waterfall-beach': dict(  # bright day, ivy-hung cliffs and a waterfall, no wreck (old scene 6)
        horizon=163, cloud_ymax=130, sea_ymax=215, ship=None, sail=None,
        land=[[(0, 0), (130, 0), (160, 10), (200, 30), (240, 50), (270, 70), (300, 90), (330, 105), (360, 108),
               (400, 110), (430, 120), (460, 140), (466, 163), (180, 170), (150, 175), (100, 181), (0, 186)],
              [(430, 130), (480, 124), (540, 138), (578, 162), (430, 163)]],
        vines=[(0, 8, 62, 92), (60, 40, 142, 92), (140, 58, 222, 102), (200, 84, 300, 122), (300, 100, 360, 125)],
        waterfall=(362, 114, 392, 165), splash=(354, 158, 400, 170),
        tufts=[(0, 146, 72, 192), (58, 150, 152, 184), (560, 335, 630, 390)], grass_gb=1.4,
        rims=None, glints=34, water_sheen=0.0, sea_test='azure',
        light=(300, -80), light_col=(255, 255, 240),
        surf_lr=(0.8, 1.2), crests=True, surf_cycles=5, ripple=0.6, far_flick=True,
        crest_dir=([0.0, 1.0], [0.0, 0.3]), wave_local=(3, 31), wave_dark=7, lean_from_shore=True,
        fill_crest_bits=True,
        haze=(150, 180, 230)),
'autumn-forest': dict(  # autumn clearing at sunset (old map 10)
        horizon=158, cloud_ymax=120, ship=None, sail=None, pond=[],
        land=[[(290, 142), (330, 122), (362, 114), (392, 122), (432, 142)]],
        sun=(448, 116, 17), beams=True, sun_color='own', sun_glow_k=0.6, rims='gold', rim_edge=2.0,
        rim_line=True, rim_line_ymax=108, rim_col=(253, 228, 176), rim_glow=1.0, rim_glint=0.8, rim_glint_col=(255, 246, 214), rim_shimmer=1.0, sun_shimmer_tight=True,   # gold lines under the clouds (old map 10)
        trees=[dict(poly=[(0, 0), (190, 0), (190, 70), (150, 95), (90, 112), (40, 130), (0, 140)], base=165, amp=1.3, cyc=5, test='leafy'),
               dict(poly=[(150, 50), (330, 70), (330, 152), (150, 152)], base=155, amp=0.8, cyc=5, ph=0.3, test='leafy'),
               dict(poly=[(495, 8), (640, 0), (640, 140), (590, 145), (520, 100)], base=165, amp=1.3, cyc=5, ph=0.55, test='leafy'),
               dict(poly=[(440, 100), (560, 95), (560, 152), (440, 152)], base=155, amp=0.6, cyc=5, ph=0.8, test='leafy'),
               dict(poly=[(510, 320), (640, 300), (640, 410), (520, 410)], base=410, amp=3.0, cyc=10, ph=0.2, test='leafy'),
               dict(poly=[(0, 145), (640, 145), (640, 172), (0, 172)], base=172, amp=1.4, cyc=10, ph=0.45, test='leafy')],
        rustle=True, leaf_light=(255, 214, 140),
        light=(448, 116), light_col=(255, 200, 130), haze=(200, 130, 150)),
    'autumn-courtyard': dict(  # autumn ruins at sunset
        horizon=160, cloud_ymax=110, ship=None, sail=None, pond=[],
        land=[[(14, 52), (74, 52), (76, 168), (14, 168)], [(88, 104), (126, 104), (128, 166), (88, 166)],
               [(66, 136), (112, 140), (116, 166), (66, 166)], [(322, 112), (412, 112), (412, 166), (322, 166)],
               [(398, 60), (576, 58), (576, 166), (398, 166)], [(476, 112), (548, 112), (548, 166), (476, 166)],
               [(592, 88), (636, 88), (636, 172), (592, 172)], [(456, 318), (566, 318), (566, 410), (456, 410)]],
        sun=(272, 107, 10), beams=False, sun_color='own', sun_glow_k=0.6, rims='gold', rim_edge=2.0,
        cloud_channel='red+green', rim_line=True, rim_line_ymax=100, rim_col=(253, 228, 176), rim_glow=1.0,   # gold lines
        rim_glint=0.8, rim_glint_col=(255, 246, 214), rim_shimmer=1.0, sun_shimmer_tight=True,                  # under the clouds
        trees=[dict(poly=[(0, 0), (240, 0), (240, 85), (175, 108), (80, 112), (0, 100)], base=160, amp=1.3, cyc=5, test='leafy'),
               dict(poly=[(0, 100), (330, 110), (330, 165), (0, 165)], base=165, amp=1.0, cyc=7, ph=0.35, test='leafy'),
               dict(poly=[(555, 60), (640, 55), (640, 150), (560, 150)], base=155, amp=0.8, cyc=5, ph=0.6, test='leafy'),
               dict(poly=[(560, 262), (640, 262), (640, 410), (572, 410)], base=410, amp=2.6, cyc=7, ph=0.15, test='leafy')],
        vines=[(398, 60, 576, 166), (14, 52, 76, 168), (592, 88, 636, 172)],
        rustle=True, leaf_light=(255, 214, 140),
        light=(272, 107), light_col=(255, 196, 140), haze=(200, 140, 160)),
    'rain-ruins': dict(  # jungle ruins after rain, dusk (old map 12), wet stone sheen
        horizon=160, cloud_ymax=110, ship=None, sail=None, pond=[],
        land=[[(14, 52), (74, 52), (76, 168), (14, 168)], [(88, 104), (126, 104), (128, 166), (88, 166)],
               [(66, 136), (112, 140), (116, 166), (66, 166)], [(322, 112), (412, 112), (412, 166), (322, 166)],
               [(398, 60), (576, 58), (576, 166), (398, 166)], [(476, 112), (548, 112), (548, 166), (476, 166)],
               [(592, 88), (636, 88), (636, 172), (592, 172)], [(456, 318), (566, 318), (566, 410), (456, 410)]],
        rims='pink', rim_min_L=160,
        trees=[dict(poly=[(0, 0), (240, 0), (240, 85), (175, 108), (80, 112), (0, 100)], base=160, amp=1.3, cyc=5, test='green'),
               dict(poly=[(0, 100), (640, 95), (640, 165), (0, 165)], base=165, amp=1.0, cyc=5, ph=0.35, test='green'),
               dict(poly=[(560, 262), (640, 262), (640, 410), (572, 410)], base=410, amp=2.6, cyc=7, ph=0.15, test='green')],
        vines=[(398, 60, 576, 166), (14, 52, 76, 168), (592, 88, 636, 172)],
        tufts=[(0, 170, 640, 410)], grass_gb=1.3,
        sheen=[(0, 166, 640, 410)], sheen_test='pink', refl_glitter=0.22, streak_cycles=4,
        rustle=True, leaf_light=(214, 240, 150),
        light=(320, 120), light_col=(255, 226, 214), haze=(160, 162, 212)),
    'snowy-ruins': dict(  # snowy ruins at a lavender dawn: sky, tree sway, a little sparkle on the snow
        horizon=160, cloud_ymax=110, ship=None, sail=None, pond=[],
        land=[[(14, 52), (74, 52), (76, 168), (14, 168)], [(88, 104), (126, 104), (128, 166), (88, 166)],
               [(66, 136), (112, 140), (116, 166), (66, 166)], [(322, 112), (412, 112), (412, 166), (322, 166)],
               [(398, 60), (576, 58), (576, 166), (398, 166)], [(476, 112), (548, 112), (548, 166), (476, 166)],
               [(592, 88), (636, 88), (636, 172), (592, 172)], [(456, 318), (566, 318), (566, 410), (456, 410)]],
        rims='pink', rim_min_L=200,
        trees=[dict(poly=[(0, 0), (190, 30), (190, 160), (0, 160)], base=162, amp=1.2, cyc=5, power=1.4),
               dict(poly=[(190, 110), (640, 70), (640, 165), (190, 165)], base=165, amp=0.8, cyc=5, ph=0.4, power=1.4),
               dict(poly=[(555, 245), (640, 245), (640, 410), (565, 410)], base=410, amp=1.6, cyc=7, ph=0.15, power=1.4)],
        snow=[(0, 140, 640, 410)], snow_sparkles=34,
        light=(320, 120), light_col=(255, 210, 230), haze=(180, 170, 210)),
    'willow-marsh': dict(  # a moonlit marsh with willows (old map 11)
        horizon=162, cloud_ymax=110, ship=None, sail=None,
        pond=[[(140, 162), (600, 160), (610, 178), (585, 196), (400, 200), (220, 197), (150, 186)]],
        refl=[(418, 163, 492, 198)], refl_warm=False, refl_glitter=0.30, glint_col=(230, 240, 255),
        streak_cycles=6, ripple_cycles=3, ripple=1.0, far_flick=True, swell_floor=0.62,
        moon=(452, 52, 24), rims='silver', rim_k=0.6,
        stars_painted=[(0, 0, 640, 150)], fireflies=[(0, 165, 640, 410)],
        trees=[dict(poly=[(0, 25), (110, 18), (218, 60), (218, 165), (150, 170), (0, 160)], hang=True, hang_len=40, amp=1.6, cyc=4, test='green'),
               dict(poly=[(535, 90), (640, 78), (640, 190), (560, 185)], hang=True, hang_len=35, amp=1.6, cyc=4, ph=0.4, test='green'),
               dict(poly=[(228, 105), (530, 105), (530, 160), (228, 160)], base=160, amp=0.5, cyc=4, ph=0.2)],
        tufts=[(140, 165, 340, 210), (440, 165, 640, 212), (0, 160, 140, 215), (500, 285, 640, 410)], grass_gb=1.0,
        light=(452, 52), light_col=(206, 224, 255), haze=(50, 72, 126)),
    'desert-oasis': dict(  # a smooth night painting: moon, stars, a pond, palms (old map 3's look)
        horizon=165, cloud_ymax=0, ship=None, sail=None,
        land=[[(0, 152), (100, 140), (180, 122), (260, 134), (330, 140), (420, 128), (520, 120), (640, 134), (640, 172), (0, 172)],
              [(44, 122), (102, 126), (146, 246), (92, 252), (64, 232)], [(480, 278), (640, 278), (640, 395), (480, 395)]],
        pond=[[(196, 190), (240, 178), (330, 178), (400, 190), (392, 214), (330, 225), (250, 222), (200, 205)]],
        refl=[(296, 178, 346, 224)], refl_warm=False, refl_glitter=0.30, glint_col=(236, 240, 255),
        streak_cycles=6, ripple_cycles=3, ripple=0.7,
        moon=(317, 60, 33), stars_painted=[(0, 0, 640, 140)], rims=None,
        trees=[dict(poly=[(366, 126), (432, 126), (432, 192), (366, 192)], base=192, amp=1.5, cyc=4),
               dict(poly=[(250, 142), (292, 142), (292, 182), (250, 182)], base=182, amp=1.0, cyc=4, ph=0.3),
               dict(poly=[(330, 142), (362, 142), (362, 182), (330, 182)], base=182, amp=1.0, cyc=4, ph=0.6),
               dict(poly=[(400, 152), (438, 152), (438, 188), (400, 188)], base=188, amp=1.0, cyc=4, ph=0.8),
               dict(poly=[(425, 300), (500, 300), (500, 392), (425, 392)], base=392, amp=2.4, cyc=5, ph=0.1),
               dict(poly=[(28, 222), (82, 222), (82, 256), (28, 256)], base=256, amp=1.6, cyc=6, ph=0.5),
               dict(poly=[(150, 232), (202, 232), (202, 262), (150, 262)], base=262, amp=1.6, cyc=6, ph=0.7)],
        light=(317, 60), light_col=(222, 228, 255), haze=(70, 70, 130)),
'erupting': dict(  # two erupting volcanoes, rivers of lava along the plain, a basalt outcrop
        horizon=150, cloud_ymax=95, ship=None, sail=None, pond=[], rims='lit',
        land=[[(380, 100), (440, 75), (500, 52), (520, 47), (575, 42), (600, 55), (640, 78), (640, 150), (380, 150)],
              [(40, 105), (80, 95), (110, 82), (130, 85), (170, 100), (210, 110), (210, 150), (40, 150)],
              [(462, 290), (560, 268), (640, 262), (640, 410), (462, 410)]],
        lava=[dict(kind='river', poly=[(0, 140), (200, 125), (380, 108), (520, 92), (560, 98), (560, 140), (420, 150), (250, 170), (0, 185)], dir=(-1, 0.25)),
              dict(kind='fall', poly=[(470, 40), (580, 40), (580, 112), (470, 112)], dir=(-0.25, 1)),
              dict(kind='crack', poly=[(90, 80), (140, 80), (140, 102), (90, 102)]),
              dict(kind='crack', poly=[(462, 290), (560, 268), (640, 262), (640, 410), (462, 410)])],
        smoke=[(505, 0, 615, 50)],
        light=(540, 30), light_col=(255, 150, 90), haze=(150, 60, 80)),
    'stone-arch': dict(  # dusk, a lava river and falls, a stone arch over lava (bottom right)
        horizon=150, cloud_ymax=80, ship=None, sail=None, pond=[], rims='lit',
        land=[[(470, 80), (520, 55), (580, 40), (640, 35), (640, 150), (470, 150)], [(462, 290), (560, 268), (640, 262), (640, 410), (462, 410)]],
        lava=[dict(kind='river', poly=[(0, 120), (300, 115), (520, 105), (560, 140), (420, 150), (250, 168), (0, 190)], dir=(-1, 0.15)),
              dict(kind='fall', poly=[(500, 60), (625, 60), (625, 140), (500, 140)], dir=(-0.35, 1)),
              dict(kind='crack', poly=[(400, 50), (490, 50), (490, 85), (400, 85)]),
              dict(kind='pool', poly=[(500, 320), (630, 320), (630, 395), (500, 395)], centre=(570, 360), squash=1.4, arms=2, bubbles=[14, 11, 12]),
              dict(kind='crack', poly=[(462, 290), (560, 268), (640, 262), (640, 410), (462, 410)])],
        light=(560, 120), light_col=(255, 150, 90), haze=(70, 60, 110)),
    'cavern': dict(  # a lava cavern: rivers, lava falls from the ceiling, no sky
        horizon=150, cloud_ymax=0, ship=None, sail=None, pond=[],
        land=[[(0, 0), (640, 0), (640, 150), (0, 150)], [(462, 290), (560, 268), (640, 262), (640, 410), (462, 410)]],
        lava=[dict(kind='river', poly=[(0, 125), (300, 118), (480, 112), (600, 115), (600, 150), (420, 150), (250, 170), (0, 192)], dir=(-1, 0.15)),
              dict(kind='fall', poly=[(490, 15), (610, 15), (610, 128), (490, 128)], dir=(0, 1)),
              dict(kind='crack', poly=[(30, 50), (70, 50), (70, 80), (30, 80)]),
              dict(kind='crack', poly=[(462, 290), (560, 268), (640, 262), (640, 410), (462, 410)])],
        light=(560, 80), light_col=(255, 150, 90), haze=(60, 40, 60)),
    'moonlit-lava': dict(  # night, a snowy volcano, the moon, lava rivers and falls
        horizon=150, cloud_ymax=95, ship=None, sail=None, pond=[],
        moon=(110, 25, 16), rims='silver', rim_k=0.6, stars_painted=[(0, 0, 640, 60)],
        land=[[(300, 70), (360, 45), (410, 30), (460, 45), (540, 70), (560, 50), (640, 40), (640, 150), (300, 150)], [(462, 290), (560, 268), (640, 262), (640, 410), (462, 410)]],
        lava=[dict(kind='river', poly=[(0, 140), (300, 128), (470, 115), (480, 150), (300, 165), (0, 205)], dir=(-1, 0.2)),
              dict(kind='fall', poly=[(470, 70), (610, 70), (610, 150), (470, 150)], dir=(-0.35, 1)),
              dict(kind='crack', poly=[(462, 290), (560, 268), (640, 262), (640, 410), (462, 410)])],
        light=(110, 25), light_col=(222, 228, 255), haze=(70, 70, 130)),
    'volcanic-arena': dict(  # orange sun, a lava river and fall, a pool, a swirling lava pit (old map 2 redrawn)
        horizon=150, cloud_ymax=90, ship=None, sail=None, pond=[], rims='gold', rim_edge=2.0,
        sun=(108, 62, 12), beams=False, sun_color='own', sun_glow_k=0.6, sun_min_l=150,
        land=[[(0, 90), (430, 88), (520, 62), (590, 25), (640, 12), (640, 165), (0, 165)]],
        lava=[dict(kind='river', poly=[(100, 140), (300, 128), (520, 110), (560, 115), (640, 120), (640, 165), (300, 165), (100, 170)], dir=(-1, 0.1)),
              dict(kind='fall', poly=[(500, 15), (640, 15), (640, 118), (500, 118)], dir=(-0.45, 1)),
              dict(kind='pool', poly=[(70, 180), (215, 180), (215, 222), (70, 222)], centre=(140, 200), squash=2.6, arms=2, bubbles=[12, 10], bub_offset=5.0),
              dict(kind='pool', poly=[(455, 310), (640, 310), (640, 410), (455, 410)], centre=(565, 375), squash=1.8, arms=3, bubbles=[25, 20, 15, 23, 21, 17, 19])],
        light=(108, 62), light_col=(255, 196, 140), haze=(150, 110, 130)),
}

C = lambda c: np.array(c, float)


def lum_of(a):
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def boxm(H, W, b, s):
    if b is None:                          # (a scene with no wreck, sail, ...)
        return np.zeros((H, W), bool)
    x0, y0, x1, y1 = [int(round(v / s)) for v in b]
    m = np.zeros((H, W), bool)
    m[max(0, y0):min(H, y1 + 1), max(0, x0):min(W, x1 + 1)] = True
    return m



def poly_mask(polys, H, W, s):
    """Outlines drawn on the 640x410 picture -> a mask at the working size."""
    from PIL import ImageDraw
    li = Image.new('L', (640, 410), 0)
    dr = ImageDraw.Draw(li)
    for poly in polys:
        if len(poly) == 4 and isinstance(poly[0], (int, float)):      # a box (x0, y0, x1, y1)
            dr.rectangle(poly, fill=255)
        else:
            dr.polygon([tuple(v) for v in poly], fill=255)
    mk = np.asarray(li) > 0
    if s == 2:
        mk = mk.reshape(205, 2, 320, 2).mean(axis=(1, 3)) >= 0.5
    return mk

def soft(mask, sigma):
    w = ndi.gaussian_filter(mask.astype(float), sigma)
    return np.clip(w / max(w[mask].mean(), 1e-6), 0, 1) if mask.any() else w


def load(src, smooth):
    im = Image.open(src).convert('RGB')
    assert im.size == (640, 410), 'expected a 640x410 picture, got %s' % (im.size,)
    a = np.asarray(im).astype(float)
    if smooth:
        return a, 1, 2                 # array, picture px per working px, working px per grid px
    return snap_grid(a), 2, 1


def snap_grid(a, k=GRID_COLORS):
    """Snap a 640x410 picture onto the 320x205 grid with crisp, well-defined pixels. Averaging each
    2x2 block (as before) blends colours across every edge, so soft art comes out blurry. Instead:
    map the picture to k colours (k-means), and give each grid pixel the colour most of its four
    picture pixels have; on a tie, the one nearest the block's average. Every grid pixel is then a
    real colour of the picture, edges stay hard and flat areas stay flat."""
    from scipy.cluster.vq import kmeans2
    rng = np.random.default_rng(1)
    ref = a
    if SNAP_FROM:                          # a retouched picture: keep the colours learned from the original
        ref = np.asarray(Image.open(SNAP_FROM).convert('RGB')).astype(float)
    X = ref.reshape(-1, 3)
    sel = X[rng.choice(len(X), 120000, replace=False)]
    init = Image.fromarray(ref.round().astype(np.uint8)).quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    c0 = np.array(init.getpalette()[:3 * k], float).reshape(-1, 3)
    cent, _ = kmeans2(sel, c0, iter=10, minit='matrix', seed=2)
    c = a.reshape(205, 2, 320, 2, 3).transpose(0, 2, 1, 3, 4).reshape(205, 320, 4, 3)
    mean = c.mean(2)
    idx = np.empty((205, 320, 4), int)
    for i in range(4):                                     # nearest of the k colours, per picture pixel
        idx[:, :, i] = np.argmin(((c[:, :, i, None, :] - cent[None, None]) ** 2).sum(-1), -1)
    cnt = (idx[..., :, None] == idx[..., None, :]).sum(-1)          # how many of the four share it
    dist = np.linalg.norm(cent[idx] - mean[:, :, None], axis=-1)
    best = np.argmax(cnt * 1000.0 - dist, axis=-1)
    return cent[np.take_along_axis(idx, best[..., None], -1)[..., 0]]


def build_masks(a, S, s, A):
    H, W = a.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    L = lum_of(a)
    sat = a.max(-1) - a.min(-1)
    hz = int(round(S['horizon'] / s))
    m = {'hz': hz}
    ship_box = boxm(H, W, S['ship'], s)
    rock_box = np.zeros((H, W), bool)
    for b in S.get('rock', []):
        rock_box |= boxm(H, W, b, s)
    rock_low = np.zeros((H, W), bool)
    for b in S.get('rock_low', []):
        rock_low |= boxm(H, W, b, s)

    # --- the sky's own colour everywhere: one smooth surface (cubic in x, y) fitted to the open
    # sky, refitted without the outliers (clouds, wood, rock) each time. Only the wreck's clearly
    # non-sky pixels are left out at the start (leaving out its whole box made the fit swing
    # wildly at the left edge)
    # --- rock (the arch): in the rock box, unlike the sky and joined to the ground (anything
    # touching it, a cloud included, stays still); below the horizon only the rock_low boxes
    sea_col = (B - R > -10) & (B - G > 25) & (L > 85)
    up = rock_box & (yy < hz) & (B < 140) & ((R - B > 12) | (L < 120))   # sky here is always bluer (B 150+)
    lab, n = ndi.label(up)
    rock = np.isin(lab, np.unique(lab[up & (yy >= hz - 3)]))
    # on the beach rocks, the shaded faces are blue-violet like the sea: in those boxes only clearly
    # blue water counts as sea, everything else is rock (it stays still and gets no glitter)
    rock |= rock_low & ~(sea_col & (B - R > 15))
    if S.get('land'):
        # land drawn as outlines (dunes, a headland, cliffs): never sky, never cloud, never sea
        from PIL import ImageDraw
        li = Image.new('L', (640, 410), 0)
        dr = ImageDraw.Draw(li)
        for poly in S['land']:
            dr.polygon([tuple(v) for v in poly], fill=255)
        lm = np.asarray(li) > 0
        if s == 2:
            lm = lm.reshape(205, 2, 320, 2).mean(axis=(1, 3)) >= 0.5
        rock |= lm                              # (outlines are drawn round land only: never sea)
        m['land'] = lm
    m.setdefault('land', np.zeros((H, W), bool))
    m['rock'] = rock
    # the moon / the sun: discs kept out of the clouds (they have their own effects)
    disc = np.zeros((H, W), bool)
    for key in ('moon', 'sun'):
        if S.get(key):
            cx_, cy_, r_ = S[key]
            dk = np.hypot(xx - cx_ / s, yy - cy_ / s) <= (r_ + 3) / s
            m[key + '_disc'] = dk
            disc |= dk
    m['disc'] = disc

    rough = (ship_box & ((L < 90) | (R - B > 70))) | ndi.binary_dilation(rock, iterations=2)
    # the sky has a strong local glow by the arch, which no simple surface follows: estimate the
    # sky at every spot from the open sky around it (a wide blur of the pixels still counted as
    # sky), dropping whatever stands out (clouds, rock, wood) and repeating
    sig = 10.0 * A
    top = a[:hz]
    ok = ~rough[:hz]
    for th in (70, 50, 36, 26, 22, 22):
        w_ = ndi.gaussian_filter(ok.astype(float), sig)
        num = np.stack([ndi.gaussian_filter(top[..., c] * ok, sig) for c in range(3)], -1)
        est = num / np.maximum(w_, 1e-4)[..., None]
        ok = ~rough[:hz] & (np.linalg.norm(top - est, axis=-1) < th)
    ref = np.repeat(a[hz - 1:hz], H, 0).copy()
    ref[:hz] = est
    d = np.linalg.norm(a - ref, axis=-1)
    m['sky_ref'] = ref

    # --- the wreck: brown wood below the horizon, and whatever joins it against the sky
    # (darker than the sky, or much warmer than it)
    Lr = lum_of(ref)
    rb, rbr = R - B, ref[..., 0] - ref[..., 2]
    brown = (R - B > 30) & (L < 160) & (G < 0.8 * R)
    sky_rows = yy < hz
    warm = ship_box & sky_rows & (((rb - rbr > 40) & (L < 215)) | (L < Lr - 30))
    warm &= ~(m['land'] & ~brown)           # land behind the mast (a green headland) is not wood
    hull = ship_box & (yy >= hz - 1) & (brown | (L < 90)) & ~(m['land'] & ~brown)
    if S.get('sea_test') == 'night':        # (the night sea is dark too: dark blue-green is sea, not wood)
        hull &= ~((G > R + 4) & (B - R > 50))
    lab, n = ndi.label(warm | hull)
    warm &= np.isin(lab, np.unique(lab[hull & (lab > 0)]))
    # --- the torn sail: pale cloth below the yard, brighter than the sky behind it
    sail_box = boxm(H, W, S['sail'], s)
    if S.get('yard'):                       # cloth hangs below the yard (a line), never above it
        (ax, ay), (bx, by) = [(u / s, v / s) for u, v in S['yard']]
        sail_box &= yy > ay + (xx - ax) * (by - ay) / (bx - ax) + 1.5 * A
    if S.get('mast'):                       # ...and never on the mast itself
        (mx0, my0), (mx1, my1), mw = S['mast']
        mxc = (mx0 + (yy * s - my0) * (mx1 - mx0) / (my1 - my0)) / s
        sail_box &= np.abs(xx - mxc) > mw / s
    cloth = sail_box & (L > 95) & ~(m['land'] & (L < S.get('cloth_land_L', 0))) & (((B > 0.62 * R) & (d > S.get('cloth_d', 40))) | ((L > Lr + 8) & (sat < 140) & (B > 0.44 * R) & (d > 18)))
    # (the translucent cloth is pinkish, bluer than the mast and ropes, which are B < 0.6 R)
    cloth = ndi.binary_opening(cloth, structure=np.ones((2, 1))) | (cloth & ndi.binary_dilation(
        ndi.binary_opening(cloth, structure=np.ones((2, 1))), iterations=1))
    if S.get('sail_poly'):
        # cloth that is nearly sky-coloured (translucent rags, moonlight): traced as outlines. Inside,
        # everything but the dark mast and ropes is cloth (sky showing through moves invisibly)
        from PIL import ImageDraw
        si = Image.new('L', (640, 410), 0)
        dr = ImageDraw.Draw(si)
        for poly in S['sail_poly']:
            dr.polygon([tuple(v) for v in poly], fill=255)
        sp = np.asarray(si) > 0
        if s == 2:
            sp = sp.reshape(205, 2, 320, 2).mean(axis=(1, 3)) >= 0.5
        mastish = ((R - B > 30) & (L < 150) & (G < 0.8 * R)) | (L < S.get('sail_dark_L', 90))
        cloth = sp & ~mastish & sail_box
    elif S.get('yard'):
        # the cloth hangs from the yard: in each column keep only the run that starts right under
        # it (small gaps allowed), so sky streaks lower down are never taken for cloth
        hung = np.zeros_like(cloth)
        for x in np.where(cloth.any(0))[0]:
            yl = int(np.ceil(ay + (x - ax) * (by - ay) / (bx - ax) + 1.5 * A))
            y, gap = yl, 0
            started = False
            while y < H and gap <= A and (y - yl) < 60 / s:
                if cloth[y, x]:
                    hung[y, x] = True; gap = 0; started = True
                elif started or (y - yl) > S.get('yard_slack', 3) * A:
                    gap += 1
                y += 1
        cloth = hung
    lab, n = ndi.label(cloth, structure=np.ones((3, 3)))
    if n:
        sz = ndi.sum(cloth, lab, range(1, n + 1))
        cloth = np.isin(lab, 1 + np.where(sz >= 10 / s ** 2)[0])
    m['sail'] = cloth
    m['wood'] = (warm | hull) & ~cloth

    # --- water: by colour over the whole picture below the horizon. The sea is blue-violet
    # (bluer than red, much bluer than green, not dark) or white foam; anything joined to the
    # open sea, or a piece of it seen past the wreck, counts. Nothing is boxed out.
    if S.get('pond') is not None:
        # a pond or lake drawn as outlines (no sea, no surf): everything inside that isn't rock
        water = poly_mask(S['pond'], H, W, s) & ~m['rock']
        foam = np.zeros((H, W), bool); cool = water
    elif S.get('sea_test') == 'teal':          # a grey-teal sea (overcast): green about red, blue a bit higher
        cool = (B - R > 8) & (G > R - 4) & (L > 85)
    elif S.get('sea_test') == 'azure':       # a bright day sea: strongly blue and green (shaded rocks are not)
        cool = (B - R > 60) & (G > R + 25) & (L > 60)
    elif S.get('sea_test') == 'night':       # a night sea: deep blue, greener than red (the sand is redder)
        cool = (G > R + 4) & (B - R > 50) & (L > 35)
    else:
        cool = (B - R > -10) & (B - G > 25) & (L > 85)
    if S.get('pond') is None:
      foam = (L > 172) & (sat < 100) & (B >= G - 6)
      cand = (yy >= hz) & (cool | foam) & ~m['rock']
      lab, n = ndi.label(cand)
      sz = ndi.sum(cand, lab, range(1, n + 1))
      # (pieces must reach up into the sea band: bluish stones on the sand are not sea)
      tops = ndi.minimum(yy, lab, range(1, n + 1))
      sea_ymax = S.get('sea_ymax', H) / s
      water = np.isin(lab, 1 + np.where((sz >= 6 / s ** 2) & (np.asarray(tops) < sea_ymax))[0])
      # foam far down on the sand isn't sea: keep foam only within reach of blue water
      near_cool = ndi.binary_dilation(water & cool, iterations=max(2, 6 // s))
      water &= cool | near_cool
      # one-pixel holes in the sea (a darker fleck) still belong to it
      water |= ndi.binary_closing(water, structure=np.ones((3, 1))) & (yy >= hz) & ~m['rock'] & ~m['wood'] & (L > 60)
      # inside the wreck's box, only water the colour of the open sea on that row counts: at night
      # lit planks are as blue-violet as the sea
      out_w = water & ~ship_box
      rowref = np.zeros((H, 3)); have = np.zeros(H, bool)
      for y in range(hz, H):
          px_ = a[y][out_w[y]]
          if len(px_) >= 3:
              rowref[y] = np.median(px_, axis=0); have[y] = True
      if have.any() and S.get('wreck_sea_tol'):
          ys_h = np.where(have)[0]
          for c_ in range(3):
              rowref[:, c_] = np.interp(np.arange(H), ys_h, rowref[ys_h, c_])
          far = np.linalg.norm(a - rowref[:, None, :], axis=-1) > S['wreck_sea_tol']
          water &= ~(ship_box & far & ~foam)
    if S.get('refl_force_water'):           # the glow's reflection streaks (orange) are sea too
        for rb_ in refl_boxes(S):
            water |= boxm(H, W, rb_, s) & (yy >= hz) & ~m['rock']
    if S.get('wreck_foam') is False:        # moonlit rail tops look like foam: none inside the wreck's box
        water &= ~(ship_box & foam & ~cool)
    water &= ~m['wood']                     # (a pixel that could be either is wreck: planks never move)
    m['water'] = water
    m['foam'] = water & foam

    # --- the shoreline: in every column, the first row below the lowest water pixel, when that
    # row is open sand (not dark wood, not rock). Behind the wreck that is wherever the beach
    # shows between the rail posts.
    # below the horizon everything in the wreck's box that isn't water counts as the wreck (moss
    # and lit planks look like sand); the beach line there is found from its surf (below)
    plank = (m['wood'] | (ship_box & (yy >= hz))) & ~water
    plank |= m['sail'] | m['rock']
    m['plank'] = plank
    shore = np.full(W, -1)
    hidden = np.zeros(W, bool)              # the beach line is behind the wreck in this column
    # the open beach's sand colour on each row (outside the wreck): sand seen through a hole in the hull
    # that matches it is beach, not hull, so the shoreline is found (and washes) there too
    sand_ref = None
    if S.get('ship') is not None:
        open_sand = (yy >= hz) & ~water & ~ship_box & ~m['rock']
        sand_ref = np.full((H, 3), np.nan)
        for y_ in range(hz, H):
            px_ = a[y_][open_sand[y_]]
            if len(px_) >= 20:
                sand_ref[y_] = np.median(px_, axis=0)
        ok_ = ~np.isnan(sand_ref[:, 0])
        if ok_.any():
            for c_ in range(3):
                sand_ref[:, c_] = np.interp(np.arange(H), np.where(ok_)[0], sand_ref[ok_, c_])
    # where the open beach's shoreline runs (outside the wreck), continued under the hull
    line_fit = None
    pts = []
    for x in range(W):
        if ship_box[:, x].any() and ship_box[hz:, x].any():
            continue
        ys_ = np.where(water[:, x])[0]
        if len(ys_) and ys_.max() + 2 < H and not plank[ys_.max() + 1:ys_.max() + 3, x].any():
            pts.append((x, ys_.max() + 1))
    if len(pts) >= 20:
        pts = np.array(pts)
        line_fit = np.polyfit(pts[:, 0], pts[:, 1], 2)
    hull_sand = np.zeros((H, W), bool)
    for x in (range(W) if S.get('pond') is None else []):
        ys = np.where(water[:, x])[0]
        if len(ys):
            y = ys.max() + 1
            run_w = 0                            # how much sea stands right above it
            while y - 1 - run_w >= 0 and water[y - 1 - run_w, x]:
                run_w += 1
            run_s = 0                            # and how tall the sand patch is
            while (sand_ref is not None and y + run_s < H
                   and np.abs(a[y + run_s, x] - sand_ref[y + run_s]).max() < 28):
                run_s += 1
            if (y < H - 2 and ship_box[y, x] and sand_ref is not None and line_fit is not None
                    and run_w >= A and run_s >= 2 * A
                    and abs(y - np.polyval(line_fit, x)) <= 10.0 / s):   # on the open beach's own shoreline
                shore[x] = y                    # beach showing through the hull
                yy2 = y
                while yy2 < H and yy2 - y < 8 * A and np.abs(a[yy2, x] - sand_ref[yy2]).max() < 28:
                    hull_sand[yy2, x] = True; yy2 += 1
            elif y < H - 2 and not plank[y:y + 2, x].any():
                shore[x] = y
            elif y < H - 2 and foam[max(hz, y - 1 - 3 * A):y, x].any():
                # the sea ends on wood, but its last rows are the painted surf line: that surf is
                # the shoreline seen past the wreck, and it moves with the rest (inside the water)
                shore[x] = y; hidden[x] = True
    good = (shore > 0) & ~hidden
    if good.sum() > 20:          # readings far off the beach line (a stray blue pixel) dropped
        xs = np.where(good)[0]
        fitc = np.polyfit(xs, shore[xs], 4)
        bad = np.abs(shore[xs] - np.polyval(fitc, xs)) > 12 / s
        shore[xs[bad]] = -1
    plank &= ~hull_sand
    m['wood'] = m['wood'] & ~hull_sand      # (brown beach sand by the hull passes the wood test: it's sand)
    m['plank'] = plank
    m['hull_sand'] = hull_sand
    m['shore'] = shore
    m['shore_hidden'] = hidden
    # each column's stretch that the surf may slide: the water just above the line and the open
    # sand just below it, never past a plank, a rock or the sail
    xs_ok = np.where(shore > 0)[0]
    lr_x = (np.interp(np.arange(W), [xs_ok.min(), xs_ok.max()], list(S.get('surf_lr', (1.0, 1.0))))
            if len(xs_ok) else np.ones(W))
    m['lr'] = lr_x
    seg = np.full((W, 2), -1)
    for x in np.where(shore > 0)[0]:
        y0 = max(hz + 1, shore[x] - 9 * A)
        y1 = shore[x] - 1 if hidden[x] else shore[x]
        reach = (SURF_AMP * lr_x[x] + 1.5) * A           # as far as the wash and the wet sand go
        while not hidden[x] and y1 + 1 < H and not plank[y1 + 1, x] and (y1 + 1) - shore[x] < reach:
            y1 += 1
        seg[x] = (y0, y1)
    m['surf_seg'] = seg
    solid = plank

    # --- clouds: sky pixels standing apart from the sky's colour, as connected pieces; those
    # tangled with the mast or touching the rock stay still
    tree_poly = np.zeros((H, W), bool)
    for tr in S.get('trees', []):
        tree_poly |= poly_mask([tr['poly']], H, W, s)
    m['tree_poly'] = tree_poly
    objects = ndi.binary_dilation(m['wood'] | m['sail'], iterations=1) | ndi.binary_dilation(rock, iterations=1) | disc
    objects |= ndi.binary_dilation(tree_poly, iterations=2 * A)
    if S.get('smoke'):                      # painted smoke has its own motion (rising), not cloud drift
        objects |= poly_mask(S['smoke'], H, W, s)
    sky_zone = (yy < hz) & ~objects
    cmax = int(round(S['cloud_ymax'] / s))
    # cores stand well apart from the sky; each grows a few pixels into its soft edge, so the
    # faint glow by the arch can't bridge separate clouds into one piece
    zone = sky_zone & (yy < cmax)
    # how much a pixel stands above the sky around it: red minus its grey opening with a tall
    # window (taller than any cloud), so the broad glow counts as sky and clouds stand out
    th_r = None
    for Ch in ([R, G] if S.get('cloud_channel') == 'red+green' else [{'lum': L, 'green': G}.get(S.get('cloud_channel'), R)]):
        # (yellow clouds on an orange sky stand out in green, the pink ones in red: both can count)
        Rf = np.where(objects | (yy >= hz), 255.0, Ch)      # (dark rock, wood, sea must not drag it down)
        t_ = Ch - ndi.grey_opening(Rf, size=(int(45 / s) | 1, int(11 / s) | 1))
        th_r = t_ if th_r is None else np.maximum(th_r, t_)
    m['tophat'] = th_r
    core0 = zone & (th_r > 40)
    core0 = ndi.binary_opening(core0, structure=np.ones((2, 2))) if A > 1 else core0
    clouds = ndi.binary_dilation(core0, iterations=3 * A, mask=zone & (th_r > 24))
    clouds = ndi.binary_closing(clouds, iterations=1) & zone
    lab, n = ndi.label(clouds, structure=np.ones((3, 3)))
    sizes = ndi.sum(clouds, lab, range(1, n + 1))
    near_obj = ndi.binary_dilation(objects, iterations=1)
    stuck = set(np.unique(lab[near_obj & (lab > 0)]))
    big = [i for i in 1 + np.where(sizes >= 8 * 4 / s ** 2)[0]]
    m['cloud_lab'] = np.where(np.isin(lab, big), lab, 0)
    moving = [i for i in big if i not in stuck]
    core = np.isin(lab, moving)
    m['cloud_core'] = core
    m['cloud_all'] = np.isin(lab, big)
    m['clouds'] = ndi.binary_dilation(core, iterations=1) & sky_zone & (yy < cmax + 1)
    m['sky_zone'] = sky_zone

    # --- the gold rims: on each cloud, its bright warm pixels at the cloud's edge
    allc = m['cloud_all']
    edge_d = ndi.distance_transform_edt(allc)
    mode = S.get('rims', 'gold')
    if mode == 'gold':
        gold = allc & (R > 210) & (G > 120) & (R - B > 50) & (L > S.get('rim_min_L', 150))
    elif mode == 'lit':                     # red-orange sunset edges (storm clouds)
        gold = allc & (R > 185) & (R - B > 60) & (L > 115)
    elif mode == 'pink':                    # pink-peach light from the horizon (dusk)
        gold = allc & (R > 200) & (R - B > 25) & (L > S.get('rim_min_L', 150))
    elif mode == 'silver':                  # moonlit edges: the brightest pixels of each cloud
        cl_l = L[allc]
        gold = allc & (L > (np.percentile(cl_l, 80) if cl_l.size else 255))
    else:
        gold = np.zeros((H, W), bool)
    rim = gold & (edge_d <= S.get('rim_edge', 3.0) * A)
    # a rim is a line, not a speck: keep runs of a few pixels
    lab_r, n_r = ndi.label(rim, structure=np.ones((3, 3)))
    if n_r:
        sz = ndi.sum(rim, lab_r, range(1, n_r + 1))
        rim = np.isin(lab_r, 1 + np.where(sz >= 3 * A)[0])
    if S.get('rim_line'):
        # the old autumn map's look: a thin gold line along the underside of every cloud (each cloud pixel with open
        # sky just below it), runs of a few pixels or more
        below_open = np.zeros((H, W), bool)
        below_open[:-1] = ~allc[1:]
        line = allc & below_open & sky_zone & ~ndi.binary_dilation(objects, iterations=3 * A)   # (not on the trees' edges)
        line &= yy < S.get('rim_line_ymax', H * s) / s                                            # (nor on bits low among them)
        lab_l, n_l = ndi.label(line, structure=np.ones((3, 3)))
        if n_l:
            sz = ndi.sum(line, lab_l, range(1, n_l + 1))
            line = np.isin(lab_l, 1 + np.where(sz >= 4 * A)[0])
        rim = line
        m['rim_line'] = line
    m['rim'] = rim

    # --- the glow's reflection on the water (pinker water under the glow)
    m['refl'] = np.zeros((H, W), bool)
    for rb_ in refl_boxes(S):
        m['refl'] |= boxm(H, W, rb_, s) & water & (((R - B > -48) | foam) if S.get('refl_warm', True) else (L > 0))

    # --- grass: yellow-green blades in the tuft boxes
    gb = S.get('grass_gb', 1.6)
    grassy = (G > gb * B) & (G > 0.55 * R) & (sat > (45 if gb > 1.5 else 25)) & (L > 45)
    tufts = np.zeros((H, W), bool)
    for b in S.get('tufts', []):
        tufts |= boxm(H, W, b, s) & grassy
    lab, n = ndi.label(tufts, structure=np.ones((3, 3)))
    if n:
        sz = ndi.sum(tufts, lab, range(1, n + 1))
        tufts = np.isin(lab, 1 + np.where(sz >= 4 * 4 / s ** 2)[0])
    m['tufts'] = tufts & ~m['wood']
    # hanging ivy / vines: leafy green in the vine boxes (it hangs, so its tips are at the bottom)
    vines = np.zeros((H, W), bool)
    for b in S.get('vines', []):
        vines |= boxm(H, W, b, s) & (G > B + 20) & (G > 0.8 * R) & (L > 50)
    lab_v, n_v = ndi.label(vines, structure=np.ones((3, 3)))
    if n_v:
        sz_v = ndi.sum(vines, lab_v, range(1, n_v + 1))
        vines = np.isin(lab_v, 1 + np.where(sz_v >= 6 * 4 / s ** 2)[0])
    m['vines'] = vines & ~m['tufts']
    # wet stone that catches the light (a sheen glints along its streaks)
    m['sheen'] = np.zeros((H, W), bool)
    if S.get('sheen'):
        sm_ = poly_mask(S['sheen'], H, W, s) & ~m['tufts'] & ~m['rock']
        if S.get('sheen_test') == 'pink':   # the sky's pink mirrored on wet stone
            sm_ &= (R > B - 10) & (R > G + 25) & (L > 95)
        m['sheen'] = sm_
    # snow that sparkles
    m['snow'] = np.zeros((H, W), bool)
    if S.get('snow'):
        m['snow'] = poly_mask(S['snow'], H, W, s) & (L > 205) & (sat < 60)
    # painted points of light that twinkle (stars, fireflies): small spots brighter than round them
    m['twinkle'] = np.zeros((H, W), bool)
    for kind in ('stars_painted', 'fireflies'):
        if not S.get(kind):
            continue
        zone = poly_mask(S[kind], H, W, s)
        bg_ = ndi.median_filter(L, size=5 * A)
        spot = zone & (L - bg_ > (28 if kind == 'stars_painted' else 22))
        if kind == 'fireflies':
            spot &= (R > 150) & (G > 160) & (B < G - 30)
        else:
            spot &= ~m['cloud_all'] & ~disc & ~ndi.binary_dilation(m['tree_poly'] | m['rock'], iterations=2 * A)
        lab_t, n_t = ndi.label(spot, structure=np.ones((3, 3)))
        if n_t:
            sz_t = ndi.sum(spot, lab_t, range(1, n_t + 1))
            spot = np.isin(lab_t, 1 + np.where(sz_t <= 14 * A * A)[0])
        m['twinkle'] |= ndi.binary_dilation(spot, iterations=1) & zone
    m['twinkle_bg'] = ndi.median_filter(a, size=(7 * A, 7 * A, 1)) if m['twinkle'].any() else None
    # lava: hot pixels (bright, red-orange-yellow) inside each lava zone; each zone says how it moves:
    # 'river' and 'fall' flow along a direction, 'pool' swirls round a centre, 'crack' only glows
    m['lava_zones'] = []
    m['lava'] = np.zeros((H, W), bool)
    for z in S.get('lava', []):
        zm = poly_mask([z['poly']], H, W, s)
        hot = zm & (R > z.get('min_r', 175)) & (R - B > z.get('min_rb', 70)) & (G > z.get('min_g', 45))
        hot = ndi.binary_closing(hot, iterations=1) & zm & (R > 140) & (R - B > 50)
        lab_l, n_l = ndi.label(hot, structure=np.ones((3, 3)))
        if n_l:
            sz_l = ndi.sum(hot, lab_l, range(1, n_l + 1))
            hot = np.isin(lab_l, 1 + np.where(sz_l >= 4 * 4 / s ** 2)[0])
        hot &= ~m['lava']                       # (a pixel belongs to the first zone that claims it)
        m['lava_zones'].append(dict(z, mask=hot))
        m['lava'] |= hot
    # rock right round the lava glows with it
    m['lava_glow'] = np.zeros((H, W))
    if m['lava'].any():
        dist_l = ndi.distance_transform_edt(~m['lava'])
        m['lava_glow'] = np.exp(-dist_l / (5.0 * A)) * ~m['lava'] * (dist_l < 14 * A)
    # painted smoke and ash that drifts up
    m['smoke'] = np.zeros((H, W), bool)
    if S.get('smoke'):
        m['smoke'] = poly_mask(S['smoke'], H, W, s) & ~m['lava'] & ~m['rock']
    # grassy slopes the wind rolls over (brightness only)
    hills = np.zeros((H, W), bool)
    for b in S.get('hills', []):
        hills |= boxm(H, W, b, s)
    m['hills'] = hills & (G > 1.15 * B) & (G > 0.7 * R) & (sat > 30) & (L > 50) & ~m['wood'] & ~m['tufts']
    # a waterfall: the bright falling water in its box (big pieces only), and the splash under it
    m['fall'] = np.zeros((H, W), bool); m['splash'] = np.zeros((H, W), bool)
    if S.get('waterfall'):
        fl = boxm(H, W, S['waterfall'], s) & (L > 165) & (B >= R - 10)
        lab_f, n_f = ndi.label(fl, structure=np.ones((3, 3)))
        if n_f:
            sz_f = ndi.sum(fl, lab_f, range(1, n_f + 1))
            fl = np.isin(lab_f, 1 + np.where(sz_f >= 15 * 4 / s ** 2)[0])
        m['fall'] = fl
        m['splash'] = boxm(H, W, S['splash'], s) & (L > 175)
    m['solid'] = solid
    return m


def mask_view(a, m, path, s):
    v = a * 0.4
    v[m['rock']] = (110, 110, 110)
    v[m['wood']] = (150, 70, 120)
    v[m['water']] = (40, 150, 255)
    v[m['foam']] = (255, 255, 255)
    v[m['refl']] = (255, 120, 200)
    v[m['cloud_all']] = (170, 150, 40)
    v[m['cloud_core']] = (255, 220, 60)
    v[m['rim']] = (255, 80, 0)
    v[m['sail']] = (0, 255, 255)
    v[m['tufts']] = (0, 230, 0)
    v[m['vines']] = (0, 160, 0)
    for z in m['lava_zones']:
        v[z['mask']] = {'river': (255, 60, 0), 'fall': (255, 230, 0), 'pool': (255, 0, 200), 'crack': (120, 255, 255)}[z.get('kind', 'river')]
    v[m['smoke']] = (200, 200, 255)
    v[m['sheen']] = (255, 150, 220)
    v[m['snow']] = (255, 255, 255)
    v[m['twinkle']] = (255, 0, 0)
    if m['tree_poly'].any():
        v[m['tree_poly'] & ~m['rock']] = v[m['tree_poly'] & ~m['rock']] * 0.6 + np.array([0, 90, 255]) * 0.4
    v[m['hills']] = v[m['hills']] * 0.5 + np.array([120, 255, 120]) * 0.5
    v[m['fall']] = (200, 255, 255)
    v[m['disc']] = v[m['disc']] * 0.5 + np.array([255, 255, 0]) * 0.5
    for x, (y0, y1) in enumerate(m['surf_seg']):
        if y0 > 0:
            v[y0:y1 + 1, x] = v[y0:y1 + 1, x] * 0.5 + np.array([255, 0, 0]) * 0.5
            v[m['shore'][x], x] = (255, 0, 0)
    im = Image.fromarray(v.clip(0, 255).astype(np.uint8))
    im.resize((im.width * 2 * s // 1, im.height * 2 * s // 1), Image.NEAREST).save(path)



def depth_pass(a, m, S, A):
    H, W = a.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    hz = m['hz']
    far = np.exp(-((yy - hz + 3 * A) / (9.0 * A)) ** 2) * ~m['wood'] * ~m['cloud_all']
    near = np.clip((yy - hz - 30 * A) / (H - hz - 30.0 * A), 0, 1) ** 1.2
    near = np.maximum(near, soft(m['wood'] & (yy > hz - 30 * A), 2.0 * A) * 0.6)
    out = a + (C(S['haze']) - a) * (DEPTH_FADE * far)[..., None]
    L = lum_of(out)[..., None]
    out = L + (out - L) * (1 + NEAR_SATURATE * near)[..., None]
    local = ndi.uniform_filter(out, size=(9 * A, 9 * A, 1))
    out = local + (out - local) * (1 + NEAR_CONTRAST * near)[..., None]
    return out.clip(0, 255)


def shift_take(f, src_y, src_x, take):
    g = f.copy()
    g[take] = f[src_y[take], src_x[take]]
    return g




def refl_boxes(S):
    r = S.get('refl')
    if not r:
        return []
    return [r] if isinstance(r[0], (int, float)) else list(r)


def smooth01(v):
    v = np.clip(v, 0, 1)
    return v * v * (3 - 2 * v)


def rolling_waves(art, m, S, A, rng, water, lum0, shore_w):
    """Map 5's rolling waves, at either scale. Each painted wave (a dark spot of the sea with its
    white crest on top) is lifted off the sea, the gap filled from the water above and below,
    and rolls toward the beach as one piece, keeping its own shape and colours (stored relative
    to the calm water round it, so it keeps its contrast on the lighter water near the beach);
    far waves fade in and grow, near ones shrink into the surf. Returns (lifted, calm, draw)."""
    H, W = art.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    hz = m['hz']
    shore = m['shore']
    rel = yy - shore_w[None, :]
    s_ = 2 if A == 1 else 1
    open_sea = water.copy()
    if not S.get('waves_behind_wreck'):
        open_sea &= ~boxm(H, W, S['ship'], s_)        # waves on the open sea only: not behind the wreck,
    if S.get('waves_avoid_refl', True):
        for rb_ in refl_boxes(S):
            open_sea &= ~boxm(H, W, rb_, s_)                                  # not in the glow's streaky reflection
    open_sea &= ~ndi.binary_dilation(m['rock'], iterations=3 * A)          # and not hugging the rocks
    wl = water & (rel < -2 * A)
    # the water's own brightness round each pixel, along its row (short and wide), so the sea
    # darkening toward the horizon doesn't read as one big dark wave
    lw = S.get('wave_local', (9, 25))
    num = ndi.uniform_filter(lum0 * water, size=(lw[0] * A, lw[1] * A))
    den = ndi.uniform_filter(water.astype(float), size=(lw[0] * A, lw[1] * A))
    Lloc = num / np.maximum(den, 1e-6)
    U0 = 0.12
    cols_ok = np.where((shore > 0) & (~m['shore_hidden'] | bool(S.get('waves_behind_wreck'))))[0]
    span_full = ndi.uniform_filter1d((shore_w - hz).astype(float), 21 * A, mode='nearest')
    top_u = np.zeros((H, W), bool)
    for x in cols_ok:
        top_u[int(hz + U0 * span_full[x]):int(shore_w[x]) - 2 * A, x] = True
    darkm = wl & open_sea & top_u & (lum0 < Lloc - S.get('wave_dark', 4))
    lab_d, n_d = ndi.label(darkm)
    sizes_d = ndi.sum(darkm, lab_d, range(1, n_d + 1))
    lifted = np.zeros((H, W), bool)
    pieces, line_cx, parts = [], {}, []
    persp = lambda u: 0.6 + 0.8 * u
    for k in range(1, n_d + 1):
        if sizes_d[k - 1] < 8 * A * A:
            continue
        ys, xs = np.where(lab_d == k)
        ux = np.unique(xs)
        if ux.max() - ux.min() > 45 * A:            # a long band: cut every 25-40 px at its thinnest
            thick = np.array([(xs == x).sum() for x in ux])
            cuts, x_at = [], ux.min()
            while ux.max() - x_at > 45 * A:
                tgt = x_at + int(rng.integers(25, 40)) * A
                win = (ux >= tgt - 6 * A) & (ux <= tgt + 6 * A)
                cut = ux[win][np.argmin(thick[win])] if win.any() else tgt
                cuts.append(cut); x_at = cut
            bounds = [ux.min()] + cuts + [ux.max() + 1]
            for lo, hi in zip(bounds[:-1], bounds[1:]):
                sel = (xs >= lo) & (xs < hi)
                if sel.sum() >= 6 * A * A:
                    parts.append((ys[sel], xs[sel]))
        else:
            parts.append((ys, xs))
    for k, (ys, xs) in enumerate(parts, start=1):
        cols, us_ = [], []
        for x in np.unique(xs):
            yc_ = np.sort(ys[xs == x])
            ytop, ybot = yc_[0], yc_[-1]
            nb = min(ybot - ytop + 1, 6 * A)
            run = 0                                  # the body stops at the first pixel that isn't sea
            while run < nb and ytop + run < H and wl[ytop + run, x]:
                run += 1
            nb = max(run, 1)
            nc = 0
            while nc < 2 * A and ytop - nc - 1 > hz and wl[ytop - nc - 1, x] and lum0[ytop - nc - 1, x] > Lloc[ytop - nc - 1, x] + 2:
                nc += 1
            y0 = ytop - nc
            cols.append((x, y0, art[y0:ytop, x].copy(), art[ytop:ytop + nb, x].copy()))
            lifted[y0:ytop + nb, x] = True
            us_.append((ytop - hz) / max(span_full[x], 1))
        xs_p = np.array([c[0] for c in cols])
        pieces.append(dict(u=float(np.mean(us_)), cols=cols, cx=xs_p.mean(),
                           half=(xs_p.max() - xs_p.min()) / 2.0 + 0.5, line=k))
        line_cx[k] = xs_p.mean()
    n_d = len(parts)
    sat0 = art.max(-1) - art.min(-1)
    # crests with no dark patch under them: pale (whitish) only, the pink glow streaks aren't crests
    lone = wl & open_sea & top_u & (lum0 > Lloc + 9) & (sat0 < 85) & ~lifted
    lab_c, n_c = ndi.label(lone, structure=np.ones((3, 3)))
    for k in range(1, n_c + 1):
        ys, xs = np.where(lab_c == k)
        if len(ys) < 3 * A * A:
            continue
        cols, us_ = [], []
        for x in np.unique(xs):
            yc_ = np.sort(ys[xs == x])
            y1c = yc_[0]
            while y1c + 1 <= yc_[-1] and wl[y1c + 1, x]:      # (a lone crest: sea pixels only)
                y1c += 1
            cols.append((x, yc_[0], art[yc_[0]:y1c + 1, x].copy(), art[0:0, x].copy()))
            lifted[yc_[0]:y1c + 1, x] = True
            us_.append((yc_[-1] - hz) / max(span_full[x], 1))
        xs_p = np.array([c[0] for c in cols])
        pieces.append(dict(u=float(np.mean(us_)), cols=cols, cx=xs_p.mean(),
                           half=(xs_p.max() - xs_p.min()) / 2.0 + 0.5, line=n_d + k))
        line_cx[n_d + k] = xs_p.mean()
    if S.get('fill_crest_bits'):
        # bits of crest left beside a lifted wave (too small to be pieces of their own) would stay
        # behind as still white dots while the wave rolls away: fill them into the calm water too
        bits = wl & open_sea & top_u & (lum0 > Lloc + 6) & ~lifted & ndi.binary_dilation(lifted, iterations=2 * A)
        lifted |= bits
    # each drawn wave: the gap down to the next wave line (where it hands over)
    lid = -np.ones((H, W), int)
    for pc in pieces:
        for x, y0, ccol, bcol in pc['cols']:
            lid[y0 + len(ccol) - (1 if len(ccol) else 0), x] = pc['line']
    stats = {}
    for L_ in set(pc['line'] for pc in pieces):
        cols_L = [(x, y0, len(cc)) for pc in pieces if pc['line'] == L_ for x, y0, cc, bc in pc['cols']]
        hops = []
        for x, y0, nc in cols_L:
            yb = y0 + nc
            nxt = [d_ for d_ in range(3 * A, 20 * A) if yb + d_ < H and lid[yb + d_, x] >= 0 and lid[yb + d_, x] != L_]
            if nxt:
                hops.append(nxt[0])
        stats[L_] = (float(np.mean([pc['u'] for pc in pieces if pc['line'] == L_])), hops, len(cols_L))
    pts = [(u_L, np.median(h)) for u_L, h, n_ in stats.values() if len(h) >= 0.25 * n_ and len(h)]
    fit = np.polyfit(*np.array(pts).T, 1) if len(pts) >= 3 else (6.0 * A, 3.0 * A)
    u_min = min(v[0] for v in stats.values())
    span_mean = float(np.mean(span_full[cols_ok]))
    line_info = {}
    for L_, (u_L, hops, n_) in stats.items():
        D = float(np.clip(np.polyval(fit, u_L), 3 * A, 10 * A))
        last = u_L + D / span_mean > 0.84
        if last:
            xm = int(round(line_cx[L_]))
            D = float(max(2 * A, shore_w[xm] - 2 * A - (hz + u_L * span_full[xm])))
        line_info[L_] = dict(last=last, first=u_L < u_min + 0.06, D=D)
    x_near, x_far = cols_ok.min(), cols_ok.max()
    if S.get('crest_thin_near', True):          # fewer waves crowding the boat: the biggest third stay
        near_boat = [i for i, pc in enumerate(pieces) if pc['cx'] < x_near + 80 * A]
        near_boat.sort(key=lambda i: -len(pieces[i]['cols']))
        drop = set(near_boat[len(near_boat) // 3:])
        pieces = [pc for i, pc in enumerate(pieces) if i not in drop]
    shore_slope = np.gradient(ndi.uniform_filter1d(shore_w.astype(float), 41 * A, mode='nearest'))
    cd_ = S.get('crest_dir', ([0.0, 1.0], [0.0, 1.0]))
    for pc in pieces:
        tx_ = np.clip((pc['cx'] - x_near) / max(x_far - x_near, 1), 0, 1)
        pc['dirx'] = float(np.interp(tx_, cd_[0], cd_[1]))
        pc['k'] = float(np.interp(pc['cx'], [x_near, x_far], list(S.get('crest_k', (1.3, 0.7)))))
        if S.get('lean_from_shore'):
            # lie along this picture's own beach line where the wave is (its slope, eased a little)
            xi_ = int(np.clip(round(pc['cx']), 0, W - 1))
            target = float(np.clip(shore_slope[xi_] * 0.8, -0.2, 0.2))
        else:
            target = -float(np.interp(tx_, WAVE_LEAN_AT, WAVE_LEAN)) * S.get('lean_sign', 1)
        xs_c = np.array([c[0] for c in pc['cols']], float)
        yb_c = np.array([c[1] + len(c[2]) for c in pc['cols']], float)
        own = np.polyfit(xs_c, yb_c, 1)[0] if len(xs_c) >= 3 else 0.0
        pc['shear'] = float(target - own)
        li = line_info[pc['line']]
        pc['last'], pc['first'], pc['D'] = li['last'], li['first'], li['D']
        pc['ph'] = rng.random()
    if S.get('wave_min_gap'):
        # spacing: two waves stacked closer than the gap (overlapping side to side) read as one
        # doubled wave when they roll; keep the bigger, the smaller melts into the calm water
        gap = S['wave_min_gap'] * A
        for pc in pieces:
            xs_c = np.array([c[0] for c in pc['cols']])
            pc['x0'], pc['x1'] = xs_c.min(), xs_c.max()
            pc['yb'] = float(np.mean([c[1] + len(c[2]) for c in pc['cols']]))
        def overlap(a_, b_):
            o = min(a_['x1'], b_['x1']) - max(a_['x0'], b_['x0'])
            return o / max(1.0, min(a_['x1'] - a_['x0'], b_['x1'] - b_['x0']))
        order = sorted(range(len(pieces)), key=lambda i: -len(pieces[i]['cols']))
        kept = []
        for i in order:
            if all(not (overlap(pieces[i], pieces[j]) > 0.3 and abs(pieces[i]['yb'] - pieces[j]['yb']) < gap) for j in kept):
                kept.append(i)
        pieces = [pieces[i] for i in sorted(kept)]
        # timing: waves near each other (overlapping side to side, within two gaps up or down)
        # start their rolls as far apart in time as they can; the biggest choose first
        cand = np.arange(24) / 24.0
        done = []
        for i in sorted(range(len(pieces)), key=lambda i: -len(pieces[i]['cols'])):
            nb = [pieces[j]['ph'] for j in done if overlap(pieces[i], pieces[j]) > 0.0
                  and abs(pieces[i]['yb'] - pieces[j]['yb']) < 2.5 * gap]
            if nb:
                dist = np.min(np.abs(((cand[:, None] - np.array(nb)[None, :]) + 0.5) % 1.0 - 0.5), axis=1)
                best = cand[dist >= dist.max() - 1e-9]
                pieces[i]['ph'] = float(best[int(rng.integers(len(best)))])
            done.append(i)
    # fill where the waves were from the water just above and below
    calm = art.copy()
    for x in np.unique(np.where(lifted)[1]):
        col = lifted[:, x]
        y = 0
        while y < H:
            if col[y]:
                y2 = y
                while y2 + 1 < H and col[y2 + 1]:
                    y2 += 1
                up_c = art[y - 1, x] if water[y - 1, x] else None
                dn_c = art[y2 + 1, x] if y2 + 1 < H and water[y2 + 1, x] else None
                if up_c is None: up_c = dn_c
                if dn_c is None: dn_c = up_c
                if up_c is not None:
                    for kk, yy_ in enumerate(range(y, y2 + 1)):
                        calm[yy_, x] = up_c + (dn_c - up_c) * (kk + 1) / (y2 - y + 2)
                y = y2 + 1
            else:
                y += 1
    sm = np.stack([ndi.uniform_filter1d(calm[..., c], 5 * A, axis=1) for c in range(3)], -1)
    calm[lifted] = sm[lifted]
    wden = np.maximum(ndi.uniform_filter(wl.astype(float), size=(7 * A, 21 * A)), 1e-6)
    calm_loc = np.stack([ndi.uniform_filter(calm[..., c] * wl, size=(7 * A, 21 * A)) for c in range(3)], -1) / wden[..., None]
    for pc in pieces:
        rel_cols = []
        for x, y0, ccol, bcol in pc['cols']:
            nc_, nb_ = len(ccol), len(bcol)
            rel_cols.append((x, y0, ccol - calm_loc[y0:y0 + nc_, x], bcol - calm_loc[y0 + nc_:y0 + nc_ + nb_, x]))
        has = [len(c[2]) > 0 for c in rel_cols]            # the crest is one unbroken light line
        if any(has):
            idx_c = [i for i, h_ in enumerate(has) if h_]
            for i, c in enumerate(rel_cols):
                if not has[i] and len(c[3]):
                    j = min(idx_c, key=lambda j_: abs(j_ - i))
                    if abs(j - i) <= 4 * A:
                        src = rel_cols[j][2]
                        rel_cols[i] = (c[0], c[1] - len(src), src.copy(), c[3])
        pc['cols'] = rel_cols
        pc['colmap'] = {x: (y0, ccol, bcol) for x, y0, ccol, bcol in rel_cols}
    roll_s = 20.0 / CREST_CYCLES
    L_ = S.get('crest_linger', 2.3) / roll_s      # how long a crest glides on after its roll
    fin = S.get('crest_fade_in', 0.15)            # how gently a new crest appears (share of a roll)

    def draw(f, p):
        f[lifted] = calm[lifted]
        for pc in pieces:
            ph_ = CREST_CYCLES * p + pc['ph']
            tau_ = (ph_ % 1.0) * roll_s
            for k_ in (1, 0):                      # the previous roll's lingering crest, then this one
                s_ = (tau_ + k_ * roll_s) / roll_s
                if s_ >= 1.0 + L_:
                    continue
                end_c = 1.0 + L_
                alpha = smooth01(s_ / fin) * smooth01((end_c - s_) / 0.15)
                alpha_b = smooth01(s_ / 0.4) * smooth01((1.0 - s_) / 0.25) if s_ < 1.0 else 0.0
                g_body = smooth01((s_ - 0.04) / 0.42) if s_ < 1.0 else 0.0
                g_crest = 1.0
                if pc['first']:
                    alpha = smooth01(s_ / 0.35) * smooth01((end_c - s_) / 0.15)
                    alpha_b = smooth01(s_ / 0.5) * smooth01((1.0 - s_) / 0.25) if s_ < 1.0 else 0.0
                    g_crest = 0.4 + 0.6 * smooth01(s_ / 0.5)
                    g_body *= g_crest
                if pc['last']:
                    alpha = smooth01(s_ / fin)
                    alpha_b = smooth01(s_ / 0.4) if s_ < 1.0 else 0.0
                    g_body *= 1.0 - smooth01((s_ - 0.3) / 0.55)
                    g_crest = 1.0 - smooth01((s_ - 0.55 - L_) / 0.45)
                if s_ <= 1.0:
                    dy = pc['D'] * WAVE_TRAVEL * s_
                else:
                    q = (s_ - 1.0) / L_
                    dy = pc['D'] * WAVE_TRAVEL * (1.0 + L_ * (q - q ** 3 / 3.0))
                xi_ = int(np.clip(round(pc['cx']), 0, W - 1))
                u_now = pc['u'] + dy / max(span_full[xi_], 1)
                g_body *= smooth01((0.93 - u_now) / 0.28)
                g_crest *= smooth01((1.0 - u_now) / 0.12)
                g_len = max(g_body, g_crest)
                if g_len < 0.05 or max(alpha, alpha_b) <= 0:
                    continue
                dxs = int(np.rint(pc['dirx'] * dy))
                k_ = pc['k'] * float(np.interp(u_now, [U0, 0.9], [0.7, 1.0]))
                ratio = (1.0 + 0.8 * dy / max(span_full[xi_], 1) / persp(pc['u'])) * k_
                half_now = g_len * pc['half'] * k_
                colmap = pc['colmap']
                for tx in range(int(np.floor(pc['cx'] - half_now)), int(np.ceil(pc['cx'] + half_now)) + 1):
                    sx_ = int(round(pc['cx'] + (tx - pc['cx']) / k_))
                    if sx_ not in colmap:
                        continue
                    y0, ccol, bcol = colmap[sx_]
                    e = abs(tx - pc['cx']) / max(half_now, 0.5)
                    if e > 1:
                        continue
                    taper = max(0.0, 1 - e * e) ** 0.6
                    x = tx + dxs
                    if x < 0 or x >= W:
                        continue
                    nc = len(ccol); nb = len(bcol)
                    yb = int(np.rint(y0 + nc + dy + pc['shear'] * (tx - pc['cx'])))
                    nc2 = max(1, int(round(nc * min(ratio, 1.5)))) if (nc and g_crest > 0.15) else 0
                    nb2 = int(round(min(nb * ratio, (1.0 + 2.2 * k_) * A) * g_body * taper))
                    for r in range(nc2):
                        ty_ = yb - nc2 + r
                        if 0 <= ty_ < H and wl[ty_, x]:
                            c_ = np.clip(calm_loc[ty_, x] + CREST_POP * ccol[min(nc - 1, r * nc // nc2)], 0, 255)
                            f[ty_, x] += (c_ - f[ty_, x]) * alpha
                    for r in range(nb2):
                        ty_ = yb + r
                        if ty_ >= H or not wl[ty_, x]:
                            break
                        c_ = np.clip(calm_loc[ty_, x] + bcol[min(nb - 1, r * nb // max(nb2, 1))], 0, 255)
                        f[ty_, x] += (c_ - f[ty_, x]) * alpha_b
        return f

    print('rolling waves: %d pieces' % len(pieces))
    return lifted, calm, draw


def beam_field(xx, yy, cx, cy, r, p, A):
    tau = 2 * np.pi
    ang = (np.degrees(np.arctan2(yy - cy, xx - cx)) + 360) % 360
    dist = np.hypot(xx - cx, yy - cy)
    field = np.zeros_like(dist)
    for deg, width, power, length, cycles, phase in BEAMS:
        sway = BEAM_SWAY * np.sin(tau * (p + phase))
        breathe = (1 - BEAM_BREATHE) + BEAM_BREATHE * (0.5 + 0.5 * np.sin(tau * (cycles * p + phase)))
        dd = (ang - (deg + sway) + 180) % 360 - 180
        field = np.maximum(field, power * breathe * np.exp(-(dd / width) ** 2) * np.clip(1 - dist / (length * A), 0, 1))
    return field * np.clip((dist - r + 1) / (5.0 * A), 0, 1)

def make_palette(stack, art, m, k):
    """One fixed palette: k-means on the picture and the effects' shades, started from a median
    cut. Small colourful things (moss, grass, rope, the sail, the cloud rims) are counted several
    times over, or the big sea and sand would take nearly every colour and they'd go dull."""
    from scipy.cluster.vq import kmeans2
    H, W = art.shape[:2]
    R, G, B = art[..., 0], art[..., 1], art[..., 2]
    sat = art.max(-1) - art.min(-1)
    colourful = (sat > 110) | ((G > 0.8 * R) & (G > B + 30))          # moss, grass, gold
    pts = [stack.reshape(-1, 3)[::3].astype(float)]
    for mask, times in ((colourful, 14), (m["tufts"], 6), (m["sail"], 8), (m["rim"], 6)):
        if mask.any():
            pts += [art[mask]] * times
    X = np.vstack(pts)
    init = Image.fromarray(stack).quantize(colors=k, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    c0 = np.array(init.getpalette()[:3 * k], float).reshape(-1, 3)
    c0 = c0[:k] if len(c0) >= k else np.vstack([c0, c0[:k - len(c0)]])
    rng = np.random.default_rng(3)
    sel = X[rng.choice(len(X), size=min(len(X), 300000), replace=False)]
    cent, _ = kmeans2(sel, c0, iter=12, minit='matrix', seed=4)
    pal = [int(round(v)) for v in cent.clip(0, 255).reshape(-1)]
    pal_img = Image.new('P', (1, 1)); pal_img.putpalette(pal + [0] * (768 - len(pal)))
    return pal_img, pal


def breaker_roll(art, water, S, A, s, m=None):
    """Big painted breakers (stormlit): each one is lifted out whole - its white crest and the curl just
    under it - and rolls in toward the beach, fading in behind and fading out as it reaches the shore, with
    a second copy half a cycle behind, so new breakers keep coming. The sea under them is filled from the
    calm water beside them. Returns (calm sea, breaker colours, breaker alpha)."""
    lum = art @ np.array([0.299, 0.587, 0.114])
    # the sea with its foam: the paler crests fail the sea's colour test, so close the gaps they leave
    water = ndi.binary_closing(water, np.ones((max(3, int(7 / s)) | 1, max(3, int(11 / s)) | 1))) | water
    if m is not None:
        water &= ~m['plank']
    Lloc = ndi.uniform_filter(lum, (3, max(3, int(31 / s))))
    foam = water & (lum > Lloc + 9) & (lum > 80) & (art[..., 2] > art[..., 0] * 0.8)
    foam = ndi.binary_opening(foam | ndi.binary_dilation(foam, np.ones((1, 3))) & foam, np.ones((1, 1)))
    # the crest, softly, and the curl face under it (2 px above, 4 below in the picture's px)
    soft = np.clip((lum - Lloc - 4) / 22.0, 0, 1) * water
    band = ndi.binary_dilation(foam, np.ones((max(1, int(round(2 / s))) * 2 + 1, 3))) | \
        ndi.binary_dilation(foam, np.ones((max(1, int(round(4 / s))) * 2 + 1, 1)), origin=(-max(1, int(round(4 / s))) // 2, 0))
    band &= water
    alpha = np.maximum(ndi.gaussian_filter(band.astype(float), 0.6) * band, soft * band)
    alpha = np.clip(np.maximum(alpha, foam * 1.0), 0, 1)
    # the calm sea: the water round each breaker, spread along the rows (normalized convolution)
    keep = water & ~band
    sig = (1.5 / s, 9.0 / s)
    wsum = ndi.gaussian_filter(keep.astype(float), sig)
    calm = np.stack([ndi.gaussian_filter(art[..., c] * keep, sig) for c in range(3)], -1) / np.maximum(wsum, 1e-6)[..., None]
    calm = np.where(keep[..., None], art, np.where((wsum > 1e-3)[..., None], calm, art))
    return calm, art.copy(), alpha, water


def render(scene, src, out, smooth):
    S = SCENES[scene]
    art, s, A = load(src, smooth)
    H, W = art.shape[:2]
    m = build_masks(art, S, s, A)
    art = depth_pass(art, m, S, A)
    tau = 2 * np.pi
    yy, xx = np.mgrid[0:H, 0:W]
    hz = m['hz']
    lum0 = lum_of(art)
    rng = np.random.default_rng(11)
    light_col = C(S['light_col'])
    glint_c = C(S.get('glint_col', (255, 250, 236)))
    lx, ly = S['light'][0] / s, S['light'][1] / s
    near_light = np.exp(-np.hypot(xx - lx, yy - ly) / (160.0 * A))
    water, refl = m['water'], m['refl'] | m['sheen']
    open_px = ~m['plank']

    # --- the beach line across the whole width (behind the wreck too), for sea depth
    shore = m['shore']
    xs_ok = np.where(shore > 0)[0]
    if len(xs_ok):
        shore_full = np.interp(np.arange(W), xs_ok, shore[xs_ok].astype(float))
    else:                                   # a pond: its far shore is its top, its near shore its bottom
        wc = np.where(water.any(0))[0]
        bot = np.array([np.where(water[:, x])[0].max() + 1 if water[:, x].any() else H for x in range(W)], float)
        shore_full = np.interp(np.arange(W), wc, bot[wc]) if len(wc) else np.full(W, float(H))
    shore_full = ndi.uniform_filter1d(shore_full, 9 * A, mode='nearest')
    sea_depth = np.clip((yy - hz) / np.maximum(shore_full[None, :] - hz, 1), 0, 1)

    # --- surf: per column, the stretch that may slide, weighted round the line
    seg = m['surf_seg']
    in_seg = np.zeros((H, W), bool)
    rel = np.zeros((H, W))
    for x in np.where(seg[:, 0] >= 0)[0]:
        in_seg[seg[x, 0]:seg[x, 1] + 1, x] = True
    if S.get('seg_open_only', True):
        in_seg &= ~m['plank']                 # (the strip is water and sand only: never rock at a cliff's foot)
    rel = yy - np.where(shore > 0, shore, H)[None, :]
    surf_w = np.where(rel < 0, np.clip(1 + rel / (9.0 * A), 0, 1), np.clip(1 - rel / (6.0 * A), 0, 1))
    surf_w *= in_seg & open_px
    sand_seg = in_seg & (rel >= 0) & ~m['shore_hidden'][None, :]
    lap_zone = None
    if S.get('shore_lap', S.get('ship') is not None):
        lap_zone = in_seg & (rel >= -3 * A) & (rel <= A - 1) & open_px & ~m['wood'] & ~m['rock']
    lr = m['lr'][None, :]

    # ripple strength: calmer where the waves roll (so they stay whole), full by and behind the
    # wreck (no rolling waves there), blended over 20 px
    shipm = boxm(H, W, S['ship'], s).astype(float)
    shipm = np.clip(ndi.gaussian_filter(shipm, 10 * A) * 2, 0, 1)
    rip_k = S.get('ripple', 1.0) + (1.0 - S.get('ripple', 1.0)) * shipm
    waves = None
    br = None
    if S.get('breaker_roll'):
        br = breaker_roll(art, water, S, A, s, m)
    if S.get('crests'):
        w_lifted, w_calm, waves = rolling_waves(art, m, S, A, np.random.default_rng(7), water, lum0, shore_full)

    # --- the reflection's streaks: horizontal runs, each with its own phase (long runs cut in pieces)
    streak_ph = np.zeros((H, W))
    rng_s = np.random.default_rng(23)          # (its own random numbers: the rims keep their timing)
    run_id = 0
    for y in np.where(refl.any(1))[0]:
        x = 0
        while x < W:
            if refl[y, x]:
                x2 = x
                while x2 + 1 < W and refl[y, x2 + 1] and x2 + 1 - x < 14 * A:
                    x2 += 1
                streak_ph[y, x:x2 + 1] = rng_s.random()
                x = x2 + 1
            else:
                x += 1

    # --- clouds: moving pieces, the sky behind them, their rims
    plate = sky_plate(art, m['clouds'], m['sky_zone'])
    lab, n = ndi.label(m['clouds'], structure=np.ones((3, 3)))
    comps = []
    for i in range(1, n + 1):
        ys, xs = np.where(lab == i)
        amp = S.get('cloud_drift', CLOUD_DRIFT) * A * (1.15 - 0.5 * ys.mean() / float(hz))     # higher clouds look closer
        comps.append((ys, xs, amp, 0.15 * xs.mean() / W + 0.05 * np.sin(i * 2.3)))
    # each cloud's rim, and the glint that runs along it (each cloud its own phase)
    rim_parts = []
    lab_mv = lab
    # one glint per stretch of rim (each connected run of rim pixels), each on its own timing,
    # so the top and bottom edges of a cloud never light up together as a band
    lab_rim, n_rim = ndi.label(m['rim'], structure=np.ones((3, 3)))
    for rid in range(1, n_rim + 1):
        rys, rxs = np.where(lab_rim == rid)
        mv = np.bincount(lab_mv[rys, rxs], minlength=n + 1)      # the moving piece that carries it
        mv[0] = 0
        piece = int(mv.argmax()) if mv.max() > 0 else 0
        w_ = RIM_WIDTH * A
        x0, x1 = rxs.min() - 3 * w_, rxs.max() + 3 * w_
        rim_parts.append(dict(ys=rys, xs=rxs, piece=piece, x0=x0, x1=x1, w=w_,
                              ph=rng.random(), ph2=rng.random(), nl=near_light[rys, rxs]))

    # --- sail and grass weights
    top = np.full(W, H)
    ys_, xs_ = np.where(m['sail'])
    for x in np.unique(xs_):
        top[x] = ys_[xs_ == x].min()
    hang = np.clip((yy - top[None, :]) / (18.0 * A), 0, 1) ** 1.1
    sail_w = soft(m['sail'], 0.8 * A) * hang * SAIL_SWAY * A
    grass_w = np.zeros((H, W))
    lab_t, n_t = ndi.label(ndi.binary_dilation(m['tufts'], iterations=1), structure=np.ones((3, 3)))
    for i in range(1, n_t + 1):
        comp = lab_t == i
        ys, xs = np.where(comp)
        y_top, y_bot = ys.min(), ys.max()
        amp = GRASS_SWAY + (GRASS_FRONT - GRASS_SWAY) * np.clip((y_bot / A - 125) / 60.0, 0, 1)
        hw = np.clip((y_bot + 1 - yy) / max(y_bot + 1 - y_top, 3), 0, 1) ** 1.2
        grass_w = np.maximum(grass_w, comp * hw * amp * A)
    st = soft(m['tufts'], 0.9 * A)
    grass_w *= st / max(st.max(), 1e-6) * 1.6
    grass_w = np.minimum(grass_w, GRASS_FRONT * A)
    # hanging ivy: each strand sways from its own top; the lower it hangs, the more
    vine_w = np.zeros((H, W))
    if m['vines'].any():
        for x in np.unique(np.where(m['vines'])[1]):
            col = m['vines'][:, x]
            y = 0
            while y < H:
                if col[y]:
                    y2 = y
                    while y2 + 1 < H and col[y2 + 1]:
                        y2 += 1
                    vine_w[y:y2 + 1, x] = np.clip((np.arange(y, y2 + 1) - y + 1) / (10.0 * A), 0, 1) ** 1.2
                    y = y2 + 1
                else:
                    y += 1
        near_v = ndi.binary_dilation(m['vines'], iterations=1)
        vine_w = np.maximum(vine_w, ndi.grey_dilation(vine_w, size=(1, 3)) * near_v) * VINE_SWAY * A
    # trees, bushes, willows: each sways by its own amount and pace (canopy tops move most; willow
    # strands hang, so they move most at their tips); a margin of sky round each moves with it
    tree_parts = []
    sky_like = np.zeros((H, W), bool)
    sky_like[:hz] = np.linalg.norm(art[:hz] - m['sky_ref'][:hz], axis=-1) < 16
    tree_any = np.zeros((H, W), bool)
    for i_t, tr in enumerate(S.get('trees', [])):
        pm = poly_mask([tr['poly']], H, W, s)
        fol = pm & ~sky_like & ~m['rock'] & ~m['wood']
        if tr.get('test') == 'green':       # leaves only (not the trunk): greener than red
            fol &= art[..., 1] > art[..., 0] + 8
        elif tr.get('test') == 'leafy':     # autumn leaves and grass: warm and saturated, not trunk-brown
            fol &= (art.max(-1) - art.min(-1) > 70) & (lum0 > 70)
        amp = tr.get('amp', 1.3) * A
        if tr.get('hang'):
            hw_ = np.zeros((H, W))
            for x in np.unique(np.where(fol)[1]):
                ys = np.where(fol[:, x])[0]
                hw_[ys, x] = np.clip((ys - ys.min() + 1) / (tr.get('hang_len', 30) * A / 1.0), 0, 1) ** 1.1
        else:
            base, top_ = tr['base'] / s, tr.get('top', tr['poly_top'] if 'poly_top' in tr else None)
            ys_f = np.where(fol.any(1))[0]
            top_ = ys_f.min() if len(ys_f) else 0
            hw_ = np.clip((base - yy) / max(base - top_, 3), 0, 1) ** tr.get('power', 1.4)
        w_ = soft(fol, 1.0 * A) * hw_ * amp
        reach = int(np.ceil(amp)) + A
        zone_t = ndi.binary_dilation(fol, iterations=reach) & (ndi.binary_dilation(pm, iterations=reach))
        zone_t &= ~m['rock'] & ~m['wood']
        tree_parts.append(dict(w=w_ * zone_t, cyc=tr.get('cyc', 5), ph=tr.get('ph', 0.13 * i_t),
                               zone=zone_t, fol=fol))
        tree_any |= fol
    m['trees'] = tree_any
    # leaf rustle: little clusters of leaves catch the light and flicker (each its own time)
    rustle = None
    if S.get('rustle') and tree_any.any():
        rr = np.random.default_rng(43)
        nz = ndi.gaussian_filter(rr.random((H, W)), 1.2 * A)
        cl_ = tree_any & (nz > np.percentile(nz[tree_any], 92)) & (lum0 > np.percentile(lum0[tree_any], 40))
        lab_r2, n_r2 = ndi.label(cl_)
        rph = rr.random(n_r2 + 1)
        rustle = (cl_, lab_r2, rph, C(S.get('leaf_light', (255, 214, 140))))
    # twinkling painted points of light
    tw_lab, tw_n = ndi.label(m['twinkle'], structure=np.ones((3, 3)))
    rr2 = np.random.default_rng(47)
    tw_ph = rr2.random(tw_n + 1); tw_cyc = rr2.integers(1, 4, tw_n + 1)
    # snow sparkles: fixed points on the snow that flash now and then
    sparkles = []
    if m['snow'].any():
        rr3 = np.random.default_rng(53)
        ys_s2, xs_s2 = np.where(m['snow'])
        for _ in range(S.get('snow_sparkles', 30)):
            j_ = int(rr3.integers(0, len(ys_s2)))
            sparkles.append((xs_s2[j_], ys_s2[j_], int(rr3.integers(1, 4)), rr3.random()))
    movers = m['sail'] | ndi.binary_dilation(m['tufts'], iterations=A) | ndi.binary_dilation(m['vines'], iterations=1)
    rigid = (m['wood'] | m['rock']) & ~m['sail'] & ~m['tufts'] & ~m['vines'] & ~tree_any & ~m['lava'] & ~m['smoke']

    # --- the sun (old map 9): one solid colour, a breathing glow, heat shimmer, shafts of light
    sun = None
    if S.get('sun'):
        scx, scy, sr0 = S['sun'][0] / s, S['sun'][1] / s, S['sun'][2] / s
        near_s = np.hypot(xx - scx, yy - scy) < sr0 + 3 * A
        sun = near_s & (lum0 > S.get('sun_min_l', 200)) & (yy < hz) & (art[..., 0] > 230)
        lab_s, n_s = ndi.label(sun)
        if n_s:
            sun = ndi.binary_fill_holes(lab_s == (np.argmax(ndi.sum(sun, lab_s, range(1, n_s + 1))) + 1))
        ys_s, xs_s = np.where(sun)
        scx = xs_s.mean(); sr = (xs_s.max() - xs_s.min() + 1) / 2.0; scy = ys_s.min() - 0.5 + sr
        sun_col = SUN_COLOR if S.get('sun_color', 'old') == 'old' else tuple(np.percentile(art[sun], 70, axis=0))
        art[sun] = sun_col                  # one solid colour (here: the painted sun's own)
        sdist = np.hypot(xx - scx, yy - scy)
        warm_sky = (yy < hz) & ~sun & ~(m['wood'] | m['sail'] | m['rock'])
        glow_base = S.get('sun_glow_k', 1.0) * 0.40 * np.exp(-np.maximum(sdist - sr, 0) / (3.5 * A)) + S.get('sun_glow_k', 1.0) * 0.12 * np.exp(-np.maximum(sdist - sr, 0) / (14.0 * A))
        glow_zone = warm_sky & (sdist < sr + 40 * A)
        sun_glow = C((255, 206, 170))
        shimmer_zone = (sun | glow_zone) & (np.abs(xx - scx) <= sr + 6 * A) & (yy >= scy - sr - A) & (yy < hz)
        if S.get('sun_shimmer_tight'):      # only the sun wavers: the disc and a thin ring of warm sky, never the hills in front
            warm_px = (art[..., 1] > art[..., 2] + 10) & ~(m['wood'] | m['sail'] | m['rock'])
            shimmer_zone = ndi.binary_dilation(sun, iterations=2 * A) & (sun | warm_px)
            # (and the rays don't play over the purple hills low in front of it either)
            hills_low = (yy > scy - sr) & (art[..., 2] > art[..., 1] + 5)
            hills_low = ndi.binary_opening(hills_low, iterations=1)
        beam_zone = (yy < hz) & ~sun & ~(m['wood'] | m['sail'] | m['rock'])
        if S.get('sun_shimmer_tight'):
            beam_zone &= ~hills_low
        rigid |= sun
    # --- the moon: its glow breathes once a loop
    moon = None
    if S.get('moon'):
        mcx, mcy, mr = S['moon'][0] / s, S['moon'][1] / s, S['moon'][2] / s
        mdist = np.hypot(xx - mcx, yy - mcy)
        moon_ring = (mdist > mr) & (mdist < mr + 14 * A) & (yy < hz) & ~m['cloud_all']
        moon_k = np.exp(-(mdist - mr) / (5.0 * A)) * moon_ring
        moon = True
    # --- stars (old map 7): small twinkles on open sky, hidden by passing clouds
    stars = []
    if S.get('stars'):
        rng_st = np.random.default_rng(31)
        open_sky = m['sky_zone'] & ~ndi.binary_dilation(m['cloud_all'], iterations=2 * A) & (yy < S.get('star_ymax', 80) / s) & ~m['disc']
        if moon:
            open_sky &= mdist > mr + 16 * A
        tries = 0
        while len(stars) < S['stars'] and tries < 5000:
            tries += 1
            sx_, sy_ = int(rng_st.integers(A, W - A)), int(rng_st.integers(A, H))
            if open_sky[sy_, sx_]:
                stars.append((sx_, sy_, int(rng_st.integers(2, 6)), rng_st.random(), rng_st.random() < 0.25))
        star_c = C((236, 236, 255))
    # --- sun glints on a bright sea (old map 8): fixed spots that sparkle
    glints = []
    if S.get('glints'):
        rng_g = np.random.default_rng(37)
        for _ in range(S['glints']):
            for _try in range(80):
                gx, gy = int(rng_g.integers(0, W)), int(rng_g.integers(hz + 1, hz + 30 * A))
                if water[gy, gx] and sea_depth[gy, gx] < 0.85 and not m['shore_hidden'][gx]:
                    glints.append((gx, gy, int(rng_g.integers(2, 5)), rng_g.random()))
                    break
    # --- a waterfall: each column of falling water scrolls down through itself
    fall_cols = []
    if m['fall'].any():
        for x in np.unique(np.where(m['fall'])[1]):
            ys = np.where(m['fall'][:, x])[0]
            if len(ys) >= 4:
                fall_cols.append((x, ys))
        fall_hash = np.random.default_rng(41).random(W)

    # --- lava: per zone, how far along / across its flow each pixel is
    lava_parts = []
    lava_m = m['lava']; lava_any = lava_m.any()
    lava_along = np.zeros((H, W)); lava_ph = np.zeros((H, W))
    for i_z, z in enumerate(m['lava_zones']):
        zm = z['mask']
        if not zm.any():
            continue
        kind = z.get('kind', 'river')
        part = dict(kind=kind, mask=zm)
        if kind == 'pool':
            cx_, cy_ = z['centre'][0] / s, z['centre'][1] / s
            dxp, dyp = xx - cx_, (yy - cy_) * z.get('squash', 2.5)        # pools are seen flattened
            rr = np.hypot(dxp, dyp) + 1e-6
            part.update(ang=np.arctan2(dyp, dxp), rr=rr, n=z.get('arms', 3),
                        tx=-dyp / rr * z.get('spin', 1), ty=dxp / rr / z.get('squash', 2.5) * z.get('spin', 1))
            lava_along[zm] = (np.arctan2(dyp, dxp) * rr / 3.0)[zm]
        else:
            d_ = np.array(z.get('dir', (-1.0, 0.0)) if kind == 'river' else z.get('dir', (0.0, 1.0)), float)
            d_ /= np.linalg.norm(d_)
            along = xx * d_[0] + yy * d_[1]; across = -xx * d_[1] + yy * d_[0]
            part.update(dx=d_[0], dy=d_[1], along=along, across=across,
                        wl=z.get('wl', 14 if kind == 'river' else 8), cyc=z.get('cyc', LAVA_CYCLES if kind == 'river' else 2 * LAVA_CYCLES))
            lava_along[zm] = along[zm] * (1.0 if kind == 'river' else 1.8)
        lava_ph[zm] = 0.9 * i_z
        lava_parts.append(part)
    # smoke moves most in its middle and not at all at its box's edges (no seam against the sky)
    smoke_w = np.clip(ndi.distance_transform_edt(m['smoke']) / (8.0 * A), 0, 1) if m['smoke'].any() else None
    lava2 = None
    if lava_any and S.get('lava_style', 2) == 2:     # the rebuild of old map 2's lava (lava640.py)
        from lava640 import Lava, GridLava
        if smooth:
            lava2 = Lava(art, m, S, s, A, np.random.default_rng(61))
        else:
            # the grid version's lava is worked out at full detail and brought down to the grid each frame
            # (worked on the grid itself, the swirl's thin rings turned to mush)
            fa, fs, fA = load(src, True)
            fm = build_masks(fa, S, fs, fA)
            fart = depth_pass(fa, fm, S, fA)
            lava2 = GridLava(Lava(fart, fm, S, fs, fA, np.random.default_rng(61)), fart)
    lava_hot = C(S.get('lava_hot', (255, 236, 150)))
    lava_warm = C(S.get('lava_warm', (255, 120, 60)))

    # --- palette: the picture plus the shades the effects make
    variants = [art, art]
    if lava_any:
        v = art.copy(); v[lava_m] += (lava_hot - v[lava_m]) * LAVA_PULSE; variants += [v] * 2
        v = art.copy(); gz_ = m['lava_glow'] > 0.01; v[gz_] += (lava_warm - v[gz_]) * (m['lava_glow'][gz_] * LAVA_GLOW)[:, None]; variants.append(v)
        lp = art[lava_m]; nl = (len(lp) // W) * W
        if nl:
            variants += [lp[:nl].reshape(-1, W, 3)] * 3
        if lava2 is not None:                   # the lava as it will be drawn, a few moments of it
            for q in (0.0, 0.13, 0.31, 0.52, 0.77):
                fq = lava2.draw(art.copy(), q)
                variants += [fq[lava_m][:nl].reshape(-1, W, 3)] * 2 if nl else []
    if sun is not None:
        for lv in np.arange(0.05, 0.56, 0.05):
            v = art.copy(); v[glow_zone] += (sun_glow - v[glow_zone]) * lv; variants.append(v[:hz])
        if S.get('beams'):
            bf = np.max([beam_field(xx, yy, scx, scy, sr, q, A) for q in np.linspace(0, 1, 12, endpoint=False)], axis=0)
            for lv in (0.4, 0.75, 1.0):
                v = art + (C(BEAM_LIGHT) - art) * (BEAM_STRENGTH * bf * beam_zone * lv)[..., None]; variants.append(v[:hz])
    if moon:
        v = art.copy(); v[moon_ring] += (light_col - v[moon_ring]) * (0.12 * moon_k[moon_ring])[:, None]; variants.append(v[:hz])
    if glints or stars:
        v = art.copy(); v[water] += (glint_c - v[water]) * 0.6; variants.append(v[hz:])
    if fall_cols:
        v = art.copy(); v[m['fall'] | m['splash']] *= 0.9; variants.append(v)
    if m['hills'].any():
        v = art.copy(); v[m['hills']] *= (1 + HILL_WIND); variants.append(v.clip(0, 255))
    if rustle is not None:
        v = art.copy(); v[rustle[0]] += (rustle[3] - v[rustle[0]]) * 0.25; variants += [v] * 2
    if m['twinkle'].any():
        v = art.copy(); tb_ = m['twinkle_bg']; v[m['twinkle']] = tb_[m['twinkle']] * 0.6 + art[m['twinkle']] * 0.4; variants.append(v)
    if sparkles:
        v = art.copy(); v[m['snow']] += (glint_c - v[m['snow']]) * 0.6; variants.append(v)
    if tree_any.any():                    # the foliage gets a fair share of the palette
        fol_px = art[tree_any]
        nf = (len(fol_px) // W) * W
        if nf:
            variants += [fol_px[:nf].reshape(-1, W, 3)] * 2
    rim_col = C(S['rim_col']) if S.get('rim_col') else light_col
    rg_, rt_ = S.get('rim_glow', RIM_GLOW), S.get('rim_glint', RIM_GLINT)
    v = art.copy(); rm = m['rim']; v[rm] += (rim_col - v[rm]) * min(1.0, rg_ + rt_); variants += [v[:hz]] * 2
    v = art.copy(); v[rm] += (rim_col - v[rm]) * rg_; variants += [v[:hz]] * (3 if S.get('rim_line') else 1)
    if S.get('rim_glint_col'):
        v = art.copy(); v[rm] = C(S['rim_glint_col']); variants += [v[:hz]] * 2
    v = art.copy(); v[water] += (glint_c - v[water]) * 0.3; variants.append(v)
    v = art.copy(); v[refl] += (glint_c - v[refl]) * S.get('refl_glitter', 0.0); variants.append(v)
    v = art.copy(); v[sand_seg] *= 0.9; variants.append(v)
    band = art[hz:int(shore_full.max()) + 2 * A]
    variants += [np.tile(band, (max(1, H // max(band.shape[0], 1)), 1, 1))] * (4 if S.get('crests') else 2)
    stack = np.vstack(variants).round().clip(0, 255).astype(np.uint8)
    if PALETTE_FROM:                       # a tweak: keep the previous GIF's colours, so the diff shows only what changed
        pg = Image.open(PALETTE_FROM)
        pal = pg.getpalette()[:3 * COLORS]
        pal_img = Image.new('P', (1, 1)); pal_img.putpalette(pal + [0] * (768 - len(pal)))
    else:
        pal_img, pal = make_palette(stack, art, m, COLORS)
    m['pal'] = pal

    frames = []
    for t in range(FRAMES):
        p = t / FRAMES
        f = art.copy()
        if br is not None:                       # the big breakers roll in to the beach and fade (stormlit)
            calm, bcol, bal, bwat = br
            D_, C_ = S['breaker_roll']           # travel (picture px), roll-ins per loop
            D_ = D_ / s
            f = np.where(bwat[..., None], calm, f)
            phx = 0.18 * np.sin(xx[0] / (85.0 / s) + 0.7) + 0.08 * np.sin(xx[0] / (37.0 / s) + 2.1)
            for k_ in (0.0,):                    # one copy: it fades in, rolls in, fades out; a calm gap, the next
                q_ = np.mod(C_ * p + k_ + phx, 1.0)                    # (per column, so the line isn't ruler-straight)
                env = smooth01(q_ / 0.25) * smooth01((0.88 - q_) / 0.3)
                dy_ = D_ * (q_ - 0.45)                                 # from behind where it was painted, on past it
                dyi = np.floor(dy_).astype(int); fr_ = dy_ - dyi
                for dd, wgt in ((0, 1 - fr_), (1, fr_)):
                    sy_ = np.clip(yy - (dyi + dd)[None, :], 0, H - 1)
                    a_ = bal[sy_, xx] * (env * wgt)[None, :] * bwat
                    f += (bcol[sy_, xx] - f) * a_[..., None]

        dxs = [0] * (n + 1)
        if S.get('sky_slide'):
            # a sky that is all cloud (a storm): the whole sky slides as one layer, so nothing tears
            dxg = int(np.rint(S.get('cloud_drift', CLOUD_DRIFT) * A * np.sin(tau * p)))
            if dxg:
                sxs_ = np.clip(xx - dxg, 0, W - 1)
                okk = m['sky_zone'] & m['sky_zone'][yy, sxs_]
                f = shift_take(f, yy, sxs_, okk)
            dxs = [dxg] * (n + 1)
            comps_now = []
        else:
            comps_now = comps
            # clouds drift over the sky behind them
            f[m['clouds']] = plate[m['clouds']]
        for i, (ys, xs, amp, ph) in enumerate(comps_now, start=1):
            dx = int(np.rint(amp * np.sin(tau * (p + ph))))
            dxs[i] = dx
            nx = xs + dx
            ok = (nx >= 0) & (nx < W)
            ok[ok] &= m['sky_zone'][ys[ok], nx[ok]]
            f[ys[ok], nx[ok]] = art[ys[ok], xs[ok]]
            for gap in ((range(W + dx, W) if dx < 0 else ()), (range(0, dx) if dx > 0 else ())):
                edge = W - 1 if dx < 0 else 0
                rows = ys[xs == edge]
                for gx in gap:
                    keep = m['sky_zone'][rows, gx]
                    f[rows[keep], gx] = art[rows[keep], edge]
        # the gold rims: a little steady warmth, and a glint sliding along each rim
        for r in rim_parts:
            c = r['x0'] + (r['x1'] - r['x0']) * ((RIM_CYCLES * p + r['ph']) % 1.0)
            k = S.get('rim_glow', RIM_GLOW) * (0.75 + 0.25 * np.sin(tau * (2 * p + r['ph2']))) \
                + S.get('rim_glint', RIM_GLINT) * np.exp(-((r['xs'] - c) / r['w']) ** 2)
            k = k * (1.0 if S.get('rim_line') else (0.4 + 0.6 * r['nl'])) * S.get('rim_k', 1.0)
            dx = dxs[r['piece']] if (r['piece'] or S.get('sky_slide')) else 0
            tx = r['xs'] + dx
            ok = (tx >= 0) & (tx < W)
            ty, tx, k = r['ys'][ok], tx[ok], k[ok]
            if S.get('rim_glint_col'):        # the line, shimmering, plus a brighter glint of its own colour sliding along it
                xo_, yo_ = r['xs'][ok], r['ys'][ok]
                kg = S.get('rim_glow', RIM_GLOW) * (0.85 + 0.15 * np.sin(tau * (2 * p + r['ph2'])))
                kt = S.get('rim_glint', RIM_GLINT) * np.exp(-((xo_ - c) / r['w']) ** 2)
                sh_ = S.get('rim_shimmer', 0.0)
                if sh_:
                    # waves of light running along the line (3 a loop), and single pixels twinkling up to the glint colour
                    band = 0.5 + 0.5 * np.sin(tau * (xo_ / (18.0 / s) - 3 * p + r['ph2']))
                    kg = kg * (1 - 0.4 * sh_ + 0.4 * sh_ * band)
                    tph = np.mod(np.sin(xo_ * 12.9898 + yo_ * 78.233) * 43758.5453, 1.0)
                    tw = np.clip((np.sin(tau * (6 * p + tph)) - 0.55) / 0.45, 0, 1) ** 1.5
                    kt = np.maximum(kt, sh_ * (0.35 * band + 0.75 * tw))
                f[ty, tx] += (rim_col - f[ty, tx]) * np.clip(np.broadcast_to(kg, (len(ty),)), 0, 1)[:, None]
                f[ty, tx] += (C(S['rim_glint_col']) - f[ty, tx]) * np.clip(kt, 0, 1)[:, None]
            else:
                f[ty, tx] += (rim_col - f[ty, tx]) * np.clip(k, 0, 1)[:, None]

        # stars twinkle, hidden by passing clouds
        for sx_, sy_, c_, ph_, big in stars:
            if m['clouds'][sy_, sx_]:
                continue
            b_ = 0.5 + 0.5 * np.sin(tau * (c_ * p + ph_))
            if b_ > 0.4:
                f[sy_, sx_] += (star_c - f[sy_, sx_]) * (0.25 + 0.6 * (b_ - 0.4) / 0.6)
                if big and b_ > 0.92 and A == 1:
                    for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        f[sy_ + ddy, sx_ + ddx] += (star_c - f[sy_ + ddy, sx_ + ddx]) * 0.25
        # the moon's glow: one slow breath per loop
        if moon:
            br = 0.06 * (0.5 + 0.5 * np.sin(tau * p))
            f[moon_ring] += (light_col - f[moon_ring]) * (br * moon_k[moon_ring])[:, None]
        # the sun: shafts, a breathing glow, then the heat ripple
        if sun is not None:
            if S.get('beams'):
                beam = BEAM_STRENGTH * beam_field(xx, yy, scx, scy, sr, p, A) * beam_zone
                f += (C(BEAM_LIGHT) - f) * beam[..., None]
            pulse = 0.5 + 0.5 * np.sin(tau * 5 * p)
            kg = glow_base * (0.85 + 0.15 * pulse)
            f[glow_zone] += (sun_glow - f[glow_zone]) * kg[glow_zone, None]
            amp_s = np.clip((yy - (scy - sr)) / (2 * sr), 0.35, 1.0) * 2.2 * A
            sdx = np.rint(amp_s * np.sin(tau * (yy / (4.0 * A) - 12 * p))).astype(int)
            sxs_ = np.clip(xx - sdx, 0, W - 1)
            f = shift_take(f, yy, sxs_, shimmer_zone & (sdx != 0) & shimmer_zone[yy, sxs_])

        # lava: its own pixels churn and flow (a pattern of small shifts that travels downstream, so the
        # bright streaks visibly move along), brighter pulses run down it, and the rock beside it glows
        if lava2 is not None:
            f = lava2.draw(f, p)
        for z in (lava_parts if lava2 is None else []):
            zm = z['mask']
            if z['kind'] == 'crack':
                continue
            if z['kind'] == 'pool':
                # around the centre: shifts along the circle, travelling round it
                ph = tau * (z['n'] * z['ang'] / tau - LAVA_CYCLES * p) + z['rr'] / (6.0 * A)
                amp = LAVA_AMP * A * (0.6 + 0.4 * np.sin(z['rr'] / (9.0 * A) - tau * 2 * p))
                du = amp * np.sin(ph)
                sxf = xx - du * z['tx']; syf = yy - du * z['ty']
            else:
                # along the flow: waves travelling downstream (whole cycles per loop: seamless)
                ph = tau * (z['along'] / (z['wl'] * A) - z['cyc'] * p) + 0.7 * np.sin(z['across'] / (5.0 * A))
                ph2 = tau * (z['along'] / (z['wl'] * 0.45 * A) - 2 * z['cyc'] * p) + z['across'] / (3.0 * A)
                du = LAVA_AMP * A * (np.sin(ph) + 0.5 * np.sin(ph2)) / 1.5
                sxf = xx - du * z['dx']; syf = yy - du * z['dy']
            sxi = np.clip(np.rint(sxf).astype(int), 0, W - 1); syi = np.clip(np.rint(syf).astype(int), 0, H - 1)
            take = zm & zm[syi, sxi] & ((sxi != xx) | (syi != yy))
            f = shift_take(f, syi, sxi, take)
        # brighter pulses running down the lava, and the glow on the rock breathing with it
        if lava_any:
            if lava2 is None:
                pulse = 0.5 + 0.5 * np.sin(tau * (lava_along / (LAVA_PULSE_WL * A) - LAVA_PULSE_CYCLES * p) + lava_ph)
                kl = np.clip((pulse - 0.55) / 0.45, 0, 1) * LAVA_PULSE
                f[lava_m] += (lava_hot - f[lava_m]) * kl[lava_m][:, None]
                breathe = 0.6 + 0.4 * np.sin(tau * 2 * p)
            else:                               # the rock flickers in the lava's light
                breathe = 0.65 + 0.2 * np.sin(tau * 7 * p + xx / (31.0 * A)) + 0.15 * np.sin(tau * 11 * p + yy / (17.0 * A) + 1.3)
            kg = m['lava_glow'] * LAVA_GLOW * breathe
            gz = kg > 0.01
            f[gz] += (lava_warm - f[gz]) * kg[gz][:, None]
        # smoke drifts up and sways
        if m['smoke'].any():
            sdy = np.rint(SMOKE_RISE * A * smoke_w * np.sin(tau * (yy / (18.0 * A) + 2 * p) + xx / (25.0 * A))).astype(int)
            sdx = np.rint(SMOKE_SWAY * A * smoke_w * np.sin(tau * (yy / (30.0 * A) - p))).astype(int)
            syi = np.clip(yy - sdy, 0, H - 1); sxi = np.clip(xx - sdx, 0, W - 1)
            f = shift_take(f, syi, sxi, m['smoke'] & m['smoke'][syi, sxi] & ((sdy != 0) | (sdx != 0)))

        # painted stars and fireflies twinkle: each fades toward the sky / ground behind it and back
        if tw_n:
            tb_ = m['twinkle_bg']
            kt = 0.5 + 0.5 * np.sin(tau * (tw_cyc * p + tw_ph))
            kpx = np.clip(1.15 * kt[tw_lab], 0, 1)[m['twinkle']] * 0.75 + 0.25
            f[m['twinkle']] = tb_[m['twinkle']] + (f[m['twinkle']] - tb_[m['twinkle']]) * kpx[:, None]
        for sx_, sy_, c_, ph_ in sparkles:
            b_ = 0.5 + 0.5 * np.sin(tau * (c_ * p + ph_))
            if b_ > 0.85:
                f[sy_, sx_] += (glint_c - f[sy_, sx_]) * (0.4 + 0.6 * (b_ - 0.85) / 0.15)
        # leaves catching the light
        if rustle is not None:
            cl_, lab_r2, rph, lcol = rustle
            kr = np.clip(np.sin(tau * (2 * p + rph)), 0, 1) ** 2 * 0.22
            kk_ = kr[lab_r2][cl_]
            f[cl_] += (lcol - f[cl_]) * kk_[:, None]

        # the painted waves roll in toward the beach, handing over from one to the next
        if waves:
            f = waves(f, p)

        # sea: slow sideways ripples, bigger near the beach
        wavelen = (1.5 + 5.0 * sea_depth) * A
        if S.get('far_flick'):             # the far rows always flick by a pixel; the calmer ripple acts nearer in
            ramp = (0.52 + 0.63 * sea_depth * rip_k) * A
        else:
            ramp = (0.52 + 0.63 * sea_depth) * A * rip_k   # (0.52: the far rows flick by a pixel too)
        rdx = np.rint(ramp * np.sin(tau * ((yy - hz) / wavelen + xx / (70.0 * A) - S.get('ripple_cycles', RIPPLE_CYCLES) * p))).astype(int)
        sxs = np.clip(xx - rdx, 0, W - 1)
        f = shift_take(f, yy, sxs, water & (rdx != 0) & water[yy, sxs])
        # swell: the wave lines nearer the beach rise and fall
        sw = SWELL_AMP * A * np.clip((sea_depth - 0.35) / 0.65, 0, 1) * (shipm if waves else 1)   # (off where waves roll)
        if S.get('far_flick'):
            # streaky water only shows a rise and fall: behind the wreck at every depth, and on the far
            # rows of open sea (above where the rolling waves start)
            sw = np.maximum(sw, SWELL_AMP * A * 0.62 * np.maximum(shipm, smooth01((0.16 - sea_depth) / 0.08)))
        if S.get('swell_floor'):                 # (no rolling waves: every row rises and falls a little)
            sw = np.maximum(sw, SWELL_AMP * A * S['swell_floor'])
        sdy = np.rint(sw * np.sin(tau * (yy / (7.0 * A) - SWELL_CYCLES * p + xx / (90.0 * A)))).astype(int)
        sys_ = np.clip(yy - sdy, 0, H - 1)
        f = shift_take(f, sys_, xx, water & (sdy != 0) & water[sys_, xx] & (surf_w == 0))
        # light on the water: glitter in the glow's reflection, a soft sheen elsewhere
        sheen = 0.5 + 0.5 * np.sin(tau * ((yy - hz) / ((1.6 + 3.0 * sea_depth) * A) - xx / (11.0 * A) - 6 * p))
        # the glow's reflection glints along its painted streaks: each horizontal run of it brightens
        # and dims as one, on its own timing (a per-pixel pattern broke into speckles on the grid)
        rg = S.get('refl_glitter', 0.0)
        gl = 0.5 + 0.5 * np.sin(tau * (S.get('streak_cycles', 3) * p + streak_ph))
        kk = np.clip((gl - 0.55) / 0.45, 0, 1) * rg
        f[refl] += (glint_c - f[refl]) * kk[refl][:, None]
        dk = np.clip((0.25 - gl) / 0.25, 0, 1) * 0.07 * rg / 0.16
        f[refl] *= (1 - dk[refl])[:, None]
        ws = water & ~refl & (sheen > 0.9) & (sea_depth < 0.8)
        f[ws] += (light_col - f[ws]) * S.get('water_sheen', 0.0)

        for gx, gy, c_, ph_ in glints:
            b_ = 0.5 + 0.5 * np.sin(tau * (c_ * p + ph_))
            if b_ > 0.82:
                kq = (b_ - 0.82) / 0.18
                f[gy, gx] += (glint_c - f[gy, gx]) * (0.5 + 0.5 * kq)
                if b_ > 0.96 and A == 1:
                    for ddx in (-1, 1):
                        if 0 <= gx + ddx < W and water[gy, gx + ddx]:
                            f[gy, gx + ddx] += (glint_c - f[gy, gx + ddx]) * 0.4
                elif b_ > 0.96:                          # (smooth: the same sparkle, 2x2 picture px)
                    for ddx, ddy in ((1, 0), (0, 1), (1, 1), (-1, 0), (2, 0), (-1, 1), (2, 1)):
                        if 0 <= gx + ddx < W and gy + ddy < H and water[gy + ddy, gx + ddx]:
                            f[gy + ddy, gx + ddx] += (glint_c - f[gy + ddy, gx + ddx]) * (0.5 if abs(ddx - 0.5) < 1 else 0.3)

        # surf: washes up the sand and back (and, behind the wreck, inside the water it can see)
        phase = tau * (S.get('surf_cycles', SURF_CYCLES) * p - xx / (150.0 * A))
        wash = (np.sin(phase) + 0.35 * np.sin(2 * phase - 0.6)) / 1.25
        dy = np.rint(SURF_AMP * A * lr * surf_w * wash).astype(int)
        sys_ = np.clip(yy - dy, 0, H - 1)
        take = (surf_w > 0) & (dy != 0) & in_seg[sys_, xx] & open_px[sys_, xx]
        f = shift_take(f, sys_, xx, take)
        front = SURF_AMP * A * lr * wash
        wet = sand_seg & (rel >= front - 0.5) & (rel < SURF_AMP * A * lr + 1.5)
        drying = np.clip(1 - (rel - front) / (SURF_AMP * A * lr + 2.0), 0, 1)
        f[wet] *= (1 - 0.10 * drying[wet])[:, None]
        fo = in_seg & (lum_of(f) > 185)
        fl = fo & (0.5 + 0.5 * np.sin(tau * (xx / (5.0 * A) + yy / (3.0 * A) - 10 * p)) < 0.2)
        f[fl] *= 0.93
        # the waterline laps: its last rows of water and first row of sand slide sideways a grid pixel and
        # back every 2 s, staggered along the beach, so the shore never sits still between washes
        if lap_zone is not None:
            ldx = np.rint(A * np.sin(tau * (LAP_CYCLES * p - xx / (23.0 * A)))).astype(int)
            lsx = np.clip(xx - ldx, 0, W - 1)
            f = shift_take(f, yy, lsx, lap_zone & (ldx != 0) & lap_zone[yy, lsx])

        # waterfall: streaks of light running down, spray churning at the foot
        if fall_cols:
            for x, ys in fall_cols:
                span = len(ys)
                sh = int(np.rint(WATERFALL_CYCLES * span * p)) % span
                idx = np.arange(span)
                col = art[ys[(idx - sh) % span], x].copy()
                phc = (idx - sh + int(fall_hash[x] * 6 * A)) % (6 * A)
                col[phc < A] *= 0.88
                col[(phc >= 3 * A) & (phc < 4 * A)] += (glint_c - col[(phc >= 3 * A) & (phc < 4 * A)]) * 0.35
                f[ys, x] = col
            ch = 0.5 + 0.5 * np.sin(tau * (10 * p) + xx * 2.3 / A + yy * 1.3 / A)
            dim = m['splash'] & (ch > 0.8)
            f[dim] *= 0.92
        # wind waves rolling over grassy slopes
        if m['hills'].any():
            ww = np.clip(np.sin(tau * (xx / (60.0 * A) - yy / (25.0 * A) - 3 * p)), 0, 1) ** 3
            hk = m['hills'] & (ww > 0.35)
            f[hk] *= 1 + HILL_WIND * ww[hk][:, None]
            f = f.clip(0, 255)

        # wind: the sail flaps at its ragged ends, grass sways
        gust = 0.85 + 0.15 * np.sin(tau * p)
        wind_s = (np.sin(tau * (SAIL_CYCLES * p - xx / (30.0 * A) - yy / (16.0 * A)))
                  + 0.35 * np.sin(tau * (3 * SAIL_CYCLES * p - xx / (9.0 * A) - yy / (7.0 * A))) * hang) * gust / 1.2
        wind_g = np.sin(tau * (GRASS_CYCLES * p) - tau * 1.4 * xx / W) * gust
        wind_v = np.sin(tau * (VINE_CYCLES * p) - tau * xx / W) * gust
        dxf = (sail_w * wind_s + grass_w * wind_g + vine_w * wind_v) * movers
        for tp in tree_parts:
            dxf = np.where(tp['zone'], dxf + tp['w'] * np.sin(tau * (tp['cyc'] * p + tp['ph'])) * gust, dxf)
        dxf[rigid] = 0
        dx = np.rint(dxf).astype(int)
        sxs = np.clip(xx - dx, 0, W - 1)
        f = shift_take(f, yy, sxs, (dx != 0) & ~rigid[yy, sxs] & ~rigid)

        frames.append(Image.fromarray(f.round().clip(0, 255).astype(np.uint8))
                      .quantize(palette=pal_img, dither=Image.Dither.NONE))

    save_gif(frames, out + '.gif')
    if not smooth:
        save_gif([fr.resize((W * 2, H * 2), Image.NEAREST) for fr in frames], out + '-preview.gif')
    return frames, art, m

if __name__ == '__main__':
    scene, src, out = [v for v in sys.argv[1:] if not v.startswith('--')][:3]
    smooth = '--smooth' in sys.argv
    for v_ in sys.argv:
        if v_.startswith('--palette-from='):
            PALETTE_FROM = v_.split('=', 1)[1]
        if v_.startswith('--snap-from='):
            SNAP_FROM = v_.split('=', 1)[1]
    a, s, A = load(src, smooth)
    m = build_masks(a, SCENES[scene], s, A)
    if '--masks' in sys.argv:
        mask_view(a, m, out + '-masks.png', s)
        print('water px', m['water'].sum(), 'shore cols', (m['shore'] > 0).sum(), 'rim px', m['rim'].sum(),
              'clouds moving', len(np.unique(ndi.label(m['cloud_core'], structure=np.ones((3, 3)))[0])) - 1)
        sys.exit()
    render(scene, src, out, smooth)
