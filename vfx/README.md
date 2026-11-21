# Showdown Plus: VFX

Hand-made move animations for Pokémon Showdown, played from sprite sheets. Each move is its own Stylus style, so
you can turn moves on and off one at a time. A move without its style on plays as before.

| Move | Style | Frames | Length |
|---|---|---|---|
| Surf | [`surf/showdown-vfx-surf.user.css`](surf/showdown-vfx-surf.user.css) | 72 at 20 fps | 3.6 s |
| Hydro Pump | [`hydro-pump/showdown-vfx-hydro-pump.user.css`](hydro-pump/showdown-vfx-hydro-pump.user.css) | 59 at 20 fps | 2.95 s |

Since version 1.1.0 the sheets are stored as lossless WebP reduced to 256 colours: Surf's style went from 1,983 KB to
657 KB, Hydro Pump's from 856 KB to 231 KB, with no visible difference (at most a few faint foam-edge pixels change).
The PNG sheets in each move's `sheets/` folder are still the full originals, and `vfx-v1` keeps the PNG styles.

## Install

1. The pin-controls userscript, **2.41.0 or later** (2.43.1 is current) ([`userscript/showdown-pin-controls.user.js`](../userscript/showdown-pin-controls.user.js)).
   2.41.0 is the first version that plays Hydro Pump; Surf works from 2.40.
2. Open each move's `.user.css` above, click *Raw*, and Stylus opens its install page.

If you had the older "Showdown - Surf sheets" style installed, turn it off: both set Surf's sheets.

## Settings (optional: put them in your *Showdown Plus - my settings* style)

Each move has its own, named after it (`--surf-...`, `--hydro-pump-...`):

- `--surf-sheets: 1` / `--hydro-pump-sheets: 1`: 0 plays Showdown's own animation instead
- `--surf-speed` / `--hydro-pump-speed`: playback speed (1 = as drawn)
- `--surf-sheet-fit` / `--hydro-pump-sheet-fit`: 1 = scale and move the sheets so their two standing spots land on the two Pokémon, 0 = exactly as drawn
- `--...-sheet-scale`, `--...-sheet-x`, `--...-sheet-y`: extra size and nudges
- `--surf-sheet-trainer-delay: 0.1`: your Surf goes behind the opponent's trainer this many seconds after it goes behind the opponent's Pokémon (-1 = never; userscript 2.43.0 or later)

## How each move is made

Every move has three layers per direction: behind the far Pokémon, between the two, and in front of the near one.
`out` (outgoing) is your Pokémon attacking, `in` (incoming) the opponent's. Frames are 320x205, shown at 2x with sharp
pixels, 8 columns to a sheet.

Each move's folder has:

- the style (the sheets are embedded in it)
- `sheets/`: the six sheets as PNGs and the timing file
- `source/`: the render scripts and their controls, to change and render it again
- `EDITING.md`: what the controls do and how to render

## Versions

Each saved version is tagged, so an earlier one can always be restored:

- `surf-v1`: the first Surf (45 frames), also kept in [`surf/archive/v1/`](surf/archive/v1)
- `vfx-v1`: Surf with the farther shared travel (72 frames) and the first Hydro Pump

To restore a move: on GitHub pick the tag in the branch menu and download its files, or run
`git checkout <tag> -- vfx/<move>`.
