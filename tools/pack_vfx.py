"""Packs a move's six sprite sheets into its Showdown Plus VFX style.

    python tools/pack_vfx.py SLUG "Move Name" SHEETS_DIR [--version 1.0.0] [--impact MS] [--feet "nx ny fx fy"]
                             [--colours 256] [--needs 2.44.0]

SLUG is the move's name in files and settings (ice-beam). SHEETS_DIR holds SLUG-outgoing-behind.png ... and
SLUG-timing.json. Writes vfx/SLUG/showdown-vfx-SLUG.user.css.

- the sheets are reduced to --colours colours with libimagequant (pip install imagequant; 0 = keep every colour) and
  stored as lossless WebP; it prints how far any pixel moved, as seen on screen
- frames, fps and columns come from the timing file; --impact defaults to its beatsMs.targetImpact (or impact)
- --feet: where the two Pokemon stand in the 640x410 window the sheets were drawn for (default: the shared
  near/far spots used by Surf, Hydro Pump and Ice Beam)
- the header carries the update link, so Stylus updates it; raise --version every time the sheets change
"""
import argparse, base64, io, json, os, sys
import numpy as np
from PIL import Image

RAW = 'https://raw.githubusercontent.com/dasmins/showdown-plus/main/'
HOME = 'https://github.com/dasmins/showdown-plus'
LAYERS = [('out', 'outgoing'), ('in', 'incoming')]


def premultiplied(a):
    a = a.astype(float)
    return np.concatenate([a[..., :3] * a[..., 3:] / 255, a[..., 3:]], -1)


def encode(im, colours):
    if colours:
        import imagequant
        im = imagequant.quantize_pil_image(im, dithering_level=0.0, max_colors=colours,
                                           max_quality=100, min_quality=0).convert('RGBA')
    b = io.BytesIO()
    im.save(b, 'WEBP', lossless=True, quality=100, method=6, exact=True)
    return b.getvalue(), im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('slug'); ap.add_argument('name'); ap.add_argument('sheets')
    ap.add_argument('--version', default='1.0.0')
    ap.add_argument('--impact', type=int)
    ap.add_argument('--feet', default='226 358 370 216')
    ap.add_argument('--colours', type=int, default=256)
    ap.add_argument('--needs', default='2.44.0', help='oldest userscript that plays this move')
    a = ap.parse_args()

    t = json.load(open(os.path.join(a.sheets, '%s-timing.json' % a.slug), encoding='utf-8'))
    fw, fh = t['spriteFrame']['width'], t['spriteFrame']['height']
    sw, sh = t['previewStage']['width'], t['previewStage']['height']
    frames, fps, cols = t['frameCount'], t['framesPerSecond'], t['atlas']['columns']
    beats = t.get('beatsMs', {})
    impact = a.impact if a.impact is not None else beats.get('targetImpact', beats.get('impact'))
    if impact is None:
        sys.exit('no impact time: pass --impact MS')
    feet = a.feet.split()
    assert len(feet) == 4, '--feet needs four numbers'
    info = ' '.join(str(v) for v in [frames, fps, cols, fw, fh] + feet + [impact, sw, sh])

    lines = []
    for short, long_ in LAYERS:
        names = t['playerAttack' if short == 'out' else 'opponentAttack']
        for layer in ('behind', 'between', 'front'):
            p = os.path.join(a.sheets, names[layer])
            im = Image.open(p).convert('RGBA')
            rows = -(-frames // cols)
            assert im.size == (cols * fw, rows * fh), '%s is %s, expected %s' % (p, im.size, (cols * fw, rows * fh))
            data, q = encode(im, a.colours)
            e = np.abs(premultiplied(np.array(im)) - premultiplied(np.array(q))).max(-1)
            vis = np.array(im)[..., 3] > 0
            print('  %-8s %-8s %4d KB  on-screen change: max %3d, pixels over 16: %d of %d' % (
                long_, layer, len(data) // 1024, round(float(e.max())), int((e > 16).sum()), int(vis.sum())))
            lines.append('    --%s-sheet-%s-%s: url("data:image/webp;base64,%s");' % (
                a.slug, short, layer, base64.b64encode(data).decode()))

    path = 'vfx/%s/showdown-vfx-%s.user.css' % (a.slug, a.slug)
    css = '''/* ==UserStyle==
@name           Showdown Plus - VFX - %(name)s
@namespace      dasmins.showdown.vfx
@version        %(version)s
@description    %(name)s plays these hand-made sprite sheets. Needs the pin-controls userscript %(needs)s or later.
@homepageURL    %(home)s
@supportURL     %(home)s/issues
@updateURL      %(raw)s%(path)s
@author         dasmins
==/UserStyle== */
@-moz-document domain("play.pokemonshowdown.com") {
  :root {
    /* %(name)s: frames, frames per second, sheet columns, frame width, frame height, near feet x y, far feet x y (in the
       %(sw)dx%(sh)d window the sheets were drawn for), impact time in ms, window width, window height */
    --%(slug)s-sheet-info: "%(info)s";
%(lines)s
  }
}
''' % dict(name=a.name, version=a.version, needs=a.needs, home=HOME, raw=RAW, path=path, sw=sw, sh=sh,
           slug=a.slug, info=info, lines='\n'.join(lines))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'w', encoding='utf-8', newline='\n').write(css)
    print('%s: %d KB, info "%s"' % (path, len(css.encode()) // 1024, info))


if __name__ == '__main__':
    main()
