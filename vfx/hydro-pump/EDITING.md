# Hydro Pump: aimed water column

This is an independent Hydro Pump asset kit. The stream follows a straight three-dimensional line from the caster's mouth toward the target's body. Its teal cylinder has moving white runnels and irregular cross-streaks. At contact, connected water sheets flare outward into rounded opaque foam caps, droplets fall onto the floor, and a small perspective pool settles and disappears.

Both attack directions use the same geometry and camera. Near water appears larger, distant water smaller. The preview uses a 640 by 410 stage and the same sample battler positions as the Surf previews.

The stream is now about 41% thicker and uses the same six teal water colors and four foam shades as Surf. The body, including its camera-facing end, uses 64% opacity. The white moving rings are opaque, irregular and shaded to show their volume. Water gathers into a churning, foamy volume at the mouth from 0.05 to 0.60 seconds before launching. The charging water blends into the stream during the first 0.18 seconds after launch. The impact foam retains its enlarged rounded billows. The source foam remains fitted to the actual animated stream radius. It now has a solid rounded foam cap and dense overlapping white billows across its center, with thicker foam built inward and along the jet rather than a larger detached ring. The source foam fades before emission stops, so it does not remain behind the traveling tail.

## Files and playback

Six RGBA atlases are supplied, with behind/between/front layers for each direction. **hydro-pump-timing.json** contains the image names, frame layout, timing and compositing order. Draw: stage, behind, far battler, between, near battler, front.

Each frame is 320 by 205 pixels. Display at 2x with nearest-neighbor sampling. Frames are anchored at the stage's top-left corner. There are 59 frames at 20 FPS, numbered 000 through 058, arranged in 8 columns and 8 rows. Each frame lasts 50 ms. Playback lasts 2.95 seconds and does not loop. The final frame is fully transparent.

## Timing and art controls

Edit **source/hydro-controls.json**:

| Control | Value | Effect |
| --- | --- | --- |
| chargeStartSeconds | 0.05 | Water begins gathering and churning at the mouth. |
| streamStartSeconds | 0.60 | Charged water surges forward. |
| travelSeconds | 0.30 | Time for the leading water to reach the target. Impact occurs at 0.90 seconds. |
| emitEndSeconds | 1.60 | Caster stops emitting; the remaining tail keeps traveling. |
| streamRadiusFraction | 0.31 | Jet radius relative to each battler's world height. |
| streamBodyOpacity | 0.64 | Translucency of the teal body; foam is more opaque. |
| foamRingSpacing | 0.14 | Roughly seven flowing rings per full stream length; smaller values add rings. |
| foamRingThickness | 0.15 | Foam ring thickness relative to jet radius. |
| sourceFoamRadiusMultiplier | 1.02 | Source collar radius relative to the water stream. |
| flowSpeed | 13.0 | Speed of the white stream texture. |
| impactRadiusFraction | 0.86 | Radius of the foaming impact relative to target height. |
| impactSheetLifetimeSeconds | 0.46 | Lifetime of each rolling splash sheet. |
| poolClearSeconds | 2.58 | Last shallow ground water disappears. |
| endSeconds | 2.90 | Final sampled frame; leave enough room for the splash to clear. |

The last emitted water reaches the target at 1.90 seconds. The stream's head and tail travel at the same rate. This prevents the whole jet from shrinking or fading away at once when emission stops.

## Render

From the extracted folder:

```powershell
py -m pip install numpy Pillow
py .\source\render_hydro_pump.py
```

Updated atlases and timing JSON appear in **source/assets**. Preview frames appear in **source/outgoing** and **source/incoming**. Keep arena.png, near.png, far.png and hydro-controls.json beside the renderer. The stage and battlers are used only in previews; the atlases contain only the transparent water effect.

To extract a frame for painting, crop the corresponding 320 by 205 tile from each atlas. The column is frame index modulo 8; the row is frame index divided by 8, rounded down. Preserve canvas size, RGBA transparency and layer order when replacing tiles.

The kit supplies effect assets and editable source. Integration with an installed Showdown CSS or userscript depends on that existing animation implementation.
