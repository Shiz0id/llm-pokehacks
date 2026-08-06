# Engine integration — the things that fail silently

Every item here loads, links, runs, and does the wrong thing without saying so.
That is the selection criterion: bugs that announce themselves do not need
documenting.

## Contents

- [Adding a map](#adding-a-map)
- [Wild encounters key on the MAP](#wild-encounters-key-on-the-map)
- [Metatile ids are tileset-pair specific](#metatile-ids-are-tileset-pair-specific)
- [Object events: templates from RAM, count from ROM](#object-events-templates-from-ram-count-from-rom)
- [Item balls read their contents from ROM](#item-balls-read-their-contents-from-rom)
- [Berry trees write SAVED state](#berry-trees-write-saved-state)
- [Hidden items are BG events, and BG events are ROM only](#hidden-items-are-bg-events-and-bg-events-are-rom-only)
- [Trainer scripts assume inline battle data in three places](#trainer-scripts-assume-inline-battle-data-in-three-places)
- [Two different post-battle pointers](#two-different-post-battle-pointers)
- [`specialvar` reads the return value](#specialvar-reads-the-return-value)
- [Trainer defeat flags are permanent](#trainer-defeat-flags-are-permanent)
- [A context-dependent value hard-coded](#a-context-dependent-value-hard-coded)
- [Map names: `gMapHeader` is RAM, `MAPSEC` tables are not all bounded](#map-names-gmapheader-is-ram-mapsec-tables-are-not-all-bounded)
- [A bare `warp` reads out of bounds](#a-bare-warp-reads-out-of-bounds)
- [A battler's sprite id lies, and its stamp does not survive](#a-battlers-sprite-id-lies-and-its-stamp-does-not-survive)

---

## Adding a map

Six steps, and missing any of them fails quietly:

1. `data/layouts/<Name>/{map.bin,border.bin}` plus an entry in `layouts.json`
2. `data/maps/<Name>/map.json` plus an entry in `map_groups.json`
3. `data/maps/<Name>/scripts.inc` defining `<Name>_MapScripts::` and `.byte 0`
4. **An `.include` for it in `data/event_scripts.s`**
5. Dispatch branches in `src/overworld.c` if the map needs special load
   handling — there are **two**, the map-load path and the load-from-save path
6. An entry in `src/data/wild_encounters.json` if anything on it should spawn
   Pokémon (see below — this one is the most commonly missed)

**The `.if IS_FRLG` trap.** `data/event_scripts.s` has an `.if IS_FRLG` block
partway down the file. Appending your include after the *last map in the file*
puts it inside that block, where it is silently never assembled for an Emerald
build. The symptom is an unchanged `undefined reference to <Name>_MapScripts`
even though the include is visibly present in the file. Put Emerald-side
additions **above** that block and leave a comment saying why, because the next
person to append will otherwise land inside it exactly as you did.

**Position in `map_groups.json` IS `MAP_NUM`.** Inserting a map in the middle
of a group renumbers every map after it. Anything holding a stored
`location.mapNum` — notably an existing save file — will then resolve to a
different map. Append to the end of a group unless you are prepared to
invalidate saves.

**Sharing a layout is usually what you want.** Several maps can point at the
same `layout`, which means `gMapHeader.mapLayoutId` is identical on all of
them, so every dispatch keyed on `mapLayoutId` keeps working with no edit. This
is how you give the same physical area different map-header properties —
weather, map type, music — without duplicating the layout.

## Wild encounters key on the MAP

`StandardWildEncounter` runs two gates before any custom hook is consulted, and
each fails silently:

1. `GetCurrentMapWildMonHeaderId()` matches `gSaveBlock1Ptr->location` against
   `gWildMonHeaders` — **the real map**, not any layout you may have swapped in
   — and returns `HEADER_NONE` if it is absent from `wild_encounters.json`.
2. It then picks the land or the water branch from the metatile behaviour under
   the player, and returns immediately if **that branch's** table is `NULL`.

So a map needs an entry for itself, carrying the table its own encounter
surface actually reads. The branch is decided by two tile flags and nothing
else:

| behaviours | `TILE_FLAG_HAS_ENCOUNTERS` | `TILE_FLAG_SURFABLE` | branch |
|---|---|---|---|
| `MB_CAVE`, `MB_TALL_GRASS`, `MB_LONG_GRASS`, `MB_INDOOR_ENCOUNTER` | yes | no | land, 12 slots |
| `MB_OCEAN_WATER`, `MB_SEAWEED_NO_SURFACING` | yes | yes | water, **5 slots** |

Read `TILE_FLAG_SURFABLE`, **not**
`MetatileBehavior_IsSurfableFishableWater` — the two disagree, and the
disagreement is exactly underwater seaweed, which is surfable-flagged but not
in the fishable list. `IsWaterWildEncounter` reads the flag, so a seafloor
counts as a water area even though the player is walking on it. Vanilla agrees:
every `MAP_UNDERWATER_*` registers `water_mons`.

Two consequences:

- **`encounter_rate` is live even when the mon table is a placeholder**, because
  the rate is read off the static JSON entry before any hook is called.
- **The slot counts differ.** If you substitute species at runtime, a window
  wider than the branch's slot count leaves entries nothing can ever roll.

A useful habit: make placeholder tables an *unmistakable* species. If your hook
ever stops substituting, a Zubat while surfing is obvious, where a placeholder
Tentacool would let the same failure pass for real.

## Metatile ids are tileset-pair specific

`0x214` is a ladder under `gTileset_Cave` and a grey stripe under
`gTileset_Rustboro`. **Nothing carrying a metatile id can be shared between
areas on different tilesets.**

The important corollary: **a function runs under every tileset it is called
with, so only a table may name a metatile.** A `#define` for one area's floor,
used directly inside a shared function, will paint the wrong thing everywhere
else — and if the id happens to land on a metatile with no encounter flag, that
area silently has no wild Pokémon at all.

This is worth enforcing with a lint: grep your own metatile constants and fail
if any appears inside a function body rather than in a table.

Note also that a *mock or simulation* of your painting code cannot catch this,
because the mock fills from the table while the game fills from whatever the
code actually reads. The mock validates a table, not the code that reads it.

## Object events: templates from RAM, count from ROM

The engine reads object event templates for the current map from the **save
block** (`gSaveBlock1Ptr->objectEventTemplates`, a fixed 64 entries), but takes
the **count** from ROM (`gMapHeader.events->objectEventCount`, read by
`TrySpawnObjectEvents`).

That split is what lets code rewrite where things stand at runtime. It also
means **`map.json` must declare a placeholder slot for every object you might
ever write** — a template past the declared count is simply never spawned, and
nothing says so.

Keep that number in one place and check it, because it lives in two files. And
derive the list of maps to check from a property the engine uses — e.g. every
`map.json` sharing the layout your dispatch keys on — rather than listing map
names by hand. A hand-maintained list of "the maps that are really mine" is
itself the bug: maps added later inherit the behaviour and none of the
declarations.

Other object event facts:

- An object event whose `flagId` is **set** does not spawn. That is how unused
  placeholder slots are hidden.
- **A defeated trainer object still blocks movement.** A boss standing in a
  doorway walls the exit off permanently.
- Templates cost **no RAM to use** — the 64 entries exist whether a map
  declares one or sixty. The real ceiling is `OBJECT_EVENTS_COUNT` (16 **live**
  sprites, player included), and objects spawn by proximity, so what matters is
  how many crowd one screen.
- `OBJ_EVENT_GFX_SPECIES()` puts a Pokémon sprite on an ordinary map object,
  and `graphics/pokemon/<species>/overworld.png` already exists for every
  species. Free NPCs with no new art.

## Item balls read their contents from ROM

`item_ball.c` looks an item up as
`gMapHeader.events->objectEvents[localId - 1].trainerRange_berryTreeId` — the
**ROM** template array, not the save block copy. So an item written into a
generated template is ignored and every ball hands over whatever `map.json`
declared. Quantity has the same problem via `movementRangeX`, which is
additionally a **4-bit field** capping at 15.

This is the one place in the engine that gets it wrong;
`GetObjectEventTemplateByLocalIdAndMap` is the correct accessor and everything
else uses it.

**Do not patch it.** A template's `script` pointer *does* come from the save
block, so pointing your objects at a script of your own means the broken path
is never entered:

```
MyMap_EventScript_ItemBall::
	specialvar VAR_RESULT, MyProject_PrepareItem
	finditem VAR_RESULT, VAR_0x8009
	special MyProject_HideTakenItem
```

Keep the shape identical to the engine's own `Common_EventScript_FindItem` —
set the item and amount, then let `finditem` do the message, fanfare, pocket
and `removeobject` — so a generated ball behaves exactly like a hand-placed one.

**`removeobject` does not keep a ball gone.** It removes the *object*; the
template it spawns from still says a ball is there, so it returns as soon as
the player walks out of range and back. The template must move off the map
(`x = y = INT16_MAX`), which is what the Battle Pyramid does for this exact
reason.

Key that on **whether the object is still there**, not on whether the item
reached the bag — `Std_FindItem` only removes the object on success, so a full
bag correctly leaves the ball standing with no special case.

## Berry trees write SAVED state

`gSaveBlock1Ptr->berryTrees[]` is a fixed 128-entry save block array and
`PlantBerryTree` writes into it. That puts berry trees on a different schedule
from everything else.

**This generalises well beyond berries.** Any code that prepares a map runs on
*every* load of that map, including load-from-save. Anything it does that
touches saved state will therefore be re-done every time the player reloads —
regrowing picked berries, respawning collected items, resetting flags.

The distinction to use: **the object event template loader does not run on the
load-from-save path.** So split the work — choose positions and contents at
prepare time, touching nothing saved, and do the saved-state write from the
template loader. Trainer defeat flags, hidden item flags and berry planting all
rely on this same property.

Berry specifics, if you need them:

- **`MOVEMENT_TYPE_BERRY_TREE_GROWTH` is how the engine recognises a tree at
  all** — it scans object events for that movement type. Not decoration.
- The tree id rides `trainerRange_berryTreeId`, the same field trainers use for
  sight range. Vanilla names ids 0–89 of 128, so custom ones start above that.
- Plant straight to `BERRY_STAGE_BERRIES` with `allowGrowth = FALSE` — the
  growth clock is real time. Then **overwrite `berryYield`**, because
  `CalcBerryYield` derives the stock 2–6 spread from watering that never
  happened. It is a 5-bit field.
- Blank unused slots with `RemoveBerryTree` rather than leaving them hidden: the
  template is invisible either way, but a live tree in the array is still found
  by anything that scans them.
- `ItemIdToBerryType` returns `BERRY_ID_NONE` for a non-berry, so a wrong item
  name in a table plants a **blank patch of dirt** and nothing in the build
  complains. Validate the names.

## Hidden items are BG events, and BG events are ROM only

Unlike object events, `bgEvents` are **never** copied to the save block —
`GetBackgroundEventAtPosition` reads `mapHeader->events->bgEvents` directly. So
the template seam that carries objects does not reach them at all.

But `gMapHeader.events` is a **pointer in a RAM struct**. Copy the ROM header's
events wholesale into your own EWRAM `struct MapEvents`, swap only `bgEvents`
and `bgEventCount`, and repoint at the copy — warps, coord events and the
object event count all keep saying what `map.json` said. `struct BgEvent` is 12
bytes; `struct MapEvents` is four counts and four pointers.

It has to run **on every load**, because `gMapHeader` is assigned wholesale
from ROM each time. That is also what makes it free to undo: warp anywhere else
and the pointer is ROM's again.

- **`elevation` must be `ELEVATION_TRANSITION`.**
  `GetBackgroundEventAtPosition` matches when the event's elevation equals the
  *player's* or is transition.
- The engine derives a hidden item's flag as
  `hiddenItemId + FLAG_HIDDEN_ITEMS_START`, so **the ids you choose are flags**
  and must be ones nothing else owns. Vanilla's block runs 0x00–0x6F. Assert
  the arithmetic rather than trusting a comment — a collision marks a vanilla
  hidden item collected on a save that never went near it.
- The Dowsing Machine works on these for free, because
  `ItemfinderCheckForHiddenItems(gMapHeader.events, …)` takes the events as a
  **parameter** rather than reaching for the global.
- `item_use.c` refuses to start dowsing while surfing or underwater, so hidden
  items on water surfaces are unreachable by design.

## Trainer scripts assume inline battle data in three places

If a trainer picks its opponent at runtime, its script has no inline
`trainerbattle` data — and the engine parses trainer scripts as battle data in
three separate places. **The frontier facilities have an explicit branch at all
three**, which is the map for where yours go:

| site | what it reads |
|---|---|
| `ConfigureAndSetUpOneTrainerBattle` | script bytes as `TrainerBattleParameter` |
| `GetTrainerFlagFromScriptPointer` (sight check) | opponent id from script |
| double-battle mode check in `trainer_see.c` | battle mode from script |

If you add anything else that picks an opponent at runtime, grep for the
facility branches first.

## Two different post-battle pointers

- Winning leaves via `gotobeatenscript` → `TRAINER_BATTLE_PARAM.battleScriptRetAddrA`
- Talking to an already-beaten trainer leaves via `gotopostbattlescript` →
  `sTrainerBattleEndScript`

Leaving `battleScriptRetAddrA` NULL makes the engine fall through to
`EventScript_TryGetTrainerScript`, which loops straight back into
`gotobeatenscript` — an infinite script loop that never releases player
control. **Set both.**

Both point at the same script in practice, which means **a post-battle script
runs again on every later conversation** — that is how the engine says "nothing
to fight here". Anything one-shot in it (a reward, an item) must sit behind a
flag or the player farms it by talking. Anything that opens the way out must
sit *outside* that flag, or a reload strands them.

## `specialvar` reads the return value

`ScrCmd_specialvar` is `*ptr = gSpecials[index]();`. `data/specials.inc` is
assembly, so there is no prototype and **nothing warns**.

A `void` special used with `specialvar` hands the script whatever is left in
`r0`, which after the epilogue is the return address — never 0, never 1, so
every `goto_if_eq` against `TRUE`/`FALSE` silently takes the wrong branch.

**Every `specialvar` target must return `u16`.** Writing `gSpecialVar_Result`
inside a `void` special instead compiles, links and runs — it just answers
wrong. Plain `special` (no var) is unaffected and may stay `void`.

## Trainer defeat flags are permanent

They were designed for a game where you fight each trainer once ever. If you
reuse stock trainers, clear their flags **once per map load, at template-load
time**.

Clearing at battle setup does not work: the battle script checks the flag
immediately after running that special, so the trainer never registers as
beaten and rematches forever.

Also keep trainer ids **distinct within a map** — the flag is derived from the
id, so two slots sharing one leaves a trainer that refuses to battle.

## A context-dependent value hard-coded

The most repeated bug shape there is: a constant that was correct for every
case that existed when it was written.

Real examples, all of which shipped:

| what was hard-coded | what it cost |
|---|---|
| a floor metatile id | one area had no wild Pokémon at all |
| object event elevation `3` | the player walked through every NPC on a water map |
| an elevation when drawing an exit | a map became impossible to leave |

That last one is worth understanding: `IsElevationMismatchAt` blocks movement
between two *different* non-zero elevations, so an exit drawn at elevation 3 on
a map the player walks at elevation 1 appears somewhere they cannot step.

When you add a per-area property, **grep for the constant, not just the field**
— the field will have been threaded through most paths and missed on one.

## Map names: `gMapHeader` is RAM, `MAPSEC` tables are not all bounded

Three facts, in the order they matter.

**`gMapHeader` is `EWRAM_DATA`, not ROM** (`src/fieldmap.c`). It is a RAM copy
made on every map load, so `gMapHeader.regionMapSectionId` can be **assigned at
runtime**, the same way the events pointer is already repointed. A map reused
for several different places does *not* need one map per name. Assume it is ROM
and you will build maps you did not need.

**A shared map means a shared name.** The name in the map-name popup comes
from that field, so every area sharing one map announces whatever that map's
`map.json` declared — one name, said aloud everywhere the map is reused, until
something rewrites the RAM copy.

**Both mapsec headers are GENERATED and gitignored.**
`include/constants/region_map_sections.h` and
`src/data/region_map/region_map_entries.h` come from
`src/data/region_map/region_map_sections.json` through jsonproc. Editing either
header directly **builds, links, runs and passes every check** — and is then
erased by the next regeneration, having never appeared in a commit. `git status`
showing fewer modified files than you edited is the only signal. Add the section
to the JSON; one list generates both, so the enum and the entries table cannot
drift.

**Adding a `MAPSEC` without a `gRegionMapEntries` row reads out of bounds.**
`gRegionMapEntries[]` (`src/data/region_map/region_map_entries.h`) is an
*unsized* array — currently 209 rows — and `GetMapName` guards with
`regionMapId < MAPSEC_NONE` (`src/region_map.c`). Those two bounds are equal
only by convention. Insert a `MAPSEC_*` before `MAPSEC_NONE`, skip the entries
row, and the guard passes while the index runs past the end. Every new section
needs both.

Two smaller notes for the same job. `regionMapSectionId` is `mapsec_u8_t` — a
**u8** — so the ceiling is 255 against 209 used, about 45 free. And
`sMapSectionToThemeId` (`src/map_name_popup.c`) is sized
`[MAPSEC_COUNT - KANTO_MAPSEC_COUNT - 1]`, so it grows with the enum and new
entries default to theme 0 rather than reading OOB — benign, but a new name
gets a default popup theme unless one is chosen.

**The save-select screen shows no location at all.** Emerald's continue window
draws exactly four things — player, Pokédex, time, badges
(`MainMenu_FormatSavegameText`). The location line is a FireRed feature. Naming
a map does not make it appear there; that is a separate field competing for a
window with no spare row (`MENU_HEIGHT_WIN2` is 6 tiles, rows at y=17 and y=33,
next window at tile row 9).

**And the RAM patch does not reach everything.** `GetCurrentRegionMapSectionId`
(`src/overworld.c`) does **not** read `gMapHeader` — it calls
`Overworld_GetMapHeaderByGroupAndId` on the saved location and reads the **ROM**
header. So a Pokémon's met location still records what `map.json` declares,
however many times the RAM copy was rewritten. This is the same shape as
`GetCurrentMapType` going through `GetMapTypeByWarpData`: patching the RAM
header buys you everything that reads `gMapHeader` and nothing that re-derives
the header from warp data.

When you patch a header field at runtime, **grep every reader of that field**
and sort them into the two groups before believing the change is complete.

---

## A bare `warp` reads out of bounds

**Always give `warp` a warp id or an x/y pair.** `warp MAP_X` on its own is the
tidiest-looking form and the only one that is broken.

`formatwarp` fills the missing coords with `-1`. `ScrCmd_warp` then puts those
through `VarGet`, and **`VarGet(0xFFFF)` is an out-of-bounds read**:
`GetVarPointer` sends anything at or above `SPECIAL_VARS_START` to
`gSpecialVars[id - 0x8000]`, so `0xFFFF` indexes **element 32767 of a 22-entry
array** — a pointer fetched 131068 bytes past its end, out of
`event_scripts.o`'s own script data — and then dereferences it. `x` and `y`
come back as whatever was lying there.

`SetWarpDestination` narrows them to `s8`, so the low byte decides the symptom,
and the common one is a coordinate outside the map. **Outside the map is not a
black screen.** It is the map's **border metatile tiled to the horizon**, with
the map's music playing and the player able to walk — which reads as
"teleported into the void" and sends you hunting the warp logic, where
everything is correct.

**The reason this deserves a check and not a comment: it is stable per build.**
That address holds ordinary script data, so a build either works or does not,
consistently — and it flips when *an unrelated script somewhere else grows and
moves those bytes*. A bare warp can ship working for months and then break
because a menu three files away got longer. Nothing about the warp changed.

Worth a lint of your own: fail on any argument-less warp. Vanilla never relies
on the form — of 197 warp-family calls in the tree, not one is bare.

Note that `warphole` is **not** affected — it is declared `map:req` with no
coord parameters and reads the player's live position instead, so its bare
vanilla call sites are correct. Check the macro in `asm/macros/event.inc`
before assuming a command takes the `formatwarp` path.

---

## A battler's sprite id lies, and its stamp does not survive

Anything that writes to a battler's sprite in battle — streaming frames,
recolouring, swapping tiles — hits two separate traps, and the second only
appears after the first is fixed.

**`gBattlerSpriteIds[battler]` is often not that battler's mon sprite.** At load
time it has not been created yet: `BtlController_HandleDrawTrainerPic` calls
`BattleLoadMonSpriteGfx` and only *then* `CreateSprite`, so the id still holds
whatever was there before. And the trainer slide code deliberately assigns
`gBattlerSpriteIds[battler] = gBattleStruct->trainerSlideSpriteIds[battler]`, so
it is sometimes a trainer's on purpose. Writing to the wrong sprite's tiles
produces a band of garbage through a healthbox, or a Pokémon frame drawn over
the opposing trainer. A healthbox is redrawn only on an HP change, so one bad
write at send-out looks like permanent corruption.

The engine stamps `data[0] = battler` and `data[2] = species` when it creates a
battler's mon sprite, and checking both is the only discriminator available.
Mon and trainer sprites come from the same `gMultiuseSpriteTemplate` and share
`frameImages` after `AllocateMonSpritesGfx`, so template and image pointers do
not distinguish them.

**But the stamp does not survive a mon animation.**
`Task_HandleMonAnimation` (`src/pokemon_animation.c`) zeroes `data[0]` and
`data[2..7]` for the duration and restores them from what it saved — except it
saves `data[0]` as `oam.paletteNum`, and saves `data[2]` off a sprite whose
scratch an earlier animation may already have cleared. Measured after a KO
animation, the surviving battler's `data[2]` came back as **1** rather than its
species, and nothing ever set it right.

So a guard written on the stamp alone passes at first and then fails for the
rest of the battle. Latch the sprite id the first time the stamp proves it and
accept that id afterwards, clearing the latch wherever the sprite is reloaded
(`BattleLoadMonSpriteGfx` is the hook for switch-in *and* transform). Both
protections survive: a stale id at load time is rejected because the latch is
clear, and a re-pointed trainer id matches neither the stamp nor the latch.

The symptom shape is worth recognising, because it does not look like a guard
bug: the code keeps running and keeps writing to its own buffer, and only the
VRAM copy stops. The sprite freezes, and then appears to *recover* on opening
the Bag or the party menu — because those recreate the sprite and restamp it.

**Headless tests cannot see any of this.** `gTestRunnerHeadless` swaps
`sMonAnimFunctions` out for `WaitAnimEnd`, which saves and restores cleanly, so
a test written for the freeze **passes against the live bug**. Use
`FORCE_MOVE_ANIM(TRUE)` in any battle test that goes near a mon animation. And
nothing headless knows which sprite the tiles actually reached, so anything
writing OBJ VRAM gets looked at on a screen before it is believed.
