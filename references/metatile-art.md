# Making art that does not exist, mostly without drawing

The recurring discovery across this material is that **the prediction "this
needs new pixel art" was wrong nearly every time.** Whole tilesets have been
produced from a palette swap; encounter surfaces from an attribute byte; thin
walls from halves of existing walls; a descent from three block entries and
nine tiles. Check what already exists — vanilla's tilesets, a recolour, a
reskin, a third-party rip — before authoring anything.

## Contents

- [What a metatile actually is](#what-a-metatile-actually-is)
- [Splicing: new metatiles from existing tiles](#splicing-new-metatiles-from-existing-tiles)
- [Owning an appended tileset](#owning-an-appended-tileset)
- [Attributes are per entry](#attributes-are-per-entry)
- [Match the behaviour to how tall the art is](#match-the-behaviour-to-how-tall-the-art-is)
- [Drawing a floor: fine noise, never a feature](#drawing-a-floor-fine-noise-never-a-feature)
- [Borrowed wall art has the donor's floor baked in](#borrowed-wall-art-has-the-donors-floor-baked-in)
- [Thin walls, corners, and what an inside corner is FOR](#thin-walls-corners-and-what-an-inside-corner-is-for)
- [Check for a reskin before mining anything](#check-for-a-reskin-before-mining-anything)
- [N consecutive metatiles may be N PHASES](#n-consecutive-metatiles-may-be-n-phases)
- [Drawing genuinely new tiles](#drawing-genuinely-new-tiles)
- [Giving a field effect its own graphic](#giving-a-field-effect-its-own-graphic)

---

## What a metatile actually is

**8 references to existing 8×8 tiles** — 4 bottom layer, 4 top layer. Each is a
`u16`: tile id in bits 0–9, x-flip 10, y-flip 11, palette 12–15. Entry order
per layer is `[TL, TR, BL, BR]`.

Everything below follows from that. A metatile is an *arrangement*, so new
arrangements are free; only genuinely new pixels cost anything.

An entry of `0x0000` references no tile at all, which is how a top layer can be
partly bare.

## Splicing: new metatiles from existing tiles

A one-block-thick wall — which vanilla caves never have, because their walls
are always 2+ thick — is the west-facing half of one existing metatile joined
to the east-facing half of another. A vertical top cap keeps that base and
overlays both north corners, exploiting the fact that some pieces are top-layer
overlays rather than standalone art.

**Check the metatile entries before deciding a splice is hard.** Two tilesets
that looked like they would need hand-built entries turned out to be pure
overlay work: all nine pieces of one nine-slice shared a single bottom layer
with every edge as a top-layer overlay laid out on a regular tile grid, so each
sliver was four quadrant copies. One other needed fiddly hand assembly. You
cannot tell which from a contact sheet — dump the entries.

**Splicing only works when the source tiles have transparency.** A metatile
that is opaque across the full 16×16 has no half to borrow, and that case needs
genuinely new art.

## Owning an appended tileset

Appending to a vanilla tileset means editing checked-in asset files
(`data/tilesets/secondary/<name>/*.bin`). Three rules make that survivable:

**One appender per tileset, by construction rather than convention.** The
idempotent way to write an appender is to truncate everything past the vanilla
count and rewrite the tail — which means a *second* script appending to the same
file gets silently wiped the next time the first one runs. Anything needing a
new metatile in that tileset should export its entries and be imported by the
one appender.

**Compare the tail's CONTENT, not its length.** An appender that decides it has
already run by counting metatiles will treat a *changed* entry as "nothing to
do", and the fix never lands.

**Attributes are per entry.** Slivers copied from a wall must behave like wall;
a floor variant must keep the floor's behaviour, or the area silently stops
spawning encounters. One shared attribute across an append is the same shape of
bug as a hard-coded per-area constant.

Pulling upstream changes to an edited tileset means **taking upstream's file
and re-running the script**, not merging.

## Attributes are per entry

This is the cheapest trick in the toolkit and deserves its own heading.

Neither `gTileset_EverGrande` nor `gTileset_Mauville` contains a single
metatile carrying `TILE_FLAG_HAS_ENCOUNTERS` — every flower in both is
`MB_NORMAL`. Making flowers work as an encounter surface needed sixteen new
metatile entries and **zero new pixels**: they reference vanilla's flower tiles
byte for byte and differ only in the attribute.

The same pixels can be decoration in one metatile and an encounter surface in
another.

Which behaviour to hang on it is a real choice:

| behaviour | encounters | what else it drags in |
|---|---|---|
| `MB_UNUSED_05` | yes | **nothing.** Its only engine reference is `Unref_MetatileBehavior_IsUnused05`, which nothing calls |
| `MB_TALL_GRASS` | yes | the rustle overlay sprite |
| `MB_LONG_GRASS` | yes | a full-tile curtain sprite, the OAM clip that hides the player's lower half, and `BATTLE_ENVIRONMENT_LONG_GRASS` |
| `MB_PUDDLE` | no | nothing — walkable, **not surfable**, no encounters |

`MB_PUDDLE` is worth knowing separately: it lets you paint water that is purely
decorative. Real pond and ocean water in the same tileset are *surfable*, and
painting those into an enclosed area lets the player surf out of it.

## Match the behaviour to how tall the art is

A set of low, bold flower beds was put on `MB_LONG_GRASS` for a good-sounding
reason — the OAM clip that behaviour brings is purely geometric, so the player
wades *into* the surface. Rendered in situ it was obviously wrong: the beds are
half-tile blooms seen from above, and the overlay is a **full-height curtain**
that hides the player's lower half. The two disagreed about how tall the thing
underfoot was.

Vanilla never has this problem because its long grass *tile* is tall, so tile
and overlay agree by construction.

The fix was not a different behaviour but **adding the surface the overlay was
describing** — a second, genuinely tall variant carrying `MB_LONG_GRASS`, with
the short one on `MB_UNUSED_05`.

**Pick the behaviour to match how tall the art is, not how much you want the
effect.** `MB_UNUSED_05` exists for exactly the case where a surface should
spawn encounters and otherwise be walked over.

## Drawing a floor: fine noise, never a feature

**A floor metatile repeats every 16 pixels, so any interior feature becomes a
lattice.** A first attempt at a snow floor had a soft diagonal swell and four
white glints. Tiled, the swell became continuous candy-stripes across the whole
area and the glints a regular dot grid. A reference image is a hand-drawn field
and never has to tile; this does, everywhere, against copies of itself.

Vanilla's answer, read off cave floor `0x201` rather than guessed:

| palette index | share |
|---|---|
| 4 | 55% |
| 5 | 34% |
| 6 | 9% |
| 3 | 1.5% |

**Fine per-pixel noise over four *adjacent* indices, never the extremes of the
ramp.** Noise has no structure to repeat, and neighbouring indices are too close
in value to read as a pattern where it does. The cave's wall interior is
flatter still — 82% one index. Reuse the proportions and slide them along the
ramp to whatever you need.

**No white in a floor.** High contrast is exactly what makes the 16-pixel
period visible. Glints belong in decoration, which is placed irregularly.

The same is true of a *patch* or region layer, not just a base floor: a feature
baked into every entry becomes a lattice at 16 pixels. Leaving some entries of
a set bare is what makes a decoration punctuate a surface instead of ruling it.

## Borrowed wall art has the donor's floor baked in

**A custom floor under a borrowed wall set does not just look different — it
looks broken.** Cave wall pieces draw the base of the cliff as *ground* inside
the wall's own metatile, so it blends into the cave floor below. Put snow under
it and that band stays cave-coloured: every room reads as a grey rectangle with
a strip of bare rock along the bottom.

This cannot arise while an area either keeps the donor's own floor or takes its
whole wall table from the same tileset as its floor — the two match by
construction. **Any area mixing a custom floor with a borrowed wall set needs
this treatment.**

### The same trap in region-autotile form

Stated generally: **an autotile's EDGES encode what the art expects to sit in,
and changing what it sits in invalidates every one of them while leaving every
id perfectly valid.**

A set of primary-tileset puddles survived a secondary-tileset replacement
untouched — the ids still resolved, the art still drew — but their edges were
drawn to meet the *old* ground and now met something else. Nothing failed. It
just looked wrong, in a way that reads as a rendering fault rather than an art
mismatch.

## Thin walls, corners, and what an inside corner is FOR

**Check whether the tileset draws one-block-thick walls natively before
assuming it needs composed metatiles.** Caves needed seven spliced metatiles
because vanilla caves are never one thick. A facility tileset full of thin
partitions needed **none** — the sliver cases already existed. A volcanic
tileset needed six: its horizontal sliver is native and used with 100%
consistency wherever floor sits both north and south, but nothing vertical
exists.

**"Vanilla uses this as a thin wall" is not the same claim as "this can be a
thin wall in *your* wall set."** A cobble garden wall genuinely runs
north–south with grass on both sides 85% of the time in vanilla — and still
failed as sliver art inside a rock mass, because the cobble's shaded face is
blue-grey against the cliff's warm tan. At game scale the vertical piece read
as a pillar of a foreign material and the horizontal one as **a hole in the
ground**. Render it in place before believing the census.

**There are four diagonal corner cases, not three.** A slot that fires on "NW
*or* NE open" cannot express a tileset with distinct art for the two. Name the
slots for the **open diagonal**, not for the wall's own position — naming them
the other way puts the art one tileset calls its south-east corner in a slot
called `CORNER_NW`, and every table looks wrong until you know that.

**Know what an inside corner is FOR before hunting for art.** Its job is to
carry the wall's dark edge from one neighbour round to the other in a
continuous L — from the south face's bottom band to the side edge's side band —
and it is **solid**. No cardinal neighbour of that block is floor, so none of it
may show any. Everything else is decoration.

Two attempts at one failed, both of which looked right in isolation: art drawn
from a *rounded* pocket had transparent corner pixels that became a bite of
water in the middle of a rock mass, and an opaque underlay fixed that but
carried no dark edge, so it was indistinguishable from plain interior.

The answer was already in the scan output at 27–43%, dismissed because those
metatiles live in the *primary* tileset and look like plain rock on a contact
sheet. **When a scan's top answer is rejected, say out loud what it *is* — do
not just note what it is not.**

**Build the junction first for any new wall set**: the corner, the two edges it
must meet, and the floor. Four metatiles, and it answers the question in one
look. Comparing that junction against a tileset you have already got working
settles in seconds what reasoning from first principles gets wrong.

**Check what the wall art is drawn against.** One facility tileset's edge
pieces are all lit strips over black, so the mass interior must be the *void*
metatile — filling it with a wall body puts a lit edge in the middle of a dark
mass.

## Check for a reskin before mining anything

Some vanilla secondaries are pure art reskins of another: same metatile
definitions, same attributes, different pixels. `gTileset_MirageTower` is one —
**411 of its 414 metatiles are byte-identical to `gTileset_Cave`** and all 414
attributes are. An entire wall table transferred verbatim, and a splice recipe
produced byte-identical slivers in sand instead of rock. A day of mining became
an afternoon.

It does not generalise — a scan of all 95 secondaries found only one other even
partly similar, at 32% — but **the check costs one script and is worth running
first.**

Two traps come with it:

- **The reskin's own vanilla map may not use the convention you want.** Mirage
  Tower walks on `0x211` and never uses `0x201`, but under the cave those two
  are the hatched rock and the smooth floor respectively. Following vanilla
  would have put the rock texture on the walkable surface and inverted what the
  player learned elsewhere.
- **Identical ids are a coincidence to write down, not to rely on.** Two
  tilesets happening to have the same vanilla metatile count means both append
  at the same ids. Spell the constants out separately so either can change
  without silently corrupting the other.

## N consecutive metatiles may be N PHASES

A set of sixteen flower metatiles looks like a scatter set — four consecutive
distinct tiles each, no flips, no top layer, and on a contact sheet the eight
of a colourway are almost indistinguishable. Painting a blob by picking among
them at random is the obvious implementation and it is **wrong**.

They are **eight steps of a diagonal banding**. Over 341 flower blocks of a
vanilla layout, **85% satisfy `variant = (y - x + k) mod 8`** for one of three
values of `k` — one constant per field, wherever the artist started it.
Rendered, the field is alternating diagonal rows of two colours, visible in the
vanilla map the moment you crop it and invisible in any per-metatile view.

**Before treating N consecutive metatiles as interchangeable, test whether
their index is a function of position.** A census asking "which of these
appears here" answers uniformly and tells you nothing. The question that works
is "what is `variant - f(x, y)`".

A diagonal is also cheaper than a hash and consumes no RNG, which matters if
your painting code can re-run — it repaints identically instead of reshuffling.

Related: **not every tileset has a region set at all**, and it is worth
checking before designing around one. Several turned out to have their apparent
region set already in use as decoration or edge art.

## Drawing genuinely new tiles

When splicing is not enough:

- **Free slots have to be measured, not assumed.** A tile slot is free only if
  no metatile in the tileset references it *and* its pixels are blank. For one
  vanilla secondary that was 220 of 512 tile slots.
- Work in the tileset's **existing palette**. A new tile drawn in colours the
  palette does not contain will be quantised to something you did not choose.
- **The hard problem is usually finding a dark.** Drawing an opening — a
  descent, a doorway, a cave mouth — needs a colour dark enough to read as
  shadow, and several palettes simply have none. One alternative that looked
  dark enough was too *saturated* to read as shadow. A palette with headroom
  can be extended by appending colours (appending only ever writes past the end,
  so existing indices never move); otherwise lift a dark verbatim from a
  palette in the same tileset.

## Giving a field effect its own graphic

**A field effect's palette is chosen in neither of the two places you would
look.** The `SpriteTemplate` has a `paletteTag`, but nothing loads from it. The
palette comes from `data/field_effect_scripts.s` (`field_eff_loadfadedpal_callnative
...`), and a script is fixed per `FLDEFF` id while a `SpriteTemplate` is
`const`. So per-area art has to be chosen in the `FldEff_` function itself.

Four things it must get right:

- **Vary `FLDEFFOBJ`, never `FLDEFF`.** The effect id must stay the same,
  because every ground-effect flag, the OAM clip, and the effect's own
  `FieldEffectStop` key on it. Only the graphic differs, so the two templates
  share an anim table and a callback.
- **Load the palette *before* creating the sprite.** `LoadSpritePalette`
  returns `0xFF` when no slot is free, and `0xFF` truncates to slot **15** in a
  four-bit OAM field — so a late failure draws the art in whatever lives there.
  Loading first lets it fall back to the stock graphic: a wrong graphic beats a
  wrong graphic in wrong colours.
- **Call `UpdateSpritePaletteWithWeather` by hand.** `loadfadedpal` is the
  *faded* half of that script command, and stepping around it means the sprite
  ignores the weather fade every other field effect obeys — immediately visible
  on any weathered map.
- **Derive the art from the one it replaces.** Remapping the original's indices
  beats generating a mass from scratch. **Noise with the right histogram still
  looks wrong**, because vanilla's light pixels are not scattered — they form
  blades, short diagonal strokes. Reusing them also inherits two properties
  hard to hit by eye: the mass is opaque enough to read as something you stand
  *in*, and it **tiles invisibly**, which matters because one sprite spawns per
  occupied tile and several sit edge to edge.

One meta-lesson from that work: the rule was "the overlay should be made of
what it sits in", and it was correctly applied — then the surface underneath
changed and the rule was not re-applied. **A rule about matching something
needs re-checking whenever the something moves.**
