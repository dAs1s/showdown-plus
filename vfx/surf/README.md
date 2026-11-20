# Surf sheets

A hand-made Surf animation for Showdown. With this style on, Surf plays these sprite sheets instead of the drawn
wave built into the userscript.

## Install

Open [`showdown-surf-sheets.user.css`](showdown-surf-sheets.user.css), click *Raw*, and Stylus opens its install
page. It needs the pin-controls userscript, and `--surf-sheets: 1` in the main style (the default).

## What is in it

- 45 frames at 20 frames a second, each 320x205, drawn at 2x for the 640x410 battle window
- Two directions (`out`: your Pokémon attacking, `in`: the opponent's), each in three layers: behind the far
  Pokémon, between the two, and in front of the near one
- The sheets in [`sheets/`](sheets): 8 columns by 6 rows of frames, the same images the style embeds

The style's `--surf-sheet-info` line describes the sheets: frames, frames per second, columns, frame size, where the
near and far Pokémon stand in the window they were drawn for, the moment of impact (ms), and that window's size. The
main style's `--surf-sheet-fit`, `--surf-sheet-scale`, `--surf-sheet-x` and `--surf-sheet-y` move and size it.

## Getting this version back

This version is tagged `surf-v1`. To restore it after changing things:

- On GitHub: switch the branch menu to the `surf-v1` tag, open the file and download it.
- With git: `git checkout surf-v1 -- vfx/surf`
