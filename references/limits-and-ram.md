# RAM, ROM and other ceilings

## RAM is the first ceiling. ROM becomes one sooner than you expect

**EWRAM is 256 KiB (262,144 bytes) and IWRAM is 32 KiB (32,768 bytes.)** Those
are hardware, they are what the linker prints its percentage against on every
link, and nothing you configure grows them.

A stock pokeemerald-expansion build already uses **~86% of both** before you add
anything — about 225 KB of the 256 KiB — against roughly 6.5 MB free of 32 MB of
ROM. So RAM is what bites first, and most of this file is about RAM.

**But do not read "ROM is not scarce" as a standing fact.** That 6.5 MB is
consumed quickly by anything asset-shaped — an animated sprite set, an imported
tileset pack, added music — and a project can go from 79% to over 90% in a
single feature. Measure with `scripts/rom_budget.py` rather than assuming; see
[the ROM budget](#the-rom-budget) at the bottom for where it actually goes and
which levers return the most.

Three fixed buffers account for most of it. Measured on one build:

| bytes | object |
|---|---|
| 115,968 | `malloc.o` — `gHeap`, one fixed `EWRAM_DATA` array sized by `HEAP_SIZE` |
| 55,308 | `load_save.o` — SaveBlock buffers |
| 20,524 | `fieldmap.o` — `sBackupMapData`, the map grid |

**191,800 bytes between them: 73% of the whole region, and ~85% of everything
that build had in use.** `HEAP_SIZE` is a project constant and does move — it
was `0x1C500` there — so measure your own rather than reusing that row.

Three consequences that surprise people:

**Cutting content frees ROM, not RAM.** Making a whole intro sequence
unreachable freed 6,504 bytes of ROM automatically via `--gc-sections`, and
moved EWRAM and IWRAM by exactly zero. If you are deleting features to make
room, check which room you actually need.

**If EWRAM gets tight, tune `HEAP_SIZE` first.** It is 44% of the whole region
in a single constant, and about half of what a stock build actually uses.
A hack that never opens contests or the Battle Frontier may not need vanilla's
heap. But heap exhaustion fails at *runtime*, so this needs
play-testing rather than a successful link.

**Mark every new static as `EWRAM_DATA`.** Plain statics land in IWRAM, which
has roughly 4 KiB free against EWRAM's ~35 KiB. Watch the linker's IWRAM line on
every build — it is printed automatically and is the cheapest regression test
you have.

`scripts/ram_budget.py` breaks the usage down by object file.

## Free storage you already have

- **`sBackupMapData`** (20,524 bytes) is allocated unconditionally. If you
  generate map data at runtime, generating into it costs nothing extra.
- **`gSaveBlock1Ptr->objectEventTemplates`** is a fixed 64 entries whether a map
  declares one or sixty. Object event templates are free to use.
- **Another weather's sprite pointer array** is free while your weather is up —
  only one weather runs at a time. One vanilla array is 101 entries for an
  effect that uses 20.

## Sprite and object ceilings

| limit | value | what it means |
|---|---|---|
| `MAX_SPRITES` | 64 | for the **whole screen**, including the player, NPCs, field effects and weather |
| `OBJECT_EVENTS_COUNT` | 16 | **live** object event sprites, player included |

Object events spawn by proximity, so what matters is how many crowd one screen,
not how many exist on the map. **Off-screen ones do not merely go unrendered —
they are destroyed**; see the object-event lifetime section of
`engine-traps.md` before writing anything that drives one at distance.

Weather sprite counts should be chosen against `MAX_SPRITES` — a map with 16
object events plus the player leaves about 47 slots, and field effects need some
of those.

## Field width limits that bite

Several fields are narrower than they look, and overflow silently:

| field | width | used for |
|---|---|---|
| `movementRangeX` | 4 bits | item ball quantity — caps at 15 |
| `berryYield` | 5 bits | berries per tree — caps at 31 |
| collision | 2 bits | only 0 and 1 appear in all of vanilla |
| elevation | 4 bits | 0 transition, 1 water, 3 ground, 4+ raised, 15 multi-level |
| OAM palette slot | 4 bits | **`0xFF` from a failed `LoadSpritePalette` truncates to 15** |

That last one is a real trap: a palette load failing late gives you slot 15,
which will contain whatever happens to live there, rather than an error.

## Map size

`(width + 15) * (height + 14) <= MAX_MAP_DATA_SIZE` (10240). All 785 vanilla
layouts satisfy it; the largest reaches 91.8%.

## The ROM budget

`scripts/rom_budget.py` reads `pokeemerald.map` and answers "where is the ROM
going". Run it rather than reasoning about it.

**Two things will mislead you before you start.** `pokeemerald.gba` is exactly
33,554,432 bytes whatever the build contains, because `gbafix -p` pads to a
power of two — the file size tells you nothing. And an object file's size is not
its ROM cost, because assets are `INCBIN`'d into whichever object references
them, so every species front pic lands in one graphics object and "which file is
big" answers nothing. Attribution has to be **by symbol**, which is why the tool
sizes each symbol by the distance to the next one.

That distance is an approximation, and it lies at section boundaries: trailing
padding is charged to whatever precedes it, so a single symbol next to a
boundary can look enormous. Category totals compare soundly; one symbol does
not.

### The single biggest thing in a stock expansion build is content you may not use

`P_GEN_N_POKEMON` in `include/config/species_enabled.h` defaults every
generation to `TRUE`, so the ROM carries cries, front and back pics, icons,
palettes and species data for ~1,500 species. Measured on one build: **cries
alone were 8.9 MB across 1,159 symbols**, and sound and music together were
9.97 MB — 34% of the whole ROM. Cutting Gen 4–9 returned **9.38 MB**.

**It is not all-or-nothing, which is the part that gets missed.** There are
**539 `P_FAMILY_*` toggles**, and each merely *defaults* to its generation:

```c
#define P_FAMILY_TURTWIG                 P_GEN_4_POKEMON
```

So a project that needs a handful of later-generation species — starters,
a rival's ace, one legendary — can disable the generation and force just those
families back on. Measured on a project doing exactly that, keeping eighteen
starter families across Gen 4–9: cutting those generations still returned
**8.66 MB**.

**EWRAM and IWRAM move by 4 bytes.** Cutting content still does not buy RAM.

**Verify surviving species by the LINK MAP, not by the build succeeding.** A
disabled family is gated with `#if P_FAMILY_X` around its `species_info` entry,
but the SPECIES_ constant survives — `SPECIES_GRENINJA = 658` is still in the
enum. Every reference still compiles, and the species becomes a zeroed
`gSpeciesInfo` row: no stats, no name, no graphics. Nothing fails. The evidence
that a species is really present is its `gMonFrontPic_*` symbol in
`pokeemerald.map`, which is what `rom_budget.py --prefix gMonFrontPic` lists.

Any checker you have written that reads `species_info` as source text cannot see
this and will pass either way.

Two things worth knowing before choosing a cut point. All eight Eeveelutions
live under `P_FAMILY_EEVEE`, so Sylveon and Glaceon survive even a Gen 1-only
build. And a species enum entry named `SPECIES_X_NORMAL` is the base form of a
species that has alternate forms — the bare `SPECIES_X` is a valueless alias
that never appears in a generated id table, while both the graphics directory
and most third-party asset sets call it plain `x`.

### Smaller reclaims

Things many hacks cannot reach at all, and roughly what they hold in a stock
expansion build:

| | | |
|---|---|---|
| Battle Frontier | 335 KB | |
| Colosseum multiboot | 160 KB | `gMultiBootProgram_PokemonColosseum_Start` |
| Contest | 158 KB | |
| Trainer Hill, Secret Bases, Mystery Event | in "other" | |

These are small against the species config, and `--gc-sections` already drops
whatever becomes genuinely unreferenced — making an intro sequence unreachable
freed 6,504 bytes with no edit to a makefile. Reach for the family toggles
first, and only if your species roster genuinely allows it.
