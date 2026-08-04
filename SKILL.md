---
name: pokemon-decomp
description: Romhacking the GBA Pokémon decompilations (pokeemerald, pokeemerald-expansion, pokefirered) — tilesets, metatiles, map layouts, map.bin, wild encounters, object events, trainer scripts, weather, field effects, and the engine traps that fail silently. Use this whenever the user is working in a decomp repo or mentions pokeemerald, pokefirered, pokeruby, decomp, romhack, ROM hack, `gTileset_*`, metatiles, `map.json`, `layouts.json`, tileset palettes, wild encounter tables, object events, or building a `.gba` from source — even if they only ask a narrow question like "why is my new map's grass not spawning anything" or "how do I add a tileset", because most of those questions have a non-obvious answer documented here and a plausible-looking wrong answer that costs hours.
---

# GBA Pokémon decomp romhacking

The decomps are C reconstructions of the retail games that build byte-identical
ROMs. They are ordinary C projects with an unusual amount of implicit contract:
the engine reads data out of ROM in some places and RAM in others, several
systems are keyed on a map's identity rather than its contents, and a
surprising amount of what you get wrong **fails silently**. No crash, no
warning, no log — the feature just does not happen.

That is the thing to internalise before anything else. In ordinary programming
a mistake usually announces itself. Here the default failure is a map that
loads perfectly and simply has no wild Pokémon in it.

## How to work in this codebase

These are not style preferences. Each one is here because doing the opposite
cost real time.

**Never guess an asset path from a symbol name.** `gTileset_SilphCo` takes its
tiles from `condominiums_frlg` and its metatiles from `silph_co_frlg`. FRLG
secondaries carry an `_frlg` directory suffix the symbol lacks. Acronyms and
digits split unpredictably. Seven tilesets share assets across directories.
Parse the declarations instead — `scripts/tileset_resolve.py` does this, and it
reads `src/data/tilesets/{headers,graphics,metatiles}.h` **and
`src/graphics.c`**, because `gTilesetTiles_General` is declared in the last one
and only that one.

**Census before you decide.** Almost every question of the form "what metatile
does vanilla use for X" is answerable by counting real placements in real
layouts, and almost every answer reached by looking at a contact sheet instead
is wrong. Metatiles that look like a grass variant turn out to be a transition
edge; things that look like a grass base row turn out to be the top of a tree.
Ask what vanilla puts *next to* a candidate before deciding what it is.

**Adjacency in the metatile grid is not evidence.** Ids next to each other are
frequently unrelated. This has produced the same class of bug repeatedly.

**Prototype in Python and render it before writing C.** Autotile tables, tile
splices and map generators are all much cheaper to validate as an image than as
a build-and-play cycle. Getting a wrong reading on screen in thirty seconds
beats finding it in an emulator in twenty minutes.

**Verify invariants host-side, over thousands of cases.** Connectivity,
determinism, out-of-bounds writes, table monotonicity. Cheaper than emulator
testing and catches a different class of bug.

**A check that has never failed is worth nothing.** Before trusting a new
verification script, break the thing it checks on purpose and confirm it fires.
This repeatedly caught checks that were passing vacuously.

**Measure per-instance, not in aggregate**, and never average across mixed
categories. An aggregate over 3,000 generated maps showed no problem while a
per-map bug was severe. A "healing power" average that pooled potions with
status items scored every arrival of a cheap-but-useful item as a regression.
When a check fires on something obviously fine, suspect the metric — then go
back and look at what survives, because the noise was hiding real bugs.

**Judge art against its neighbours and at game scale.** A wall metatile that
looks correct on a contact sheet at 5× can be obviously wrong when placed next
to the piece it must join, at 2×. Build the smallest fixture that produces the
case — for wall art that is one rectangular room, which yields exactly one of
each corner — and look at that instead.

**Read the scan output again before concluding it found nothing.** A low
confidence score often means the census pooled unrelated things, not that the
answer is absent. Re-ask the narrower question.

**Solve a case once, then check the tileset that already solved it.** Comparing
directly against a working example settles in one look what reasoning from
first principles gets wrong.

## Orientation: where things live

| what | where |
|---|---|
| map headers, object events, warps | `data/maps/<Name>/map.json` |
| map scripts | `data/maps/<Name>/scripts.inc` |
| map → group assignment (**this is `MAP_NUM`**) | `data/maps/map_groups.json` |
| layouts, dimensions, tileset pair | `data/layouts/layouts.json` |
| block data | `data/layouts/<Name>/map.bin`, `border.bin` |
| tileset declarations | `src/data/tilesets/{headers,graphics,metatiles}.h` |
| tileset assets | `data/tilesets/{primary,secondary}/<name>/` |
| wild encounters | `src/data/wild_encounters.json` |
| script includes | `data/event_scripts.s` |
| map load dispatch | `src/overworld.c` |

Build with `make -j$(nproc)`. The linker prints EWRAM/IWRAM/ROM usage on every
link — watch it, for the reason in `references/limits-and-ram.md`.

## The three facts most likely to cost you a day

**1. Metatile ids are tileset-pair specific.** `0x214` is a ladder under
`gTileset_Cave` and a grey stripe under `gTileset_Rustboro`. Nothing carrying a
metatile id can be shared between areas that use different tilesets. A constant
named inside a function runs under every tileset the function is called with —
so only a table may name a metatile. This shipped as a visible bug twice, and
the second time it silently disabled wild encounters across a whole area
because the id landed on a metatile with no encounter flag.

**2. Wild encounters key on the MAP, not the layout.**
`GetCurrentMapWildMonHeaderId` matches `gSaveBlock1Ptr->location` against
`gWildMonHeaders` and returns `HEADER_NONE` if the map is absent from
`wild_encounters.json` — silently. Then it picks the land or water branch from
the behaviour under the player and returns if *that branch's* table is `NULL`.
A new map needs its own entry, carrying the table its own encounter surface
actually reads. See `references/engine-traps.md`.

**3. RAM is the ceiling, not ROM.** A stock expansion build uses ~86% of both
EWRAM and IWRAM before you add anything, while ROM has megabytes free. Cutting
content frees ROM and moves RAM by exactly zero — ~84% of EWRAM is three fixed
buffers. See `references/limits-and-ram.md`.

## Reference material

Read the file that matches what you are doing. Each is self-contained.

| file | read it when |
|---|---|
| `references/engine-traps.md` | adding a map, generating anything at runtime, touching trainers/items/object events/wild encounters, or something works in the editor and not in game |
| `references/map-format.md` | reading or writing `map.bin`, deriving autotile rules, generating layouts programmatically |
| `references/metatile-art.md` | you need art that does not exist — composing metatiles from existing tiles, floors, walls, encounter surfaces, animated tiles |
| `references/tilesets.md` | adding or recolouring a tileset, swapping tilesets at runtime, importing a third-party sheet, resolving tileset paths |
| `references/weather.md` | adding or modifying a weather effect |
| `references/limits-and-ram.md` | the linker is complaining, or you are adding anything that costs RAM |

## Tools

`scripts/` holds Python that answers the questions above with data instead of
guesswork. Every script takes the decomp repo root as `--repo` (or the
`POKEDECOMP_REPO` environment variable) so they can live outside the tree.

| script | what it answers |
|---|---|
| `tileset_resolve.py` | `gTileset_*` → real asset paths. Import this rather than joining paths yourself. |
| `tileset_atlas.py`, `build_all_atlases.py` | render every metatile of a tileset pair as a labelled contact sheet, with behaviours |
| `sheet.py` | render a chosen list of metatiles, big and labelled — for comparing candidates |
| `render_layout.py` | render a whole vanilla layout, and census its metatiles split by collision |
| `derive_wall_table.py` | tally which metatile vanilla uses per open-neighbour mask, with a confidence figure |
| `derive_wall_autotile.py` | the earlier variant, keyed on *wall* neighbours rather than open ones |
| `validate_maps.py` | round-trip the `map.bin` codec against every vanilla layout |
| `import_tile_sheet.py` | build a whole secondary tileset from a gridded third-party sheet |
| `ram_budget.py` | where EWRAM and IWRAM are actually going |
| `tree_edges.py` | worked example of a census: what vanilla puts above and below a tree |

Pillow is required for anything that renders. `scripts/README.md` has the
per-script detail.

## Two workflow notes

Long shell heredocs break on apostrophes in prose — write patch scripts to a
file, or use editing tools directly. And `Path.write_text` on Windows emits
CRLF into repo files; pass `newline='\n'`.

If you are working across a WSL boundary, note that image work needs Pillow on
whichever side has it, and the scripts resolve the repo from `--repo` rather
than their own location precisely so they can run from either side.
