# llm-pokehacks

An Agent Skill plus a Python toolkit for romhacking the GBA Pokémon
decompilations (`pokeemerald`, `pokeemerald-expansion`, `pokefirered`,
`pokeruby`) with an LLM coding agent.

The scripts answer questions about a decomp with data instead of guesswork —
resolve tileset asset paths, render labelled metatile contact sheets, census a
vanilla layout, derive autotile rules, round-trip the `map.bin` codec, account
for RAM. The skill is the other half, and arguably the more valuable one: the
engine behaviours that **fail silently**, written down.

 An agent with a contact-sheet renderer and no 
knowledge of the traps will still put a grey ladder in a forest, still register
a new map's wild encounters nowhere, still hard-code a metatile inside a
function that runs under three tilesets. 
## Layout

```
SKILL.md              the skill: working method, orientation, router
references/           the findings, by task
  engine-traps.md       things that load, run, and silently do nothing
  map-format.md         map.bin, elevation, deriving autotile rules
  metatile-art.md       making art that does not exist, mostly without drawing
  tilesets.md           resolving, swapping, recolouring, importing
  weather.md            adding and modifying weather effects
  limits-and-ram.md     RAM/ROM ceilings and narrow fields
scripts/              the Python
```

## Using it

**As a skill:** point your agent at this directory. `SKILL.md` is the entry
point and routes to the reference files as needed.

**Standalone:** the scripts work on their own.

```bash
pip install pillow numpy          # numpy only for import_tile_sheet.py
export POKEDECOMP_REPO=/path/to/pokeemerald-expansion
python scripts/render_layout.py PetalburgWoods_Layout
```

Every script finds the decomp in this order: a `--repo <path>` argument, the
`POKEDECOMP_REPO` environment variable, then an upward search from the current
directory. A directory counts as a decomp if it has `data/layouts/layouts.json`
and `src/data/tilesets/headers.h`, so forks work.

Renders go to `scripts/_out/`, never into the repo being inspected — PNGs in
somebody's `git status` are noise at best and an accidental commit at worst.
Override with `POKEDECOMP_OUT`.

See `scripts/README.md` for what each one does.


## Tested against

| checkout | tilesets resolved | assets present | layouts round-tripped |
|---|---|---|---|
| `pret/pokeemerald` (clean) | 75/75 | 75/75 | 421 |
| `rh-hideout/pokeemerald-expansion` | 146/146 | 146/146 | 782 |
| `pret/pokefirered` (clean) | 68/68 | 68/68 | 365 |

`pokeruby` is untested. It is very likely fine, being the same era and idiom as
pokeemerald
## Requirements

- Python 3.8+
- Pillow, for anything that renders
- NumPy, for `import_tile_sheet.py` only
- A decomp checkout to point at

If you work across a WSL boundary, note that image work needs Pillow on
whichever side runs it; the scripts take `--repo` precisely so they can run from
either side of the mount.

## Licensing and provenance

The Python and the documentation here are original work — see `LICENSE`.

They *operate on* a decompilation, which is a separate project with its own
(complicated, community-tolerated) status. Nothing from a decomp is vendored
here. Metatile ids and derived tables in the documentation are factual
observations about retail game data, included because they are useless without
the game they describe.

This is an unofficial fan toolkit. Pokémon is © Nintendo / Creatures / GAME
FREAK. Nothing here contains or distributes their code or assets.
