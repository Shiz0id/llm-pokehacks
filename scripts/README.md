# Scripts

All of these take the decomp repo from `--repo <path>`, `$POKEDECOMP_REPO`, or
an upward search from the current directory. Renders land in `_out/` next to
these scripts.

```bash
pip install pillow numpy
export POKEDECOMP_REPO=/path/to/pokeemerald-expansion
```

## Reference and analysis

| script | what it does |
|---|---|
| `repo.py` | finds the decomp checkout. Imported by the others; not run directly |
| `tileset_resolve.py` | `gTileset_*` → real asset paths, by parsing the declarations. **Import this rather than joining paths yourself** — see below |
| `tileset_atlas.py` | renders every metatile of a tileset pair to a labelled contact sheet, annotated with behaviours |
| `build_all_atlases.py` | atlas + JSON index for every tileset pair in the repo |
| `sheet.py` | renders a chosen list of metatiles, big and labelled, for comparing candidates |
| `render_layout.py` | renders a whole vanilla layout, and censuses its metatiles split by collision |
| `derive_wall_table.py` | tallies which metatile vanilla uses per **open**-neighbour mask, with a confidence figure |
| `derive_wall_autotile.py` | the earlier variant, keyed on **wall** neighbours. Kept because the two answer different questions |
| `tree_edges.py` | a worked example of a census: what vanilla places above and below a tree |
| `ram_budget.py` | where EWRAM and IWRAM actually go, by object file. Needs a built `pokeemerald.map` |
| `rom_budget.py` | where the ROM goes, by category, by object or by symbol prefix. Needs the same map. Attribution is by SYMBOL, because assets are `INCBIN`'d into whichever object references them — and the `.gba` is always exactly 32 MB, since `gbafix -p` pads to a power of two, so its file size tells you nothing |

## Verification

| script | what it checks |
|---|---|
| `validate_maps.py` | round-trips the `map.bin` codec against every vanilla layout |

## Writers

| script | what it writes |
|---|---|
| `import_tile_sheet.py` | a whole secondary tileset — tiles, palettes, metatiles, attributes — from a gridded sheet with an autotile legend |

## Usage notes

**`tileset_resolve.py` is the one to reach for first.** Guessing asset paths
from symbol names does not work: FRLG secondaries carry an `_frlg` directory
suffix the symbol lacks, acronyms and digits split unpredictably, and seven
tilesets share assets across directories. It parses `headers.h`, `graphics.h`,
`metatiles.h` **and `src/graphics.c`** — the last of which declares
`gTilesetTiles_General` and nothing else does.

```python
from repo import REPO
from tileset_resolve import TilesetResolver
r = TilesetResolver(REPO)
print(r.resolve('gTileset_Cave'))   # dict of absolute paths
print(r.report())                   # (total, resolved, unresolved names)
```

**`derive_wall_table.py` reports confidence for a reason.** Vanilla varies wall
art decoratively, so there is frequently no rule to recover by counting.
Anything under ~80% is a hint, not an answer — go and read a grid instead. A
uniformly low score usually means the census pooled unrelated features rather
than that the tileset has no structure. See `references/map-format.md`.

**`import_tile_sheet.py` needs sheets you supply.** None ship — see the note in
the file and in the top-level README. Put yours in `scripts/sheets/` or set
`POKEDECOMP_SHEETS`. Read the `TILESETS` table as the documentation for the
config format; the `lapis` entry is the one that exercises the most of it
(multi-sheet composition, shared-palette quantisation, a drawn descent).

It **owns its output directory** and rewrites every file in it on each run, so
nothing else may append to a tileset it manages.

**`ram_budget.py` and `rom_budget.py` need a build.** They read
`pokeemerald.map`, which appears after a successful link.
