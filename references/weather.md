# Adding and modifying weather

Weather is cheap to add and the cost is almost entirely in knowing which places
to touch — several of which fail silently.

## Weather is a MAP property and cannot be faked

`GetCurrentMapType` and the weather loader read the **ROM header by warp group
and id**, not `gMapHeader`. So the RAM tileset swap that lets one map wear
another's art cannot reach weather. If you want the same physical area with
different weather, you need a second **map** — not a second layout.

That is cheap: give it the same `layout` as the original, so
`gMapHeader.mapLayoutId` is identical and every dispatch keyed on it is
untouched, and give it an empty `scripts.inc` pointing at the original's
scripts. One `map.json`, one `scripts.inc`, an include, a `map_groups.json`
entry, and — **do not forget this** — a `wild_encounters.json` entry and a full
set of object event slots, because it is a new map and inherits none of the
original's declarations. See `engine-traps.md`.

**Name such a map for the WEATHER, not for the area that first wanted it.**
Nothing in it is area-specific, and the next area wanting the same weather then
costs zero.

## There are free constant slots

`WEATHER_COUNT` is 24, but the named values stop at `WEATHER_ABNORMAL` (15) and
resume at `WEATHER_ROUTE119_CYCLE` (20). **16–19 are an unused gap**, already
inside the bound, and `sWeatherNames[WEATHER_COUNT]` already sizes for them.

## The four places a novel weather touches

| what | why it matters |
|---|---|
| `sWeatherFuncs` | indexed with **no bounds check**, and vanilla's table ends at 15 |
| `TranslateWeatherNum` | **the one that bites** — see below |
| `sWeatherNames` | debug only |
| the constant itself | the gap at 16–19 |

**`TranslateWeatherNum` is the silent failure.** Without a `case`, a map header
asking for your new weather falls through to `default: return WEATHER_NONE` and
*absolutely nothing happens*. No crash, no warning. The map loads perfectly and
is simply not weathered.

## A weather that joins a FAMILY costs nine places, not four

This is the important correction. Four places is right for a weather unlike
anything else in the game. But **vanilla has no concept of "a rain"** — it asks
that question **nine separate times, by enumerating the three rains it knows
about**:

| where | what it decides | how it fails without you |
|---|---|---|
| `SetNextWeather` | play the rain-*stopping* SFX | the stop sound fires as the rain *starts* |
| `FadeInScreenWithWeather` | use the rain fade path | fades in wrong, wrong colour map |
| the palette-select switch | `useWeatherPal = TRUE` | the weather palette is not used |
| `Rain_Finish` | keep sprites across a change | raindrops torn down and rebuilt |
| `Thunderstorm_Finish` | as above | as above |
| `battle_util.c` overworld→battle | `B_WEATHER_RAIN_NORMAL` | **the weather is cosmetic** |
| `battle_main.c` Weather Ball | `TYPE_WATER` | Weather Ball stays Normal in rain |
| `pokemon.c` `IF_WEATHER` | rain-conditional evolutions | they never fire |
| `TranslateWeatherNum` | existing at all | nothing happens, silently |

Every one is silent and none is near the others. **Grep the weather you are
deriving from before writing anything** — `grep -rn WEATHER_DOWNPOUR src/`
is the entire map.

Some of those are `switch` labels and take a `case`. For the if-chains, add a
predicate (`IsWeatherRainy(weather)`) and use it, so the *next* one costs one
place instead of five. Note that `B_WEATHER_RAIN` already exists as a
battle-side aggregate — which is exactly why the missing overworld-side
predicate is easy to overlook.

Watch out for tables that are **declared and never read**: at least one weather
string table has no references anywhere, so it needs no entry and its absence
is not a bug.

## Read the row in `sWeatherFuncs`, not the name of the constant

`WEATHER_DOWNPOUR` sounds like the calm heavy rain — the thunderstorm is a
*different constant*. It is not. Its `sWeatherFuncs` row is
`{Downpour_InitVars, Thunderstorm_Main, Downpour_InitAll, Thunderstorm_Finish}`,
so it runs the full lightning cycle. The `isDownpour` flag gates only raindrop
sprite speed and angle; nothing in the bolt state machine reads it.
`WEATHER_RAIN` is the only stock rain without bolts, and it is also the
lightest.

So "heavy rain, no lightning" did not exist and had to be built. **The table
row is the truth; the constant name is a hint.**

## Deriving a new weather from an existing one

Often a whole new weather is one table row. Take an existing `InitVars` for the
look you want, and drive it with a different `Main`:

- The rain loops' first three states are numerically identical
  (`Rain_Main`'s 0/1/2 are `THUNDER_STATE_LOAD_RAIN`, `_CREATE_RAIN`,
  `_INIT_RAIN`), so they agree for exactly as long as there is rain to set up
  and part at state 3 — where one walks into the bolt cycle and the other falls
  off the end of its switch. Substituting one for the other gives you the heavy
  rain without the lightning, at the cost of one row.
- Sprite storage can be shared outright. Only one weather runs at a time, so
  another effect's sprite array is free while yours is up. One vanilla array is
  101 entries and the effect using it needs 20.

**Leaning on a coincidence like that state numbering is fine if it fails
loudly.** Inserting a state at the front of either enum breaks it visibly — the
rain never loads at all — rather than subtly.

## Decide explicitly whether it reaches battle

A new weather is **cosmetic until you put it in `battle_util.c`'s
overworld-to-battle switch.** That is a decision, not a default.

**And when your new weather replaces a mechanical one, the default is a
regression rather than a neutral omission.** If an area already ran on
`WEATHER_SNOW` — which is mechanical, giving Ice types 1.5× Defence — then
swapping part of it to a new snow variant that is *not* in that switch quietly
removes the boost. Ask what the area had before, not just what the new weather
should have.

A pleasant side effect of a distinct constant: switches that key on one
specific member still behave correctly. `B_THUNDERSTORM_TERRAIN` keys on
`WEATHER_RAIN_THUNDERSTORM` alone, so a lightning-free rain variant correctly
sets no Electric Terrain.

## Sprite motion: an oscillation has no net travel

Every falling weather in the game moves horizontally by writing `sprite->x2`
from `gSineTable` — one at `/64` is a 4-pixel shiver, another at `/16` a
16-pixel sway. **However wide you make it, it does not go anywhere.** If you
want driving snow or rain that crosses the screen, you must move `sprite->x`
itself and leave `x2` at zero: `x2` is applied at draw time and takes **no part
in the horizontal wrap test**, so a sprite carried out of frame on it never
comes back.

Two things fall out of moving `x` for real:

- **Accumulate the sub-pixel remainder, not the position.** The vertical axis
  uses a Q7 `tPos` accumulator, and copying that for x overflows: `sprite->x`
  is stored relative to `gSpriteCoordOffsetX`, which grows without bound as the
  camera scrolls, so `x * 128` in an `s16` will not survive a large map. Add
  whole pixels to `x` and keep only the fraction — the accumulator stays in
  0–127 forever and `x` remains the single authority the wrap can rewrite.
- **You need a vertical respawn that the original did not.** Wrapping sideways
  keeps a sprite alive indefinitely, so without one they all drift into the
  bottom band and the top of the screen empties. The original never has to
  think about this because its sprites leave downward almost immediately.

Also: **`InitAll` spinning its update loop is load-bearing.** It creates one
sprite per N counter ticks while updating all existing ones each iteration, so
the first sprite is updated a thousand times before the last is created — which
is what stops all of them arriving in a band across the top. Copy that
structure.

## Palettes

**Never put new colours in `PALTAG_WEATHER`.** It holds `gFogPalette` and is
shared by rain, snow, ash, bubbles and fog, so recolouring it repaints every
weather in the game.

The route is `PALTAG_WEATHER_2`, a lazily-allocated second slot filled by
`LoadCustomWeatherSpritePalette()` — which **clouds and sandstorm already use**,
so there is precedent to copy rather than plumbing to invent. It calls
`UpdateSpritePaletteWithWeather` itself, so the fade comes free. There is only
one such slot, so a `PALTAG_WEATHER_2` weather cannot coexist with clouds or
sandstorm — which never arises, since one weather runs at a time.

If your new weather reuses an existing effect's art, it needs no palette at
all: the existing `PALTAG_WEATHER` is already correct for it.

## Dead machinery is often the next effect's feature

`InitSnowflakeSpriteMovement` writes `tFallCounter`, `tFallDuration` and
`tDeltaY2` on every spawn and **nothing reads them**; `WaitSnowflakeSprite` is
`UNUSED`. A pause-and-resume cycle was built and left inert. Snow does not need
it — but a drifting petal does, and a thing that stalls, hangs and drops again
is most of what separates blossom from confetti falling at a constant rate.

**Before writing new sprite behaviour, look for the `UNUSED` function and the
fields nothing reads.**

## `WEATHER_SNOW` is not a stub

`constants/weather.h` marks it `// Unused` and no vanilla map sets it, but it
is fully wired: an entry in `sWeatherFuncs` with a complete init/main/finish
set, real art, and 16 sprites with two flake sizes, sine drift and screen wrap.
Only the pause-and-respawn cycle above was cut. It is usable as-is, and it is
mechanical in battle when `B_OVERWORLD_SNOW >= GEN_9`.
