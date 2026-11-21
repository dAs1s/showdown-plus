"""Pack a finished 700x500 battle background GIF as one map of the Showdown battle style.

    python make_map_css640.py <gif> <out.css> <name> --slot=N [--smooth] [--webp] [--usercss]

The battle window shows x 50-690, y 40-450 of Showdown's 700x500 backdrop, so the GIF is cut to that 640x410. New 640x410 pictures are used whole (no crop); a 320x205 GIF is stored as is.
Pixel art (2x2 blocks) is stored at half size (320x205) and drawn at 2x with sharp pixels; --smooth (a painting) is
stored at 640x410 and drawn as is. Every frame is checked against the input. The file names its slot (--map-N-on),
applies only to battles marked with it, and has a block for this map's own numbers (all left to the main style
until you turn one on)."""
import sys, io, base64
import numpy as np
from PIL import Image, ImageSequence

args = [a for a in sys.argv[1:] if not a.startswith('--')]
src, out, name = args[0], args[1], args[2]
slot = int(next(a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--slot=')))
smooth = '--smooth' in sys.argv
im = Image.open(src); assert im.size in ((700, 500), (640, 410), (320, 205)), im.size
# 640x410 pictures (the new maps) are used whole, no crop; a 320x205 GIF is already the pixel grid, stored as is
crop = im.size == (700, 500)
if im.size == (320, 205):
    assert not smooth, 'a 320x205 GIF is pixel art: leave out --smooth'
frames, durs = [], []
for f in ImageSequence.Iterator(im):
    rgb = np.array(f.convert('RGB'))
    if crop:
        rgb = rgb[40:450, 50:690]
    if not smooth and rgb.shape[:2] == (410, 640):
        s = rgb[0::2, 0::2]
        assert (np.repeat(np.repeat(s, 2, 0), 2, 1) == rgb).all(), 'not 2x2 pixel art: use --smooth'
        rgb = s
    frames.append(rgb); durs.append(f.info.get('duration', 100))
# one palette for every frame (the input's colours: at most 256 of them over the whole loop)
allc = np.unique(np.concatenate([fr.reshape(-1, 3) for fr in frames]), axis=0)
assert len(allc) <= 255, '%d colours: more than one GIF palette can hold (one entry is kept for see-through)' % len(allc)
key = lambda a: (a[..., 0].astype(np.int64) << 16) | (a[..., 1].astype(np.int64) << 8) | a[..., 2].astype(np.int64)
keys = key(allc); order = np.argsort(keys); keys = keys[order]; allc = allc[order]
pal = allc.reshape(-1).tolist(); pal += [0] * (768 - len(pal))
# each frame stores only the pixels that changed since the one before (the rest see-through): much smaller
TR = 255
P = []; prev = None
for fr in frames:
    idx = np.searchsorted(keys, key(fr)).astype(np.uint8); b = idx.copy()
    if prev is not None: b[idx == prev] = TR
    prev = idx
    o = Image.fromarray(b, 'P'); o.putpalette(pal); P.append(o)
buf = io.BytesIO()
P[0].save(buf, 'GIF', save_all=True, append_images=P[1:], duration=durs, loop=0, optimize=False, disposal=1, transparency=TR)
data = buf.getvalue()
back = Image.open(io.BytesIO(data)); worst = 0
for fr, f in zip(frames, ImageSequence.Iterator(back)):
    worst = max(worst, int(np.abs(np.array(f.convert('RGB')).astype(int) - fr.astype(int)).max()))
assert worst == 0, 'frames changed when stored (%d)' % worst
mime = 'gif'
if '--webp' in sys.argv:                     # animated lossless WebP: the same pixels, about 28% smaller (not for the tower,
    wb = io.BytesIO()                        # whose second light the userscript times from a GIF)
    rgbs = [Image.fromarray(fr) for fr in frames]
    rgbs[0].save(wb, 'WEBP', save_all=True, append_images=rgbs[1:], duration=durs, loop=0, lossless=True, quality=100,
                 method=4, minimize_size=True)
    wdata = wb.getvalue(); back = [np.array(f.convert('RGB')) for f in ImageSequence.Iterator(Image.open(io.BytesIO(wdata)))]
    assert len(back) == len(frames), 'WebP has %d frames, not %d' % (len(back), len(frames))
    for fr, f in zip(frames, back):
        assert np.array_equal(f, fr), 'a WebP frame differs from the input'
    print('  GIF %d KB -> WebP %d KB' % (len(data) // 1024, len(wdata) // 1024))
    data, mime = wdata, 'webp'
b64 = base64.b64encode(data).decode()
N = str(slot)
sel = 'html:root body .battle[data-ps-map="%s"][data-ps-map]' % N
css = '''/* ==========================================================================
   Showdown Plus - map %(N)s: %(name)s
   A separate Stylus style: one map of your rotation. Turn it off in Stylus to take this map out.
   ========================================================================== */
@-moz-document domain("play.pokemonshowdown.com") {

  :root {
    /* MAP SLOT %(N)s: each battle gets one installed map at random (the userscript picks; --map-pick: %(N)s in the
       main style always shows this one, for tuning it). To move it to another slot, change every "%(N)s" in this file */
    --map-%(N)s-on: 1;

    /* this map's cast shadows (to use one here, delete the comment marks at both ends of its line; otherwise the main style's apply).
       Angles: where each falls on screen, 0deg = right, 90deg = straight down (toward you), 180deg = left */
    /* --map%(N)s-shadow-angle-foe-trainer: 40deg; */
    /* --map%(N)s-shadow-angle-foe: 44deg; */
    /* --map%(N)s-shadow-angle-player: 58deg; */
    /* --map%(N)s-shadow-angle-player-trainer: 62deg; */
    /* --map%(N)s-shadow-length: 1; */
    /* --map%(N)s-shadow-strength: 0.4; */
    /* --map%(N)s-shadow-blur: 1.5px; */
  }

  /* THIS MAP'S OWN NUMBERS: any setting from the main style can go here, and then applies only in battles on this
     map. To use one, delete the comment marks at both ends of its line and change the value (the values shown are the main style's
     at the time this file was made). Anything left out follows the main style. */
  %(sel)s {
    /* your Pokemon */
    /* --player-scale: 1.9; */
    /* --player-x: 100px; */
    /* --player-y: 75px; */
    /* the opponent's Pokemon */
    /* --foe-scale: 1.3; */
    /* --foe-x: 30px; */
    /* --foe-y: 50px; */
    /* --foe-ground: 25px; */
    /* your trainer */
    /* --player-trainer-x: 135px; */
    /* --player-trainer-y: 470px; */
    /* --player-trainer-scale: 3.40; */
    /* the opponent's trainer */
    /* --foe-trainer-x: 510px; */
    /* --foe-trainer-y: 240px; */
    /* --foe-trainer-scale: 1.10; */
    /* team preview */
    /* --tp-x: 50px; */
    /* --tp-player-scale: 1.5; */
    /* --tp-player-gap-x: 55px; */
    /* --tp-player-gap-y: 8px; */
    /* --tp-player-x: -95px; */
    /* --tp-player-y: -15px; */
    /* --tp-foe-scale: 0.7; */
    /* --tp-foe-gap-x: -5px; */
    /* --tp-foe-gap-y: -1px; */
    /* --tp-foe-x: 40px; */
    /* --tp-foe-y: 25px; */
    /* talk bubbles */
    /* --bubble-player-x: 7px; */
    /* --bubble-player-y: -7px; */
    /* --bubble-foe-x: 0px; */
    /* --bubble-foe-y: 0px; */
    /* where the picture sits (the main style's at the time: zoom 1.1, x 0px, y -5px). Pixel art keeps even pixels only at zoom 1, 1.5 and 2 */
    /* --bg-zoom: 1.1; */
    /* --bg-x: 0px; */
    /* --bg-y: -5px; */
    /* look of this background (the main style's --bg-contrast, --bg-brightness and --bg-saturate apply unless set here; 1 = as drawn) */
    /* --cbg-contrast: 1; */
    /* --cbg-brightness: 1; */
    /* --cbg-saturate: 1; */
    --cbg-haze: 0;                 /* the main style's haze and vignette on top (0 = off, 1 = as on Showdown's own backgrounds) */
  }

  /* the picture, made for your 640x410 battle window (x 50-690, y 40-450 of the 700x500 backdrop): the padding
     leaves exactly that area, and the picture is drawn only there%(how)s */
  html body .battle[data-ps-map="%(N)s"] .innerbattle > .backdrop {
    background-image: url("data:image/%(mime)s;base64,%(b64)s") !important;
    box-sizing: border-box !important;
    padding: 40px 10px 50px 50px !important;
    background-origin: content-box !important;
    background-clip: content-box !important;
    background-size: 100%% 100%% !important;
    background-position: 0 0 !important;
    background-repeat: no-repeat !important;
    image-rendering: %(render)s !important;
    /* Showdown shows every background at 80%% strength over a pale grey panel; this one is at full strength */
    opacity: 1 !important;
    filter:
      url(#ps-darks)
      url(#ps-lights)
      contrast(var(--cbg-contrast, 1))
      brightness(var(--cbg-brightness, 1))
      saturate(var(--cbg-saturate, 1)) !important;
  }
  html body .battle[data-ps-map="%(N)s"] .innerbattle > .backdrop::before {
    content: none !important;
  }
  html body .battle[data-ps-map="%(N)s"] .innerbattle > .backdrop::after {
    opacity: var(--cbg-haze, 0) !important;
  }
}
''' % dict(N=N, name=name, sel=sel, b64=b64, mime=mime, render='auto' if smooth else 'pixelated',
           how=(' as is (a painting: smooth)' if smooth else ', at exactly 2x (320x205 -> 640x410) with sharp pixels'))
open(out, 'w', encoding='utf-8', newline='\n').write(css)
if '--usercss' in sys.argv:                  # the same style with a header, so Stylus installs it directly
    hdr = '''/* ==UserStyle==
@name           Showdown Plus - map %s: %s
@namespace      dasmins.showdown.maps
@version        %s
@description    One animated map of the battle background rotation (slot %s).
@author         dasmins
==/UserStyle== */
''' % (N, name, '1.1.0' if mime == 'webp' else '1.0.0', N)
    open(out.replace('.css', '.user.css'), 'w', encoding='utf-8', newline='\n').write(hdr + css)
print('%-34s slot %2s  %s  %.2f MB  %d frames, %d colours, stored exactly' % (out.split('/')[-1], N, 'smooth' if smooth else 'pixel ', len(css) / 1e6, len(frames), len(allc)))
