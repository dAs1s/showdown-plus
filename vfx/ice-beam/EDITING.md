# Ice Beam: charge, beam and crystal shatter

A stronger white/cyan frost charge gathers at the caster's mouth: 30 ice flecks and broad curls of fog spiral inward and compress into a brighter, denser icy core before the beam fires. The existing brief charge duration and beam launch time are retained. Fine white pinpoints also spiral into the source during that charge. These smaller particles shimmer independently, smoothly dimming and brightening rather than showing large cross-shaped stars. A bright narrow beam then travels directly toward the opponent, shedding white frozen glints that fall under gravity. While the beam hits, a denser, more forceful spray of white sparkling particles ricochets outward from the target and arcs downward. The impact emits twelve fine shimmering particles every 0.04 seconds at 3.25 times the original launch speed. A large white/cyan initial blast, sustained pulsing impact core, repeated spreading frost plumes and flying pointed ice chips exaggerate the hit throughout contact. The charge includes four perspective-projected ice-energy rings contracting into the muzzle. Outer rings start at 22% of their former opacity, then smoothly become brighter and more opaque as they approach the source. Ring paths and timing are unchanged. Dense pale frost fog is centered over the exact impact point and drifts outward. Sustained white/cyan light shafts pulse outward throughout beam contact. Moving brightness bands and varying white filaments make the beam itself shimmer. A brilliant white central spine is now drawn over the beam body, with traveling width/glow highlights; the icy outer body and fog retain their original appearance. The beam geometry, charge duration, contact duration, attached crystal clusters and shatter timing remain unchanged. Four dense crystal clusters grow directly on the target. Crystal points and their shared bases are 12% larger, and each point has a longer taper for a sharper silhouette. Breakup retains its 0.20-second delay. When each cluster breaks, a local frost cloud expands from its base and 20 fine white shimmering sparkles fly outward. The larger ice fragments use a balanced outward burst, halfway between the original motion and the strongest shatter. Existing frost clouds, shimmer particles, size, lifetime and timing are retained. Each patch has eight unequal crystal points growing from an overlapping, solid faceted base, replacing the separated ice growths. Pale frosty fog curls away from the beam, expanding and drifting briefly after its core passes. After a short hold, the ice breaks apart into rotating, falling shards that fade away. The reference's pale cyan edges, bright white core and icy impact spray are adapted to the existing pixel-art battle view.

Both attack directions use the same perspective camera and three-dimensional targeting. The effect kit contains transparent VFX only; the arena and sample battlers are included for previews. Surf and Hydro Pump are separate and unchanged.

## Playback

Six RGBA atlases contain behind/between/front layers for outgoing and incoming attacks. Use **ice-beam-timing.json** for frame dimensions, layout, timing and file names. Composite stage, behind, far battler, between, near battler, front. Each frame is 320 by 205 pixels, displayed at 2x with nearest-neighbor sampling on a 640 by 410 stage. Anchor the frame at the stage's top-left corner.

There are 65 frames at 20 FPS, numbered 000 through 064, packed into eight columns and nine rows. Each frame lasts 50 milliseconds. Playback lasts 3.25 seconds and does not loop. The first and final frames are transparent. The preview video shows the two attack directions side by side.

## Timing and art controls

Edit **source/ice-beam-controls.json**:

| Control | Value | Meaning |
| --- | --- | --- |
| chargeStartSeconds | 0.05 | Frost begins gathering. |
| beamStartSeconds | 0.45 | Beam launches after the brief charge. |
| travelSeconds | 0.18 | Beam reaches the target at 0.63 seconds. |
| emitEndSeconds | 1.55 | Source stops; the remaining beam travels into the target until 1.73 seconds. |
| beamRadiusFraction | 0.065 | Beam radius relative to battler world height. |
| iceGrowthSeconds | 0.46 | Growth time for each small crystal, with staggered starts. |
| iceHoldSeconds | 0.94 | Minimum hold after a crystal finishes growing. |
| shatterSeconds | 2.15 | Earliest break time; each crystal also respects its minimum growth and hold times. |
| shardLifetimeSeconds | 0.76 | Maximum shard lifetime, shortened when a shard reaches the floor. |
| crystalClusterCount | 4 | Number of attached crystal masses on the target. |
| crystalsPerCluster | 8 | Unequal points sharing each cluster root and faceted foundation. |
| crystalSizeMultiplier | 1.12 | Size of the attached points and shared foundation. |
| crystalTipShoulderFraction | 0.30 | Start of the long tapered tip along each point; smaller values sharpen the silhouette. |
| shatterSpeedMultiplier | 1.50 | Balanced launch speed between the original and strongest shatter. |
| shatterOutwardKickFraction | 0.45 | Half of the strongest outward impulse, relative to target height. |
| shatterDepthKickFraction | 0.10 | Half of the strongest additional depth impulse. |
| shatterFogOpacity | 0.64 | Density of the expanding freezing vapor at breakup. |
| shatterSparklesPerCluster | 20 | Fine shimmering particles released by each breaking cluster. |
| shatterFogLifetimeSeconds | 0.52 | Time each cluster's shatter cloud expands and clears. |
| fogOpacity | 0.50 | Opacity scale of the pale, layered freezing mist. |
| fogRadiusFraction | 0.13 | Mist puff size relative to local battler height. |
| fogLifetimeSeconds | 0.58 | How long each emitted wisp expands and drifts. |
| chargeParticleCount | 30 | Inward-gathering frost flecks during charge. |
| chargeGatherRadiusFraction | 0.64 | Initial gathering radius relative to caster height. |
| chargeCoreMultiplier | 1.50 | Bright core/star scale compared with the prior charge. |
| chargeFogOpacity | 0.56 | Opacity scale of the gathering fog; independent of beam fog. |
| chargeRingCount | 4 | Number of staggered ice-energy rings contracting toward the source. |
| chargeRingRadiusFraction | 0.62 | Starting ring radius relative to caster height. |
| chargeRingOuterOpacity | 0.22 | Relative opacity far from the source; rises smoothly to full opacity as rings contract inward. |
| impactBurstRadiusFraction | 0.72 | Maximum reach of the first icy impact blast. |
| impactFrostPlumeMultiplier | 1.45 | Size of the spreading impact fog blooms. |
| impactFogOpacity | 0.58 | Opacity of the added foreground frost fog at the contact point. |
| impactLightRayCount | 10 | Pulsing white/cyan light shafts radiating throughout impact. |
| impactLightRayReachFraction | 0.90 | Ray reach relative to target height. |
| beamShimmerStrength | 0.85 | Strength of the beam surface brightness variation. |
| beamShimmerSpeed | 21.0 | Phase speed of the traveling beam highlights. |
| beamCoreRadiusFraction | 0.42 | Bright central-spine radius relative to the existing beam radius. |
| beamCoreShimmerSpeed | 26.0 | Phase speed of moving highlights in the white central spine. |
| chargeWhiteSparkleCount | 22 | Additional pure-white glints converging on the source. |
| beamSparkleSpacingSeconds | 0.13 | Emission interval at each of nine positions along the traveled beam. |
| impactSparkleSpacingSeconds | 0.04 | Interval between bursts of twelve white target ricochets. |
| impactSparklesPerBurst | 12 | White particles emitted per impact burst. |
| impactSparkleSpeedMultiplier | 3.25 | Impact ejection speed relative to the prior version. |
| sparkleLifetimeSeconds | 0.58 | Maximum falling/ricochet sparkle life; glints also clear when reaching the floor. |
| sparkleSizeMultiplier | 0.40 | Small pinpoint scale, with occasional tiny peak glints; paths and particle counts unchanged. |
| sparkleShimmerRate | 0.55 | Multiplier of each particle phase for independent smooth brightness pulses. |
| framesPerSecond | 20 | Render rate. |
| endSeconds | 3.20 | Final sampled time; leave enough room for fragments to clear. |

Beam contact is extended by 0.40 seconds: first impact stays at 0.63 seconds, while the last beam energy reaches the target at 1.73 instead of 1.33 seconds. Crystal hold and shatter include that 0.40-second extension plus the latest 0.20-second breakup delay, with the earliest break at 2.15 seconds. The charge, beam travel speed, crystal growth and fragment motion are unchanged. Each cluster starts with a broad, low ice patch. Its points grow out of that shared root, hold together and shatter as a group. Crystal growth starts shortly after impact. Each crystal breaks after the later of the configured shatter time or its individual growth/hold interval. Groups are staggered by up to 0.07 seconds. The current effect clears before 3.07 seconds, with transparent room at the end.

The beam has a solid white center, pale icy cyan body, translucent outer light and flowing fine highlights. Crystal facets use shaded blue undersides and bright white tips. Rotating fragments use the same palette.

## Render

From the extracted folder:

```powershell
py -m pip install numpy Pillow
py .\source\render_ice_beam.py
```

Atlases and timing JSON are written to **source/assets**. Preview PNG frames appear in **source/outgoing** and **source/incoming**. Keep the controls, arena.png, near.png and far.png beside the renderer.

To paint a frame manually, crop its 320 by 205 tile from each layer atlas. Column = frame index modulo 8; row = frame index divided by 8 and rounded down. Preserve RGBA transparency, frame canvas size and compositing order.

This kit supplies assets and editable source. Installing it into an existing Showdown customization requires the current CSS/userscript or game animation code so the move can trigger these frames correctly.
