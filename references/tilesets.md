# Tilesets: resolving, swapping, recolouring, importing

## Never guess an asset path from a symbol name

This is worth stating twice because it looks like it should work and does not:

- FRLG secondaries carry an `_frlg` **directory suffix the symbol lacks**.
- Acronyms and digits split unpredictably when converting `CamelCase` to
  `snake_case`.
- **Seven tilesets share assets across directories.** `gTileset_SilphCo` takes
  its tiles and palettes from `condominiums_frlg` and its metatiles from
  `silph_co_frlg`.

Parse the declarations instead. Four files, and the fourth is the one people
miss:

| file | declares |
|---|---|
| `src/data/tilesets/headers.h` | `gTileset_X` → component symbols |
| `src/data/tilesets/graphics.h` | `gTilesetTiles_Y` / `gTilesetPalettes_Y` → paths |
| `src/data/tilesets/metatiles.h` | `gMetatiles_Y` / `gMetatileAttributes_Y` → paths |
| **`src/graphics.c`** | `gTilesetTiles_General` — and only here |

`scripts/tileset_resolve.py` does this. Import it rather than joining paths.

### Parsing the declaration is necessary but not sufficient

**A declaration may name the build artifact rather than the source art**, and
which one you get differs *between decomps*:

| | tiles | palettes |
|---|---|---|
| **pokeemerald** | `INCGFX_U32(".../tiles.png", ".4bpp.lz")` | `INCGFX_U16(".../00.pal", ".gbapal")` |
| **pokefirered** | `INCBIN_U32(".../tiles.4bpp.lz")` | `INCBIN_U16(".../00.gbapal")` |

`INCGFX` names the **source** and takes the built extension as a second
argument. `INCBIN` names the **artifact** — which does not exist until `make`
has run, and is LZ77-compressed or raw BGR555 even then.

So a naive parser resolves firered's tilesets to paths that are simply not
present in a clean checkout, and anything wanting to *look* at the art gets
nothing. Strip the build suffixes (`.lz`, `.4bpp`, `.8bpp`, `.gbapal`) and try
the source extension beside it. `tileset_resolve.py` does this and falls
through to the declared path when no source is there, so a project that
genuinely ships built data still resolves.

If you do read a `.gbapal`, it is BGR555 — one `u16` per colour, 5 bits each,
red in bits 0–4. Scale to 8-bit with `v * 255 // 31`, not `v << 3`, which caps
white at 248 and tints every render slightly dark.

### FRLG-mode tilesets split differently

Emerald-mode tilesets divide the combined tile and palette space **512/6**
between primary and secondary. FRLG-mode divides it **640/7**. Anything
decoding a metatile entry needs the right split or every tile index above the
boundary resolves to the wrong tileset.

**Corollary for anything you write:** declare palettes and asset arrays
longhand, not behind a macro. A pasted symbol name is invisible to a parser,
and the tooling will silently lose the tileset rather than error.

## Swapping tilesets at runtime

`gMapHeader` is EWRAM — a RAM *copy* of the ROM header — and
`CopyMapTilesetsToVram` reads `gMapHeader.mapLayout`. If your code runs early
enough in the map load (state 0 of `LoadMapFromWarp`, before `InitMapView()`
uploads tilesets), you can point one map at another layout's tilesets:

```c
gMapHeader.mapLayout = GetMapLayout(someOtherLayoutId);
```

**Never patch `mapLayoutId`.** Dispatch code all over the engine — and probably
in your project — keys on it. The donor layout is a tileset source only; no map
needs to point at it.

**What this cannot reach:** anything read from the **ROM header by warp group
and id** rather than from `gMapHeader`. That includes `GetCurrentMapType` and
the weather loader, which is why weather and dive are per-*map* properties that
a tileset swap cannot fake. If you need those to vary, you need a second map
sharing the same `layout` — see `references/engine-traps.md` and
`references/weather.md`.

It also does not reach `wild_encounters.json`, which keys on the real map.

## The cheapest art there is: a palette-only tileset

A whole visual variant can cost **one palette directory**. Several tilesets can
share `tiles`, `metatiles` **and** `metatileAttributes` and differ only in
`.palettes`. Vanilla does this — `gMetatiles_SecretBaseSecondary` is shared by
six tilesets.

**Whether it works is one measurement**, and you should take it before
designing around it: census which palette slot each metatile you actually paint
draws from. It works when everything you paint draws from the tileset's *own*
secondary slots. `NUM_PALS_IN_PRIMARY` is 6, so palette 6 is the first
secondary slot.

In one real case every wall metatile, both stairs and all seven composed
slivers drew from palette 6 and only palette 6 — so one palette file recoloured
everything. The same census showed the region layer was 45% *primary* palette 5
and the decoration 50% primary palette 3. Those belong to the shared primary
tileset and **cannot be recoloured**, which is why that variant shipped with no
region layer and no decoration rather than with mismatched ones.

Consequences:

- **Sharing the attributes matters as much as sharing the metatiles**, and is
  easier to miss. Behaviours come with them, so encounter flags carry over
  unchanged.
- **`.callback` must be carried over too.** Tileset animation DMAs tile
  *pixels*, not colours, and the tiles are shared — but `NULL` silently stops
  the animation on your variant only.
- **This is the one place metatile ids may legitimately be shared** across
  areas. Everywhere else that is the bug described in `engine-traps.md`; here
  the ids are literally the same file, so one constants block serves all
  variants. A tileset that merely *happens* to be byte-identical still needs
  its own constants — that equality is a coincidence.

**Both `graphics.h` and `headers.h` end inside an FRLG branch**, and in
`headers.h` it is an `#else` rather than a trailing `#endif`, so the Emerald
block ends well before the end of the file. **Appending at the end of either
file is silently dropped from an Emerald build** — the same trap as
`data/event_scripts.s`.

## Importing a third-party sheet

`scripts/import_tile_sheet.py` builds a complete secondary tileset — tiles,
metatiles, attributes and palettes — from a gridded sheet.

**The thing worth importing is often not the art, it is the rules.** Vanilla
ships maps, not autotile rules, which is why deriving them statistically fails
(see `map-format.md`). A well-formatted rip frequently ships a **Legend column
giving each cell's neighbour mask**, which can be decoded and matched against
autotile slots directly. In one case all twenty slots matched at full score,
nothing was guessed, and it yielded two things no vanilla-derived table had:
**four distinct inside corners** (vanilla Emerald never drew them) and **native
one-block-thick walls in every case** (vanilla walls are never one thick).

### Composing one tileset from several sheets

A tileset does not have to come from one sheet. The importer takes a list of
blocks, each naming its own sheet and column, and **the block order is the
metatile order**. Rules that fall out of that:

- **The 15-colour budget is per PALETTE SLOT, not per block.** Blocks sharing a
  slot must be quantised **together** — a tileset has one palette per slot, so
  quantising them apart hands the slot whichever was written last and silently
  recolours the others.
- **Every block carries its own donor attribute, and that is a design decision
  rather than boilerplate.** A decoration variant that replaces a floor block
  in place needs the *floor's* behaviour. A decor tile missing the encounter
  flag is a hole in the encounter surface that looks exactly like the surface —
  and a checker that tests what your table names as the floor will not see it.
- **Ids move when a block's cell count changes.** Re-run and diff the printed
  declarations rather than assuming ids held still.
- **Alternates pair by LEGEND POSITION, not by order.** A variant cell at
  `(row, k)` varies whatever the base block draws at the same `(row, k)` — the
  same neighbour mask, therefore the same autotile case. Pairing by hand puts a
  north-edge variant on an interior block, which reads as a hole in the mass.
- **A palette that does not fit is reduced, not refused.** A block wanting more
  than fifteen colours has its lowest-error pairs merged until it fits. Read
  the merge output — it is the only notice that art lost a colour.

### Judging a fill you did not draw

A flat fill can be better than a textured one. Measure the **seam**: how
visible the join is when the tile is placed against a copy of itself. One flat
dark fill measured 0.0 against 35–42 for every textured rock face in a tileset
evaluated beside it, where a fill at that seam became visible corduroy across a
whole wall mass.

### Licensing, which is not optional

Ripped sheets are the original publisher's art. A ripper's "credit
appreciated" covers their formatting labour, not the underlying copyright.
**Do not redistribute sheets** — ship the importer and the sheet format, and
let people supply their own.
