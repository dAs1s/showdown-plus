# Tools

The scripts that make and pack the maps. Python 3 with `numpy`, `scipy` and `Pillow`.

| Script | What it does |
|---|---|
| `beach640.py` | The animator. `python beach640.py SCENE src.png out [--smooth] [--palette-from=old.gif] [--snap-from=original.png] [--masks]`. Scenes are in its `SCENES` dict. |
| `lava640.py` | The lava for the lava scenes (used by `beach640.py`). |
| `animate.py`, `masks.py` | Shared helpers (GIF saving, sky, masks). |
| `make_map_css640.py` | Packs a GIF into a map slot's style: `python make_map_css640.py in.gif out.css NAME --slot=N [--smooth] [--webp] [--usercss]`. `--webp` stores it as lossless animated WebP and checks every frame. |
| `pack_vfx.py` | Packs a move's six sheets into its VFX style: `python pack_vfx.py SLUG "Move Name" SHEETS_DIR --version 1.0.0`. 256 colours (needs `pip install imagequant`), lossless WebP, update link in the header. |
| `check_release.py` | Run before every push: headers, update links, version bumps, braces, embedded pictures. |
| `shrink_far_leaves.py` | A one-off source edit: far leaves on the autumn forest floor made smaller by distance. |

Formats: 640x410 source pictures, used whole. Pixel art is rendered on a 320x205 grid and shown at 2x; GIFs are
200 frames at 100 ms, seamless, at most 255 colours.
