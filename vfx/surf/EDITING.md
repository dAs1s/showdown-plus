# Surf: original wave with recent trailing water

Base: surf-behind-caster-sprite-sheets(2).zip. Ground-water style: surf-closer-receding-trail.

The opening surge, striking foam, spray, camera, sprites, wave height curve, travel path, and approach/impact timing are preserved. The late wave finish is stretched as described below. After impact, the rolling wave now compensates for perspective and continues growing in projected width as it lowers. The original main puddle is replaced by the recent turquoise ground sheet and edge foam. It follows the wave’s actual ground-contact rows. Newly released water begins narrower and grows outward continuously into a tapered fan with rounded ends. A solid teal film joins the sheet to the full wave base, sealing the floor without spreading foam across the join. The older trail remains narrow toward the caster and recedes from bottom to top. Cleared water leaves darker wet ground, which then dries.

Impact remains at 1.30 seconds and the wave now finishes at 2.65 seconds. The water trail clears by 2.65 seconds; wet ground is gone by 3.55 seconds. The longer export allows the ground effects to finish without stretching the opening surge or the approach and impact.

## Slower post-impact settling

Approach and impact remain unchanged, with contact at 1.30 seconds. Slower playback now begins at impact instead of waiting until 1.50 seconds. The wave keeps moving, but its raised profile lingers longer before settling. The remaining crest height and opacity ease into the puddle's 2.65-second clear time.

The visible wave, projected ground contact, puddle attachment and contact-film strength now share the same wave pose. The solid joining film loses strength as the wave becomes shallow, so a detached opaque strip cannot remain behind. White crest shading transitions gradually into the teal body after impact, replacing the old binary shell cutoff. Existing puddle expansion controls, opening trim, edge-foam volume, palette and damp-ground settings are retained. The approved milestone remains separate.

Edit **source/timing-controls.json**:

| Control | Value | Effect |
| --- | --- | --- |
| waveTailStretchStartSeconds | 1.30 | Slow the collapse immediately after impact; approach is unchanged. |
| waveTailSourceEndSeconds | 1.94 | Last low-water source pose, eased to zero height at the final clear time. |
| waveTailClearSeconds | 2.65 | Wave and puddle clear time. |
| waveTailFadeSeconds | 0.55 | Height/opacity settle from 2.10 to 2.65 seconds. |
| waveTailBlendSeconds | 0.20 | Smooth transition into slower post-impact playback. |

## Farther shared travel

Only the outgoing shared carry is increased, matching the reference marked behind the opponent. The wave and its attached ground sheet travel farther together after contact. The incoming animation, approach, impact, collapse/fade clocks, palette, foam, spread controls and damp-ground controls remain unchanged.

## Forward momentum after impact

Forward travel is now independent of the slower crest-collapse clock. The wave matches its arrival speed at impact, then smoothly builds to a cruise speed that never decreases before the water clears. The entire puddle uses the same advancing ground flow, including its fading pattern. All parts of the footprint keep moving forward; the trailing edge can spread while still advancing. This replaces the previous small added offset and post-impact braking.

Depth compensation keeps the footprint from compressing into a thin distant stripe. The ground transform remains invertible, retains rounded edges, and preserves the wave-to-puddle attachment. The final clear time is still 2.65 seconds. Colors, raised foam, height/collapse timing, impact timing and the approved milestone are retained.

Edit **source/timing-controls.json**:

| Control | Value | Effect |
| --- | --- | --- |
| waterMaintainMomentum | true | Separate forward travel from collapse playback; no post-impact braking. |
| waterCruiseGainOutgoing | 3.60 | Forward cruise rate relative to the outgoing arrival speed. |
| waterCruiseGainIncoming | 1.60 | Forward cruise rate relative to the incoming arrival speed. |
| waterMomentumBlendSeconds | 0.10 | Smooth speed increase after contact; no pause or slowdown. |
| waterPerspectiveWidthStrength | 0.55 | Partial compensation; retains perspective narrowing while preventing excessive widening. |
| waterPerspectiveWidthCompensation | true | Preserve the spreading footprint's readable width as it travels deeper. |
| waterTrailingReachCompensation | 0.90 | Preserve the fan's depth while every point still advances by at least 15% of the shared flow. |

The preceding waterCarryDistanceFraction and waterCarryEaseSeconds settings are legacy controls used only when waterMaintainMomentum is false.

The post-impact wave width growth is slightly increased from 0.12 to 0.18. Puddle expansion increases from 1.10 to 1.18, and mature released-water width from 1.07 to 1.16. Starting width, foam cell size and the opening trim are unchanged.

## Post-impact wave width

Edit **source/timing-controls.json**:

| Control | Value | Effect |
| --- | --- | --- |
| wavePostImpactWidthGrowth | 0.18 | Extra projected width after impact. A value of 0 preserves impact width instead of narrowing. |
| wavePostImpactWidthSpreadSeconds | 0.50 | Spreading timescale; growth eases in and continues until the wave disappears. |

The outgoing wave’s ground width grows from about 346 stage pixels at impact to 377 stage pixels near 2.0 seconds. The incoming wave retains its existing natural widening toward the camera. Wave height, forward movement, and timing are independent of this width correction.

The puddle's outward growth now uses an 80% steady-rate curve and 20% of its previous easing. This reduces the initial burst and carries more expansion through the later visible frames. At 1.25 seconds of deposited-water age, the spread matches the approved milestone; its initial widths are also unchanged. The connected wave edges, pigment, foam, opening trim, wave motion and fade controls remain as approved. The bottom-up retreat uses the original reference footprint so its timing stays unchanged.

The puddle begins 0.30 seconds earlier, removing the previous appearance delay. The two-frame smooth reveal, narrower start, continuous spreading, wave timing, colors, edge foam, bottom-up retreat and wet-ground drying remain unchanged.

The wave's two ground-contact tips now connect to the existing puddle banks with curved shoulders projected onto the ground plane. This fills only the join, using the puddle's existing teal shading and outer-edge foam. The connection follows the moving wave and inherits the current bottom-up retreat. The rest of the puddle keeps its narrower start and continuous outward expansion; no timing or wave settings change.

The first 0.40 seconds (eight frames at 20 FPS) of the puddle are cut from view, including the additional 0.15-second trim. Later puddle frames stay at their original times; this is an opening trim, not a playback shift. The wave, connected edges, spread, recession and wet-ground animation are unchanged.

The wave and puddle share a continuously advancing forward flow, while the crest collapse retains its slower deformation clock. Approach, impact and final clear time remain unchanged.

The reference's low raised white water edges are represented by perspective-scaled foam caps with cool teal undersides. Existing outer-edge cells provide the shapes. Near crests rise more than distant ones, and both follow the puddle's original visibility and fade. The turquoise fill, cell placement, spread, footprint and timing controls remain unchanged.

## Ground-water controls

Edit **source/trail-controls.json**:

| Control | Value | Effect |
| --- | --- | --- |
| trailSpreadUniformity | 0.80 | Evenness of expansion: 0 restores the milestone curve; 1 is steady growth. |
| trailSpreadReferenceSeconds | 1.25 | Age where the adjusted spread matches the milestone. |
| trailFoamVolumePixels | 3.20 | Maximum-reference shoreline relief in stage pixels, scaled by depth; 0 restores flat foam. |
| trailStartCutSeconds | 0.40 | Cut the opening puddle frames without shifting later animation. |
| trailAppearanceDelaySeconds | 0.00 | Visibility delay for the puddle, without shifting the wave or later growth/fade clocks. |
| trailBottomRecedeSeconds | 0.10 | Lowest band starts retreating. |
| trailTopRecedeSeconds | 1.85 | Upper bank starts retreating. |
| trailReleasedStartWidthFraction | 0.43 | Newly released post-impact water starts at 43% of the wave footprint, then spreads. |
| trailReleasedMatureWidthFraction | 1.16 | Mature released-water width, with continued slower expansion after this. |
| trailFoamEdgeBandPixels | 7 | Far-edge foam band; grows slightly toward the camera. The center stays teal. |
| trailContactFillPixels | 12 | Width of the solid teal joining strip at the wave base. |
| trailRowFadeSeconds | 0.80 | Fade duration for each ground band. |
| trailRearBoundarySlope | 0.11 | Shallow retreat angle. |
| trailSideStraightness | 0.65 | Cleaner long banks; retains rounded ends and mild irregularity. |
| trailStartWidthFraction | 0.16 | Narrow initial deposit. |
| trailCasterWidthFraction | 0.38 | Caster-end taper. |
| trailAttachmentSeconds | 0.28 | Legacy control; full-width stamp attachment is replaced by the teal contact film. |
| trailSpreadSeconds | 0.50 | Initial spreading timescale. |
| trailExpansionMultiplier | 1.18 | Extra outward expansion. |
| trailLateSpreadPerSecond | 0.12 | Continued spreading during disappearance. |
| trailEdgeIrregularityPixels | 1.8 | Gentle shoreline variation, in 640 by 377 stage pixels. |
| trailFoamPatchStrength | 0.90 | Thicker foam patches near edges. |
| dampGroundOpacity | 0.31 | Wet-ground darkness, increased from 0.23. |
| dampGroundFadeSeconds | 0.90 | Drying time after the water clears. |

Foam cells follow only the outer shoreline of visible water. The interior retains its teal/cyan shading. The join under the wave is opaque teal while the raised water remains substantial, then blends into the settling sheet. Each ground band fades over 0.80 seconds instead of 0.55.

Wet spots are recorded from the visible, clipped water trail, rather than the whole wave footprint. The recent module retains historical code for compatibility; this hybrid uses **TrailWater** only for the puddle and wet residue. Its copied-surge, post-impact slowdown, and additional crash-foam methods are unused. Original wave controls remain in **source/timing-controls.json**.

## Render

Run from the extracted folder:

```powershell
py -m pip install numpy Pillow
py .\source\render_surf.py
```

Six transparent sheets and **surf-timing.json** are written into **source/assets**. Keep **trail_water.py** and **trail-controls.json** beside **render_surf.py**. Preview frames appear in **source/outgoing** and **source/incoming**.

## Paint frames

```powershell
py .\source\edit_frames.py split . .\frames
```

Edit the transparent 320 by 205 PNGs, retaining their canvas and RGBA mode. Reassemble:

```powershell
py .\source\edit_frames.py pack . .\frames --output .\edited-assets
```

There are 72 frames, numbered 000 through 071, at 20 FPS. Atlases use eight columns and nine rows. Display at 2x using nearest-neighbor sampling on the 640 by 410 stage. Composite stage, behind sheet, far battler, between sheet, near battler, then front sheet.
