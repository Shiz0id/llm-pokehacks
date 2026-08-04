# RAM, ROM and other ceilings

## RAM is the ceiling, not ROM

A stock pokeemerald-expansion build already uses **~86% of both EWRAM and
IWRAM** before you add anything. ROM is not scarce — roughly 6.5 MB free of 32.

Where EWRAM's ~226 KB goes:

| bytes | object |
|---|---|
| 115,968 | `malloc.o` — `gHeap`, one fixed `EWRAM_DATA` array sized by `HEAP_SIZE` |
| 55,308 | `load_save.o` — SaveBlock buffers |
| 20,524 | `fieldmap.o` — `sBackupMapData`, the map grid |

**~84% is three fixed buffers.** This has three consequences that surprise
people:

**Cutting content frees ROM, not RAM.** Making a whole intro sequence
unreachable freed 6,504 bytes of ROM automatically via `--gc-sections`, and
moved EWRAM and IWRAM by exactly zero. If you are deleting features to make
room, check which room you actually need.

**If EWRAM gets tight, tune `HEAP_SIZE` first.** It is 51% of all EWRAM in one
constant. A hack that never opens contests or the Battle Frontier may not need
vanilla's heap. But heap exhaustion fails at *runtime*, so this needs
play-testing rather than a successful link.

**Mark every new static as `EWRAM_DATA`.** Plain statics land in IWRAM, which
has roughly 4 KB free against EWRAM's ~35 KB. Watch the linker's IWRAM line on
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
not how many exist on the map. Weather sprite counts should be chosen against
`MAX_SPRITES` — a map with 16 object events plus the player leaves about 47
slots, and field effects need some of those.

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
