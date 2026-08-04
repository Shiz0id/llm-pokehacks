# Map format, and deriving autotile rules

## `map.bin`

A flat little-endian `u16` array, row-major, `width * height`. No header, no
compression.

| bits | meaning |
|---|---|
| 0–9 | metatile id |
| 10–11 | collision |
| 12–15 | elevation |

Validated by round-tripping all 785 vanilla layouts: 765 byte-identical, 20
with exactly one extra trailing block (19 of them named `LAYOUT_UNUSED_*`) — a
benign vanilla quirk, since the game reads `width * height` and ignores the
tail. `scripts/validate_maps.py` re-runs that check.

**Collision is binary in practice.** Only 0 and 1 appear anywhere in vanilla,
despite the field being two bits.

**Elevation** is the one people get wrong:

| value | meaning |
|---|---|
| 0 | transition / any — moves freely to and from anything |
| 1 | water |
| 3 | standard ground |
| 4+ | raised levels |
| 15 | multi-level (bridges) |

`IsElevationMismatchAt` blocks movement between two *different* non-zero
elevations. A tile at elevation 3 placed on a map the player traverses at
elevation 1 is unreachable — it will look completely normal and simply refuse
to be walked onto. Elevation 0 is the escape hatch and is why warps and stairs
generally use it.

**Size ceiling:** `(width + 15) * (height + 14) <= MAX_MAP_DATA_SIZE` (10240).
All 785 vanilla layouts satisfy it; the largest reaches 91.8%.

**`sBackupMapData` already exists in EWRAM.** If you generate layouts at
runtime, generating into it costs no extra memory — that buffer is
unconditionally allocated (20,524 bytes) whether you use it or not. Set
`gBackupMapLayout.map`, `.width` and `.height` alongside it, and note the width
is the playfield **plus the border margin** (`width + MAP_OFFSET_W`), not the
playfield alone. Getting that wrong shears every row by a few blocks, which
looks like a corrupted tileset rather than an arithmetic mistake.

## Autotiling: how to actually derive the rules

The natural approach — count, across many layouts, which metatile appears for
each neighbour bitmask, and take the winner — **does not work**, and the reason
matters.

Deriving a neighbour-mask → metatile table across 47 cave layouts gave a top
choice that wins only **26.5%** of the time (30.8% with diagonals). Vanilla
varies its wall art decoratively. There is no rule to recover by counting,
because the mapper was not following one.

**Read real examples out of a single vanilla layout as a grid instead**, then
validate by rendering your generated output beside vanilla. That worked first
time where statistics had failed repeatedly.

`scripts/derive_wall_table.py` still earns its place — it tallies per
open-neighbour mask *and reports how decisive each answer is*. Treat anything
under ~80% as a hint rather than an answer, and go look at a grid.

### When a low score means you asked the wrong question

A census over four sea-route layouts put **nothing above 37.8%**, which read as
"this tileset has no rules". It did — the census was pooling three unrelated
things: island shores, the map-edge water barrier, and free-standing rocks.

Dumping isolated solid components as a grid showed a clean 3×3 nine-slice on
sight:

```
338 339 33A
340 341 342
348 349 34A
```

Checking each id **alone** then confirmed it: `0x339` faces north 79% of the
time, `0x349` south 80%, `0x342` east 76%, and no two share a dominant mask.
The corners score lower (41–53%) only because they also appear in tighter
two-wide rocks.

The same data that looked like noise was decisive once asked the right
question. **The failure was the pooling, not the tileset.**

## Two worked autotile tables

These are vanilla facts, useful directly and useful as a shape to copy.

### Cave (`gTileset_General` + `gTileset_Cave`)

Resolve in this order — the south face wins because it is the most visible:

| case | left | middle | right |
|---|---|---|---|
| 1-thick horizontal | — | `0x39F`\* | — |
| floor **south** (visible face) | `0x218` | `0x219` | `0x21A` |
| floor **north** (room bottom) | `0x220` | `0x209` | `0x222` |
| 1-thick vertical | — | `0x39E`\* | — |
| vertical edges | `0x210` | `0x211` | `0x212` |
| outer corners (diagonal open) | `0x21B` SE | `0x21C` SW | `0x223` NW/NE |
| interior | — | `0x211` | — |

Floor is `0x201` (`MB_CAVE`, so encounters fire anywhere on it).

\* `0x39E`–`0x3A4` are **not vanilla** — vanilla caves are never one block
thick, so that art does not exist and must be composed. See
`references/metatile-art.md`.

**Do not omit the north edge.** Vanilla uses `0x211` for both floor and wall
bulk, so a missing boundary is *invisible* rather than merely plain, and rooms
stop reading as enclosed. Legibility in vanilla comes almost entirely from a
continuous outline, never from floor/rock contrast.

### Woodland (`gTileset_General` + `gTileset_Rustboro`)

Trees are **2 wide × 3 tall** blocks on even coordinates — 95% x-aligned and
99% y-aligned in vanilla. Rows: `0x1D4`/`0x1D5` canopy, `0x1DC`/`0x1DD` trunk,
`0x1E4`/`0x1E5` ground contact, the third row used **only where a tree mass
ends**. Vanilla never leaves `0x1DC` exposed; doing so dangles the trunk in
mid-air.

A tree also has a **fourth row above it** — the crown poking up into the block
above the canopy, composited over whatever is already there: `0x1CE`/`0x1CF`
over plain grass, `0x1C6`/`0x1C7` over tall grass. Behaviour is preserved
exactly across the swap (`0x1CE` is `MB_NORMAL` like plain grass, `0x1C6` is
`MB_TALL_GRASS` like tall grass), so it cannot move where encounters fire.

Grass: `0x001` plain (no encounters) and `0x00D` tall.

**This pair has no long grass.** `gTileset_General` contains no
`MB_LONG_GRASS_SOUTH_EDGE` metatile at all — the only one, `0x208`, is in
`gTileset_Fortree`.

Because trees tile on a 2×2 grid, a generator for this kind of area can work at
half resolution and stamp whole cells, which removes the need for an autotile
pass entirely. Choose that by **how the art tiles, not by what it depicts** —
a leaf mass that tiles 1×1 (Fortree) needs the 1×1 path even though it is also
"trees".

## Two cautionary tales about reading metatiles

**`0x016`/`0x017` look exactly like a grass base row and are not.** They are
solid in all 691 of their vanilla placements across every General+Rustboro and
General+Fortree layout, always under the leafy canopy `0x0C6`/`0x0C7`. They are
a canopy base row. Drawing them passable puts a walkable hedge fragment in the
middle of a field. The reasoning that produced the bug: they sit immediately
after `0x015` in the metatile grid. **Adjacency in the grid is not evidence.**

**`0x1C6`/`0x1CE` read as grass with a sprout at the bottom**, which looks like
the bottom edge of a grass patch. The census said otherwise: they sit directly
above the canopy `0x1D4`/`0x1D5` 139 times, and the "sprout" is the top of the
tree. **Ask what a candidate sits next to before deciding what it is** — the
picture alone supported the wrong answer both times.
