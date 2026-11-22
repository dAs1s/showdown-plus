// ==UserScript==
// @name         Showdown Plus - pin controls
// @namespace    showdown-custom
// @version      2.43.2
// @description  Measures the battle window for the Stylus style (controls stay in place at any zoom), adds a pixelate filter for the background/weather, and finds each Pokémon's feet so its shadow sits right under it.
// @homepageURL  https://github.com/dasmins/showdown-plus
// @supportURL   https://github.com/dasmins/showdown-plus/issues
// @updateURL    https://raw.githubusercontent.com/dasmins/showdown-plus/main/userscript/showdown-pin-controls.user.js
// @downloadURL  https://raw.githubusercontent.com/dasmins/showdown-plus/main/userscript/showdown-pin-controls.user.js
// @match        https://play.pokemonshowdown.com/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

(function () {
  'use strict';

  // the style shows a note in the battle when this is missing or is not the version it was written for
  document.documentElement.dataset.psPin = '2.36.0';

  // ---------- BACKGROUND & WEATHER FILTERS ----------
  // These are now set in your STYLUS style (in its :root block), not here:
  //   --bg-pixel, --bg-pixel-strength, --bg-darks, --bg-mids, --bg-lights,
  //   --wx-pixel, --wx-pixel-strength,
  //   --ui-pixel, --ui-pixel-strength
  // The script reads them and rebuilds the filters whenever you change them,
  // so edits show up live — no refresh needed. The numbers below are only used
  // if the style doesn't set them.
  const DEFAULTS = {
    bgPixel: 4,          // background block size (2 = finest, 4 = retro, 6+ = chunky)
    bgStrength: 1,       // background: how blocky (0 = smooth, 1 = full blocks)
    bgDarks: 1.65,       // background: deeper darks (1 = none, 1.3 = noticeable, 1.6+ = moody)
    bgMids: 1,           // background: mid-tones (1 = none, above 1 = brighter, below 1 = darker)
    bgLights: 1,         // background: brighter lights (1 = none, 0.8 = brighter highlights)
    wxPixel: 2,          // weather block size
    wxStrength: 1,       // weather: how blocky
    uiPixel: 2,          // UI (HP bars, names, VS sign, buttons, text) block size
    uiStrength: 1,       // UI: how blocky
  };

  // a number as it applies inside one battle: a map's own block (.battle[data-ps-map="N"] { ... }) can override the
  // main style's value there. (Read again after each settings update: kept per battle until then.)
  let mapNumGen = 0;
  const mapNums = new WeakMap();
  function battleNumber(battle, name, fallback) {
    if (!battle) return readNumber(name, fallback);
    let c = mapNums.get(battle);
    if (!c || c.gen !== mapNumGen || c.map !== battle.dataset.psMap) { c = { gen: mapNumGen, map: battle.dataset.psMap, cs: getComputedStyle(battle), v: {} }; mapNums.set(battle, c); }
    if (!(name in c.v)) { const n = parseFloat(c.cs.getPropertyValue(name).trim()); c.v[name] = Number.isFinite(n) ? n : NaN; }
    return Number.isFinite(c.v[name]) ? c.v[name] : fallback;
  }
  function readNumber(name, fallback) {
    const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const n = parseFloat(raw);
    return Number.isFinite(n) ? n : fallback;
  }

  // builds one pixelate filter with its own block size and strength
  function pixelateFilter(id, pixel, strength) {
    const size = Math.max(2, Math.round(pixel));
    const half = Math.max(1, Math.floor(size / 2));
    const k2 = Math.min(1, Math.max(0, strength));
    const k3 = 1 - k2;
    return (
      '<filter id="' + id + '" x="0" y="0" width="100%" height="100%">' +
        '<feFlood x="' + half + '" y="' + half + '" width="1" height="1"/>' +
        '<feComposite width="' + size + '" height="' + size + '"/>' +
        '<feTile result="grid"/>' +
        '<feComposite in="SourceGraphic" in2="grid" operator="in"/>' +
        '<feMorphology operator="dilate" radius="' + half + '" result="blocks"/>' +
        // blend the blocky version with the original for a finer look
        '<feComposite in="blocks" in2="SourceGraphic" operator="arithmetic"' +
          ' k1="0" k2="' + k2 + '" k3="' + k3 + '" k4="0"/>' +
      '</filter>'
    );
  }

  // a filter that changes nothing (a setting at its neutral value still needs its filter to exist)
  function plainFilter(id) {
    // (colour-interpolation-filters="sRGB": without it the browser works out the contrast / saturation that follow it
    // in the style in a different colour space, and the sprite comes out harsher and darker)
    return '<filter id="' + id + '" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB"><feOffset dx="0" dy="0"/></filter>';
  }

  // a thinner black border: the outermost r px of the sprite's shape are taken off, which is the outer part of the
  // dark line the artist drew round it; what is left of that line stays as black as it was. Nothing inside the sprite
  // is touched (no colour, no dark area, no inner line). Parts too thin to survive that (a whisker or an antenna one
  // pixel wide) are kept whole.
  function thinFilter(id, r) {
    if (!(r > 0.01)) return plainFilter(id);
    const rad = r.toFixed(3);
    return '<filter id="' + id + '" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">' +
      '<feMorphology in="SourceAlpha" operator="erode" radius="' + rad + '" result="smaller"/>' +      // the shape, r px smaller all round
      '<feMorphology in="smaller" operator="dilate" radius="' + rad + '" result="regrown"/>' +         // ...grown back: everything but the thin parts
      '<feComposite in="SourceAlpha" in2="regrown" operator="out" result="fine"/>' +                   // the thin parts
      '<feMerge result="keep"><feMergeNode in="smaller"/><feMergeNode in="fine"/></feMerge>' +
      '<feComposite in="SourceGraphic" in2="keep" operator="in"/></filter>';
  }

  // ---------- GOLD SPARKLES ON THE SUN-LIT BORDER ----------
  // Sparkles are drawn by a filter on the sprite itself, so they sit exactly on its border in whatever frame of its
  // animation is showing, and move with it. The filter:
  //   1 finds the lit part of the border: light is cast from the map's sun toward the sprite as straight rays, and a
  //     border pixel is lit when nothing of the sprite lies between it and the sun (the sprite's shape is swept away
  //     from the sun; what the sweep does not cover is what the rays hit first). Of that, only the very outermost
  //     ring, one screen pixel wide, is used: the outer edge of the black border.
  //   2 lays a flowing field of brightness over that ring (made from the browser's own noise): the gleam
  //   3 grows four points on the gleam's brightest spots: the stars. Pale in the middle, gold at the tips.
  function hashOf(text) {
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  const sparkleOf = {};      // filter id -> { gain, off, a, b } for the stepper, or null
  // The gleam is steered by two slowly turning angles (a, b). They mix three layers of the browser's own noise into
  // one field, and the mix decides how bright each spot of the edge is. As the angles turn the field flows, so every
  // star comes up and dies away gradually. The two turn at different rates, so the pattern takes over a minute to
  // come round again. (The noise's fourth layer picks which sparkles are the slightly orange ones.)
  const TURN_A = 2 * Math.PI / 22, TURN_B = 2 * Math.PI / 29;        // per step (a unit steps every 150 ms: 3.3 s and 4.4 s a turn)
  const NOISE_SPREAD = 0.106;                                        // how much the browser's noise varies round its middle (measured)
  // the numbers of the mixing step: the edge's brightness = gain x (the mix of the three noise layers) + off
  function mixValues(o) {
    const tilt = 0.9 * Math.sin(o.b);
    const w = [Math.cos(o.a) * Math.cos(tilt) * o.gain, Math.sin(o.a) * Math.cos(tilt) * o.gain, Math.sin(tilt) * o.gain];
    const off = o.off - 0.5 * (w[0] + w[1] + w[2]);
    return '0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  ' + w.map((x) => x.toFixed(4)).join(' ') + ' 0 ' + off.toFixed(4);
  }
  // a sparkle's colour follows its strength (six steps, faint to strong); `st` = its strength when fully lit.
  // sat: how strong the colour is (1 = as designed; below 1 = each step is pulled toward the grey of the same
  // lightness, so the spread between its strongest and weakest channel shrinks by exactly that much)
  const SPARK = {
    gold: [[1, 1, 1, 1, 1, 1], [0.66, 0.70, 0.78, 0.86, 0.94, 0.99], [0.16, 0.20, 0.32, 0.50, 0.70, 0.88]],
    orange: [[1, 1, 1, 1, 1, 1], [0.56, 0.60, 0.68, 0.76, 0.84, 0.90], [0.10, 0.12, 0.20, 0.34, 0.50, 0.66]],
    emerald: [[0.18, 0.24, 0.34, 0.46, 0.58, 0.70], [0.74, 0.80, 0.87, 0.93, 0.97, 1], [0.28, 0.32, 0.40, 0.50, 0.60, 0.72]],
    lime: [[0.52, 0.58, 0.66, 0.76, 0.86, 0.94], [0.82, 0.86, 0.91, 0.95, 0.98, 1], [0.10, 0.14, 0.22, 0.34, 0.48, 0.62]],
    sea: [[0.04, 0.08, 0.16, 0.30, 0.46, 0.62], [0.68, 0.74, 0.82, 0.90, 0.96, 1], [0.56, 0.62, 0.70, 0.80, 0.88, 0.94]],
  };
  // bright: the colour itself made darker or lighter (1 = as designed)
  // floor, low: the gleam never falls under `floor` on the lit edge (see sparkleFilter); this colour treats that
  // dimmest point as strength `low` instead, so one colour can stay brighter at the bottom of its cycle than another
  function sparkleColours(input, result, name, st, sat, bright, floor, low) {
    const out = sparkleTable(name, st, sat, bright, floor, low).map((t) => t.map((x) => x.toFixed(3)));
    return '<feComponentTransfer in="' + input + '" result="' + result + '">' +
      '<feFuncR type="table" tableValues="' + out[0].join(' ') + '"/><feFuncG type="table" tableValues="' + out[1].join(' ') + '"/><feFuncB type="table" tableValues="' + out[2].join(' ') + '"/>' +
      '<feFuncA type="table" tableValues="' + out[3].join(' ') + '"/>' +
      '</feComponentTransfer>';
  }
  // (the same tables as numbers: red, green, blue and opacity at 21 strengths from 0 to 1)
  function sparkleTable(name, st, sat, bright, floor, low) {
    const c = SPARK[name], alpha = [0, 0.3, 0.62, 0.85, 1, 1], out = [[], [], [], []];
    const at = (table, x) => { const i = Math.min(4, Math.floor(x * 5)), f = x * 5 - i; return table[i] + (table[i + 1] - table[i]) * f; };
    for (let n = 0; n <= 20; n++) {
      const a = n / 20;
      // the strength this colour shows at gleam level a
      const e = floor > 0 && low > floor ? (a >= floor ? low + (1 - low) * (a - floor) / (1 - floor) : a * low / floor) : a;
      const rgb = [at(c[0], e), at(c[1], e), at(c[2], e)];
      const grey = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2];
      for (let k = 0; k < 3; k++) out[k].push(Math.min(1, Math.max(0, (grey + (rgb[k] - grey) * sat) * bright)));
      out[3].push(n === 0 ? 0 : at(alpha, e) * st);
    }
    return out;
  }
  // How many stars open at a moment. Two things set it: how far apart the star places are (the noise's grain,
  // `gap` screen dots) and how much of the edge is bright enough to open into a star (`share`). Measured: along an
  // edge the stars open at a moment come to about STARS(share) / gap per screen dot. `want` = stars wanted per
  // screen dot; d = a star's middle, in dots. The places are kept between 1.5 and 3 star sizes apart (closer and
  // the stars run together), the share between 10% and 45% of the edge.
  const STARS = [[0.10, 0.21], [0.16, 0.26], [0.30, 0.35], [0.45, 0.42]];    // share -> stars per place (measured on all four characters)
  function starsAt(share) {
    for (let i = 1; i < STARS.length; i++) {
      if (share <= STARS[i][0]) { const a = STARS[i - 1], b = STARS[i]; return a[1] + (b[1] - a[1]) * (share - a[0]) / (b[0] - a[0]); }
    }
    return STARS[STARS.length - 1][1];
  }
  function starPlan(want, d) {
    const lo = Math.max(2, 1.5 * d), hi = 3 * d;
    const gap = Math.min(hi, Math.max(lo, starsAt(0.3) / want));           // first by spacing, at a middling share...
    const need = want * gap;                                               // ...then the share that gives the number at that spacing
    let share = STARS[0][0];
    if (need >= STARS[STARS.length - 1][1]) share = STARS[STARS.length - 1][0];
    else {
      for (let i = 1; i < STARS.length; i++) {
        if (need <= STARS[i][1]) { const a = STARS[i - 1], b = STARS[i]; share = need <= a[1] ? a[0] : a[0] + (b[0] - a[0]) * (need - a[1]) / (b[1] - a[1]); break; }
      }
    }
    return { gap: gap, share: share };
  }
  // dots: how many of the screen's own dots one of the element's own px covers (its size on the page x the page's zoom
  // x the screen's density). Sizes below are whole screen dots, so the stars stay crisp at any zoom.
  // second: which way the map's second light is (the tower's serpent), or null while it is not out; its level 0 to 1
  // pixel: above 0 = drawn in flat square blocks the size of a star's middle, on one grid (pixel art), not in soft dots
  // look: for the gold (and orange) sparkles and for the green ones, each its own: `low` = how bright a sparkle stays
  // at the dimmest point of its cycle (0 = it goes out completely, 1 = it never dims), `sat` = colour strength,
  // `bright` = brightness (both 1 = as designed)
  function sparkleFilter(id, aim, wb, px, count, size, strength, dots, points, second, secondLevel, pixel, look) {
    const low = Math.min(look.gold.low, look.green.low);          // (the gleam's own floor: the lower of the two)
    if (!aim || !(count > 0) || !(strength > 0) || !(size > 0) || !(dots > 0)) { sparkleOf[id] = null; return plainFilter(id); }
    const ax = -aim.ux, ay = -aim.uy;                          // away from the sun
    const n3 = (x) => x.toFixed(5);
    // one star block: `size` battle px, as a whole number of screen dots (at least one)
    const perPx = dots / aim.scale;                            // screen dots to one battle px
    let d = Math.max(1, Math.round(size * perPx));
    const blocky = pixel > 0 && d >= 2;                        // (a star one screen dot thick is a block already)
    // (blocks are an odd number of dots across: 3, 5, 7... Each has one middle dot to take its value from, so it comes
    // out one flat colour with clean edges)
    if (blocky) d = Math.max(3, 2 * Math.round((size * perPx - 1) / 2) + 1);
    // how far a star's points reach from its middle: `points` star sizes, in whole screen dots (0 = no points: the
    // star is a plain square)
    const reach = Math.max(0, Math.round(points * d));
    const long = points >= 1.5 && reach >= 2;                  // long points are drawn in two steps: strong near the middle, fainter at the tips
    const r1 = (d + 0.02) / dots, rIn = ((long ? Math.max(1, Math.round(reach / 2)) : reach) + 0.02) / dots, rOut = (reach + 0.02) / dots;
    const st = Math.min(1, strength);
    // the field is roughly bell-shaped: the level below which a share q of it lies, in spreads from its middle
    const levelBelow = function (q) {          // (a standard approximation of the bell curve's inverse)
      const t = Math.sqrt(-2 * Math.log(Math.min(q, 1 - q)));
      const v = t - (2.515517 + 0.802853 * t + 0.010328 * t * t) / (1 + 1.432788 * t + 0.189269 * t * t + 0.001308 * t * t * t);
      return q < 0.5 ? -v : v;
    };
    // 85% of the lit edge gleams at a moment
    const dark = levelBelow(0.15) * NOISE_SPREAD, full = 1.8 * NOISE_SPREAD;  // the field's level where the edge starts to gleam, and where it is at full strength
    // how many stars: `count` per 100 battle px of lit edge (see starPlan)
    const plan = starPlan(count / (100 * perPx), d);
    const gap = plan.gap;
    const floor = Math.min(0.95, Math.max(0, low || 0));
    // where the gleam opens into a star, as a strength (with a floor under the gleam, every strength sits that much higher)
    const open = floor + (1 - floor) * Math.min(0.9, Math.max(0.2, (levelBelow(1 - plan.share) * NOISE_SPREAD - dark) / (full - dark)));
    const was = sparkleOf[id];
    const o = { gain: 1 / (full - dark), off: -dark / (full - dark), a: was ? was.a : (hashOf(id) % 628) / 100, b: was ? was.b : (hashOf(id + 'b') % 628) / 100 };
    let f = '<filter id="' + id + '" x="-6%" y="-6%" width="112%" height="112%" color-interpolation-filters="sRGB">', nodes = '';
    for (let i = 0; i < 10; i++) {
      f += '<feOffset in="SourceAlpha" dx="' + n3(ax * (wb + i * px)) + '" dy="' + n3(ay * (wb + i * px)) + '" result="c' + i + '"/>';
      nodes += '<feMergeNode in="c' + i + '"/>';
    }
    f += '<feMerge result="shade">' + nodes + '</feMerge>' +
      '<feComposite in="SourceAlpha" in2="shade" operator="out" result="' + (second ? 'litSun' : 'lit') + '"/>';   // what the rays hit first
    if (second) {
      // the same for the map's second light (the serpent): what ITS rays hit first. `-glow` holds how far it is out
      // (0 to 1; the stepper below keeps it up to date), so its part of the edge fades in and out with it.
      const bx = -second.ux, by = -second.uy; nodes = '';
      for (let i = 0; i < 10; i++) {
        f += '<feOffset in="SourceAlpha" dx="' + n3(bx * (wb + i * px)) + '" dy="' + n3(by * (wb + i * px)) + '" result="e' + i + '"/>';
        nodes += '<feMergeNode in="e' + i + '"/>';
      }
      f += '<feMerge result="shade2">' + nodes + '</feMerge>' +
        '<feComposite in="SourceAlpha" in2="shade2" operator="out" result="lit2full"/>' +
        '<feComponentTransfer in="lit2full" result="lit2"><feFuncA id="' + id + '-glow" type="linear" slope="' + secondLevel.toFixed(3) + '"/></feComponentTransfer>' +
        '<feMerge result="lit"><feMergeNode in="litSun"/><feMergeNode in="lit2"/></feMerge>' +           // lit by either light
        // where the sparkles are the second light's colour: on and round what it lights (wide enough for a star's points)
        '<feMorphology in="lit2" operator="dilate" radius="' + n3((reach + d + 0.02) / dots) + '" result="' + (blocky ? 'zone2fine' : 'zone2') + '"/>';
    }
    // In blocks: a grid of sample points, one per block (the block's middle dot, or its middle 2 x 2 dots when the
    // block is an even number of dots across). `held(x)` keeps x at those points only and spreads each point's value
    // over its whole block. The noise, the lit ring and the second light's zone all go through it, so everything made
    // from them (the gleam, the stars, their colours) comes out in flat blocks on the one grid.
    const seedDots = d % 2 ? 1 : 2, spread = (d - seedDots) / 2;
    const held = (input, result) => (spread > 0 ?
      '<feComposite in="' + input + '" in2="grid" operator="in" result="' + result + 'At"/><feMorphology in="' + result + 'At" operator="dilate" radius="' + n3((spread + 0.02) / dots) + '" result="' + result + '"/>' :
      '<feComposite in="' + input + '" in2="grid" operator="in" result="' + result + '"/>');
    if (blocky) {
      // (the grid starts where a whole screen dot starts: a little before the picture's own corner, by the part of
      // a dot that corner sits at; a mirrored picture runs the other way across)
      const ox = (aim.mirrored ? (aim.gx || 0) : -(aim.gx || 0)) / dots, oy = -(aim.gy || 0) / dots;
      // (the sample point is given a hair inside its whole dots: the browser rounds its box outward to whole dots, and
      // one that spilled over by a rounding error would grow by a whole dot. The block itself is given exactly: the
      // grid repeats at exactly the block's size)
      const hair = 0.2 / dots, n6 = (x) => x.toFixed(6);
      f += '<feFlood flood-color="#fff" x="' + n6(ox + spread / dots + hair) + '" y="' + n6(oy + spread / dots + hair) + '" width="' + n6(seedDots / dots - 2 * hair) + '" height="' + n6(seedDots / dots - 2 * hair) + '" result="seed"/>' +
        '<feOffset in="seed" dx="0" dy="0" x="' + n6(ox) + '" y="' + n6(oy) + '" width="' + n6(d / dots) + '" height="' + n6(d / dots) + '" result="cell"/>' +
        '<feTile in="cell" result="grid"/>';
      if (second) f += held('zone2fine', 'zone2');
    }
    f += '<feMorphology in="SourceAlpha" operator="erode" radius="' + n3(r1) + '" result="inner"/>' +
      '<feComposite in="lit" in2="inner" operator="out" result="' + (blocky ? 'edgeFine' : 'edge') + '"/>' +   // ...of that, the outermost ring, one block wide
      // the browser's own noise, its grain as wide as the stars are apart, drawn at the screen's own dots and fixed to the sprite
      '<feTurbulence type="fractalNoise" baseFrequency="' + n3(dots / gap) + '" numOctaves="1" seed="' + (hashOf(id + 's') % 9000 + 1) + '" result="' + (blocky ? 'noiseFine' : 'noise') + '"/>' +
      (blocky ? held('edgeFine', 'edge') + held('noiseFine', 'noise') : '') +
      '<feColorMatrix id="' + id + '-mix" in="noise" type="matrix" values="' + mixValues(o) + '" result="' + (floor > 0 ? 'fieldRaw' : 'field') + '"/>' +     // the flowing field (the stepper below turns it)
      // (the floor: the field's dark end is lifted, so a sparkle dims to `low` at the bottom of its cycle and no further)
      (floor > 0 ? '<feComponentTransfer in="fieldRaw" result="field"><feFuncA type="table" tableValues="' + floor.toFixed(3) + ' 1"/></feComponentTransfer>' : '') +
      '<feComposite in="field" in2="edge" operator="in" result="gleam"/>' +                             // the gleam: the field, kept only on the outer ring
      // the brightest spots of the gleam (above `open`) grow four points: they become the stars. The points grow
      // with the spot's strength, so a star opens and closes gradually.
      '<feComponentTransfer in="gleam" result="peak"><feFuncA type="linear" slope="' + (1 / (1 - open)).toFixed(3) + '" intercept="' + (-open / (1 - open)).toFixed(3) + '"/></feComponentTransfer>' +
      '';
    if (reach > 0) {
      f += '<feMorphology in="peak" operator="dilate" radius="' + n3(rIn) + ' 0" result="h1"/>' +
        '<feMorphology in="peak" operator="dilate" radius="0 ' + n3(rIn) + '" result="v1"/>' +
        '<feMerge result="arm1"><feMergeNode in="h1"/><feMergeNode in="v1"/></feMerge>' +
        '<feComponentTransfer in="arm1" result="point1"><feFuncA type="linear" slope="' + (long ? 0.75 : 0.55) + '"/></feComponentTransfer>';
    }
    if (long) {
      f += '<feMorphology in="peak" operator="dilate" radius="' + n3(rOut) + ' 0" result="h2"/>' +
        '<feMorphology in="peak" operator="dilate" radius="0 ' + n3(rOut) + '" result="v2"/>' +
        '<feMerge result="arm2"><feMergeNode in="h2"/><feMergeNode in="v2"/></feMerge>' +
        '<feComponentTransfer in="arm2" result="point2"><feFuncA type="linear" slope="0.4"/></feComponentTransfer>';
    }
    f += '<feMerge result="star">' + (long ? '<feMergeNode in="point2"/>' : '') + (reach > 0 ? '<feMergeNode in="point1"/>' : '') + '<feMergeNode in="gleam"/></feMerge>' +
      '<feColorMatrix in="star" type="matrix" values="0 0 0 1 0  0 0 0 1 0  0 0 0 1 0  0 0 0 1 0" result="starN"/>' +
      // gold: amber-gold where faint (the tips, a star coming up or dying away), pale gold where strong
      sparkleColours('starN', 'gold', 'gold', st, look.gold.sat, look.gold.bright, floor, look.gold.low) +
      // about a third of the sparkles are slightly orange instead: picked by the noise's fourth layer (so which ones
      // has nothing to do with how bright they are), with a soft edge
      sparkleColours('starN', 'orange', 'orange', st, look.gold.sat, look.gold.bright, floor, look.gold.low) +
      '<feColorMatrix in="noise" type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 23.6 -12.18" result="warm"/>' +
      '<feComposite in="gold" in2="warm" operator="out" result="goldPart"/>' +
      '<feComposite in="orange" in2="warm" operator="in" result="orangePart"/>' +
      '<feComposite in="goldPart" in2="orangePart" operator="arithmetic" k1="0" k2="1" k3="1" k4="0" result="' + (second ? 'sunSpark' : 'spark') + '"/>';
    if (second) {
      // green where the second light reaches: emerald where faint, light green where strong. Of these, about a
      // third are a yellower lime green and about a third a bluer sea green (picked by the noise's fourth layer:
      // its high end and its low end)
      f += sparkleColours('starN', 'emerald', 'emerald', st, look.green.sat, look.green.bright, floor, look.green.low) +
        sparkleColours('starN', 'lime', 'lime', st, look.green.sat, look.green.bright, floor, look.green.low) +
        sparkleColours('starN', 'sea', 'sea', st, look.green.sat, look.green.bright, floor, look.green.low) +
        '<feColorMatrix in="noise" type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 -23.6 11.42" result="cool"/>' +
        '<feComposite in="emerald" in2="warm" operator="out" result="em1"/>' +
        '<feComposite in="em1" in2="cool" operator="out" result="emeraldPart"/>' +
        '<feComposite in="lime" in2="warm" operator="in" result="limePart"/>' +
        '<feComposite in="sea" in2="cool" operator="in" result="seaPart"/>' +
        '<feComposite in="emeraldPart" in2="limePart" operator="arithmetic" k1="0" k2="1" k3="1" k4="0" result="gr1"/>' +
        '<feComposite in="gr1" in2="seaPart" operator="arithmetic" k1="0" k2="1" k3="1" k4="0" result="green"/>' +
        '<feComposite in="sunSpark" in2="zone2" operator="out" result="sunPart"/>' +
        '<feComposite in="green" in2="zone2" operator="in" result="greenPart"/>' +
        '<feComposite in="sunPart" in2="greenPart" operator="arithmetic" k1="0" k2="1" k3="1" k4="0" result="spark"/>';
    }
    sparkleOf[id] = o;
    return f + '<feMerge><feMergeNode in="SourceGraphic"/><feMergeNode in="spark"/></feMerge></filter>';
  }
  // the stepper: one of the four units at a time takes its next step (each unit --sun-sparkle-steps times a second,
  // about every 150 ms as set): its two angles turn a little and the mixing step gets its new numbers; while the
  // map's second light is out, its level is brought up to date too.
  // (Each step makes the browser draw that unit again. Stepped like this it costs a fixed number of redraws;
  // animating it inside the filter would redraw on every screen frame.)
  //
  // KEEPING THE GAME SMOOTH. Those redraws are by far the most expensive thing this style does (the whole filter runs
  // again over the unit, at the screen's own dots). So:
  //   --sun-sparkle-rest: 1   while a Pokémon is moving or an effect is on screen, the sparkles hold still (the
  //                           moves and effects get the whole frame)
  //   --sun-sparkle-auto: 1   the screen's frame rate is watched; when it falls below --sun-sparkle-min-fps while
  //                           the sparkles are stepping, the steps are spaced further apart (up to 40 times) until it
  //                           holds, and brought back when there is room again
  // Alt+P shows a small meter in the tab's title (frames a second, the longest frame, how fast the sparkles step).
  // Alt+Shift+P runs a 9 second test: 3 s with everything on at full rate, 3 s with the sparkles standing still,
  // 3 s without them; its three results are then shown on the page.
  const SPARKLE_IDS = ['ps-sun-foe', 'ps-sun-mine', 'ps-sun-tfoe', 'ps-sun-tmine'];
  let sparkleTick = 0;
  let sparkCanvas = 1, sparkSet = null, hoverOn = 1;
  let sparkSteps = 6.6, sparkRest = 1, sparkAuto = 1, sparkMinFps = 50, perfShow = 0, perfFlip = false;
  let busyAt = -1e9;                       // when something in a battle last moved (a Pokémon, an effect)
  const perf = { fps: 0, worst: 0, rate: 0, slow: 1, gap: 16, n: 0, from: 0, long: 0, steps: 0, last: 0, held: false, still: false, off: false, test: null, result: '' };
  const TEST = [['everything on, full rate', 'all'], ['sparkles standing still', 'still'], ['no sparkles', 'off']];
  function sparkleStep() {
    if (document.hidden) return;
    const now = performance.now();
    const level = secondLightLevel(now);
    if ((level > 0) !== secondLight.built) { try { updateFilters(); } catch (e) { /* next round */ } }    // it has just come out, or gone: the filters gain or lose its part
    if (sparkCanvas > 0) {                  // drawn on canvases: nothing to hold back for, a step costs next to nothing
      perf.held = perf.still;
      const role = SPARKLE_IDS[sparkleTick++ % 4].slice(7);
      if (!perf.held && !perf.off && sparkUnits.size) { stepSparkRole(role); perf.steps++; }
      return;
    }
    perf.held = perf.still || (sparkRest > 0 && !perf.test && now - busyAt < Math.max(250, 3 * perf.gap));   // (on a slow screen the frames that notice movement are further apart)
    const id = SPARKLE_IDS[sparkleTick++ % 4], o = sparkleOf[id];
    if (!o) return;
    const glow = document.getElementById(id + '-glow'), lv = level.toFixed(3);
    const fade = !!glow && glow.getAttribute('slope') !== lv;
    if (perf.held && !fade) return;
    if (!perf.held) {
      o.a = (o.a + TURN_A) % (2 * Math.PI); o.b = (o.b + TURN_B) % (2 * Math.PI);
      const mix = document.getElementById(id + '-mix');
      if (mix) mix.setAttribute('values', mixValues(o));
    }
    if (fade) glow.setAttribute('slope', lv);
    perf.steps++;
  }
  (function stepLoop() {
    setTimeout(() => { safely(sparkleStep); stepLoop(); }, Math.max(8, 250 / sparkSteps * (perf.test || sparkCanvas > 0 ? 1 : perf.slow)));
  })();
  function perfPhase(now) {                 // the test: its three parts, one after the other
    const t = perf.test, i = Math.floor((now - t.from) / 3000);
    if (i !== t.i) {
      if (t.i >= 0 && t.n > 0) t.out.push(TEST[t.i][0] + ' ' + (t.n * 1000 / t.time).toFixed(0) + ' fps (longest frame ' + t.long.toFixed(0) + ' ms)');
      t.i = i; t.n = 0; t.time = 0; t.long = 0;
      const mode = i < TEST.length ? TEST[i][1] : '';
      perf.still = mode === 'still';
      const off = mode === 'off';
      if (off !== perf.off) { perf.off = off; lastFilterKey = ''; safely(updateFilters); sparkDirtyAll(); }
      if (i >= TEST.length) { perf.result = t.out.join(' | '); perf.test = null; perf.slow = 1; console.log('[showdown style] speed test: ' + perf.result); }
    }
  }
  function countFrame(now) {               // (called on every screen frame)
    const gap = now - perf.last; perf.last = now;
    if (gap < 1000) perf.gap = gap;
    if (document.hidden || gap > 1000) { perf.n = 0; perf.from = now; perf.long = 0; perf.steps = 0; return; }
    if (perf.test) {
      const t = perf.test;
      if (now - t.from - t.i * 3000 > 600) { t.n++; t.time += gap; if (gap > t.long) t.long = gap; }   // (each part's first 0.6 s is left out)
      perfPhase(now);
    }
    perf.n++; if (gap > perf.long) perf.long = gap;
    if (now - perf.from < 500) return;
    const span = now - perf.from;
    perf.fps = perf.n * 1000 / span; perf.worst = perf.long; perf.rate = perf.steps * 1000 / span / 4;
    if (sparkAuto > 0 && !perf.test && !(sparkCanvas > 0)) {
      if (perf.fps < sparkMinFps) { if (perf.steps > 0) perf.slow = Math.min(40, perf.slow * (perf.fps < sparkMinFps / 2 ? 2 : 1.5)); }   // (slow frames with no sparkle step in them are not the sparkles' doing)
      else if (perf.fps >= sparkMinFps + 4 && !perf.held) perf.slow = Math.max(1, perf.slow / 1.2);
    } else if (!perf.test) perf.slow = 1;
    perf.n = 0; perf.from = now; perf.long = 0; perf.steps = 0;
    showMeter();
  }
  // The meter's running numbers go in the TAB'S TITLE, not on the page: anything that changes on the page can make the
  // browser draw the sparkle filters again, so a meter drawn there would slow down the very thing it measures. Only
  // the test's result is put on the page (once, when the test is over; Alt+P takes it away again).
  let ownTitle = '', pageTitle = null;
  function showMeter() {
    const on = (perfShow > 0) !== perfFlip || !!perf.test;
    if (on) {
      const line = perf.test ? 'testing ' + (perf.test.i + 1) + '/3: ' + (TEST[perf.test.i] || [''])[0] :
        perf.fps.toFixed(0) + ' fps, longest frame ' + perf.worst.toFixed(0) + ' ms, sparkles ' + perf.rate.toFixed(1) + '/s' +
        (perf.held ? ' (holding still)' : perf.slow > 1.01 ? ' (slowed x' + perf.slow.toFixed(1) + ')' : '');
      if (pageTitle === null || document.title.trim() !== ownTitle) pageTitle = document.title.replace(/^\[[^\]]*\]\s*/, '');   // (Showdown changed the title: keep its new one)
      ownTitle = ('[' + line + '] ' + pageTitle).trim();
      if (document.title.trim() !== ownTitle) document.title = ownTitle;
    } else if (pageTitle !== null) {
      if (document.title.trim() === ownTitle) document.title = pageTitle;
      pageTitle = null;
    }
    let box = document.getElementById('ps-perf');
    if (!perf.result) { if (box) box.remove(); return; }
    if (!box) { box = document.createElement('div'); box.id = 'ps-perf'; document.body.appendChild(box); }
    const text = 'speed test (Alt+P closes this)\n' + perf.result.split(' | ').join('\n');
    if (box.textContent !== text) box.textContent = text;
  }
  window.addEventListener('keydown', (e) => {
    if (e.altKey && !e.ctrlKey && !e.metaKey && (e.code === 'KeyP' || (e.key || '').toLowerCase() === 'p')) {
      if (e.shiftKey) { if (!perf.test) { perf.result = ''; perf.test = { from: performance.now(), i: -1, n: 0, time: 0, long: 0, out: [] }; } }
      else if (perf.result) perf.result = '';
      else perfFlip = !perfFlip;
      showMeter();
      e.preventDefault();
      e.stopPropagation();
    }
  }, true);

  // ---------- THE MAP'S SECOND LIGHT (the tower's serpent) ----------
  // Some maps have a second light that is only there for part of the picture's loop: the tower's serpent rises in
  // front of the sun, glowing green. The style says where it is (--mapN-serpent-x / -y, px in the 640 x 410 picture),
  // when it is out (--mapN-serpent-from / -to, seconds into the loop), how long it takes to come and go
  // (--mapN-serpent-fade) and how long the loop is (--mapN-loop).
  // A page cannot ask the browser which frame of an animated picture is showing. So, for such a map, this gives the
  // backdrop the very same picture again under a new #tag: the browser then starts its loop from the first frame,
  // and from that moment the frame showing follows from the clock. (The browser keeps an animated picture on the
  // clock, skipping frames when it is late. After the battle was out of sight, tab or room, it is started again.)
  const secondLight = { cfg: null, loop: null, built: false };
  const LOOP_LAG = 100;           // ms from handing the picture over to its first frame showing (measured: 0.1 to 0.2 s)
  let loopCount = 0;
  function secondLightLevel(now) {
    const c = secondLight.cfg, l = secondLight.loop;
    if (!c || !l || !l.ok) return 0;
    const at = (((now - l.t0) / 1000) % c.loop + c.loop) % c.loop;
    const fade = Math.max(0.05, c.fade);
    return Math.min(1, Math.max(0, Math.min((at - c.from) / fade, (c.to - at) / fade)));
  }
  function probeOf(inner) {          // a hidden stand-in for the backdrop: it shows what the styles give this map's backdrop
    let p = inner.querySelector(':scope > .backdrop[data-ps-probe]');
    if (!p) {
      p = document.createElement('div');
      p.className = 'backdrop'; p.dataset.psProbe = '1';
      p.style.setProperty('display', 'none', 'important');
      inner.appendChild(p);
    }
    return p;
  }
  function stopLoop(bd) {
    if (bd && bd._psLoop) { bd.style.removeProperty('background-image'); bd._psLoop = null; }
  }
  function startLoop(bd, inner, map) {
    const src = getComputedStyle(probeOf(inner)).backgroundImage;
    if (!/^url\("data:image\/gif/.test(src)) { stopLoop(bd); return null; }
    const tag = '#ps' + (++loopCount);
    bd.style.setProperty('background-image', src.slice(0, -2) + tag + '")', 'important');
    const l = { t0: performance.now() + LOOP_LAG, src: src, map: map, hiddenAt: 0, checked: performance.now(), ok: false };
    l.ok = getComputedStyle(bd).backgroundImage.slice(-(tag.length + 2)) === tag + '")';     // (if another style outranks this, the loop cannot be timed: no second light)
    bd._psLoop = l;
    if (!l.ok) bd.style.removeProperty('background-image');
    return l;
  }
  // called a few times a second: keeps the shown battle's loop timed, for a map that has a second light
  function timeTheLoop() {
    const battle = Array.from(document.querySelectorAll('.battle[data-ps-map]')).find((b) => b.offsetParent !== null);
    document.querySelectorAll('.battle .innerbattle > .backdrop:not([data-ps-probe])').forEach((bd) => {
      const b = bd.closest('.battle');
      if (bd._psLoop && (b !== battle || bd._psLoop.map !== b.dataset.psMap)) {
        if (b !== battle && bd._psLoop.map === b.dataset.psMap) { if (!bd._psLoop.hiddenAt) bd._psLoop.hiddenAt = performance.now(); }   // out of sight: note since when
        else stopLoop(bd);                                                                                                             // another map now
      }
    });
    const n = battle && battle.dataset.psMap;
    const cfg = n ? {
      x: readNumber('--map' + n + '-serpent-x', NaN), y: readNumber('--map' + n + '-serpent-y', NaN),
      from: readNumber('--map' + n + '-serpent-from', NaN), to: readNumber('--map' + n + '-serpent-to', NaN),
      fade: readNumber('--map' + n + '-serpent-fade', 0.5), loop: readNumber('--map' + n + '-loop', NaN),
    } : null;
    const inner = battle && battle.querySelector('.innerbattle'), bd = inner && inner.querySelector(':scope > .backdrop:not([data-ps-probe])');
    const wanted = cfg && bd && [cfg.x, cfg.y, cfg.from, cfg.to, cfg.loop].every(Number.isFinite) && cfg.loop > 0 && cfg.to > cfg.from && readNumber('--sun-rim', 1) > 0;
    if (!wanted) { if (bd) stopLoop(bd); secondLight.cfg = null; secondLight.loop = null; return; }
    const now = performance.now();
    let l = bd._psLoop;
    if (l && document.hidden) { if (!l.hiddenAt) l.hiddenAt = now; }
    else if (l && l.hiddenAt) { l = now - l.hiddenAt > 1000 ? null : l; if (l) l.hiddenAt = 0; }       // back in sight: after more than a second away, start it again
    if (l && l.ok && bd.style.getPropertyPriority('background-image') !== 'important') l = null;         // (Showdown reset the backdrop)
    if (l && now - l.checked > 3000) {                                                                  // has the map's picture itself changed (a new version of its style)?
      l.checked = now;
      if (getComputedStyle(probeOf(inner)).backgroundImage !== l.src) l = null;
    }
    if (!l) l = startLoop(bd, inner, n);
    secondLight.cfg = cfg; secondLight.loop = l;
  }
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && secondLight.loop && !secondLight.loop.hiddenAt) secondLight.loop.hiddenAt = performance.now();
  });

  // ---------- WHERE THE MAP'S SUN IS ----------
  // which way the sun is from each of the four (your Pokémon, the opponent's, the two trainers), from where they
  // stand on screen and where the map's picture has its sun (--mapN-sun-x / -y: px in the 640 x 410 picture, which
  // sits 50 px in and 40 px down inside Showdown's 700 x 500 background box). Kept to steps of 5 degrees so the
  // sparkle filters are rebuilt only when something really moved.
  const sunAim = {};
  const secondAim = {};      // the same toward the map's second light: role -> { deg, ux, uy }
  function aimAtSun() {
    const battle = Array.from(document.querySelectorAll('.battle[data-ps-map]')).find((b) => b.offsetParent !== null);
    const n = battle && battle.dataset.psMap;
    const px = n ? readNumber('--map' + n + '-sun-x', NaN) : NaN, py = n ? readNumber('--map' + n + '-sun-y', NaN) : NaN;
    const bd = battle && battle.querySelector('.innerbattle > .backdrop');
    if (!bd || !Number.isFinite(px) || !Number.isFinite(py)) { Object.keys(sunAim).forEach((k) => delete sunAim[k]); return; }
    const br = bd.getBoundingClientRect();
    if (!br.width || !bd.offsetWidth) return;
    const sx = br.left + (px + 50) / bd.offsetWidth * br.width, sy = br.top + (py + 40) / bd.offsetHeight * br.height;
    const innerEl = battle.querySelector('.innerbattle'), kPage = innerEl && innerEl.offsetWidth ? innerEl.getBoundingClientRect().width / innerEl.offsetWidth : 1;
    const aim = (role, el) => {
      if (!el) return;
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;
      let deg = Math.atan2(sy - (r.top + r.height / 2), sx - (r.left + r.width / 2)) * 180 / Math.PI;
      // how many battle px one of the element's own px is drawn (its size setting): the sparkles' size is given in battle px
      const scale = Math.max(0.2, Math.round((r.width / (el.offsetWidth || r.width)) / kPage * 1000) / 1000);
      const was = sunAim[role];
      const dpr = window.devicePixelRatio || 1;
      const dotsNow = Math.round(r.width / (el.offsetWidth || r.width) * dpr * 1000) / 1000;
      let mirrored = was ? was.mirrored : false;
      if (!was) { try { mirrored = new DOMMatrix(getComputedStyle(el).transform).a < 0; } catch (e) { /* no transform */ } }
      // where the picture's own corner falls between the screen's dots (to a hundredth of a dot): the pixel blocks'
      // grid is started that much off the corner, so that its lines fall on whole dots
      const part = (v) => Math.round((v - Math.floor(v)) * 100) % 100 / 100;
      const gx = part((mirrored ? r.right : r.left) * dpr), gy = part(r.top * dpr);
      const near = (a, b2) => Math.min(Math.abs(a - b2), 1 - Math.abs(a - b2)) < 0.025;
      if (was && Math.abs(((deg - was.deg + 540) % 360) - 180) < 4 && Math.abs(scale - was.scale) < 0.01 && Math.abs(dotsNow - was.dots) < 0.01 && near(gx, was.gx) && near(gy, was.gy)) return;      // (hardly changed: keep the old aim)
      const keep = was && Math.abs(((deg - was.deg + 540) % 360) - 180) < 4;
      deg = keep ? was.deg : Math.round(deg / 5) * 5;
      try { mirrored = new DOMMatrix(getComputedStyle(el).transform).a < 0; } catch (e) { /* no transform */ }
      sunAim[role] = { deg: deg, scale: scale, dots: dotsNow, gx: part((mirrored ? r.right : r.left) * dpr), gy: gy, mirrored: mirrored, ux: Math.cos(deg * Math.PI / 180) * (mirrored ? -1 : 1), uy: Math.sin(deg * Math.PI / 180) };
    };
    battle.querySelectorAll(SPRITES).forEach((img) => {
      const st = tracks.get(img);
      if (st && st.atHome) aim(st.mine ? 'mine' : 'foe', img);         // (only from where it rests, not in the middle of a jump)
    });
    aim('tmine', battle.querySelector('.leftbar .trainersprite'));
    aim('tfoe', battle.querySelector('.rightbar .trainersprite'));
    // toward the second light, for the same four (the mirrored trainer flips left and right, as for the sun)
    const c = secondLight.cfg;
    Object.keys(secondAim).forEach((k) => { if (!c || !sunAim[k]) delete secondAim[k]; });
    if (c) {
      const gx = br.left + (c.x + 50) / bd.offsetWidth * br.width, gy = br.top + (c.y + 40) / bd.offsetHeight * br.height;
      const aim2 = (role, el) => {
        if (!el || !sunAim[role]) return;
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height) return;
        let deg = Math.atan2(gy - (r.top + r.height / 2), gx - (r.left + r.width / 2)) * 180 / Math.PI;
        const was = secondAim[role];
        if (was && Math.abs(((deg - was.deg + 540) % 360) - 180) < 4) return;
        deg = Math.round(deg / 5) * 5;
        secondAim[role] = { deg: deg, ux: Math.cos(deg * Math.PI / 180) * (sunAim[role].mirrored ? -1 : 1), uy: Math.sin(deg * Math.PI / 180) };
      };
      battle.querySelectorAll(SPRITES).forEach((img) => {
        const st = tracks.get(img);
        if (st && st.atHome) aim2(st.mine ? 'mine' : 'foe', img);
      });
      aim2('tmine', battle.querySelector('.leftbar .trainersprite'));
      aim2('tfoe', battle.querySelector('.rightbar .trainersprite'));
    }
  }

  // tone curves (black stays black, white stays white):
  //   darks above 1 deepen the shadows; the old curve also dragged every mid-tone down
  //   (at 1.6 a 50% grey became 33%), which made darker backgrounds look muddy and
  //   very dark. Now the effect fades out toward the mid-tones (50% grey -> 45%).
  //   lights below 1 lift the bright areas and mid-tones.
  //   mids move only the middle of the range: above 1 = brighter, below 1 = darker (at 1.2 a 50% grey
  //   becomes 55%, at 1.5 it becomes 62%); the push fades to nothing toward black and toward white.
  function darksCurve(d) {
    const a = Math.min(3, Math.max(-0.7, d - 1));
    return (x) => Math.pow(x, 1 + a * (1 - x) * (1 - x));
  }
  function lightsCurve(l) {
    const k = 1 / Math.max(0.1, l);
    return (x) => 1 - Math.pow(1 - x, k);
  }
  function midsCurve(m) {
    const a = Math.min(0.3, Math.max(-0.3, (m - 1) * 0.25));       // (beyond +-0.3 the curve would fold back on itself)
    return (x) => x + a * 16 * x * x * (1 - x) * (1 - x);
  }
  function toneFilter(id, curve, neutral) {
    if (neutral) {     // nothing to change: pass the picture through untouched (a table would shift some colours by a level)
      return (
        '<filter id="' + id + '" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">' +
          '<feOffset dx="0" dy="0"/>' +
        '</filter>'
      );
    }
    const steps = 64;
    const table = [];
    for (let i = 0; i <= steps; i++) {
      const y = curve(i / steps);
      table.push(Math.min(1, Math.max(0, y)).toFixed(6));
    }
    const fn = (c) => '<feFunc' + c + ' type="table" tableValues="' + table.join(' ') + '"/>';
    return (
      '<filter id="' + id + '" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">' +
        '<feComponentTransfer>' + fn('R') + fn('G') + fn('B') + '</feComponentTransfer>' +
      '</filter>'
    );
  }

  let lastFilterKey = '';

  function updateFilters() {
    const v = {
      bgPixel: readNumber('--bg-pixel', DEFAULTS.bgPixel),
      bgStrength: readNumber('--bg-pixel-strength', DEFAULTS.bgStrength),
      bgDarks: readNumber('--bg-darks', DEFAULTS.bgDarks),
      bgMids: readNumber('--bg-mids', DEFAULTS.bgMids),
      bgLights: readNumber('--bg-lights', DEFAULTS.bgLights),
      wxPixel: readNumber('--wx-pixel', DEFAULTS.wxPixel),
      wxStrength: readNumber('--wx-pixel-strength', DEFAULTS.wxStrength),
      uiPixel: readNumber('--ui-pixel', DEFAULTS.uiPixel),
      uiStrength: readNumber('--ui-pixel-strength', DEFAULTS.uiStrength),
      sun: readNumber('--sun-rim', 0),
      sunPlayer: Math.min(1, Math.max(0, readNumber('--sun-rim-player', 1))),
      sunFoe: Math.min(1, Math.max(0, readNumber('--sun-rim-foe', 1))),
      sparkStrength: Math.max(0, readNumber('--sun-sparkle-strength', 1)),
      canvas: sparkCanvas > 0 ? 1 : 0,
      sparkPlayer: perf.off ? 0 : Math.min(500, Math.max(0, readNumber('--sun-sparkles-player', 0))),
      sparkFoe: perf.off ? 0 : Math.min(500, Math.max(0, readNumber('--sun-sparkles-foe', 0))),
      sizePlayer: Math.max(0, readNumber('--sun-sparkle-size-player', 1)),
      sizeFoe: Math.max(0, readNumber('--sun-sparkle-size-foe', 0.5)),
      pointsPlayer: Math.min(6, Math.max(0, readNumber('--sun-sparkle-points-player', 2))),
      pointsFoe: Math.min(6, Math.max(0, readNumber('--sun-sparkle-points-foe', 1))),
      sparkPixel: readNumber('--sun-sparkle-pixel', 1) > 0 ? 1 : 0,
      sparkLook: {
        gold: { low: Math.min(0.95, Math.max(0, readNumber('--sun-sparkle-low-gold', 0))), sat: Math.min(2, Math.max(0, readNumber('--sun-sparkle-saturate-gold', 1))), bright: Math.min(2, Math.max(0, readNumber('--sun-sparkle-bright-gold', 1))) },
        green: { low: Math.min(0.95, Math.max(0, readNumber('--sun-sparkle-low-green', 0))), sat: Math.min(2, Math.max(0, readNumber('--sun-sparkle-saturate-green', 1))), bright: Math.min(2, Math.max(0, readNumber('--sun-sparkle-bright-green', 1))) },
      },
      sunAim: ['foe', 'mine', 'tfoe', 'tmine'].map((k) => (sunAim[k] ? sunAim[k].deg + (sunAim[k].mirrored ? 'M' : 'N') + sunAim[k].scale + '/' + sunAim[k].dots + '@' + sunAim[k].gx + ',' + sunAim[k].gy : '-')).join(' '),
      // the second light counts only while it is out (its part of the filters is left out otherwise)
      second: secondLightLevel(performance.now()) > 0 ? ['foe', 'mine', 'tfoe', 'tmine'].map((k) => (secondAim[k] ? secondAim[k].deg : '-')).join(' ') : '',
      playerLines: readNumber('--player-lines', 1),
      playerTrainerLines: readNumber('--player-trainer-lines', 1),
      // how many screen px one of your Pokémon's own pixels is drawn (2 with BW sprites, 1.5 otherwise): learned when one stands at home
      playerPx: Math.round(Array.from(document.querySelectorAll('.battle')).map((b) => (b._psSize || {}).mine).find((x) => x) || 2),
    };
    sparkSet = v;                                   // (the canvases read their settings from here)
    secondLight.built = v.second !== '';
    const level2 = secondLightLevel(performance.now());
    const key = JSON.stringify(v);
    if (key === lastFilterKey && document.getElementById('ps-pixelate-defs')) return;   // nothing changed
    lastFilterKey = key;

    let svg = document.getElementById('ps-pixelate-defs');
    if (!svg) {
      const ns = 'http://www.w3.org/2000/svg';
      svg = document.createElementNS(ns, 'svg');
      svg.id = 'ps-pixelate-defs';
      svg.setAttribute('width', '0');
      svg.setAttribute('height', '0');
      svg.style.position = 'absolute';
      document.body.appendChild(svg);
    }
    svg.innerHTML =
      pixelateFilter('ps-pixelate', v.bgPixel, v.bgStrength) +
      pixelateFilter('ps-pixelate-weather', v.wxPixel, v.wxStrength) +
      pixelateFilter('ps-pixelate-ui', v.uiPixel, v.uiStrength) +
      // darks, mids and lights are separate tone curves, applied one after the other (darks and mids share the
      // first filter, so styles that already use #ps-darks and #ps-lights get the mids without being changed)
      toneFilter('ps-darks', ((d, m) => (x) => m(d(x)))(darksCurve(v.bgDarks), midsCurve(v.bgMids)), v.bgDarks === 1 && v.bgMids === 1) +
      toneFilter('ps-lights', lightsCurve(v.bgLights), v.bgLights === 1) +
      // (the border is one of the sprite's own pixels thick: playerPx px for your Pokémon, 1 px for your trainer)
      thinFilter('ps-player-lines', Math.max(0, 1 - v.playerLines) * v.playerPx) +
      thinFilter('ps-player-trainer-lines', Math.max(0, 1 - v.playerTrainerLines)) +
      // (after the aim: the border's width and one of the sprite's own pixels, both in the element's own px; how many; star size; strength; screen dots per own px; point length)
      sparkleFilter('ps-sun-foe', sunAim.foe, 1, 1, (v.canvas ? 0 : v.sparkFoe), v.sizeFoe, v.sun * v.sunFoe * v.sparkStrength, sunAim.foe ? sunAim.foe.dots : 0, v.pointsFoe, v.second ? secondAim.foe : null, level2, v.sparkPixel, v.sparkLook) +
      sparkleFilter('ps-sun-mine', sunAim.mine, v.playerPx, v.playerPx, (v.canvas ? 0 : v.sparkPlayer), v.sizePlayer, v.sun * v.sunPlayer * v.sparkStrength, sunAim.mine ? sunAim.mine.dots : 0, v.pointsPlayer, v.second ? secondAim.mine : null, level2, v.sparkPixel, v.sparkLook) +
      sparkleFilter('ps-sun-tfoe', sunAim.tfoe, 1, 1, (v.canvas ? 0 : v.sparkFoe), v.sizeFoe, v.sun * v.sunFoe * v.sparkStrength, sunAim.tfoe ? sunAim.tfoe.dots : 0, v.pointsFoe, v.second ? secondAim.tfoe : null, level2, v.sparkPixel, v.sparkLook) +
      sparkleFilter('ps-sun-tmine', sunAim.tmine, 1, 1, (v.canvas ? 0 : v.sparkPlayer), v.sizePlayer, v.sun * v.sunPlayer * v.sparkStrength, sunAim.tmine ? sunAim.tmine.dots : 0, v.pointsPlayer, v.second ? secondAim.tmine : null, level2, v.sparkPixel, v.sparkLook);
  }

  // ---------- SHADOWS: FIND EACH POKÉMON'S FEET ----------
  // Looks at the sprite's actual pixels to find its lowest visible row and the
  // middle of its feet, then hands those to the style as --feet-x / --feet-y
  // (fractions of the sprite's box), so the shadow is drawn right under it.
  // How each Pokémon is centered left-right:
  //   'box'  = the middle of its full width, tip to tip (wide Pokémon like Wingull
  //            stick out equally on both sides)
  //   'body' = its balance point (a long tail or wing on one side barely moves it)
  const CENTER_MODE = 'box';

  // The Pokémon themselves. The HP labels also hold small pictures from /sprites/
  // (type icons, the Tera icon next to the name, Mega symbols); those must not be
  // treated as Pokémon.
  const SPRITES = '.innerbattle > div > div > img[src*="/sprites/"]';

  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d', { willReadFrequently: true });

  function readPixels(source, w, h) {
    canvas.width = w;
    canvas.height = h;
    ctx.clearRect(0, 0, w, h);
    ctx.drawImage(source, 0, 0);
    return ctx.getImageData(0, 0, w, h).data;
  }

  // Scans one picture and reports its lowest visible row, its left/right edges
  // and its balance point.
  function scan(data, w, h) {
    let bottom = -1, minX = w, maxX = -1, sum = 0, weight = 0;
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const a = data[(y * w + x) * 4 + 3];
        if (a > 40) {
          if (y > bottom) bottom = y;
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          sum += (x + 0.5) * a;
          weight += a;
        }
      }
    }
    return { bottom, minX, maxX, sum, weight, w, h };
  }

  function setFeet(img, st) {
    if (!st || st.bottom < 0 || !st.weight) return;
    const cx = CENTER_MODE === 'body'
      ? st.sum / st.weight / st.w
      : (st.minX + st.maxX + 1) / 2 / st.w;
    img.style.setProperty('--feet-x', cx.toFixed(4));
    img.style.setProperty('--feet-y', ((st.bottom + 1) / st.h).toFixed(4));
  }

  // Most sprites are animated. Measuring only the frame on screen right now gave
  // a different answer depending on where a bobbing/hovering Pokémon was in its
  // bounce (some looked like they floated, and spacing came out uneven). So each
  // sprite is also decoded frame by frame, and the feet are taken from all frames
  // together: the lowest point it ever reaches and its full width.
  const allFrames = new Map();   // sprite address -> 'pending' | 'fail' | result

  async function measureAllFrames(src) {
    if (!('ImageDecoder' in window)) return null;
    const res = await fetch(src);
    if (!res.ok) return null;
    const type = (res.headers.get('content-type') || '').split(';')[0] ||
      (/\.gif/i.test(src) ? 'image/gif' : 'image/png');
    if (!(await ImageDecoder.isTypeSupported(type))) return null;
    const dec = new ImageDecoder({ data: res.body, type });
    try {
      await dec.tracks.ready;
      await dec.completed;
      const count = dec.tracks.selectedTrack ? dec.tracks.selectedTrack.frameCount : 1;
      const step = Math.max(1, Math.ceil(count / 120));   // very long animations: sample
      let total = null;
      const lines = [];          // each frame's ground line: the pose it is in most of the time gives the resting ground
      for (let i = 0; i < count; i += step) {
        const { image } = await dec.decode({ frameIndex: i });
        const w = image.displayWidth, h = image.displayHeight;
        canvas.width = w;
        canvas.height = h;
        ctx.clearRect(0, 0, w, h);
        ctx.drawImage(image, 0, 0);
        const shownFor = image.duration || 1;          // (how long this frame stays on screen)
        image.close();
        const px = ctx.getImageData(0, 0, w, h).data;
        const st = scan(px, w, h);
        if (st.bottom < 0) continue;
        const gl = groundFromPixels(px, w, h);
        if (gl) { gl.time = shownFor; lines.push(gl); }
        if (!total) { total = st; continue; }
        total.bottom = Math.max(total.bottom, st.bottom);
        total.minX = Math.min(total.minX, st.minX);
        total.maxX = Math.max(total.maxX, st.maxX);
        total.sum += st.sum;
        total.weight += st.weight;
      }
      if (total && lines.length) {
        // where its lowest point is for most of the time (a hop, a kick or a swinging tail are the exceptions): its resting pose
        const seen = {};
        let rest = lines[0].bottom;
        lines.forEach((l) => { seen[l.bottom] = (seen[l.bottom] || 0) + l.time; });
        lines.forEach((l) => { if (seen[l.bottom] > seen[rest] || (seen[l.bottom] === seen[rest] && l.bottom > rest)) rest = l.bottom; });
        total.rest = lines.find((l) => l.bottom === rest);
      }
      return total;
    } finally {
      dec.close();
    }
  }

  function measureFeet(img) {
    if (!img.complete || !img.naturalWidth) {
      if (!img.dataset.feetWait) {
        img.dataset.feetWait = '1';
        img.addEventListener('load', () => { delete img.dataset.feetWait; schedule(); }, { once: true });
      }
      return;
    }
    const src = img.src;
    const info = allFrames.get(src);

    // best answer available: measured across every frame
    if (info && typeof info === 'object') {
      if (img.dataset.feetSrc !== src + '#all') {
        // the feet are where its lowest point is in its resting pose (not the lowest it ever reaches: a kick or a
        // swinging tail in one frame used to count as the feet, which left the Pokémon standing above its ground)
        setFeet(img, info.rest ? Object.assign({}, info, { bottom: info.rest.bottom - 1 }) : info);
        img.dataset.feetSrc = src + '#all';
      }
      return;
    }

    // quick answer from the frame on screen, used until the full one is ready
    if (img.dataset.feetSrc !== src && img.dataset.feetSrc !== src + '#all') {
      img.dataset.feetSrc = src;
      const w = img.naturalWidth, h = img.naturalHeight;
      try {
        setFeet(img, scan(readPixels(img, w, h), w, h));
      } catch (e) {
        const copy = new Image();
        copy.crossOrigin = 'anonymous';
        copy.onload = () => {
          try { setFeet(img, scan(readPixels(copy, w, h), w, h)); } catch (e2) { /* keep defaults */ }
        };
        copy.src = src;
      }
    }

    if (!info) {
      allFrames.set(src, 'pending');
      measureAllFrames(src)
        .then((r) => allFrames.set(src, r || 'fail'))
        .catch(() => allFrames.set(src, 'fail'))
        .finally(schedule);
    }
  }

  // ---------- CONTROLS MEASUREMENT ----------
  const observed = new WeakSet();
  const ro = new ResizeObserver(() => schedule());
  let queued = false;

  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      update();
    });
  }

  function watch(el) {
    if (el && !observed.has(el)) {
      ro.observe(el);
      observed.add(el);
    }
  }

  // ---------- TEAM PREVIEW DETECTION ----------
  // When several Pokémon per side are on the field at once, it's the face-off at the
  // start. Mark the battle with the class "ps-tp" and number each side's Pokémon
  // left-to-right from the middle (--tp-i: -2.5 ... +2.5) so the style can space them.
  function isShowing(img) {
    if (img.offsetParent === null) return false;
    const cs = getComputedStyle(img);
    // faded-out or hidden sprites (old leads, fainted Pokémon) don't count
    return cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > 0.05;
  }

  function markTeamPreview(battle) {
    const all = Array.from(battle.querySelectorAll(SPRITES));
    const imgs = all.filter(isShowing);
    const front = imgs.filter((img) => !img.src.includes('-back'));
    const back = imgs.filter((img) => img.src.includes('-back'));

    // the face-off shows both teams at once; requiring both sides avoids false
    // alarms from a leftover sprite on one side during normal battle
    const preview = front.length >= 3 && back.length >= 3;

    if (battle.classList.contains('ps-tp') !== preview) {
      battle.classList.toggle('ps-tp', preview);
    }

    if (!preview) {
      all.forEach((img) => {
        if (img.style.getPropertyValue('--tp-i')) img.style.removeProperty('--tp-i');
      });
      return;
    }

    [front, back].forEach((group) => {
      // sort by where Showdown placed each one (its center before any enlarging),
      // not where it appears on screen — enlarged wide Pokémon overlap their
      // neighbors and would otherwise get numbered out of order
      group
        .map((img) => ({ img, x: img.offsetLeft + img.offsetWidth / 2 }))
        .sort((a, b) => a.x - b.x)
        .forEach((item, i, list) => {
          const v = (i - (list.length - 1) / 2).toString();
          if (item.img.style.getPropertyValue('--tp-i') !== v) {
            item.img.style.setProperty('--tp-i', v);
          }
        });
    });
  }

  // Hand each sprite's on-page box size to the style, so it can line every
  // Pokémon's feet up on the same spot regardless of how its image is padded.
  function measureBox(img) {
    const w = img.offsetWidth + 'px';
    const h = img.offsetHeight + 'px';
    if (img.style.getPropertyValue('--box-w') !== w) img.style.setProperty('--box-w', w);
    if (img.style.getPropertyValue('--box-h') !== h) img.style.setProperty('--box-h', h);
  }

  // ---------- WEATHER TEXT, KEPT CRISP ----------
  // The "Rain (3 or 6 turns)" text lives inside the same element as the rain, so
  // any filter on the rain also hits the text. Show a copy of the text in its own
  // element outside the rain (class "ps-weather-label"), and hide the original.
  function mirrorWeatherText(battle) {
    // Showdown has two layers with the class "weather": terrain first, then the
    // weather itself. Only the weather layer carries the text (weather turns, plus
    // Reflect, Tailwind, Stealth Rock, Trick Room...), so pick the one that has it.
    const layers = Array.from(battle.querySelectorAll('.innerbattle > .weather'));
    const weather = layers.find((el) => el.querySelector(':scope > em')) || null;
    const source = weather && weather.querySelector(':scope > em');
    let label = battle.querySelector(':scope > .ps-weather-label');

    if (!label) {
      label = document.createElement('div');
      label.className = 'ps-weather-label';
      battle.appendChild(label);
    }

    // Showdown starts the text with a line break (to clear its old turn counter);
    // drop it so the label sits exactly where --weather-top puts it
    const html = source ? source.innerHTML.replace(/^\s*<br\s*\/?>/i, '') : '';
    const showing = source && weather.offsetParent !== null &&
      getComputedStyle(weather).display !== 'none' && html.trim() !== '';

    if (label.innerHTML !== html) label.innerHTML = html;

    // follow Showdown's own fade in/out of the weather (set directly on the element),
    // not the see-through setting from the style, and borrow the theme's text styling
    // Showdown keeps the rain itself at half opacity, so the text would be half
    // faded too; show it fully, and only follow the weather's fade in and out
    const wOp = parseFloat(weather && weather.style.opacity);
    const opacity = showing
      ? String(Number.isFinite(wOp) ? Math.round(Math.min(1, wOp * 2) * 100) / 100 : 1)
      : '0';
    if (label.style.opacity !== opacity) label.style.opacity = opacity;
    if (showing && !label.dataset.styled) {
      const cs = getComputedStyle(source);
      label.style.font = cs.font;
      label.style.color = cs.color;
      label.style.textShadow = cs.textShadow;
      label.style.letterSpacing = cs.letterSpacing;
      label.dataset.styled = '1';
    }
  }

  // ---------- NOTICES FROM THE BUTTONS, SHOWN AT THE TOP ----------
  // "You are trapped and cannot switch!", "might be trapped / disabled / locked" and the like are written by Showdown
  // in among the buttons, where the style's single line of buttons squeezed them. The style hides them there; a copy
  // of their words is shown at the top of the battle, under the VS / Turn sign (class "ps-notice-label"), and the
  // weather text moves down below it (--ps-notice-h, the copy's height).
  const NOTICES = 'em.movewarning, .switchmenu > em, .movemenu > p > em, .message-error';
  function mirrorNotices(battle, ctrl) {
    let label = battle.querySelector(':scope > .ps-notice-label');
    if (!label) { label = document.createElement('div'); label.className = 'ps-notice-label'; battle.appendChild(label); }
    const lines = [];
    if (ctrl) {
      ctrl.querySelectorAll(NOTICES).forEach((el) => {
        if (el.parentElement && el.parentElement.closest(NOTICES)) return;           // (a notice inside another counts once)
        const copy = el.cloneNode(true);
        copy.querySelectorAll('button, br').forEach((x) => x.remove());
        const text = copy.textContent.replace(/\s+/g, ' ').trim();
        if (text && !lines.includes(text)) lines.push(text);
      });
    }
    const key = lines.join('\n');
    if (label.dataset.text !== key) {
      label.dataset.text = key;
      label.textContent = '';
      lines.forEach((t, i) => { if (i) label.appendChild(document.createElement('br')); label.appendChild(document.createTextNode(t)); });
    }
    const h = lines.length ? label.offsetHeight + 'px' : '0px';
    put(battle, '--ps-notice-h', h);
    put(label, 'opacity', lines.length ? '1' : '0');
  }

  // ---------- TRAINER NAMES, CENTERED OVER THEIR TRAINER ----------
  // Names are kept on one line, which stops Showdown from centering them; measure
  // where each trainer actually is on screen and slide the name over it (--name-dx).
  function centerTrainerNames(battle, scale) {
    battle.querySelectorAll('.trainer').forEach((trainer) => {
      const name = trainer.querySelector(':scope > strong');
      const sprite = trainer.querySelector('.trainersprite');
      if (!name || !sprite || sprite.offsetParent === null) return;
      const rs = sprite.getBoundingClientRect();
      const rn = name.getBoundingClientRect();
      if (!rs.width || !rn.width) return;
      const delta = ((rs.left + rs.right) / 2 - (rn.left + rn.right) / 2) / scale;
      if (Math.abs(delta) < 0.5) return;
      const cur = parseFloat(name.style.getPropertyValue('--name-dx')) || 0;
      name.style.setProperty('--name-dx', (cur + delta).toFixed(1) + 'px');
    });
  }

  // ---------- VISIBLE PART OF THE BACKGROUND ----------
  // The background picture is larger than the battle window and hangs off its edges
  // (and themes can move or scale it). Measure where the battle window falls on the
  // picture as actually drawn, so the style can lay the haze and vignette over exactly
  // the battle window, whatever the theme, zoom or pan.
  function measureVisible(battle) {
    const bd = battle.querySelector('.innerbattle > .backdrop');
    const inner = battle.querySelector('.innerbattle');
    if (!bd || !inner || !bd.offsetWidth || !bd.offsetHeight) return;
    const b = bd.getBoundingClientRect();
    const ir = inner.getBoundingClientRect();
    const fr = battle.getBoundingClientRect();
    if (!b.width || !b.height) return;
    // the battle window = the battle area, clipped to the battle frame
    const left = Math.max(ir.left, fr.left), top = Math.max(ir.top, fr.top);
    const right = Math.min(ir.right, fr.right), bottom = Math.min(ir.bottom, fr.bottom);
    if (right <= left || bottom <= top) return;
    // screen pixels per pixel of the picture (includes any theme scaling and your zoom)
    const kx = b.width / bd.offsetWidth;
    const ky = b.height / bd.offsetHeight;
    const vals = {
      '--vis-x': ((left - b.left) / kx - bd.clientLeft).toFixed(1) + 'px',
      '--vis-y': ((top - b.top) / ky - bd.clientTop).toFixed(1) + 'px',
      '--vis-w': ((right - left) / kx).toFixed(1) + 'px',
      '--vis-h': ((bottom - top) / ky).toFixed(1) + 'px',
    };
    for (const k in vals) {
      if (bd.style.getPropertyValue(k) !== vals[k]) bd.style.setProperty(k, vals[k]);
    }
  }

  // run one feature without letting a failure in it stop the others
  // ---------- MAPS: ONE OF YOUR INSTALLED MAPS, PICKED AT RANDOM FOR EACH BATTLE ----------
  // A map is a background style that names its slot (1-20) by setting --map-N-on: 1, and only applies to a battle
  // marked with that number. This marks every battle with one of the installed slots, picked at random when the
  // battle first appears and kept for as long as the battle lasts (also across a page reload). --map-pick in the
  // main style forces one slot instead (0 = random). With no map installed, Showdown's own backgrounds show.
  const MAP_SLOTS = 20;
  const mapChoice = new Map();
  function installedMaps() {
    const cs = getComputedStyle(document.documentElement);
    const out = [];
    for (let i = 1; i <= MAP_SLOTS; i++) {
      if (cs.getPropertyValue('--map-' + i + '-on').trim() === '1') out.push(i);
    }
    return out;
  }
  function pickMap(battle) {
    const maps = installedMaps();
    let slot = '';
    if (maps.length) {
      const forced = Math.round(readNumber('--map-pick', 0));
      if (maps.includes(forced)) {
        slot = forced;
      } else {
        const room = battle.closest('[id^="room-"]');
        const key = room ? room.id : '';
        let s = key ? mapChoice.get(key) : battle._psMap;
        if (s === undefined && key) {
          try { s = parseInt(sessionStorage.getItem('ps-map:' + key), 10); } catch (e) { /* storage blocked */ }
        }
        if (!maps.includes(s)) s = maps[Math.floor(Math.random() * maps.length)];
        if (key) {
          mapChoice.set(key, s);
          try { sessionStorage.setItem('ps-map:' + key, String(s)); } catch (e) { /* storage blocked */ }
        } else {
          battle._psMap = s;
        }
        slot = s;
      }
    }
    if ((battle.dataset.psMap || '') !== String(slot)) {
      if (slot === '') delete battle.dataset.psMap; else battle.dataset.psMap = String(slot);
    }
  }

  // ---------- WHERE EACH POKÉMON IS ON ITS WAY TO THE OTHER ONE ----------
  // Showdown moves an attacking Pokémon to the spot where it draws the defender. The style draws each side shifted
  // and resized by its own numbers, so an attacker that keeps its own side's shift lands beside the defender, not
  // on it. This works out, every frame, how far each Pokémon has gone from its own resting place toward the other
  // side's (0 = at home, 1 = there) and hands it to the style as --trav; the style slides the Pokémon from its
  // own side's shift and size to the other side's as it goes. The resting place is wherever the Pokémon last
  // stood still on its own half of the field.
  const tracks = new WeakMap();
  // Showdown moves its sprites with jQuery; while one of its animations is running on a sprite, that sprite is not at rest
  function runningOn(img) {
    try {
      const jq = window.jQuery;
      return jq && jq.timers ? jq.timers.filter((t) => t && t.elem === img) : [];
    } catch (e) { return []; }
  }
  function beingMoved(img) { return runningOn(img).length > 0; }
  // the height Showdown is growing a sprite to right now (when it is sent out it starts at size 0), or 0 if unknown
  function growingTo(img) {
    let best = 0;
    runningOn(img).forEach((t) => {
      const h = t.anim && t.anim.props ? parseFloat(t.anim.props.height) : NaN;
      if (Number.isFinite(h) && h > best) best = h;
    });
    return best;
  }
  // How far below the middle of its box the style draws a Pokémon's feet, for a box h px tall (this repeats the
  // style's own sums for the two SPRITES rules: the feet alignment, its cap, and your side growing up from its feet).
  // While a Pokémon is smaller than its full size (being sent out, shrinking) this is what puts its feet higher or
  // lower than where they rest, on top of where Showdown has moved its box.
  let snapOn = 1, fixMax = 45, foeGround = 25, playerScale = 1;
  function feetBelowMiddle(mine, h, fy) {
    const cap = (lo, v, hi) => Math.min(hi, Math.max(lo, v));
    if (!mine) return (fy - 0.5) * h + cap(-fixMax, (foeGround - (fy - 0.5) * h) * snapOn, fixMax);
    const oy = 1 - (1 - fy) * snapOn;
    return h * (oy - 0.5 + playerScale * (fy - oy)) + cap(0, (1 - fy) * h * snapOn, 2 * fixMax);
  }
  function trackSprites(battle, inner, ir, k, now) {
    // (this battle's own numbers: its map may set them)
    snapOn = battleNumber(battle, '--snap', 1); fixMax = Math.abs(battleNumber(battle, '--fix-max', 45));
    foeGround = battleNumber(battle, '--foe-ground', 25); playerScale = battleNumber(battle, '--player-scale', 1);
    ballFromTrainer = battleNumber(battle, '--ball-from-trainer', 1); ballFromX = battleNumber(battle, '--ball-from-x', 0.5); ballFromY = battleNumber(battle, '--ball-from-y', 0.45);
    const list = [];
    battle.querySelectorAll(SPRITES).forEach((img) => {
      const l = parseFloat(img.style.left), t = parseFloat(img.style.top);
      const w = parseFloat(img.style.width) || img.offsetWidth, h = parseFloat(img.style.height) || img.offsetHeight;
      if (!Number.isFinite(l) || !Number.isFinite(t) || !w || !h) return;
      measureBox(img);                             // (every frame: the feet alignment follows the sprite as it grows or shrinks)
      let st = tracks.get(img);
      if (!st) { st = { moved: now }; tracks.set(img, st); }
      const cx = l + w / 2, by = t + h;
      st.cy = t + h / 2;
      st.h = h;
      // standing still = within half a pixel of where it was when it last counted as moving. (Not of the frame before:
      // on a fast screen a slow rise or fall moves less than that per frame, and its bottom edge hardly moves at all
      // while it rises and grows at once, so a Pokémon in the air passed for one standing at home.)
      if (st.ax === undefined || Math.abs(cx - st.ax) > 0.5 || Math.abs(t - st.at) > 0.5 || Math.abs(h - st.ah) > 0.5 || st.src !== img.src) {
        st.moved = now; st.ax = cx; st.at = t; st.ah = h;
      }
      st.cx = cx; st.by = by; st.src = img.src;
      st.mine = img.src.indexOf('-back') >= 0;
      const op = img.style.opacity !== '' ? parseFloat(img.style.opacity) : 1;
      st.shown = img.style.display !== 'none' && op > 0.05;
      st.atHome = st.shown && op > 0.95 && now - st.moved > 250 && (st.mine ? cx < 320 : cx > 320) && !battle.classList.contains('ps-tp') && !beingMoved(img);
      if (st.atHome) {
        st.homeCx = cx; st.homeCy = st.cy; st.homeH = h;
        (battle._psHome || (battle._psHome = {}))[st.mine ? 'mine' : 'foe'] = st.cy;
        if (img.naturalHeight) (battle._psSize || (battle._psSize = {}))[st.mine ? 'mine' : 'foe'] = h / img.naturalHeight;
      }
      list.push({ img, st });
    });
    list.forEach(({ img, st }) => {
      let p = 0;
      if (!st.atHome && st.homeCx !== undefined) {
        const other = list.find((o) => o.st.mine !== st.mine && o.st.shown && o.st.homeCx !== undefined);
        if (other && Math.abs(other.st.homeCx - st.homeCx) > 20) {
          p = Math.min(1, Math.max(0, (st.cx - st.homeCx) / (other.st.homeCx - st.homeCx)));
        }
        st.other = other ? other.st : null;
      }
      st.p = p;
      put(img, '--trav', p.toFixed(3));
    });
    return list;
  }

  // ---------- CAST SHADOWS: EACH POKÉMON'S AND TRAINER'S OWN OUTLINE LAID ON THE GROUND ----------
  // For every Pokémon and trainer in a battle, a copy of its picture is kept in a layer under the Pokémon (just
  // over the background). The copy sits exactly where the original is drawn, frame by frame; the style then turns
  // it black, lays it down from the feet along the map's shadow angle, and fades it to the map's shadow strength.
  // The shadow belongs to the ground, not to the feet: the ground under a Pokémon is where its feet rest at home,
  // and on the way to the other Pokémon it is the straight line between the two resting places. A Pokémon that
  // is above that line (a jump) has its shadow left on the ground, moved along the shadow's direction by its
  // height (--h), the way a real shadow separates from something in the air.
  // On when the style sets --cast-show above 0.
  // Height above the ground is worked out in Showdown's own positions: the middle of a Pokémon's box at rest is its
  // ground level; anything above that is height (the hop when it is sent out, a jump at the other Pokémon).
  // Until a Pokémon has stood still once, its side's last resting level in this battle is used, and before any,
  // Showdown's own for single battles: 245 px down on your side, 135 px down on the opponent's.
  let castOn = false;
  const REST_Y = { mine: 245, foe: 135 };
  const castOf = new WeakMap();
  function put(el, prop, value) {                 // (write only what changed)
    if (el.style.getPropertyValue(prop) !== value) el.style.setProperty(prop, value);
  }
  function castLayer(inner) {
    let layer = inner.querySelector(':scope > .ps-cast-layer');
    if (!layer) {
      layer = document.createElement('div');
      layer.className = 'ps-cast-layer';
      const weather = inner.querySelectorAll(':scope > .weather');
      inner.insertBefore(layer, weather.length ? weather[weather.length - 1].nextSibling : inner.firstChild);
    }
    return layer;
  }
  // The ground under a Pokémon, from one picture of it. Its underside is traced; every place where it reaches down
  // (a foot, a tail on the ground) within the bottom 30% of the Pokémon counts as touching the ground. The ground
  // line goes exactly through the lowest of those (its main foot) and through the lowest one on the other side of
  // the body, at least a fifth of the Pokémon's width away (its other foot), so the shadow starts right at both.
  // With only one such place the ground is level. Returns { at0, slope, bottom, x0, x1 }: the line in fractions of the
  // picture's height / width, the lowest visible row, and where the feet standing on that line start and end
  // (fractions of the width: the left edge of the leftmost one, the right edge of the rightmost one).
  // level = true (trainers): the ground stays level at the lowest foot, and a foot up to 5% of the height above it still counts.
  function groundFromPixels(d, w, h, level) {
    const under = new Array(w).fill(-1);
    let top = h, lowest = -1, minX = w, maxX = -1;
    for (let x = 0; x < w; x++) {
      for (let y = h - 1; y >= 0; y--) {
        if (d[(y * w + x) * 4 + 3] > 40) { under[x] = y; break; }
      }
      if (under[x] < 0) continue;
      if (under[x] > lowest) lowest = under[x];
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      for (let y = 0; y < h; y++) {
        if (d[(y * w + x) * 4 + 3] > 40) { if (y < top) top = y; break; }
      }
    }
    if (lowest < 0) return null;
    const reach = Math.max(2, Math.round(w * 0.06));
    const floor = lowest - 0.3 * (lowest - top + 1);
    const feet = [];                                     // runs of columns that reach down, each { x0, x1, y }
    for (let x = 0; x < w; x++) {
      if (under[x] < floor) continue;
      let peak = true;
      for (let q = Math.max(0, x - reach); q <= Math.min(w - 1, x + reach); q++) {
        if (under[q] > under[x]) { peak = false; break; }
      }
      if (!peak) continue;
      const last = feet[feet.length - 1];
      if (last && x - last.x1 <= 1 && last.y === under[x] + 1) last.x1 = x; else feet.push({ x0: x, x1: x, y: under[x] + 1 });
    }
    const mid = (f) => (f.x0 + f.x1 + 1) / 2;
    let main = null;
    feet.forEach((f) => { if (!main || f.y > main.y || (f.y === main.y && f.x1 - f.x0 > main.x1 - main.x0)) main = f; });
    const line = { at0: (lowest + 1) / h, slope: 0, bottom: lowest + 1 };
    if (main) {
      const apart = 0.2 * (maxX - minX + 1);
      let second = null;
      feet.forEach((f) => { if (Math.abs(mid(f) - mid(main)) >= apart && (!second || f.y > second.y)) second = f; });
      if (second && !level) {
        const slope = Math.max(-0.5, Math.min(0.5, ((second.y - main.y) / h) / ((mid(second) - mid(main)) / w)));
        line.slope = slope;
        line.at0 = main.y / h - slope * mid(main) / w;
      } else {
        line.at0 = main.y / h;
      }
      const near = Math.max(2, Math.round(h * (level ? 0.05 : 0.03)));    // (how close to the line still counts as standing on it)
      let x0 = main.x0, x1 = main.x1;
      feet.forEach((f) => {
        if (Math.abs(f.y - (line.at0 + line.slope * mid(f) / w) * h) > near) return;
        if (f.x0 < x0) x0 = f.x0;
        if (f.x1 > x1) x1 = f.x1;
      });
      line.x0 = x0 / w;
      line.x1 = (x1 + 1) / w;
    }
    return line;
  }
  // (from the picture as the page can read it: for an animated sprite that is its first frame. Used until the
  // frame-by-frame measurement is ready, which gives the ground of the pose it rests in)
  const groundOf = new Map();      // picture address -> line | 'none'
  function groundLine(img) {
    const key = img.currentSrc || img.src;
    const got = groundOf.get(key);
    if (got) return got === 'none' ? null : got;
    if (!img.complete || !img.naturalWidth) return null;
    try {
      const w = img.naturalWidth, h = img.naturalHeight;
      const line = groundFromPixels(readPixels(img, w, h), w, h);
      groundOf.set(key, line || 'none');
      return line;
    } catch (e) {
      groundOf.set(key, 'none');
      return null;
    }
  }
  // a trainer's feet: the lowest visible row of its picture and the middle of its body, as fractions of its box
  const trainerFeet = new Map();   // picture address -> 'pending' | { fx, fy }
  function feetOfTrainer(el) {
    const m = /url\(["']?(.*?)["']?\)/.exec(el.style.backgroundImage || '');
    if (!m) return null;
    const got = trainerFeet.get(m[1]);
    if (got && got !== 'pending') {
      const bw = el.offsetWidth || got.w, bh = el.offsetHeight || got.h;       // the picture sits top-centre in the box
      const at = (f) => ((bw - got.w) / 2 + f * got.w) / bw;
      return { fx: at(got.cx), fy: Math.min(1, got.bottom / bh), fl: at(got.x0), fr: at(got.x1) };
    }
    if (!got) {
      trainerFeet.set(m[1], 'pending');
      const im = new Image();
      im.onload = () => {
        try {
          const px = readPixels(im, im.naturalWidth, im.naturalHeight);
          const st = scan(px, im.naturalWidth, im.naturalHeight);
          if (st.bottom >= 0 && st.weight) {
            const cx = st.sum / st.weight / st.w;
            const gl = groundFromPixels(px, im.naturalWidth, im.naturalHeight, true);     // (only for where its feet start and end)
            const got = gl && gl.x0 !== undefined;
            trainerFeet.set(m[1], { w: st.w, h: st.h, cx: cx, bottom: st.bottom + 1, x0: got ? gl.x0 : cx, x1: got ? gl.x1 : cx });
          }
        } catch (e) { /* the picture can't be read: the fallback below stays */ }
      };
      im.src = m[1];
    }
    return null;
  }
  function syncCast(battle, inner, ir, k, list) {
    if (!castOn) {
      const old = inner.querySelector(':scope > .ps-cast-layer');
      if (old) old.remove();
      return;
    }
    const layer = castLayer(inner);
    const sources = list.map((o) => o.img).concat(Array.from(battle.querySelectorAll('.trainer .trainersprite')));
    const boxes = sources.map((src) => src.getBoundingClientRect());      // (read everything first, then write)
    const live = new Set();
    sources.forEach((src, i) => {
      const isMon = i < list.length;
      const st = isMon ? list[i].st : null;
      let c = castOf.get(src);
      if (!c || c.parentNode !== layer) {
        c = document.createElement('div');
        // (whose shadow it is: the style gives each of the four - your Pokémon, your trainer, the opponent's Pokémon,
        // the opponent's trainer - its own angle)
        const mine = isMon ? st.mine : !!src.closest('.leftbar');
        c.className = 'ps-cast' + (isMon ? '' : ' ps-cast-trainer') + (mine ? ' ps-cast-mine' : ' ps-cast-foe');
        layer.appendChild(c);
        castOf.set(src, c);
      }
      live.add(c);
      const r = boxes[i];
      const op = isMon && src.style.opacity !== '' ? parseFloat(src.style.opacity) : 1;
      const shown = r.width > 0 && r.height > 0 && src.style.display !== 'none' && op > 0.01;
      put(c, 'display', shown ? 'block' : 'none');
      if (!shown) return;
      const x = (r.left - ir.left) / k, y = (r.top - ir.top) / k, w = r.width / k, h = r.height / k;
      put(c, 'left', x.toFixed(1) + 'px');
      put(c, 'top', y.toFixed(1) + 'px');
      put(c, 'width', w.toFixed(1) + 'px');
      put(c, 'height', h.toFixed(1) + 'px');
      const pic = isMon ? 'url("' + (src.currentSrc || src.src) + '")' : src.style.backgroundImage;
      if (c.dataset.pic !== pic) { c.dataset.pic = pic; c.style.backgroundImage = pic; }
      let fx = 0.5, fy = isMon ? 0.92 : 0.98, lift = 0, slope = 0, fl = null, fr = null;
      const flip = !isMon && src.closest('.leftbar') && !src.classList.contains('noflip');
      if (isMon) {
        fx = parseFloat(src.style.getPropertyValue('--feet-x')) || 0.5;
        fy = parseFloat(src.style.getPropertyValue('--feet-y')) || 0.92;
        if (!battle.classList.contains('ps-tp')) {                         // (the face-off has no ground line: attached)
          const side = st.mine ? 'mine' : 'foe';
          const seen = battle._psHome || {};
          const own = st.homeCy !== undefined ? st.homeCy : (seen[side] !== undefined ? seen[side] : REST_Y[side]);
          const far = st.p > 0 && st.other && st.other.homeCy !== undefined ? st.other.homeCy : own;
          lift = own + (far - own) * st.p - st.cy;                        // how far above the ground line Showdown has its box
          if (!(st.p > 0)) {
            // ...and how much higher its feet are drawn because it is not at its full size (sent out: it grows from nothing)
            let full = st.homeH;
            if (full === undefined) {
              const to = growingTo(src);
              if (to) st.growTo = to;                  // (kept: between the end of that animation and its first rest)
              full = st.growTo || 0;
              const size = (battle._psSize || {})[side] || (st.mine ? (/\/gen5/.test(src.src) ? 2 : 1.5) : 1);
              if (!full && src.naturalHeight) full = src.naturalHeight * size;
            }
            if (full && Math.abs(full - st.h) > 0.5) {
              const cssFy = parseFloat(src.style.getPropertyValue('--feet-y')) || (st.mine ? 1 : 0.5);
              lift += feetBelowMiddle(st.mine, full, cssFy) - feetBelowMiddle(st.mine, st.h, cssFy);
            }
          }
          if (lift < 1) lift = 0;
        }
        const all = allFrames.get(src.src);          // the ground under it in its resting pose (or, until that is
        const line = all && typeof all === 'object' && all.rest ? all.rest : groundLine(src);   // measured, in its first frame)
        if (line) {
          fy = Math.min(1, Math.max(0, line.at0 + line.slope * fx));
          slope = line.slope * h / w;
          if (line.x0 !== undefined) { fl = line.x0; fr = line.x1; }
        }
      } else {
        const tf = feetOfTrainer(src);
        if (tf) { fx = flip ? 1 - tf.fx : tf.fx; fy = tf.fy; fl = flip ? 1 - tf.fr : tf.fl; fr = flip ? 1 - tf.fl : tf.fr; }
      }
      put(c, '--fx', fx.toFixed(4));
      put(c, '--fy', fy.toFixed(4));
      // where its feet on the ground start and end, and its width: at flat shadow angles the style turns the line under
      // the feet about the foot the shadow leaves from, so no foot's shadow starts in front of it
      put(c, '--fl', (fl === null ? fx : Math.min(fl, fx)).toFixed(4));
      put(c, '--fr', (fr === null ? fx : Math.max(fr, fx)).toFixed(4));
      put(c, '--bw', w.toFixed(1) + 'px');
      put(c, '--h', lift.toFixed(1) + 'px');
      put(c, '--trav', isMon ? st.p.toFixed(3) : '0');   // (on its way to the other side its angle turns into that side's)
      put(c, '--gs', slope.toFixed(4));
      put(c, '--o', op.toFixed(2));
      put(c, '--flip', flip ? '-1' : '1');
    });
    Array.from(layer.children).forEach((c) => { if (!live.has(c)) c.remove(); });
  }
  // The level's shakes (Earthquake, Bulldoze, Earth Power): Showdown moves only the background, by animating its
  // "top" away from where it rests (-90px). Every frame this reads how far it is from rest and hands the style that
  // distance from --shake-lag frames ago (times --shake-follow) as --shake-y; the style adds it to the Pokémon and
  // the trainers, so they move with the ground, that many frames behind it. Their shadows copy them, so they follow too.
  const BG_REST = -90;
  let shakeFollow = 1, shakeLag = 1;
  const shakes = new WeakMap();    // battle -> the background's last distances from rest, oldest first
  function followShake(battle, inner) {
    const bd = inner.querySelector(':scope > .backdrop');
    const top = bd ? parseFloat(bd.style.top) : NaN;
    let past = shakes.get(battle);
    if (!past) { past = []; shakes.set(battle, past); }
    past.push(Number.isFinite(top) ? top - BG_REST : 0);
    while (past.length > shakeLag + 1) past.shift();
    const y = past[0] * shakeFollow;
    put(inner, '--shake-y', Math.abs(y) < 0.005 ? '0px' : y.toFixed(2) + 'px');
  }
  // ---------- EFFECTS START WHERE THE POKÉMON REALLY ARE ----------
  // Showdown places every effect (hit sparks, things that fly off, the "-25%" and "Burned!" pop-ups) from where IT
  // put the Pokémon. The style then draws the Pokémon somewhere else (moved, resized, nudged), so the effects were
  // left behind. Here every effect is shifted by the same amount as the Pokémon it is at: for each Pokémon, how far
  // the middle of its picture is drawn from where Showdown put it (taken while it stands at home); an effect gets
  // the shift of the Pokémon it is nearest to, blended smoothly on the way from one Pokémon to the other.
  let fxFollow = 1, ballFromTrainer = 1, ballFromX = 0.5, ballFromY = 0.45;
  const HOME = { mine: { x: 210, y: 245 }, foe: { x: 430, y: 135 } };        // Showdown's own resting places in a single battle
  // Poké Balls. Showdown throws the ball in from just behind where the Pokémon will stand, and takes it back out the
  // same way. Here a thrown ball leaves from its trainer and lands where the Pokémon comes out; a ball that takes a
  // Pokémon back goes from the Pokémon to the trainer. Showdown's own path (its arc, its timing) is kept: only the two
  // ends are moved, and the shift slides from one end's to the other's as the ball travels.
  // Returns the shift for this frame as [dx, dy], or null when this is not such a ball (or the trainer is not shown).
  function ballShift(el, inner, ir, k, list, x, y) {
    if (!(ballFromTrainer > 0) || el.tagName !== 'IMG' || el.src.indexOf('pokeball') < 0) return null;
    let b = el._psBall;
    if (!b) {
      const mine = x < 320;
      const side = list.find((o) => o.st.mine === mine && o.st.homeCx !== undefined);
      const home = side ? { x: side.st.homeCx, y: side.st.homeCy } : HOME[mine ? 'mine' : 'foe'];
      b = el._psBall = { mine: mine, ax: x, ay: y, home: home, kind: '', w: parseFloat(el.style.width) || 0 };
    }
    // where Showdown is taking it (the end of its running animation), once it is under way
    if (b.ex === undefined) {
      runningOn(el).forEach((t) => {
        const p = t.anim && t.anim.props;
        if (p && p.left !== undefined && p.top !== undefined) {
          b.ex = parseFloat(p.left) + (parseFloat(p.width) || 0) / 2; b.ey = parseFloat(p.top) + (parseFloat(p.height) || 0) / 2;
        }
      });
      if (b.ex === undefined) {
        if (Math.abs(b.ax - b.home.x) <= 30) return null;                 // (waiting at the Pokémon: nothing to move yet)
      } else if (Math.abs(b.ax - b.home.x) > 30 && Math.abs(b.ex - b.home.x) < 20) b.kind = 'out';      // thrown in: from behind to the Pokémon's place
      else if (Math.abs(b.ax - b.home.x) < 20 && Math.abs(b.ex - b.home.x) > 30 && b.w < 24 * (b.mine ? 1.5 : 1) * 0.85) b.kind = 'back';   // (the small ball: a knocked-off item is drawn full size)
      else b.kind = 'other';
    }
    if (b.kind === 'other' || b.kind === '' && Math.abs(b.ax - b.home.x) <= 30) return null;
    const pic = inner.querySelector((b.mine ? '.leftbar' : '.rightbar') + ' .trainersprite');
    const pr = pic && pic.getBoundingClientRect();
    if (!pr || !pr.width || parseFloat(getComputedStyle(pic).opacity) < 0.05) return null;
    // the trainer's hand: across from the picture's back edge toward the way the trainer faces, and down from its top
    const tx = ((b.mine ? pr.left + pr.width * ballFromX : pr.right - pr.width * ballFromX) - ir.left) / k, ty = (pr.top + pr.height * ballFromY - ir.top) / k;
    // The Pokémon's end of the path, as a shift from Showdown's own:
    //  - taken back: the ball sets off from the Pokémon, shifted the way the Pokémon itself is drawn shifted
    //  - thrown in: the ball lands on the middle of where the Pokémon will stand. It is not there yet (it waits at
    //    size 0), so an unseen copy of its picture is laid out at its full size in its resting place for a moment,
    //    and measured.
    // Worked out once, when the ball sets off (the Pokémon goes on to grow, or is put away, while the ball still shows).
    if (b.kind && b.px === undefined) {
      b.px = 0; b.py = 0;
      const side = list.find((o) => o.st.mine === b.mine && o.st.fxOff);
      if (side) { b.px = side.st.fxOff.dx; b.py = side.st.fxOff.dy; }
      if (b.kind === 'out') {
        let img = null, best = 1e9;
        inner.querySelectorAll(':scope > div > div > img[src*="/sprites/"]').forEach((i) => {
          if ((i.src.indexOf('-back') >= 0) !== b.mine || i.style.display === 'none') return;
          const far = Math.abs(parseFloat(i.style.left) + (parseFloat(i.style.width) || 0) / 2 - b.home.x) + (parseFloat(i.style.width) || 0);    // (nearest the place, smallest)
          if (far < best) { best = far; img = i; }
        });
        const battle = inner.closest('.battle');
        const size = ((battle && battle._psSize) || {})[b.mine ? 'mine' : 'foe'] || (b.mine ? (img && img.src.indexOf('/gen5') >= 0 ? 2 : 1.5) : 1);
        if (img && img.naturalWidth && img.parentElement) {
          const w = img.naturalWidth * size, h = img.naturalHeight * size;
          safely(() => measureFeet(img));                      // (its feet, so the copy stands the way the Pokémon will)
          const copy = img.cloneNode(false);
          copy.style.left = (b.home.x - w / 2) + 'px'; copy.style.top = (b.home.y - h / 2) + 'px'; copy.style.width = w + 'px'; copy.style.height = h + 'px';
          copy.style.display = 'block'; copy.style.visibility = 'hidden'; copy.style.opacity = '0';
          img.parentElement.appendChild(copy);
          measureBox(copy);
          const r = copy.getBoundingClientRect();
          copy.remove();
          if (r.width) { b.px = (r.left + r.width / 2 - ir.left) / k - b.ex; b.py = (r.top + r.height / 2 - ir.top) / k - b.ey; }
        } else if (side) { b.px = b.home.x + side.st.fxOff.dx - b.ex; b.py = b.home.y + side.st.fxOff.dy - b.ey; }
      }
    }
    const px = b.px || 0, py = b.py || 0;
    if (b.kind === 'back') {
      const u = Math.min(1, Math.max(0, (x - b.ax) / ((b.ex - b.ax) || 1)));
      return [(1 - u) * px + u * (tx - b.ex), (1 - u) * py + u * (ty - b.ey)];
    }
    // thrown in (or still waiting behind, before its animation starts)
    const ex = b.ex === undefined ? b.home.x : b.ex, ey = b.ex === undefined ? b.home.y : b.ey;
    const u = Math.min(1, Math.max(0, (x - b.ax) / ((ex - b.ax) || 1)));
    return [(1 - u) * (tx - b.ax) + u * px, (1 - u) * (ty - b.ay) + u * py];
  }
  function moveEffects(inner, ir, k, list) {
    const bar = inner.querySelector(':scope > .leftbar');
    const fx = bar && bar.previousElementSibling;          // Showdown's effects layer sits just before the two side bars
    if (!fx || fx.tagName !== 'DIV' || fx.className) return;
    if (fx.firstElementChild) busyAt = performance.now();                              // an effect or a pop-up is on screen
    const at = [];
    list.forEach(({ img, st }) => {
      if (st.atHome) {
        const r = img.getBoundingClientRect();
        if (r.width) st.fxOff = { dx: (r.left + r.width / 2 - ir.left) / k - st.cx, dy: (r.top + r.height / 2 - ir.top) / k - st.cy };
      }
      if (st.fxOff && st.shown && st.homeCx !== undefined) at.push({ x: st.homeCx, y: st.homeCy, dx: st.fxOff.dx, dy: st.fxOff.dy });
    });
    const own = fx.previousElementSibling && fx.previousElementSibling.classList.contains('ps-results') ? Array.from(fx.previousElementSibling.children) : [];
    for (let el of Array.from(fx.children).concat(own)) {
      let value = '';
      {
        const l = parseFloat(el.style.left), t = parseFloat(el.style.top);
        if (Number.isFinite(l) && Number.isFinite(t)) {
          // the middle of the effect, in Showdown's own positions (a pop-up is a 150 px wide line of text hung from its top)
          const pop = el.classList.contains('result');
          const x = l + (pop ? 75 : (parseFloat(el.style.width) || 0) / 2), y = t + (pop ? 5 : (parseFloat(el.style.height) || 0) / 2);
          const ball = pop ? null : ballShift(el, inner, ir, k, list, x, y);
          if (ball) value = ball[0].toFixed(1) + 'px ' + ball[1].toFixed(1) + 'px';
          else if (fxFollow > 0 && at.length) {
            let sw = 0, dx = 0, dy = 0;
            for (const a of at) {
              const d2 = (x - a.x) * (x - a.x) + (y - a.y) * (y - a.y);
              const w = 1 / (d2 * d2 + 2500);          // (falls off fast: near a Pokémon, the other one hardly counts)
              sw += w; dx += w * a.dx; dy += w * a.dy;
            }
            value = (dx / sw * fxFollow).toFixed(1) + 'px ' + (dy / sw * fxFollow).toFixed(1) + 'px';
          }
        }
      }
      if (el.style.translate !== value) el.style.translate = value;
    }
  }

  // ---------- THE ROOM: NO CHAT LOG, THE BATTLE FILLS THE ROOM ----------
  // With --log-show at 0 the style removes the log column, and this enlarges the battle to fill the room (above the
  // line you type chat into). It works from what is actually on screen: it measures the battle and the room, and
  // corrects the battle's size and place until it fits, so it holds whatever else scales or moves the battle.
  let logShow = 1, fitOn = 1, fitMax = 4;
  // "Maximize battle screen" (--battle-maximize: 1): while a battle is showing, only the battle is on the page. The
  // style hides Showdown's top bar and every other panel and stretches the battle's room over the whole window; this
  // marks the page and the room for it (data-ps-max / data-ps-maxroom) and sizes the battle to the window. The line
  // you type chat into sits at the bottom right. Alt+M switches it off and on again without touching the style (to get
  // back to the other tabs); that choice lasts until the tab is closed.
  let maxWanted = 0, maxFlip = false;
  try { maxFlip = sessionStorage.getItem('ps-max-flip') === '1'; } catch (e) { /* storage blocked */ }
  const maxOn = () => (maxWanted > 0) !== maxFlip;
  function toggleMax() {
    maxFlip = !maxFlip;
    try { sessionStorage.setItem('ps-max-flip', maxFlip ? '1' : '0'); } catch (err) { /* storage blocked */ }
    schedule();
  }
  window.addEventListener('keydown', (e) => {
    if (e.altKey && !e.ctrlKey && !e.metaKey && (e.code === 'KeyM' || (e.key || '').toLowerCase() === 'm')) {
      toggleMax();
      e.preventDefault();
      e.stopPropagation();
    }
  }, true);
  // the maximize button: one per battle room, at the lower right corner of the battle beside the chat line (the
  // style places it). It shows four corners pointing out while the battle can be maximized, and in while it is.
  const MAX_ICON = {
    out: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square"><path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"/></svg>',
    in: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square"><path d="M6 2v4H2M14 6h-4V2M10 14v-4h4M2 10h4v4"/></svg>',
  };
  function maxButton(room) {
    let b = room.querySelector(':scope > .ps-max-button');
    if (!b) {
      b = document.createElement('button');
      b.type = 'button';
      b.className = 'ps-max-button';
      b.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); toggleMax(); });
      room.appendChild(b);
    }
    const state = maxOn() ? 'in' : 'out';
    if (b.dataset.state !== state) {
      b.dataset.state = state;
      b.innerHTML = MAX_ICON[state];
      b.title = (state === 'in' ? 'Back to the normal view' : 'Maximize the battle screen') + ' (Alt+M)';
    }
    return b;
  }
  function markMaximized() {
    const battle = maxOn() ? Array.from(document.querySelectorAll('.ps-room .battle')).find((b) => b.offsetParent !== null) : null;
    const room = battle ? battle.closest('.ps-room') : null;
    document.querySelectorAll('.ps-room[data-ps-maxroom]').forEach((r) => { if (r !== room) delete r.dataset.psMaxroom; });
    if (room && room.dataset.psMaxroom !== '1') room.dataset.psMaxroom = '1';
    const mark = room ? '1' : '0';
    if (document.documentElement.dataset.psMax !== mark) document.documentElement.dataset.psMax = mark;
  }
  function clearFit(battle) {
    if (!battle._psFit) return;
    battle.style.removeProperty('scale'); battle.style.removeProperty('translate'); battle.style.removeProperty('transform-origin');
    battle._psFit = null;
  }
  function fitBattle(battle) {
    const room = battle.closest('.ps-room') || battle.offsetParent;
    const whole = room && room.dataset.psMaxroom === '1';      // (maximized: the room is the whole window)
    if (!room || (!whole && (logShow > 0 || !(fitOn > 0))) || battle.offsetParent === null) { clearFit(battle); return; }
    const rr = room.getBoundingClientRect();
    if (!rr.width || !rr.height || !room.offsetWidth) return;
    const rs = rr.width / room.offsetWidth;                    // (on-screen px per px of the room's own layout)
    const add = room.querySelector('.battle-log-add');
    const addH = !whole && add && add.offsetParent !== null ? add.getBoundingClientRect().height : 0;   // (maximized, the chat line sits inside the battle: no room kept for it)
    const availW = Math.floor(rr.width), availH = Math.floor(rr.height - addH);
    if (availW < 50 || availH < 50) return;
    const set = (f) => {
      battle.style.setProperty('transform-origin', '0 0', 'important');
      battle.style.setProperty('scale', f.s.toFixed(4), 'important');
      battle.style.setProperty('translate', f.x.toFixed(2) + 'px ' + f.y.toFixed(2) + 'px', 'important');
    };
    let f = battle._psFit || { s: 1, x: 0, y: 0 };
    for (let i = 0; i < 3; i++) {
      set(f);
      const b = battle.getBoundingClientRect();
      if (!b.width || !b.height) return;
      const ratio = Math.min(availW / b.width, availH / b.height);
      const s = Math.min(fitMax, Math.max(0.2, f.s * ratio));
      const grow = s / f.s;                                    // (the battle grows from its top left corner)
      // (centred across; at the top of the room, or in the middle of the window when maximized)
      const x = f.x + (rr.left + (availW - b.width * grow) / 2 - b.left) / rs, y = f.y + (rr.top + (whole ? (availH - b.height * grow) / 2 : 0) - b.top) / rs;
      // (close enough to what it already is: left exactly as it is. Re-fitting by hair's breadths on every round made
      // the battle, its buttons and HP bars shiver by a fraction of a pixel, which shows as a one-pixel jitter)
      const done = Math.abs(grow - 1) < 0.002 && Math.abs(x - f.x) < 0.75 && Math.abs(y - f.y) < 0.75;
      if (done) break;
      f = { s: Math.round(s * 10000) / 10000, x: Math.round(x), y: Math.round(y) };
    }
    if (!battle._psFit || f.s !== battle._psFit.s || f.x !== battle._psFit.x || f.y !== battle._psFit.y) set(f);
    battle._psFit = f;
  }

  // ---------- TALK BUBBLES ----------
  // When one of the two players says something in the battle's chat, it shows in a bubble beside that player's
  // trainer: to the right of your trainer's face, to the left of the opponent's. The style sets where, how wide and
  // for how long (--bubble-...). Only what is said while you watch: not the chat that was there when you joined.
  let bubbleOn = 1;
  const toId = (text) => String(text || '').toLowerCase().replace(/[^a-z0-9]+/g, '');
  function placeBubble(battle, bubble) {
    const inner = battle.querySelector('.innerbattle');
    const mine = bubble.classList.contains('ps-bubble-mine');
    const pic = battle.querySelector((mine ? '.leftbar' : '.rightbar') + ' .trainersprite');
    if (!inner || !pic || !inner.offsetWidth) return false;
    const ir = inner.getBoundingClientRect(), r = pic.getBoundingClientRect();
    if (!ir.width || !r.width) return false;
    const k = ir.width / inner.offsetWidth;
    const fx = battleNumber(battle, '--bubble-face-x', 0.14), fy = battleNumber(battle, '--bubble-face-y', 0.28);
    put(bubble, '--ax', ((r.left + r.width * (0.5 + (mine ? fx : -fx)) - ir.left) / k).toFixed(1) + 'px');
    put(bubble, '--ay', ((r.top + r.height * fy - ir.top) / k).toFixed(1) + 'px');
    // the shape: one line round the rounded box and its point. The point leaves the bottom edge near the corner on
    // the speaker's side and runs diagonally down toward the speaker (down-left for yours, down-right for the other).
    const w = bubble.offsetWidth, h = bubble.offsetHeight;
    const path = bubble.querySelector('.ps-bubble-shape path');
    if (path && w && h && bubble._psShape !== w + 'x' + h) {
      bubble._psShape = w + 'x' + h;
      const rad = Math.max(0, Math.min(battleNumber(battle, '--bubble-radius', 7), w / 2, h / 2)), t = Math.max(0, battleNumber(battle, '--bubble-tail', 9));
      const a = Math.min(rad + 2, w / 2), b = Math.min(a + t * 0.9, w - rad);       // where the point joins the bottom edge (from the speaker's corner)
      const tip = a - t * 0.6;                                                    // its tip: further toward the speaker, t below the box
      const X = (x) => (mine ? x : w - x).toFixed(1);                              // (mirrored for the opponent's)
      const sweep = mine ? 1 : 0;
      const arc = (x, y) => 'A' + rad + ' ' + rad + ' 0 0 ' + sweep + ' ' + X(x) + ' ' + y.toFixed(1);
      path.setAttribute('d', 'M' + X(rad) + ' 0 L' + X(w - rad) + ' 0 ' + arc(w, rad) + ' L' + X(w) + ' ' + (h - rad).toFixed(1) + ' ' + arc(w - rad, h) +
        ' L' + X(b) + ' ' + h + ' L' + X(tip) + ' ' + (h + t).toFixed(1) + ' L' + X(a) + ' ' + h + ' L' + X(rad) + ' ' + h + ' ' + arc(0, h - rad) + ' L' + X(0) + ' ' + rad + ' ' + arc(rad, 0) + ' Z');
      const svg = path.parentNode; svg.setAttribute('width', w); svg.setAttribute('height', h + t);
      bubble.style.setProperty('--tipx', tip.toFixed(1) + 'px');
    }
    return true;
  }
  function say(battle, mine, text) {
    const inner = battle.querySelector('.innerbattle');
    if (!inner) return;
    const cls = mine ? 'ps-bubble-mine' : 'ps-bubble-foe';
    inner.querySelectorAll(':scope > .ps-bubble.' + cls).forEach((old) => old.remove());       // one bubble per trainer: a new line replaces the old
    const max = Math.max(10, Math.round(readNumber('--bubble-max-letters', 140)));
    const bubble = document.createElement('div');
    bubble.className = 'ps-bubble ' + cls;
    const shape = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    shape.setAttribute('class', 'ps-bubble-shape');
    shape.appendChild(document.createElementNS('http://www.w3.org/2000/svg', 'path'));
    const words = document.createElement('span');
    words.textContent = text.length > max ? text.slice(0, max - 1).trimEnd() + '…' : text;
    bubble.appendChild(shape); bubble.appendChild(words);
    inner.appendChild(bubble);
    if (!placeBubble(battle, bubble)) { bubble.remove(); return; }
    requestAnimationFrame(() => bubble.classList.add('ps-on'));
    const stay = Math.max(1, readNumber('--bubble-time', 6)) * 1000;
    setTimeout(() => { bubble.classList.remove('ps-on'); setTimeout(() => bubble.remove(), 300); }, stay);
  }
  function heardChat(line) {
    if (!(bubbleOn > 0)) return;
    const log = line.closest('.battle-log');
    const room = log && (log.closest('.ps-room') || log.parentElement);
    const battle = room && room.querySelector('.battle');
    if (!battle || battle.offsetParent === null) return;
    if (!log._psHeardFrom || performance.now() < log._psHeardFrom) return;        // (still catching up with what was already there)
    try {       // (Showdown replaying the battle up to now, after joining late or skipping turns: not live chat)
      const r = window.app && window.app.rooms && room.id && window.app.rooms[room.id.replace(/^room-/, '')];
      if (r && r.battle && r.battle.seeking !== null && r.battle.seeking !== undefined) return;
    } catch (e) { /* not that client */ }
    const who = line.querySelector('strong .username, .username');
    const words = line.querySelector('em');
    if (!who || !words || words.contains(who)) return;                            // (no speaker, or a "/me" line)
    const text = words.textContent.replace(/\s+/g, ' ').trim();
    if (!text) return;
    const id = toId(who.dataset.name || who.textContent);
    const name = (side) => { const el = battle.querySelector(side + ' .trainer strong'); return el ? toId(el.textContent) : ''; };
    if (id && id === name('.leftbar')) say(battle, true, text);
    else if (id && id === name('.rightbar')) say(battle, false, text);
  }
  new MutationObserver((records) => {
    for (const rec of records) {
      // (a burst of lines at once is the log being filled in, not someone talking)
      const lines = [];
      rec.addedNodes.forEach((n) => { if (n.nodeType === 1 && n.classList.contains('chat') && n.parentElement && n.parentElement.closest('.battle-log')) lines.push(n); });
      if (lines.length && lines.length <= 2) lines.forEach((n) => safely(() => heardChat(n)));
    }
  }).observe(document.body, { childList: true, subtree: true });


  // ---------- THE SPARKLES, DRAWN ON CANVASES (--sun-sparkle-canvas: 1) ----------
  // The same sparkles as the filter makes (the same lit edge, blocks, strengths, colours, stars and twinkle), worked out
  // here in the script and painted on a small canvas laid over each character. The browser no longer has to run a long
  // filter over the whole character on every step: a step is a few hundred blocks painted again.
  //
  //   pictures     the character's own pixels, read once per picture (every frame of an animated one, with how long
  //                each frame is shown)
  //   which frame  an animated picture's frames can't be read off the page, but its clock can be told: it starts
  //                when the picture is loaded into its <img> and runs on evenly (measured: hiding it does not stop
  //                the clock; a new <img> starts a new one). So the frame on screen is known from the time.
  //   cells        for one frame at one size: which blocks are on the sun-lit edge (and which on the second light's)
  //   a draw       every edge block's strength from the three slowly mixed noise layers, then its colour
  const pictures = new Map();          // address -> { state, w, h, frames: [{ a, ms }], starts, loop }
  // when each animated picture's clock last started. Measured: the browser keeps ONE clock per picture address. It is
  // set back to the start every time an <img> with that address is put on the page already loaded, finishes loading
  // there, or has its address set again; it then starts running when that picture is first actually drawn (a Pokémon
  // being sent out is on the page, invisible, for a moment before it appears). A box that merely uses the picture as
  // its background joins the running clock; hiding the picture later does not stop it.
  const clockAt = new Map();           // address -> { at: when it started (0 = set back, not yet drawn), img, t: when it was set back }
  const clockKey = (src) => String(src || '').split('#')[0];
  function clockOf(img) {
    const src = img.src;
    if (img.complete && img.naturalWidth) { clockAt.set(clockKey(src), { at: 0, img: img, t: performance.now() }); return; }
    img.addEventListener('load', () => { if (img.src === src) clockAt.set(clockKey(src), { at: 0, img: img, t: performance.now() }); }, { once: true });
  }
  new MutationObserver((records) => {
    for (const rec of records) {
      if (rec.type === 'attributes') { if (rec.target.tagName === 'IMG' && /\/sprites\//.test(rec.target.src || '')) clockOf(rec.target); continue; }
      rec.addedNodes.forEach((n) => {
        if (n.nodeType !== 1) return;
        if (n.tagName === 'IMG') { if (/\/sprites\//.test(n.src || '')) clockOf(n); } else if (n.firstElementChild) n.querySelectorAll('img[src*="/sprites/"]').forEach(clockOf);
      });
    }
  }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['src'] });
  const sparkUnits = new Map();        // the character's element -> its canvas and everything worked out for it
  try { window.__psSparkles = { units: sparkUnits, clocks: clockAt, pictures: pictures }; } catch (e) { /* (for looking into it from the console) */ }
  const sparkAngles = {};              // role -> { a, b }: the two turning angles (kept when a canvas is rebuilt)
  const SHOW_LATE = 16;                // (a frame reaches the screen about one screen refresh after its time)

  function pictureOf(url) {
    let p = pictures.get(url);
    if (p) return p;
    p = { state: 'wait', w: 0, h: 0, frames: [], starts: [], loop: 0 };
    pictures.set(url, p);
    readPicture(url, p).then(() => {
      let t = 0;
      p.starts = p.frames.map((f) => { const at = t; t += f.ms; return at; });
      p.loop = t;
      p.state = p.frames.length ? 'ready' : 'fail';
    }, () => { p.state = 'fail'; });
    return p;
  }
  async function readPicture(url, p) {
    const grab = (source, w, h, ms) => {
      const px = readPixels(source, w, h), a = new Uint8Array(w * h);
      for (let i = 0; i < a.length; i++) a[i] = px[i * 4 + 3] > 127 ? 1 : 0;
      p.frames.push({ a: a, ms: ms }); p.w = w; p.h = h;
    };
    if ('ImageDecoder' in window) {
      try {
        const res = await fetch(url);
        const type = (res.headers.get('content-type') || '').split(';')[0] || (/\.gif/i.test(url) ? 'image/gif' : 'image/png');
        if (res.ok && await ImageDecoder.isTypeSupported(type)) {
          const dec = new ImageDecoder({ data: res.body, type: type });
          try {
            await dec.tracks.ready;
            await dec.completed;
            const count = dec.tracks.selectedTrack ? dec.tracks.selectedTrack.frameCount : 1;
            for (let i = 0; i < count && i < 400; i++) {
              const { image } = await dec.decode({ frameIndex: i });
              const ms = (image.duration || 0) / 1000;
              // (the browser shows a frame marked 10 ms or less for 100 ms)
              grab(image, image.displayWidth, image.displayHeight, count > 1 ? (ms <= 10 ? 100 : ms) : 0);
              image.close();
            }
          } finally { dec.close(); }
          if (p.frames.length) return;
        }
      } catch (e) { p.frames = []; }
    }
    // (no decoder in this browser, or it could not be fetched: the picture as an ordinary image, its first frame)
    await new Promise((done, fail) => {
      const im = new Image();
      im.onload = () => { try { grab(im, im.naturalWidth, im.naturalHeight, 0); done(); } catch (e) { fail(e); } };
      im.onerror = fail;
      im.src = url;
    });
  }
  function frameNow(p, since, now) {
    if (p.frames.length < 2 || !(p.loop > 0)) return 0;
    const t = (((now - since - SHOW_LATE) % p.loop) + p.loop) % p.loop;
    let i = p.starts.length - 1;
    while (i > 0 && p.starts[i] > t) i--;
    return i;
  }

  // smooth noise, one value per point, the same every time for the same point and layer (a gradient noise on a grid
  // of one unit; scaled so that it varies as much round 0.5 as the browser's own noise did in the filter)
  const GRAD = Array.from({ length: 16 }, (_, i) => [Math.cos(i * Math.PI / 8), Math.sin(i * Math.PI / 8)]);
  function gradAt(ix, iy, seed) {
    let h = Math.imul(ix, 374761393) ^ Math.imul(iy, 668265263) ^ Math.imul(seed, 1274126177);
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    return GRAD[((h ^ (h >>> 16)) >>> 0) & 15];
  }
  function smoothNoise(x, y, seed) {
    const x0 = Math.floor(x), y0 = Math.floor(y), fx = x - x0, fy = y - y0;
    const u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy);
    const g00 = gradAt(x0, y0, seed), g10 = gradAt(x0 + 1, y0, seed), g01 = gradAt(x0, y0 + 1, seed), g11 = gradAt(x0 + 1, y0 + 1, seed);
    const a = g00[0] * fx + g00[1] * fy, b = g10[0] * (fx - 1) + g10[1] * fy, c = g01[0] * fx + g01[1] * (fy - 1), d = g11[0] * (fx - 1) + g11[1] * (fy - 1);
    return a + (b - a) * u + (c + (d - c) * u - (a + (b - a) * u)) * v;
  }
  let noiseSpread = 0;
  function noiseScale() {
    if (!noiseSpread) {
      let sum = 0, sq = 0, n = 0;
      for (let i = 0; i < 6000; i++) { const v = smoothNoise(i * 0.6180339 % 97 + i * 0.013, i * 0.7548776 % 89 + 0.31, 7); sum += v; sq += v * v; n++; }
      noiseSpread = Math.sqrt(sq / n - (sum / n) * (sum / n)) || 0.25;
    }
    return NOISE_SPREAD / noiseSpread;
  }

  // the rest of the character's colour settings (the style applies them to the picture after the sparkles went on,
  // so they applied to the sparkles too): the same done to the sparkle colours here
  function toneOf(role) {
    const mon = role === 'mine' || role === 'foe';
    const side = role === 'mine' ? '--player' : role === 'foe' ? '--foe' : role === 'tmine' ? '--player-trainer' : '--foe-trainer';
    const con = readNumber(side + '-contrast', 1) * (mon ? 1.06 : 1), sat = readNumber(side + '-saturate', 1) * (mon ? 1.1 : 1), bri = readNumber(side + '-brightness', 1);
    const cl = (x) => Math.min(1, Math.max(0, x));
    const contrast = (c) => c.map((x) => cl((x - 0.5) * con + 0.5));
    const saturate = (c) => {
      const s2 = sat;
      return [cl((0.213 + 0.787 * s2) * c[0] + (0.715 - 0.715 * s2) * c[1] + (0.072 - 0.072 * s2) * c[2]),
        cl((0.213 - 0.213 * s2) * c[0] + (0.715 + 0.285 * s2) * c[1] + (0.072 - 0.072 * s2) * c[2]),
        cl((0.213 - 0.213 * s2) * c[0] + (0.715 - 0.715 * s2) * c[1] + (0.072 + 0.928 * s2) * c[2])];
    };
    const bright = (c) => c.map((x) => cl(x * bri));
    return { key: [con, sat, bri].join(','), fn: mon ? (c) => bright(saturate(contrast(c))) : (c) => bright(contrast(saturate(c))) };
  }
  // one colour's table at 256 strengths: [r, g, b, opacity] each 0-255
  function colourLut(name, st, look, floor, tone) {
    const t = sparkleTable(name, st, look.sat, look.bright, floor, look.low), lut = new Uint8ClampedArray(1024);
    for (let i = 0; i < 256; i++) {
      const x = i / 255 * 20, k = Math.min(19, Math.floor(x)), f = x - k;
      const rgb = tone([0, 1, 2].map((c) => t[c][k] + (t[c][k + 1] - t[c][k]) * f));
      lut[i * 4] = rgb[0] * 255; lut[i * 4 + 1] = rgb[1] * 255; lut[i * 4 + 2] = rgb[2] * 255; lut[i * 4 + 3] = (t[3][k] + (t[3][k + 1] - t[3][k]) * f) * 255;
    }
    return lut;
  }

  function sparkSources(battle, list) {
    const out = list.map(({ img, st }) => ({ el: img, role: st.mine ? 'mine' : 'foe', st: st }));
    const a = battle.querySelector('.leftbar .trainer .trainersprite'), b = battle.querySelector('.rightbar .trainer .trainersprite');
    if (a) out.push({ el: a, role: 'tmine', st: null });
    if (b) out.push({ el: b, role: 'tfoe', st: null });
    return out;
  }
  function dropSpark(el) {
    const u = sparkUnits.get(el);
    if (u) { u.canvas.remove(); sparkUnits.delete(el); }
  }
  function sparkDirtyAll() { sparkUnits.forEach((u) => { u.drawn = ''; }); }
  function stepSparkRole(role) {
    const o = sparkAngles[role] || (sparkAngles[role] = { a: (hashOf('ps-sun-' + role) % 628) / 100, b: (hashOf('ps-sun-' + role + 'b') % 628) / 100 });
    o.a = (o.a + TURN_A) % (2 * Math.PI); o.b = (o.b + TURN_B) % (2 * Math.PI);
    sparkUnits.forEach((u) => { if (u.role === role) u.drawn = ''; });
  }

  // everything about a character's sparkles that stays the same from step to step: sizes, the grid of blocks, the
  // noise at each block, the colour tables
  function buildSpark(u, src, aim, rect, dpr) {
    const v = sparkSet, mineSide = u.role === 'mine' || u.role === 'tmine';
    const count = mineSide ? v.sparkPlayer : v.sparkFoe, size = mineSide ? v.sizePlayer : v.sizeFoe, points = mineSide ? v.pointsPlayer : v.pointsFoe;
    const strength = v.sun * (mineSide ? v.sunPlayer : v.sunFoe) * v.sparkStrength, look = v.sparkLook, dots = aim.dots;
    if (!(count > 0) || !(strength > 0) || !(size > 0) || !(dots > 0)) return null;
    // (the same sizes as the filter: see sparkleFilter)
    const perPx = dots / aim.scale;
    let d = Math.max(1, Math.round(size * perPx));
    const blocky = v.sparkPixel > 0 && d >= 2;
    if (blocky) d = Math.max(3, 2 * Math.round((size * perPx - 1) / 2) + 1);
    const reach = Math.max(0, Math.round(points * d)), long = points >= 1.5 && reach >= 2;
    const rIn = long ? Math.max(1, Math.round(reach / 2)) : reach, rOut = reach;
    const st = Math.min(1, strength);
    const levelBelow = function (q) {
      const t = Math.sqrt(-2 * Math.log(Math.min(q, 1 - q)));
      const w = t - (2.515517 + 0.802853 * t + 0.010328 * t * t) / (1 + 1.432788 * t + 0.189269 * t * t + 0.001308 * t * t * t);
      return q < 0.5 ? -w : w;
    };
    const dark = levelBelow(0.15) * NOISE_SPREAD, full = 1.8 * NOISE_SPREAD;
    const plan = starPlan(count / (100 * perPx), d), gap = plan.gap;
    const low = Math.min(look.gold.low, look.green.low), floor = Math.min(0.95, Math.max(0, low || 0));
    const open = floor + (1 - floor) * Math.min(0.9, Math.max(0.2, (levelBelow(1 - plan.share) * NOISE_SPREAD - dark) / (full - dark)));
    // the canvas: the character's box on the screen in whole screen dots, with room round it for the stars' points
    // (the grid of blocks is the filter's: its lines run through the whole screen dot the box's own corner falls in -
    // its right corner for a mirrored picture - so the canvas starts a whole number of blocks before that)
    const pad = d * Math.ceil(Math.max(2, rOut + 1) / d);
    const L = rect.left * dpr, T = rect.top * dpr, R = rect.right * dpr, bw = Math.max(1, Math.round(rect.width * dpr)), bh = Math.max(1, Math.round(rect.height * dpr));
    const SL = aim.mirrored ? Math.floor(R + 0.005) - d * Math.ceil((Math.floor(R + 0.005) - Math.floor(L + 0.005) + pad) / d) : Math.floor(L + 0.005) - pad, ST = Math.floor(T + 0.005) - pad;
    const W = Math.ceil(R) + pad - SL, H = Math.ceil(T + bh) + pad - ST, nx = Math.ceil(W / d), ny = Math.ceil(H / d);
    if (nx * ny > 1500000) return null;
    // how the picture lies in the box: one of its own pixels = sNat screen dots; a trainer's picture sits top-centre
    // in its box at its own size, a Pokémon's fills its box
    const pic = src.pic, mon = u.role === 'mine' || u.role === 'foe';
    const sNat = mon ? rect.width * dpr / pic.w : dots;
    const ox = mon ? 0 : ((u.el.offsetWidth || pic.w) - pic.w) / 2 * dots;
    const tone = toneOf(u.role);
    const g = {
      d: d, reach: reach, long: long, rIn: rIn, rOut: rOut, pad: pad, W: W, H: H, bw: bw, bh: bh, nx: nx, ny: ny, sNat: sNat, ox: ox, mirrored: !!aim.mirrored,
      offX: SL - L, offY: ST - T, gap: gap, floor: floor, open: open, gain: 1 / (full - dark), off: -dark / (full - dark),
      sun: [Math.cos(aim.deg * Math.PI / 180), Math.sin(aim.deg * Math.PI / 180)],
      lut: {}, cells: new Map(),
      n1: new Float32Array(nx * ny), n2: new Float32Array(nx * ny), n3: new Float32Array(nx * ny), warm: new Float32Array(nx * ny), cool: new Float32Array(nx * ny),
    };
    ['gold', 'orange'].forEach((n) => { g.lut[n] = colourLut(n, st, look.gold, floor, tone.fn); });
    ['emerald', 'lime', 'sea'].forEach((n) => { g.lut[n] = colourLut(n, st, look.green, floor, tone.fn); });
    // the noise at every block's middle: three layers for the brightness, a fourth that picks the colour
    const k = noiseScale(), seed = hashOf('ps-sun-' + u.role + 's') % 9000 + 1, mid = (d - 1) / 2;
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const x = (i * d + mid + 0.5 + (SL - L)) / gap, y = (j * d + mid + 0.5 + (ST - T)) / gap, c = j * nx + i;
        g.n1[c] = 0.5 + smoothNoise(x, y, seed) * k; g.n2[c] = 0.5 + smoothNoise(x + 37.3, y + 11.7, seed + 101) * k; g.n3[c] = 0.5 + smoothNoise(x + 71.9, y + 53.1, seed + 202) * k;
        const pick = 0.5 + smoothNoise(x + 19.1, y + 83.3, seed + 303) * k;
        g.warm[c] = Math.min(1, Math.max(0, 23.6 * pick - 12.18)); g.cool[c] = Math.min(1, Math.max(0, -23.6 * pick + 11.42));
      }
    }
    return g;
  }
  // for one frame of the picture: the blocks on the lit edge
  function sparkCells(u, frame, second) {
    const g = u.geo, key = frame + '|' + (second ? second.deg : '-');
    let cells = g.cells.get(key);
    if (cells) return cells;
    const pic = u.pic, a = pic.frames[frame].a, w = pic.w, h = pic.h, s = g.sNat, d = g.d, mid = (d - 1) / 2;
    // is there picture at this spot? (x, y in screen dots from the box's own corner)
    const at = (x, y) => {
      const px = Math.floor(((g.mirrored ? g.bw - x : x) - g.ox) / s), py = Math.floor(y / s);
      return px >= 0 && py >= 0 && px < w && py < h && a[py * w + px] === 1;
    };
    // lit by a light in direction (ux, uy): nothing of the picture one to ten of its own pixels toward the light
    // (each of those ten distances in whole screen dots, as the filter shifted its copies)
    const lit = (x, y, ux, uy) => {
      for (let m = 1; m <= 10; m++) if (at(x + Math.round(ux * m * s), y + Math.round(uy * m * s))) return false;
      return true;
    };
    // on the outer ring (one block wide): not every dot within a block of here is picture. (Checked a picture pixel
    // apart, and at the far ends: the picture has no detail finer than that.)
    const hop = Math.max(1, Math.floor(s)), offs = [];
    for (let q = -d; q < d; q += hop) offs.push(q);
    offs.push(d);
    const ring = (x, y) => {
      for (let a2 = 0; a2 < offs.length; a2++) for (let b2 = 0; b2 < offs.length; b2++) if (!at(x + offs[b2], y + offs[a2])) return true;
      return false;
    };
    const idx = [], sunOn = [], secOn = [], zone = second ? new Uint8Array(g.nx * g.ny) : null;
    const u2 = second ? [Math.cos(second.deg * Math.PI / 180), Math.sin(second.deg * Math.PI / 180)] : null;
    for (let j = 0; j < g.ny; j++) {
      for (let i = 0; i < g.nx; i++) {
        const x = i * d + mid + 0.5 + g.offX, y = j * d + mid + 0.5 + g.offY;      // the block's middle dot, from the box's own corner
        if (!at(x, y)) continue;
        const bySun = lit(x, y, g.sun[0], g.sun[1]), bySec = !!u2 && lit(x, y, u2[0], u2[1]);
        if (bySec) {                                   // (its colour reaches the blocks round it too)
          for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) {
            const ii = i + di, jj = j + dj;
            if (ii >= 0 && jj >= 0 && ii < g.nx && jj < g.ny) zone[jj * g.nx + ii] = 1;
          }
        }
        if ((bySun || bySec) && ring(x, y)) { idx.push(j * g.nx + i); sunOn.push(bySun ? 1 : 0); secOn.push(bySec ? 1 : 0); }
      }
    }
    cells = { idx: Int32Array.from(idx), sun: Uint8Array.from(sunOn), sec: Uint8Array.from(secOn), zone: zone };
    if (g.cells.size > 240) g.cells.clear();
    g.cells.set(key, cells);
    return cells;
  }
  function drawSpark(u, frame, level, second) {
    const g = u.geo, cells = sparkCells(u, frame, second), nx = g.nx, d = g.d;
    const o = sparkAngles[u.role] || (sparkAngles[u.role] = { a: (hashOf('ps-sun-' + u.role) % 628) / 100, b: (hashOf('ps-sun-' + u.role + 'b') % 628) / 100 });
    const tilt = 0.9 * Math.sin(o.b);
    const w1 = Math.cos(o.a) * Math.cos(tilt) * g.gain, w2 = Math.sin(o.a) * Math.cos(tilt) * g.gain, w3 = Math.sin(tilt) * g.gain, off = g.off - 0.5 * (w1 + w2 + w3);
    const img = u.small.createImageData(nx, g.ny), px = img.data, str = u.str;
    str.fill(0);
    const L = g.lut, col = [0, 0, 0, 0];
    // the colour of block c at strength s (0 to 1): gold or slightly orange in the sun; emerald, lime or sea green
    // where the second light reaches (as far as it is out)
    const colour = (c, sv) => {
      const k = Math.min(255, Math.max(0, Math.round(sv * 255))) * 4, wm = g.warm[c], z = cells.zone && cells.zone[c] ? level : 0;
      for (let q = 0; q < 4; q++) {
        let val = L.gold[k + q] * (1 - wm) + L.orange[k + q] * wm;
        if (z > 0) {
          const cm = g.cool[c], green = L.emerald[k + q] * (1 - wm) * (1 - cm) + L.lime[k + q] * wm + L.sea[k + q] * cm;
          val = val * (1 - z) + green * z;
        }
        col[q] = val;
      }
      return col;
    };
    const stars = [];
    for (let n = 0; n < cells.idx.length; n++) {
      const c = cells.idx[n];
      const edge = cells.sec[n] ? level + (cells.sun[n] ? 1 - level : 0) : 1;      // (lit by either light; the second one as far as it is out)
      if (!(edge > 0)) continue;
      const field = Math.min(1, Math.max(0, w1 * g.n1[c] + w2 * g.n2[c] + w3 * g.n3[c] + off));
      const gl = (g.floor > 0 ? g.floor + (1 - g.floor) * field : field) * edge;
      const peak = gl > g.open ? (gl - g.open) / (1 - g.open) : 0;
      const p1 = g.reach > 0 ? peak * (g.long ? 0.75 : 0.55) : 0, p2 = g.long ? peak * 0.4 : 0;
      const sv = 1 - (1 - gl) * (1 - p1) * (1 - p2);
      str[c] = sv;
      const rgba = colour(c, sv);
      px[c * 4] = rgba[0]; px[c * 4 + 1] = rgba[1]; px[c * 4 + 2] = rgba[2]; px[c * 4 + 3] = rgba[3];
      if (peak > 0 && g.reach > 0) stars.push(c, p1, p2);
    }
    u.small.putImageData(img, 0, 0);
    const ctx2 = u.ctx;
    ctx2.clearRect(0, 0, g.W, g.H);
    ctx2.imageSmoothingEnabled = false;
    ctx2.drawImage(u.smallCanvas, 0, 0, nx * d, g.ny * d);
    // the stars' four short points: strips beside the block, as strong as that part of a star is; where a strip
    // falls on another lit block it adds to that block's own strength
    const strip = (c, p, x, y, wd, ht) => {
      const sv = 1 - (1 - str[c]) * (1 - p), rgba = colour(c, sv);
      ctx2.clearRect(x, y, wd, ht);
      ctx2.fillStyle = 'rgba(' + Math.round(rgba[0]) + ',' + Math.round(rgba[1]) + ',' + Math.round(rgba[2]) + ',' + (rgba[3] / 255).toFixed(3) + ')';
      ctx2.fillRect(x, y, wd, ht);
    };
    for (let n = 0; n < stars.length; n += 3) {
      const c = stars[n], i = c % nx, j = (c - i) / nx, x = i * d, y = j * d;
      const arms = (p, r) => {
        if (!(p > 0) || !(r > 0)) return;
        const whole = Math.floor(r / d), part = r - whole * d;          // (a long point crosses whole blocks, then part of one)
        for (let q = 1; q <= whole + (part > 0 ? 1 : 0); q++) {
          const len = q <= whole ? d : part;
          if (i - q >= 0) strip(c - q, p, x - (q - 1) * d - len, y, len, d);
          if (i + q < nx) strip(c + q, p, x + q * d, y, len, d);
          if (j - q >= 0) strip(c - q * nx, p, x, y - (q - 1) * d - len, d, len);
          if (j + q < g.ny) strip(c + q * nx, p, x, y + q * d, d, len);
        }
      };
      if (g.long) arms(stars[n + 2], g.rOut);                                    // (long points: fainter out to the tip...)
      arms(g.long ? 1 - (1 - stars[n + 1]) * (1 - stars[n + 2]) : stars[n + 1], g.rIn);   // (...stronger near the middle)
    }
  }
  // called on every screen frame: each character's canvas is kept on its character, and drawn again when its
  // sparkles took a step or its picture moved on to its next frame
  function syncSparks(battle, inner, ir, k, list, now) {
    const sources = sparkSources(battle, list), dpr = window.devicePixelRatio || 1;
    const on = sparkCanvas > 0 && sparkSet && sparkSet.sun > 0 && !perf.off;
    const seen = new Set();
    for (const src of sources) {
      const el = src.el, aim = sunAim[src.role];
      const mon = !!src.st;
      const op = mon && el.style.opacity !== '' ? parseFloat(el.style.opacity) : 1;
      if (mon) {
        // its picture's clock: set back and not yet running, it starts when this picture is first drawn (or, when
        // the <img> that set it back is some other one still on the page, it started there and then)
        const c = clockAt.get(clockKey(el.src));
        if (c && !c.at) {
          if (c.img === el || !c.img.isConnected) { if (op > 0 && el.style.display !== 'none') c.at = now - 20; } else c.at = c.t;      // (measured: it began 13-32 ms before this frame saw it)
        }
      }
      if (!on || !aim) { dropSpark(el); continue; }
      const url = mon ? (el.currentSrc || el.src) : ((/url\(["']?(.*?)["']?\)/.exec(el.style.backgroundImage || '') || [])[1] || '');
      if (!url) { dropSpark(el); continue; }
      const pic = pictureOf(url.split('#')[0]);
      if (pic.state !== 'ready') { if (pic.state === 'fail') dropSpark(el); continue; }
      const r = el.getBoundingClientRect();
      const shown = r.width > 0 && r.height > 0 && el.style.display !== 'none' && op > 0.01;
      let u = sparkUnits.get(el);
      if (!u || !u.canvas.isConnected || u.canvas.previousElementSibling !== el) {
        if (u) u.canvas.remove();
        const canvas = document.createElement('canvas');
        canvas.className = 'ps-spark ps-spark-' + src.role;
        el.after(canvas);
        const smallCanvas = document.createElement('canvas');
        u = { el: el, role: src.role, canvas: canvas, ctx: canvas.getContext('2d'), smallCanvas: smallCanvas, small: smallCanvas.getContext('2d'), geo: null, key: '', drawn: '', sizeAt: now, size: '' };
        sparkUnits.set(el, u);
      }
      seen.add(el);
      put(u.canvas, 'display', shown ? 'block' : 'none');
      if (!shown) continue;
      // (re)build when the picture, its size on screen, the light's direction or a setting has changed; a size that
      // is still changing (growing as it is sent out, a move that scales it) waits until it has settled
      const size = Math.round(r.width * dpr) + 'x' + Math.round(r.height * dpr);
      if (size !== u.size) { u.size = size; u.sizeAt = now; }
      const tone = toneOf(src.role);
      const sv = sparkSet;
      const key = [url, size, aim.deg, aim.dots, aim.scale, aim.mirrored, dpr, tone.key, sv.sun, sv.sunPlayer, sv.sunFoe, sv.sparkStrength, sv.sparkPlayer, sv.sparkFoe,
        sv.sizePlayer, sv.sizeFoe, sv.pointsPlayer, sv.pointsFoe, sv.sparkPixel, JSON.stringify(sv.sparkLook)].join('|');
      if (key !== u.key && (!u.geo || now - u.sizeAt > 120)) {
        u.key = key; u.pic = pic; u.drawn = '';
        u.geo = buildSpark(u, { pic: pic }, aim, r, dpr);
        if (u.geo) {
          u.canvas.width = u.geo.W; u.canvas.height = u.geo.H; u.smallCanvas.width = u.geo.nx; u.smallCanvas.height = u.geo.ny;
          u.str = new Float32Array(u.geo.nx * u.geo.ny);
          u.box = { w: r.width, h: r.height };
        }
      }
      const g = u.geo;
      if (!g) { put(u.canvas, 'display', 'none'); continue; }
      // where it goes: over the character, on whole screen dots (in the px of whatever the canvas is placed against)
      const parent = u.canvas.offsetParent || inner, pr = parent.getBoundingClientRect();
      const kx = parent.offsetWidth ? pr.width / parent.offsetWidth : k, ky = parent.offsetHeight ? pr.height / parent.offsetHeight : k;
      const sx = r.width / u.box.w, sy = r.height / u.box.h;                  // (stretched with the character while its size is changing)
      const x = Math.round(r.left * dpr + g.offX * sx) / dpr, y = Math.round(r.top * dpr + g.offY * sy) / dpr;
      put(u.canvas, 'translate', ((x - pr.left) / kx - parent.clientLeft).toFixed(3) + 'px ' + ((y - pr.top) / ky - parent.clientTop).toFixed(3) + 'px');
      put(u.canvas, 'width', (g.W * sx / dpr / kx).toFixed(3) + 'px');
      put(u.canvas, 'height', (g.H * sy / dpr / ky).toFixed(3) + 'px');
      if (mon) put(u.canvas, 'opacity', op < 0.995 ? op.toFixed(2) : '');
      // which frame of the picture is on screen, and the second light
      let frame = 0;
      if (u.pic.frames.length > 1) {
        const c = clockAt.get(clockKey(el.src));
        if (c && c.at) { u.since = c.at; u.sinceSrc = url; }
        else if (!u.since || u.sinceSrc !== url) { u.since = now; u.sinceSrc = url; }      // (its start was not seen: from now, which may be out of step)
        frame = frameNow(u.pic, u.since, now);
      }
      const second = secondLight.cfg && secondAim[src.role] ? secondAim[src.role] : null;
      const level = second ? secondLightLevel(now) : 0;
      const state = frame + '|' + level.toFixed(3) + '|' + (second ? second.deg : '-') + '|' + (sparkAngles[src.role] ? sparkAngles[src.role].a.toFixed(4) : '');
      if (u.drawn !== state) {
        u.drawn = state;
        drawSpark(u, frame, level, level > 0 ? second : null);
        if (u.canvas.dataset.frame !== String(frame)) u.canvas.dataset.frame = String(frame);      // (which frame of the picture it was drawn for)
      }
    }
    sparkUnits.forEach((u, el) => { if (!seen.has(el) && (!el.isConnected || battle.contains(el))) dropSpark(el); });
  }


  // ---------- HOVER INFO OVER THE POKÉMON, AND TOOLTIPS ABOVE WHAT YOU POINT AT ----------
  // Showdown's hover boxes over the Pokémon sit where it would draw them, not where the style moves and resizes them,
  // and team preview has none. So: each hover box is laid over the Pokémon as it is shown; on team preview each of the
  // twelve gets one (Showdown's own "pokemon" info: types, ability, item and stats as far as they are known). And
  // every tooltip in a battle is placed centred above the thing pointed at (below it when there is no room above).
  // (the box is the Pokémon's own drawn pixels, not its whole picture: the pictures are mostly empty and overlap
  // their neighbours, and the one on top would catch the pointer)
  function opaqueOf(pic) {
    if (pic.bbox !== undefined) return pic.bbox;
    let x0 = pic.w, y0 = pic.h, x1 = -1, y1 = -1;
    pic.frames.forEach((f) => {
      for (let y = 0; y < pic.h; y++) for (let x = 0; x < pic.w; x++) {
        if (f.a[y * pic.w + x]) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
      }
    });
    pic.bbox = x1 < 0 ? null : { x0: x0 / pic.w, y0: y0 / pic.h, x1: (x1 + 1) / pic.w, y1: (y1 + 1) / pic.h };
    return pic.bbox;
  }
  function hoverRect(el, layer, k) {
    let r = el.getBoundingClientRect();
    const lr = layer.getBoundingClientRect(), url = (el.currentSrc || el.src || '').split('#')[0];
    if (url) {
      const pic = pictureOf(url), bb = pic.state === 'ready' ? opaqueOf(pic) : null;
      if (bb) r = { left: r.left + bb.x0 * r.width, top: r.top + bb.y0 * r.height, width: (bb.x1 - bb.x0) * r.width, height: (bb.y1 - bb.y0) * r.height };
    }
    return { left: (r.left - lr.left) / k, top: (r.top - lr.top) / k, width: r.width / k, height: r.height / k };
  }
  function placeHover(zone, b) {
    put(zone, 'left', b.left.toFixed(1) + 'px'); put(zone, 'top', b.top.toFixed(1) + 'px');
    put(zone, 'width', Math.max(4, b.width).toFixed(1) + 'px'); put(zone, 'height', Math.max(4, b.height).toFixed(1) + 'px');
  }
  function battleObject(battle) {
    const room = battle.closest('.ps-room');
    const r = room && window.app && window.app.rooms && window.app.rooms[room.id.replace(/^room-/, '')];
    return r && r.battle ? r.battle : null;
  }
  function syncHover(battle, inner, k, list) {
    const layer = inner.querySelector(':scope > .tooltips');
    if (!layer || !(hoverOn > 0)) return;
    const own = Array.from(layer.querySelectorAll(':scope > .has-tooltip:not(.ps-hover)'));
    const mine = Array.from(layer.querySelectorAll(':scope > .ps-hover'));
    if (battle.classList.contains('ps-tp')) {
      own.forEach((z) => put(z, 'display', 'none'));                       // (no one is out yet: Showdown's boxes point at nobody)
      const tpUnits = [];
      const bo = battleObject(battle), flip = bo && bo.viewpointSwitched ? 1 : 0;
      const zones = [];
      // each side's sprites are in the order of its team (Showdown wrote them so)
      Array.from(inner.querySelectorAll(':scope > div > div')).forEach((box) => {
        const imgs = Array.from(box.querySelectorAll(':scope > img[src*="/sprites/"]'));
        if (imgs.length < 2) return;
        const back = imgs[0].src.includes('-back'), side = (back ? 0 : 1) ^ flip;
        // (your own team: Showdown's fuller info from your team sheet - real stats, ability, item, moves)
        const own = bo && bo.mySide && bo.sides && bo.sides[side] === bo.mySide && bo.myPokemon && bo.myPokemon.length === imgs.length;
        imgs.forEach((img, i) => zones.push({ img: img, back: back, tip: own ? 'switchpokemon|' + i : 'pokemon|' + side + '|' + i }));
      });
      // (your six are drawn big and their boxes reach over the opponent's: the opponent's boxes go on top)
      zones.sort((a, b) => (b.back ? 1 : 0) - (a.back ? 1 : 0));
      zones.forEach((z, n) => {
        let zone = mine[n];
        if (!zone) { zone = document.createElement('div'); zone.className = 'has-tooltip ps-hover'; zone.dataset.ownheight = '1'; layer.appendChild(zone); }
        if (zone.dataset.tooltip !== z.tip) zone.dataset.tooltip = z.tip;
        put(zone, 'position', 'absolute'); put(zone, 'display', isShowing(z.img) ? 'block' : 'none'); put(zone, 'pointer-events', 'none');
        placeHover(zone, hoverRect(z.img, layer, k));
        tpUnits.push({ img: z.img, zone: zone });
      });
      mine.slice(zones.length).forEach((z) => z.remove());
      // (in the order they are drawn, last on top)
      tpUnits.sort((a, b) => (a.img.compareDocumentPosition(b.img) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1);
      battle._psUnits = tpUnits;
      return;
    }
    mine.forEach((z) => z.remove());
    const units = [];
    // in battle: Showdown's boxes (p1a, p2b, ...) laid over the Pokémon in that spot, as shown
    ['1', '2'].forEach((p) => {
      const slot = (z) => parseInt((z.dataset.tooltip || '').split('|')[2], 10) || 0;
      const boxes = own.filter((z) => (z.dataset.id || '').charAt(1) === p).sort((a, b) => slot(a) - slot(b));
      // (Showdown names its spots by the screen, not by player: "p1" spots are always the near side - yours - and
      // "p2" the far side, whichever player you are)
      const mineSide = p === '1';
      const sprites = list.filter(({ st }) => st.shown && !!st.mine === mineSide).map(({ img }) => img).sort((a, b) => a.offsetLeft - b.offsetLeft);
      boxes.forEach((z, i) => {
        const img = sprites[i];                       // (the spots in order: a, b, c; spots nobody stands in catch nothing)
        if (!img) { put(z, 'display', 'none'); return; }
        put(z, 'display', 'block'); put(z, 'pointer-events', 'none');
        placeHover(z, hoverRect(img, layer, k));
        units.push({ img: img, zone: z });
      });
    });
    units.sort((a, b) => (a.img.compareDocumentPosition(b.img) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1);
    battle._psUnits = units;
  }
  // Which Pokémon is under the pointer: the one whose own drawn pixel is there, the one drawn on top winning (a
  // picture's empty corners catch nothing). Buttons, the chat line and anything else you can click come first.
  // Its info is then shown, placed above it (as Showdown would for its own hover boxes).
  let pointerAt = null, hoverShown = null;
  document.addEventListener('mousemove', (e) => { pointerAt = { x: e.clientX, y: e.clientY }; safely(checkHover); }, { passive: true, capture: true });
  document.addEventListener('mouseleave', () => { pointerAt = null; safely(checkHover); }, true);
  window.addEventListener('blur', () => { pointerAt = null; safely(checkHover); });
  const ON_TOP = 'button, input, textarea, select, a, label, .battle-controls, .battle-log-add, .ps-max-button, #tooltipwrapper, .picon, .leftbar .statbar, .rightbar .statbar, .has-tooltip:not(.ps-hover):not(.tooltips > div)';
  function drawnAt(img, x, y, give) {
    const r = img.getBoundingClientRect();
    if (x < r.left || y < r.top || x >= r.right || y >= r.bottom || !r.width || !r.height) return false;
    const url = (img.currentSrc || img.src || '').split('#')[0], pic = url && pictureOf(url);
    if (!pic || pic.state !== 'ready') return true;                        // (not read yet: its whole box)
    let f = 0;
    if (pic.frames.length > 1) { const c = clockAt.get(clockKey(img.src)); if (c && c.at) f = frameNow(pic, c.at, performance.now()); }
    const a = pic.frames[f].a, px = Math.floor((x - r.left) / r.width * pic.w), py = Math.floor((y - r.top) / r.height * pic.h);
    const g = give ? 1 : 0;
    for (let dy = -g; dy <= g; dy++) for (let dx = -g; dx <= g; dx++) {   // (with give: a picture pixel's width round the edge)
      const qx = px + dx, qy = py + dy;
      if (qx >= 0 && qy >= 0 && qx < pic.w && qy < pic.h && a[qy * pic.w + qx]) return true;
    }
    return false;
  }
  function checkHover() {
    let found = null, battleEl = null;
    if (pointerAt && hoverOn > 0) {
      const top = document.elementFromPoint(pointerAt.x, pointerAt.y);
      battleEl = top && top.closest('.battle');
      if (battleEl && battleEl._psUnits && !top.closest(ON_TOP)) {
        const list = battleEl._psUnits;
        // (first exactly on a drawn pixel; only when that finds nobody, a pixel's give round the edges)
        for (let pass = 0; pass < 2 && !found; pass++) {
          for (let i = list.length - 1; i >= 0; i--) {
            const u = list[i];
            if (u.zone.isConnected && u.zone.style.display !== 'none' && isShowing(u.img) && drawnAt(u.img, pointerAt.x, pointerAt.y, pass === 1)) { found = u.zone; break; }
          }
        }
      }
    }
    const BT = window.BattleTooltips;
    if (!BT || BT.isLocked) return;
    if (found === hoverShown) return;
    if (found) {
      const bo = battleObject(battleEl), tt = bo && bo.scene && bo.scene.tooltips;
      if (!tt) return;
      tt.showTooltip(found);
      hoverShown = found;
    } else {
      if (hoverShown) BT.hideTooltip();
      hoverShown = null;
    }
  }
  // the tooltip itself: after Showdown has placed it (at the left edge of the thing pointed at), centred above it
  function wrapTooltips() {
    const BT = window.BattleTooltips;
    if (!BT || !BT.prototype || BT.prototype._psWrapped || typeof BT.prototype.placeTooltip !== 'function') return;
    const orig = BT.prototype.placeTooltip;
    BT.prototype.placeTooltip = function (innerHTML, hoveredElem) {
      const out = orig.apply(this, arguments);
      try {
        if (hoverOn > 0 && hoveredElem && hoveredElem.closest && hoveredElem.closest('.ps-room, .battle')) {
          const wrap = document.getElementById('tooltipwrapper'), tip = BT.elem;
          if (wrap && tip) {
            const r = hoveredElem.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
            const vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
            const x = Math.min(Math.max(2, r.left + r.width / 2 - w / 2), vw - w - 2);
            let y = r.top - 4;                                          // (the wrapper's top is the tooltip's bottom edge)
            if (y - h < 2) y = Math.min(vh - 2, r.bottom + 4 + h);      // (no room above: below it)
            wrap.style.left = (x + window.scrollX) + 'px';
            wrap.style.top = (y + window.scrollY) + 'px';
          }
        }
      } catch (e) { /* leave Showdown's placing */ }
      return out;
    };
    BT.prototype._psWrapped = true;
  }


  // ---------- SURF: A TALL 2D WAVE (--surf-custom: 1) ----------
  // In place of Showdown's blue flash and stream of water blobs: water swells up round the attacker (as in Black and
  // White 2), rises into a tall breaking wave that runs across to the target, crashes down on it in a burst of
  // spray, and drains away. Drawn flat, in bands of blue with white crest lines, bubbles and round foam, on a
  // canvas at half the battle's resolution (each of its pixels is 2 battle px) laid over the battle.
  const SURF = { deep: [22, 74, 190], mid: [48, 128, 232], light: [118, 190, 255], pale: [196, 232, 255], white: [246, 252, 255] };
  const rgba = (c, a) => 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a.toFixed(3) + ')';
  const ease = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
  const span = (t, a, b) => ease((t - a) / (b - a));
  function surfSeeded(n) { let x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); }
  // where a sprite stands and how big it is, in the battle's own px (its drawn pixels, not its whole picture)
  function standOf(sprite, inner) {
    const img = sprite && sprite.$el && sprite.$el[0];
    if (!img || !img.getBoundingClientRect) return null;
    const ir = inner.getBoundingClientRect(), k = inner.offsetWidth ? ir.width / inner.offsetWidth : 1;
    const b = hoverRect(img, inner, k);
    if (!(b.width > 0)) return null;
    return { x: b.left + b.width / 2, y: b.top + b.height, w: b.width, h: b.height };
  }
  // the wave's outline, standing on the ground at (cx, gy), W wide and H tall, its front toward dir (+1 right,
  // -1 left); curl 0 = a rising wall, 1 = the lip thrown forward over its own face
  function wavePath(g, cx, gy, W, H, curl, dir, lean) {
    const X = (u) => cx + dir * u * W, Y = (v) => gy - v * H;
    const lx = 0.18 + 0.32 * curl + lean, ly = 1 - 0.28 * curl;
    g.beginPath();
    g.moveTo(X(-0.5), Y(0));
    g.bezierCurveTo(X(-0.48), Y(0.45), X(-0.36), Y(0.9), X(-0.08), Y(1));      // back, up to the crest
    g.bezierCurveTo(X(0.12 + 0.1 * curl), Y(1.06), X(lx + 0.06), Y(ly + 0.02), X(lx), Y(ly - 0.1 * curl));   // over the top to the lip
    g.bezierCurveTo(X(lx - 0.1), Y(ly - 0.12), X(0.12 + 0.12 * curl), Y(0.86), X(0.2 + 0.06 * curl), Y(0.62));   // under the lip, into the face
    g.bezierCurveTo(X(0.24), Y(0.4), X(0.3), Y(0.18), X(0.5), Y(0));             // down the face to the ground
    g.closePath();
  }
  function foam(g, x, y, r, a) {
    if (!(r > 0.5) || !(a > 0)) return;
    // a puff: three round lumps, a pale shadow under each
    for (let i = 0; i < 3; i++) {
      const ox = (i - 1) * r * 0.8, oy = (i === 1 ? -r * 0.45 : 0), rr = r * (i === 1 ? 1 : 0.78);
      g.fillStyle = rgba(SURF.pale, a); g.beginPath(); g.arc(x + ox + rr * 0.12, y + oy + rr * 0.18, rr, 0, Math.PI * 2); g.fill();
    }
    for (let i = 0; i < 3; i++) {
      const ox = (i - 1) * r * 0.8, oy = (i === 1 ? -r * 0.45 : 0), rr = r * (i === 1 ? 1 : 0.78);
      g.fillStyle = rgba(SURF.white, a); g.beginPath(); g.arc(x + ox, y + oy, rr * 0.86, 0, Math.PI * 2); g.fill();
    }
  }
  // a white fringe line across the water: a row of little hanging scallops, as Black and White 2 draws its crests
  function fringe(g, x0, x1, y, size, phase, a) {
    g.strokeStyle = rgba(SURF.white, a); g.lineWidth = 1.1;
    g.beginPath();
    const step = Math.max(4, size);
    let first = true;
    for (let x = x0 - ((phase * step) % step); x < x1 + step; x += step) {
      const yy = y + Math.sin(x * 0.07 + phase) * size * 0.25;
      if (first) { g.moveTo(x, yy); first = false; }
      g.quadraticCurveTo(x + step / 2, yy + size * 0.55, x + step, yy);
    }
    g.stroke();
    g.fillStyle = rgba(SURF.white, a * 0.5);                  // (a soft white band just above it)
    g.fillRect(x0, y - size * 0.35, x1 - x0, size * 0.3);
  }
  function drawWave(g, cx, gy, W, H, curl, dir, lean, t, alpha) {
    if (!(H > 1) || !(W > 1) || !(alpha > 0)) return;
    const x0 = cx - W, x1 = cx + W;
    g.save();
    wavePath(g, cx, gy, W, H, curl, dir, lean);
    g.save();
    g.clip();
    // the body: see-through, deep below, lighter towards the top, each band edged by a fringe of white scallops
    const bands = [[SURF.deep, 0.62, 0], [SURF.mid, 0.6, 0.3], [SURF.light, 0.55, 0.62], [SURF.pale, 0.5, 0.86]];
    bands.forEach(([c, a, v]) => { g.fillStyle = rgba(c, a * alpha); g.fillRect(x0, gy - H * 1.25, x1 - x0, H * (1.25 - v) + 2); });
    // bubbles: rounded cells in the upper water, drifting up
    for (let i = 0; i < 40; i++) {
      const bx = cx + (surfSeeded(i) - 0.5) * W * 1.1, v = 0.5 + 0.5 * ((surfSeeded(i + 50) + t * 0.7) % 1), by = gy - H * v;
      const rw = W * (0.025 + 0.03 * surfSeeded(i + 9)), rh = rw * (0.6 + 0.3 * surfSeeded(i + 19));
      g.strokeStyle = rgba(SURF.pale, 0.7 * alpha); g.lineWidth = 1;
      g.beginPath(); g.ellipse(bx, by, rw, rh, 0, 0, Math.PI * 2); g.stroke();
    }
    // the fringes: at the band edges, and more rising through the water
    const sz = Math.max(4, Math.min(W * 0.045, H * 0.16));
    [0.3, 0.62, 0.86].forEach((v, k) => fringe(g, x0, x1, gy - H * v, sz, t * 6 + k * 2, 0.9 * alpha));
    for (let k = 0; k < 3; k++) {
      const v = ((k / 3 + t * 0.9) % 1) * 0.95;
      fringe(g, x0, x1, gy - H * v, sz * 0.8, t * 8 + k * 3.1, 0.6 * alpha * Math.sin(Math.PI * v));
    }
    g.restore();
    // the outline: a white crest along the top and the lip
    wavePath(g, cx, gy, W, H, curl, dir, lean);
    g.strokeStyle = rgba(SURF.white, 0.95 * alpha); g.lineWidth = 1.6; g.stroke();
    g.restore();
  }
  function surfFrame(st, t) {
    const g = st.g, S = st.scale, A = st.a, D = st.d, BH = st.ch / S;
    g.clearRect(0, 0, st.cw, st.ch);
    g.save();
    g.scale(S, S);
    const dir = D.x >= A.x ? 1 : -1, clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
    // sizes at the attacker and at the target (a far target is smaller, so its wave is too); never taller than
    // the battle has room for above where it stands
    // (wide and low: about twice as wide and a little over half as tall as the first version)
    const wA = clamp(A.w * 2.3, 150, 460), hA = clamp(A.h * 0.65, 50, Math.min(BH * 0.36, A.y - 8));
    const wD = clamp(D.w * 3.2, 130, 380), hD = clamp(D.h * 1.05, 45, Math.min(BH * 0.32, D.y - 8));
    if (st.flash > 0) { g.fillStyle = 'rgba(0, 40, 200, ' + (st.flash * span(t, 0.05, 0.25) * (1 - span(t, 0.9, 1.3))).toFixed(3) + ')'; g.fillRect(0, 0, st.cw / S, st.ch / S); }
    const puffs = (x, y, W, n, r, a, seed) => { for (let i = 0; i < n; i++) foam(g, x + (n > 1 ? (i / (n - 1) - 0.5) : 0) * W, y - surfSeeded(i + seed) * r * 0.6, r * (0.75 + 0.5 * surfSeeded(i + seed + 7)), a); };
    if (t < 0.34) {
      // 1. water swells up round the attacker, foam bubbling at its foot
      const r = span(t, 0, 0.3);
      drawWave(g, A.x, A.y + 4, wA * (0.75 + 0.25 * r), hA * r, 0, dir, 0, t, 1);
      puffs(A.x, A.y + 2, wA * 0.95, 8, wA * 0.035 * r, 0.95 * r, 3);
    } else if (t < 0.74) {
      // 2. it rises into a tall breaker, its lip curling forward, and runs across to the target
      const m = span(t, 0.34, 0.74), x = A.x + (D.x - A.x) * m, y = A.y + (D.y - A.y) * m + 4;
      const W = wA + (wD - wA) * m, H = Math.min((hA + (hD - hA) * m) * (1 + 0.1 * Math.sin(Math.PI * m)), y - 10);
      drawWave(g, x, y, W, H, 0.2 + 0.6 * m, dir, 0, t, 1);
      puffs(x, y, W * 0.9, 7, W * 0.032, 0.95, 11);
    } else if (t < 1.0) {
      // 3. it crashes down on the target: the lip falls over and the wave collapses into a burst of foam
      const c = span(t, 0.74, 1.0), x = D.x, y = D.y + 4;
      drawWave(g, x + dir * wD * 0.12 * c, y, wD * (1 + 0.3 * c), hD * (1 - 0.7 * c), 0.8 + 0.2 * c, dir, 0.3 * c, t, 1);
      puffs(x, y, wD * (1 + 0.3 * c), 9, wD * (0.03 + 0.025 * c), 0.95, 21);
    }
    // spray: white tongues bursting up round the target (drawn over it), and drops flying and falling
    if (t > 0.78 && t < 1.34) {
      const p = (t - 0.78) / 0.56;
      for (let i = 0; i < 6; i++) {
        const sx = D.x + (i / 5 - 0.5) * Math.min(wD * 0.9, D.w * 1.6) + (surfSeeded(i + 40) - 0.5) * 10, rise = Math.sin(Math.PI * Math.min(1, p * 1.1));
        const len = D.h * (0.55 + 0.6 * surfSeeded(i + 60)) * rise, wdt = D.w * (0.09 + 0.07 * surfSeeded(i + 70));
        const bend = (i / 5 - 0.5) * 1.1 + (surfSeeded(i + 80) - 0.5) * 0.3, a = 0.92 * (1 - span(p, 0.55, 1));
        if (len <= 1 || a <= 0) continue;
        g.fillStyle = rgba(SURF.pale, a * 0.8);
        g.beginPath(); g.moveTo(sx - wdt, D.y + 3); g.quadraticCurveTo(sx - wdt * 0.2 + bend * len * 0.3, D.y - len * 0.6, sx + bend * len * 0.55, D.y - len); g.quadraticCurveTo(sx + wdt * 0.4 + bend * len * 0.3, D.y - len * 0.5, sx + wdt, D.y + 3); g.closePath(); g.fill();
        g.fillStyle = rgba(SURF.white, a);
        g.beginPath(); g.moveTo(sx - wdt * 0.5, D.y + 2); g.quadraticCurveTo(sx + bend * len * 0.3, D.y - len * 0.55, sx + bend * len * 0.5, D.y - len * 0.92); g.quadraticCurveTo(sx + wdt * 0.2 + bend * len * 0.3, D.y - len * 0.45, sx + wdt * 0.5, D.y + 2); g.closePath(); g.fill();
      }
      for (let i = 0; i < 14; i++) {
        const q = p - surfSeeded(i + 90) * 0.3; if (q <= 0) continue;
        const vx = (surfSeeded(i + 100) - 0.5) * wD * 1.5, vy = D.h * (1 + surfSeeded(i + 110));
        const dx = D.x + vx * q, dy = D.y - vy * (2 * q - 2.2 * q * q), r = 1.4 + 1.6 * surfSeeded(i + 120);
        g.fillStyle = rgba(SURF.white, 0.95 * (1 - span(q, 0.7, 1))); g.beginPath(); g.arc(dx, dy, r, 0, Math.PI * 2); g.fill();
      }
    }
    // 4. after the crash the water rushes on past the target, away from the attacker, as a flat sheet across the
    // ground: a white foam edge in front, a web of white foam lace on its surface that thins and breaks apart, foam
    // lumps along its far side, and the whole sheet thinning and fading as it runs out
    if (t >= 0.86 && t < SURF_END) {
      const q = Math.min(1, (t - 0.86) / (SURF_END - 0.86));
      const run = 1 - Math.pow(1 - q, 2.2);                                     // (fast at first, slowing)
      // (it runs on to about the edge of the battle on that side, at least a little way)
      const edge = dir > 0 ? st.cw / S - 6 : 6, reach = Math.max(wD * 0.8, Math.abs(edge - D.x));
      const front = D.x + dir * (wD * 0.1 + reach * run), back = D.x - dir * wD * (0.55 - 0.75 * run);
      const len = Math.abs(front - back), mid = (front + back) / 2, gy = D.y + 3;
      // (it lies flat on the ground: only a little deep, as seen from the side)
      const depth = clamp(D.h * 0.3, 8, 30) * (1 + 0.25 * run) * (1 - 0.3 * q), fade = 1 - span(q, 0.6, 1);
      if (fade > 0 && len > 2) {
        const P = (u, v) => [back + (front - back) * u, gy + v * depth * (0.55 + 0.45 * Math.sin(Math.PI * Math.min(1, u * 1.1)))];
        const sheet = () => {
          g.beginPath();
          for (let i = 0; i <= 24; i++) { const u = i / 24, w = Math.sin(u * 9 + t * 4) * 0.08; const p2 = P(u, -1 - w); if (i) g.lineTo(p2[0], p2[1]); else g.moveTo(p2[0], p2[1]); }
          const f1 = P(1, -0.6), f2 = P(1, 0.6);
          g.quadraticCurveTo(front + dir * depth * 0.9, gy, f2[0], f2[1]);
          for (let i = 24; i >= 0; i--) { const u = i / 24, w = Math.sin(u * 7 - t * 3) * 0.08; const p2 = P(u, 1 + w); g.lineTo(p2[0], p2[1]); }
          g.closePath();
          return f1;
        };
        g.save();
        sheet(); g.fillStyle = rgba(SURF.deep, 0.62 * fade); g.fill();
        g.clip();
        g.fillStyle = rgba(SURF.mid, 0.5 * fade); g.fillRect(Math.min(back, front), gy - depth * 1.2, len, depth * 0.9);    // (the far half lighter)
        // the lace: a web of thin white lines between scattered points, thinning and breaking apart
        const pts = st.lace;
        g.strokeStyle = rgba(SURF.white, 0.9 * fade); g.lineCap = 'round';
        g.lineWidth = Math.max(0.6, 1.8 * (1 - 0.6 * q));
        g.beginPath();
        for (let i = 0; i < pts.length; i++) {
          const pa = pts[i];
          for (const j of pa.n) {
            const pb = pts[j];
            if (surfSeeded(i * 31 + j) < q * 1.15 - 0.3) continue;            // (more and more of it breaks off)
            const A2 = P(pa.u, pa.v), B2 = P(pb.u, pb.v);
            g.moveTo(A2[0], A2[1]); g.lineTo(B2[0], B2[1]);
          }
        }
        g.stroke();
        g.restore();
        // the foam edge in front: lumps along the leading curve, shrinking
        for (let i = 0; i < 7; i++) {
          const v = i / 6 * 2 - 1, p2 = P(1, v * 0.85), r = depth * (0.14 + 0.1 * surfSeeded(i + 140)) * (1 - 0.6 * q);
          foam(g, p2[0] + dir * depth * 0.5 * (1 - v * v), p2[1], r, 0.95 * fade);
        }
        // foam lumps along the far side, left behind as it runs
        for (let i = 0; i < 9; i++) {
          const u = surfSeeded(i + 160), p2 = P(u, -1), r = depth * (0.12 + 0.12 * surfSeeded(i + 170)) * (1 - 0.5 * q);
          if (u > run + 0.15) continue;
          foam(g, p2[0], p2[1] - r * 0.3, r, 0.9 * fade);
        }
      }
    }
    g.restore();
  }
  const SURF_END = 2.3;                // (seconds: the wave 1, the water running out the rest)
  function surfAnim(scene, sprites) {
    try { if (sheetSurf(scene, sprites)) return; } catch (e) { /* (the drawn wave instead) */ }
    const attacker = sprites[0], defenders = sprites.slice(1).filter(Boolean);
    const target = defenders[1] || defenders[0] || attacker;
    const inner = attacker && attacker.$el && attacker.$el[0] && attacker.$el[0].closest('.innerbattle');
    const acc = scene.acceleration || 1;
    // the target(s) shake as the wave crashes on them (Showdown waits for this before going on)
    defenders.forEach((d) => {
      d.delay(800 / acc);
      for (let i = 0; i < 3; i++) { d.anim({ z: d.behind(5), time: 75 }, 'swing'); d.anim({ time: 75 }, 'swing'); }
    });
    if (!inner) return;
    const A = standOf(attacker, inner), D = standOf(target, inner);
    if (!A || !D) return;
    let cv = inner.querySelector(':scope > canvas.ps-surf');
    if (!cv) { cv = document.createElement('canvas'); cv.className = 'ps-surf'; inner.appendChild(cv); }
    const cw = Math.round(inner.offsetWidth / 2), ch = Math.round(inner.offsetHeight / 2);
    if (cv.width !== cw) cv.width = cw;
    if (cv.height !== ch) cv.height = ch;
    const lace = [];
    for (let i = 0; i < 52; i++) lace.push({ u: 0.04 + 0.92 * surfSeeded(i + 200), v: (surfSeeded(i + 300) * 2 - 1) * 0.85 });
    lace.forEach((pa, i) => {                        // (each point joined to its nearest two or three)
      const near = lace.map((pb, j) => [j, (pa.u - pb.u) ** 2 * 9 + (pa.v - pb.v) ** 2]).filter(([j]) => j !== i).sort((x, y) => x[1] - y[1]);
      pa.n = near.slice(0, 2 + (i % 2)).map(([j]) => j).filter((j) => j > i);
    });
    const st = { g: cv.getContext('2d'), cw: cw, ch: ch, scale: cw / inner.offsetWidth, a: A, d: D, lace: lace, flash: Math.max(0, readNumber('--surf-flash', 0.12)) };
    const speed = Math.max(0.2, readNumber('--surf-speed', 1)) * acc, clock = () => (window.__psSurfClock ? window.__psSurfClock() : performance.now());
    const t0 = clock(), run = ++surfRun;
    put(cv, 'display', 'block');
    (function step() {
      if (run !== surfRun) return;
      const t = (clock() - t0) / 1000 * speed;
      if (t >= SURF_END + 0.02 || !cv.isConnected) { st.g.clearRect(0, 0, cw, ch); put(cv, 'display', 'none'); return; }
      try { surfFrame(st, t); } catch (e) { put(cv, 'display', 'none'); return; }
      requestAnimationFrame(step);
    })();
  }
  // ---------- SURF FROM YOUR SPRITE SHEETS (the "Showdown Surf sheets" style) ----------
  // With that style on (and --surf-sheets not 0), Surf plays your hand-made frames instead of the drawn wave. Each
  // direction has three layers: behind the far Pokémon, between the two, and in front of the near one. The sheets
  // were drawn for a window with the Pokémon standing at set spots; the frames are scaled and moved (never rotated)
  // so those spots land where the two Pokémon really stand (--surf-sheet-fit: 0 draws them exactly as rendered).
  const sheetImgs = new Map();
  const sheetCaches = {};            // move prefix ('surf', 'hydro-pump') -> its sheets, once read
  function sheetImage(url) {
    let e = sheetImgs.get(url);
    if (!e) {
      const img = new Image(); e = { img: img, ok: false };
      img.onload = () => { e.ok = true; };
      img.src = url; sheetImgs.set(url, e);
    }
    return e;
  }
  // A move's sheets come from its VFX style: --<prefix>-sheet-info and the six --<prefix>-sheet-<way>-<layer> pictures;
  // --<prefix>-sheets: 0 in the main style switches them off (Surf: --surf-sheets, Hydro Pump: --hydro-pump-sheets)
  function readSheets(prefix) {
    prefix = prefix || 'surf';
    if (readNumber('--' + prefix + '-sheets', 1) <= 0) return null;
    const cs = getComputedStyle(document.documentElement);
    const raw = cs.getPropertyValue('--' + prefix + '-sheet-info').trim();
    if (!raw) return null;
    const key = raw + '|' + cs.getPropertyValue('--' + prefix + '-sheet-out-behind').length;
    const sheetCache = sheetCaches[prefix];
    if (sheetCache && sheetCache.key === key) return sheetCache;
    const info = raw.replace(/^["']|["']$/g, '').split(/\s+/).map(Number);
    if (info.length < 12 || info.some((n) => !Number.isFinite(n))) return null;
    const set = {};
    for (const way of ['out', 'in']) for (const layer of ['behind', 'between', 'front']) {
      const m = /url\(\s*(['"]?)([\s\S]*?)\1\s*\)/.exec(cs.getPropertyValue('--' + prefix + '-sheet-' + way + '-' + layer));
      if (!m) return null;
      set[way + '-' + layer] = sheetImage(m[2]);
    }
    const [frames, fps, cols, fw, fh, nx, ny, fx, fy, impact, stageW, stageH] = info;
    return (sheetCaches[prefix] = { key: key, frames: frames, fps: fps, cols: cols, fw: fw, fh: fh, near: [nx, ny], far: [fx, fy], impact: impact, stageW: stageW, stageH: stageH, set: set });
  }
  // plays a move's sheets (Surf, Hydro Pump); false when that move has none, or they are not loaded yet
  function sheetSurf(scene, sprites) { return sheetMove(scene, sprites, 'surf'); }
  // the first frame in which the behind layer has water above the far Pokémon's feet (at least 150 of its pixels): the
  // wave rising behind it. -1 if none (or the sheet can't be read)
  function behindFrameOf(sh, img) {
    try {
      const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight;
      const g = c.getContext('2d', { willReadFrequently: true }); g.drawImage(img, 0, 0);
      const d = g.getImageData(0, 0, c.width, c.height).data, W = c.width;
      const k = sh.fw / sh.stageW, footY = Math.round(sh.far[1] * k);
      for (let f = 0; f < sh.frames; f++) {
        const x0 = (f % sh.cols) * sh.fw, y0 = Math.floor(f / sh.cols) * sh.fh;
        let n = 0;
        for (let y = y0; y < y0 + footY; y++) for (let x = x0; x < x0 + sh.fw; x++) if (d[(y * W + x) * 4 + 3] > 40) n++;
        if (n >= 150) return f;
      }
    } catch (e) { /* (sheet not readable: no change) */ }
    return -1;
  }
  function sheetMove(scene, sprites, prefix) {
    const sh = readSheets(prefix);
    if (!sh) return false;
    const opt = (name, fallback) => readNumber('--' + prefix + '-' + name, fallback);      // (each move its own: --surf-speed, --hydro-pump-speed...)
    const attacker = sprites[0], target = sprites.slice(1).filter(Boolean)[0];
    const el = (s) => s && s.$el && s.$el[0];
    const farBox = scene.$sprites && scene.$sprites[1] && scene.$sprites[1][0], nearBox = scene.$sprites && scene.$sprites[0] && scene.$sprites[0][0];
    if (!el(attacker) || !el(target) || !farBox || !nearBox || farBox.parentNode !== nearBox.parentNode) return false;
    const way = nearBox.contains(el(attacker)) ? 'out' : 'in';
    const L = ['behind', 'between', 'front'].map((n) => sh.set[way + '-' + n]);
    if (!L.every((e) => e.ok)) return false;                  // (not loaded yet: the drawn wave this once)
    const inner = el(attacker).closest('.innerbattle');
    if (!inner) return false;
    const acc = scene.acceleration || 1;
    const speed = Math.max(0.2, opt('speed', 1)) * acc;
    // the target shakes as the wave hits it (Showdown waits for this before going on)
    sprites.slice(1).filter(Boolean).forEach((d) => {
      d.delay(sh.impact / speed);
      for (let i = 0; i < 3; i++) { d.anim({ z: d.behind(5), time: 75 }, 'swing'); d.anim({ time: 75 }, 'swing'); }
    });
    // where the sheets go: their window sits at the bottom of the battle (the 50 px above it are yours)
    const ox = (inner.offsetWidth - sh.stageW) / 2, oy = inner.offsetHeight - sh.stageH;
    let s = 1, tx = ox, ty = oy;
    const nearStand = standOf(way === 'out' ? attacker : target, inner), farStand = standOf(way === 'out' ? target : attacker, inner);
    if (opt('sheet-fit', 1) > 0 && nearStand && farStand) {
      const dp = [sh.far[0] - sh.near[0], sh.far[1] - sh.near[1]], da = [farStand.x - nearStand.x, farStand.y - nearStand.y];
      const len = dp[0] * dp[0] + dp[1] * dp[1];
      if (len > 1) s = Math.min(1.4, Math.max(0.7, (dp[0] * da[0] + dp[1] * da[1]) / len));
      tx = (nearStand.x + farStand.x) / 2 - s * (sh.near[0] + sh.far[0]) / 2;
      ty = (nearStand.y + farStand.y) / 2 - s * (sh.near[1] + sh.far[1]) / 2;
    }
    s *= Math.max(0.2, opt('sheet-scale', 1));
    tx += opt('sheet-x', 0); ty += opt('sheet-y', 0);
    const host = farBox.parentNode;
    host.querySelectorAll(':scope > canvas.ps-surf-sheet').forEach((c) => c.remove());     // (one sheet move at a time)
    const cvs = L.map((e, i) => {
      const c = document.createElement('canvas');
      c.className = 'ps-surf-sheet ps-surf-' + ['behind', 'between', 'front'][i];
      c.width = sh.fw; c.height = sh.fh;
      c.style.cssText = 'position:absolute;margin:0;pointer-events:none;image-rendering:pixelated;' +
        'left:' + tx.toFixed(2) + 'px;top:' + ty.toFixed(2) + 'px;width:' + (sh.stageW * s).toFixed(2) + 'px;height:' + (sh.stageH * s).toFixed(2) + 'px';
      return c;
    });
    host.insertBefore(cvs[0], farBox);                       // behind the far Pokémon
    host.insertBefore(cvs[1], farBox.nextSibling);           // between the two
    host.insertBefore(cvs[2], nearBox.nextSibling);          // in front of the near Pokémon
    const gs = cvs.map((c) => c.getContext('2d'));
    // Your attack only: once the wave has gone behind the opponent's Pokémon, its "behind" layer also goes behind the
    // opponent's trainer, --<move>-sheet-trainer-delay seconds later (0.1 s; below 0 = never). When it goes behind: the
    // first frame whose behind layer reaches up past the far Pokémon's feet, found in the sheet itself.
    const tDelay = opt('sheet-trainer-delay', 0.1);
    let behindAt = -1;
    if (way === 'out' && tDelay >= 0) {
      if (sh.behindFrame === undefined) sh.behindFrame = behindFrameOf(sh, L[0].img);
      if (sh.behindFrame >= 0) behindAt = sh.behindFrame / sh.fps + tDelay;
    }
    let tucked = false;
    const clock = () => (window.__psSurfClock ? window.__psSurfClock() : performance.now());
    const t0 = clock(), run = ++surfRun;
    let shown = -1;
    (function step() {
      if (run !== surfRun || !cvs[0].isConnected) { cvs.forEach((c) => c.remove()); return; }
      const tNow = (clock() - t0) / 1000 * speed;
      const f = Math.floor(tNow * sh.fps);
      if (f >= sh.frames) { cvs.forEach((c) => c.remove()); return; }
      if (behindAt >= 0 && !tucked && tNow >= behindAt) {
        // (below the opponent's trainer, which the style draws at -1 just over the background: at the same level but
        // earlier on the page, the trainer covers it; still above the background and the shadows)
        cvs[0].style.setProperty('z-index', '-1');
        tucked = true;
      }
      if (f !== shown && f >= 0) {
        shown = f;
        const sx = (f % sh.cols) * sh.fw, sy = Math.floor(f / sh.cols) * sh.fh;
        gs.forEach((g, i) => { g.clearRect(0, 0, sh.fw, sh.fh); g.drawImage(L[i].img, sx, sy, sh.fw, sh.fh, 0, 0, sh.fw, sh.fh); });
      }
      requestAnimationFrame(step);
    })();
    return true;
  }

  let surfRun = 0, surfOriginal = null, sheetTry = -1e9, hydroOriginal = null;
  const sheetReady = (p) => !!(sheetCaches[p] && Object.values(sheetCaches[p].set).every((e) => e.ok));
  // Hydro Pump: its sheets when its VFX style is on (and loaded); Showdown's own otherwise
  function hydroAnim(scene, sprites) {
    try { if (sheetMove(scene, sprites, 'hydro-pump')) return; } catch (e) { /* (Showdown's own instead) */ }
    return hydroOriginal.apply(this, arguments);
  }
  function hookSurf() {
    const M = window.BattleMoveAnims;
    if (!M || !M.surf) return;
    const now = performance.now();                 // (looks for the sheets every 2 s until they are loaded)
    if (now - sheetTry > 2000 && !(sheetReady('surf') && sheetReady('hydro-pump'))) { sheetTry = now; safely(() => readSheets('surf')); safely(() => readSheets('hydro-pump')); }
    if (!surfOriginal) surfOriginal = M.surf.anim;
    const want = readNumber('--surf-custom', 1) > 0;
    const anim = want ? surfAnim : surfOriginal;
    if (M.surf.anim !== anim) M.surf.anim = anim;
    if (M.hydropump) {
      if (!hydroOriginal) hydroOriginal = M.hydropump.anim;
      const hy = readSheets('hydro-pump') ? hydroAnim : hydroOriginal;
      if (M.hydropump.anim !== hy) M.hydropump.anim = hy;
    }
  }

  // ---------- POP-UPS OVER THE POKÉMON LAST LONGER (--result-time) ----------
  // "-25%", "Burned", "1.5x SpA", an ability's name: Showdown fades them out in about a second. Here they take
  // --result-time times as long (4 = four times). Showdown empties its effects layer at every step of the battle, which
  // would cut them short, so they are drawn in a layer of their own beside it; and the battle is held up only as long
  // as Showdown's own pop-up would have held it, so the game does not slow down.
  let resultTime = 4;
  function resultLayer(scene) {
    const fx = scene.$fx && scene.$fx[0];
    if (!fx || !fx.parentNode) return null;
    let layer = fx.previousElementSibling;
    if (!layer || !layer.classList.contains('ps-results')) {
      layer = document.createElement('div'); layer.className = 'ps-results';
      fx.parentNode.insertBefore(layer, fx);
    }
    return layer;
  }
  function pacer(scene, ms) {          // (an invisible stand-in the battle waits for: as long as the original pop-up)
    const $p = window.jQuery('<div style="display:none"></div>');
    scene.$fx.append($p);
    $p.delay(scene.timeOffset).animate({ opacity: 0 }, ms);
    return $p;
  }
  function patchResults() {
    const BS = window.BattleScene, $ = window.jQuery;
    if (!BS || !BS.prototype || !$ || BS.prototype._psResults || typeof BS.prototype.resultAnim !== 'function') return;
    const origResult = BS.prototype.resultAnim, origAbility = BS.prototype.abilityActivateAnim;
    BS.prototype.resultAnim = function (pokemon, result, type) {
      const layer = resultLayer(this), k = Math.max(1, resultTime);
      if (!this.animating || !layer || k === 1) return origResult.apply(this, arguments);
      const $effect = $('<div class="result ' + type + 'result"><strong>' + result + '</strong></div>');
      $(layer).append($effect);
      $effect.delay(this.timeOffset).css({ display: 'block', opacity: 0, top: pokemon.sprite.top - 5, left: pokemon.sprite.left - 75 }).animate({ opacity: 1 }, 1);
      $effect.animate({ opacity: 0, top: pokemon.sprite.top - 65 }, 1000 * k, 'swing', () => $effect.remove());
      this.wait(this.acceleration < 2 ? 350 : 250);
      pokemon.sprite.updateStatbar(pokemon);
      if (this.acceleration < 3) this.waitFor(pacer(this, 1000));
    };
    if (typeof origAbility === 'function') {
      BS.prototype.abilityActivateAnim = function (pokemon, result) {
        const layer = resultLayer(this), k = Math.max(1, resultTime);
        if (!this.animating || !layer || k === 1) return origAbility.apply(this, arguments);
        const $effect = $('<div class="result abilityresult"><strong>' + result + '</strong></div>');
        $(layer).append($effect);
        $effect.delay(this.timeOffset).css({ display: 'block', opacity: 0, top: pokemon.sprite.top + 15, left: pokemon.sprite.left - 75 }).animate({ opacity: 1 }, 1);
        $effect.delay(800 * k).animate({ opacity: 0 }, 400 * k, 'swing', () => $effect.remove());
        this.wait(100);
        pokemon.sprite.updateStatbar(pokemon);
        if (this.acceleration < 3) this.waitFor(pacer(this, 1200));
      };
    }
    BS.prototype._psResults = true;
  }

  function everyFrame() {
    safely(() => {
      const now = performance.now();
      countFrame(now);
      document.querySelectorAll('.battle').forEach((battle) => {
        const inner = battle.querySelector('.innerbattle');
        if (!inner) return;
        const ir = inner.getBoundingClientRect();
        if (!ir.width || !inner.offsetWidth) return;
        const k = ir.width / inner.offsetWidth;        // how much bigger than its own pixels the battle is drawn
        followShake(battle, inner);
        const list = trackSprites(battle, inner, ir, k, now);
        if (list.some(({ st }) => st.shown && now - st.moved < 50)) busyAt = now;      // a Pokémon is on the move
        syncCast(battle, inner, ir, k, list);
        syncSparks(battle, inner, ir, k, list, now);
        moveEffects(inner, ir, k, list);
        syncHover(battle, inner, k, list);
      });
      if (pointerAt) checkHover();                       // (the Pokémon moved under a still pointer)
      wrapTooltips();
      hookSurf();
      patchResults();
    });
    requestAnimationFrame(everyFrame);
  }

  function safely(fn) {
    try { fn(); } catch (e) { console.warn('[showdown style]', e); }
  }

  function update() {
    safely(timeTheLoop);
    safely(aimAtSun);
    updateFilters();
    castOn = readNumber('--cast-show', 0) > 0;
    fxFollow = Math.min(1, Math.max(0, readNumber('--fx-follow', 1)));
    ballFromTrainer = readNumber('--ball-from-trainer', 1);
    ballFromX = readNumber('--ball-from-x', 0.5);
    ballFromY = readNumber('--ball-from-y', 0.45);
    logShow = readNumber('--log-show', 1);
    fitOn = readNumber('--battle-fit', 1);
    fitMax = Math.max(0.2, readNumber('--battle-fit-max', 4));
    bubbleOn = readNumber('--bubble-show', 1);
    maxWanted = readNumber('--battle-maximize', 0);
    sparkSteps = Math.min(30, Math.max(0.2, readNumber('--sun-sparkle-steps', 6.6)));
    sparkRest = readNumber('--sun-sparkle-rest', 1);
    sparkAuto = readNumber('--sun-sparkle-auto', 1);
    sparkMinFps = Math.min(240, Math.max(5, readNumber('--sun-sparkle-min-fps', 50)));
    perfShow = readNumber('--perf-show', 0);
    sparkCanvas = readNumber('--sun-sparkle-canvas', 1);
    mapNumGen++;
    hoverOn = readNumber('--hover-info', 1);
    resultTime = Math.min(20, Math.max(1, readNumber('--result-time', 4)));
    safely(markMaximized);
    // (the style removes the log column and moves the chat line when these say so)
    if (document.documentElement.dataset.psLog !== (logShow > 0 ? '1' : '0')) document.documentElement.dataset.psLog = logShow > 0 ? '1' : '0';
    const maxBtn = readNumber('--max-button-show', 1) > 0 ? '1' : '0';
    if (document.documentElement.dataset.psMaxButton !== maxBtn) document.documentElement.dataset.psMaxButton = maxBtn;
    const chatLine = readNumber('--chat-line-show', 1) > 0 ? '1' : '0';
    if (document.documentElement.dataset.psChatLine !== chatLine) document.documentElement.dataset.psChatLine = chatLine;
    document.querySelectorAll('.battle-log').forEach((log) => {
      if (!log._psHeardFrom) log._psHeardFrom = performance.now() + 1500;      // (chat counts as live from a moment after its log first shows)
    });
    snapOn = readNumber('--snap', 1);
    fixMax = Math.abs(readNumber('--fix-max', 45));
    foeGround = readNumber('--foe-ground', 25);
    playerScale = readNumber('--player-scale', 1);
    shakeFollow = readNumber('--shake-follow', 1);
    shakeLag = Math.min(120, Math.max(0, Math.round(readNumber('--shake-lag', 1))));
    document.querySelectorAll('.battle ' + SPRITES).forEach((img) => {
      safely(() => measureFeet(img));
      safely(() => measureBox(img));
    });
    document.querySelectorAll('.battle').forEach((battle) => {
      safely(() => pickMap(battle));
      safely(() => markTeamPreview(battle));
      safely(() => mirrorWeatherText(battle));
      safely(() => mirrorNotices(battle, battle._psCtrl && battle._psCtrl.isConnected ? battle._psCtrl : ((battle.closest('.ps-room') || battle.parentElement || document).querySelector('.battle-controls'))));
      safely(() => fitBattle(battle));
      safely(() => measureVisible(battle));
      safely(() => battle.querySelectorAll('.innerbattle > .ps-bubble').forEach((bubble) => placeBubble(battle, bubble)));
      safely(() => {
        const r = battle.getBoundingClientRect();
        if (battle.offsetWidth && r.width) centerTrainerNames(battle, r.width / battle.offsetWidth);
      });
    });

    document.querySelectorAll('.battle-controls').forEach((ctrl) => {
      const room = ctrl.offsetParent;            // what the controls are positioned against
      const holder = ctrl.parentElement;
      if (!room || !holder) return;              // room hidden (inactive tab)

      const battle =
        holder.querySelector(':scope > .battle') ||
        room.querySelector('.battle');
      if (!battle) return;
      battle._psCtrl = ctrl;

      watch(battle);
      watch(room);

      const r = room.getBoundingClientRect();
      const b = battle.getBoundingClientRect();
      if (!b.width || !b.height || !room.offsetWidth || !room.offsetHeight) return;

      // the theme may scale the room; convert on-screen pixels into the
      // room's own layout pixels, which is what the controls are placed in
      const sx = r.width / room.offsetWidth;
      const sy = r.height / room.offsetHeight;

      // battle window's position and size, in the controls' coordinate space
      const x = (b.left - r.left) / sx - room.clientLeft + room.scrollLeft;
      const y = (b.top - r.top) / sy - room.clientTop + room.scrollTop;

      ctrl.style.setProperty('--bx', x + 'px');
      ctrl.style.setProperty('--by', y + 'px');
      ctrl.style.setProperty('--bw', (b.width / sx) + 'px');
      ctrl.style.setProperty('--bh', (b.height / sy) + 'px');
      // the chat line and the maximize button are placed from the same numbers (the style puts them just above the line of buttons)
      const mb = room.classList.contains('ps-room') ? maxButton(room) : null;
      [room.querySelector('.battle-log-add'), mb].forEach((el) => {
        if (!el) return;
        put(el, '--bx', x.toFixed(1) + 'px'); put(el, '--by', y.toFixed(1) + 'px');
        put(el, '--bw', (b.width / sx).toFixed(1) + 'px'); put(el, '--bh', (b.height / sy).toFixed(1) + 'px');
      });
    });
  }

  // re-run when battles open, Pokémon switch in, rooms switch, the window resizes or the zoom changes
  updateFilters();
  new MutationObserver(schedule).observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['src'],
  });
  window.addEventListener('resize', schedule);
  document.addEventListener('fullscreenchange', schedule);
  // Showdown hides sprites by fading them rather than removing them, which the
  // watchers above can't see, so also re-check a few times a second
  setInterval(schedule, 400);
  update();
  everyFrame();
})();