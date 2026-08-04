"""Turn a gridded third-party tile sheet into a GBA secondary tileset.

Everything before this script could only READ tilesets. This one writes a whole
new one -- tiles.png, sixteen palettes, metatiles.bin and metatile_attributes.bin
-- from a sheet laid out as a grid of terrain blocks with an autotile legend.

Written for the Pokemon Mystery Dungeon: Red Rescue Team "Lapis Cave" sheet
(ripped and formatted by SilverDeoxys563, who asks only for optional credit),
but the sheet layout is a config entry, so a second sheet is a table addition.

WHAT MAKES IT NON-TRIVIAL

  * The sheet is 24x24 per cell and a GBA metatile is 16x16. Downscaled with
    BOX and re-quantised to the sheet's own palette, which keeps the colours
    exact -- a plain resize invents blends and blows the 15-colour budget.
  * A tile stores palette-relative indices, so two visually identical tiles
    under different palettes are NOT the same tile. Dedupe is keyed on
    (palette, pixels) for that reason.
  * Dedupe also folds x/y flips, because a metatile entry carries flip bits.
    On this sheet that is most of the saving.
  * Attributes are copied per block from a vanilla donor metatile rather than
    synthesised. See references/tilesets.md: attributes are per entry, and one
    shared attribute is the same shape of bug as a hard-coded per-area
    constant. The ground copies the cave floor's MB_CAVE so wild encounters
    fire; getting this wrong is silent until nothing spawns.

IDEMPOTENT, AND IT OWNS ITS DIRECTORY. It rewrites every output file from the
sheet each run, so nothing else may append to this tileset -- the same rule
any appender to a shared tileset needs, and for the same reason.

Usage:
    python import_tile_sheet.py lapis            # report only
    python import_tile_sheet.py lapis --write    # write the tileset
    python import_tile_sheet.py lapis --decls    # print the C declarations
"""
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from repo import REPO  # noqa: E402  (see repo.py)

NUM_TILES_IN_PRIMARY = 512      # secondary tiles are absolute 512..1023
NUM_PALS_IN_PRIMARY = 6         # secondary palettes land in slots 6..12
NUM_PALS_TOTAL = 13

# ---------------------------------------------------------------- sheet specs

# A SHEET is a source image, resolved relative to SHEETS_DIR (this script's
# `sheets/` by default, or $POKEDECOMP_SHEETS). Every rip SilverDeoxys563 has
# formatted shares one geometry, verified identical across all four here, so a
# new one is a one-line entry until a sheet turns up that disagrees.
#
# NO SHEETS ARE BUNDLED and these four will not resolve out of the box. They
# are ripped from a commercial game: the ripper's "credit appreciated" covers
# their formatting labour, not the publisher's copyright, so redistributing the
# images is not ours to do. The entries are kept because the CONFIG is the
# documentation - this is what a working import looks like - and because anyone
# holding the same rips can drop them in and run it. Supply your own and add an
# entry; SHEET_GEOMETRY below describes what the importer expects to find.
SHEETS_DIR = Path(os.environ.get('POKEDECOMP_SHEETS',
                                 Path(__file__).resolve().parent / 'sheets'))

SHEETS = {
    'lapis_cave': dict(source='lapis_cave.png'),
    'mt_freeze': dict(source='mt_freeze.png'),
    'howling_jungle': dict(source='howling_jungle.png'),
    'murky_cave': dict(source='murky_cave.png'),
}

SHEET_GEOMETRY = dict(
    origin=(8, 162),        # top-left of the first grid RULE, not the cell
    pitch=25,               # 24px cell + 1px rule
    cell=24,
    legend_col=0,           # three 3x3 masks per row, one per terrain cell
    background=(0, 128, 128),
    colorkey=(255, 0, 255),
)

# Each NAMED column on these sheets is three grid cells wide, and the Legend
# carries one 3x3 mask per cell, so a block is addressed by the first of its
# three. The Alt groups hold a single cell each on both sheets - they are
# variants of the plain fill, not autotile cases.
COL = dict(walls=3, wall_alt1=6, wall_alt2=9,
           ground=12, ground_alt1=15, ground_alt2=18, water=21)

# A TILESET is what gets written. Blocks may come from DIFFERENT sheets, and
# blocks sharing a palette slot are quantised together against one palette.
#
# THE ORDER HERE IS THE METATILE ORDER, and metatile ids are what your own
# tables name, so appending a block is safe and reordering one is not.
TILESETS = {
    # TWO SHEETS, ONE TILESET: Lapis Cave's crystal walls over Mt. Freeze's
    # snow, because neither sheet has both and the area wanted a snowy floor
    # under crystal walls. This is the entry to read first - it exercises
    # multi-sheet composition, shared-palette quantisation and a drawn
    # descent, which is most of what the format can do.
    'lapis': dict(
        out='data/tilesets/secondary/rogue_lapis_cave',
        symbol='RogueLapisCave',
        prefix='LAPIS',
        blocks=[
            # attr is behaviour+layer type copied from a vanilla donor metatile
            # rather than synthesised - see the module docstring. 0x0008 is cave
            # 0x201: MB_CAVE, layer NORMAL, so wild encounters fire.
            dict(name='wall', sheet='lapis_cave', col=COL['walls'], pal=6, attr=0x0008),
            dict(name='ground', sheet='mt_freeze', col=COL['ground'], pal=7, attr=0x0008),
            # The decor variants MUST carry the ground's attribute, not a bare
            # one: they replace floor blocks in place, and a decorated block
            # with no encounter flag would be a dead spot the player cannot see.
            dict(name='decor1', sheet='mt_freeze', col=COL['ground_alt1'], pal=7, attr=0x0008),
            dict(name='decor2', sheet='mt_freeze', col=COL['ground_alt2'], pal=7, attr=0x0008),
            # Never actually painted - kept because it is what the sheet has,
            # and dropping it would move every metatile id after it.
            dict(name='water', sheet='lapis_cave', col=COL['water'], pal=8, attr=0x0008),
            # A crack in the ice. Drawn in slot 7, the snow, so the corners are
            # the snowfield itself - but snow has NO dark tone at all (157 to
            # 240 luminance), so the mouth and the rim are appended out of
            # palette 6 and the well is lit like the crystal walls it cuts into.
            # 0x0000 is MB_NORMAL, the same attribute the woods stairs carry:
            # the descent triggers on metatile id, and the tile it replaces
            # carried no encounters either.
            dict(name='stairs', pal=7, attr=0x0000, stairs=dict(
                rounded=True,
                append=[(0x00, 0x39, 0x52), (0x00, 0x6B, 0xF7)],
                roles=dict(d=(0x00, 0x39, 0x52), t=(0x84, 0xC6, 0xEF),
                           e=(0xDE, 0xF7, 0xF7), r=(0x00, 0x6B, 0xF7),
                           R=(0x63, 0xAD, 0xE7)))),
        ]),

    # WHY IMPORT AT ALL: this area was built almost entirely out of
    # gTileset_General - plain grass, vanilla canopy, vanilla puddles - and read
    # as a Route rather than a jungle, because that is literally what its art
    # is. Its whole wall table was TWO metatiles, canopy and
    # canopy-with-a-base-row, so a wall mass had no silhouette at all. A sheet
    # with a legend supplies the entire wall vocabulary in one import.
    #
    # Water is deliberately NOT imported yet. The sheet ships it as two columns
    # at two animation rates - the water at 14 frames and a separate, 98%
    # transparent Sparkle overlay at 6 - which needs top-layer compositing and
    # tileset animation that this importer does not do. Walls and ground first.
    'jungle': dict(
        out='data/tilesets/secondary/rogue_howling_jungle',
        symbol='RogueHowlingJungle',
        prefix='JUNGLE',
        blocks=[
            # 0x0008 is cave 0x201: MB_CAVE, layer NORMAL.
            dict(name='wall', sheet='howling_jungle', col=COL['walls'], pal=6, attr=0x0008),
            # Wall Alt 2 costs NOTHING: walls alone need 14 colours and walls
            # plus this need 14, so it is scatter for free. Wall Alt 1 is the
            # flowered set and needs 17 - over the 4bpp limit - so it is left
            # out rather than given a slot of its own for five cells.
            dict(name='walldecor', sheet='howling_jungle', col=COL['wall_alt2'],
                 pal=6, attr=0x0008, varies='wall'),
            # 0x0000 is General 0x001, the plain route grass this floor
            # replaces: MB_NORMAL, so it carries NO encounters. That is the
            # jungle's design and predates the art swap - encounters come from
            # the long grass layer, the way they do in the woods, and the ground
            # is somewhere safe to cross. The cave's 0x0008 would have been the
            # obvious copy-paste and would have silently turned wild battles on
            # across the whole floor.
            dict(name='ground', sheet='howling_jungle', col=COL['ground'], pal=7, attr=0x0000),
            # Ground plus both variants is EXACTLY 15 colours - the 4bpp limit,
            # with no headroom at all. Anything else wanting slot 7 has to
            # displace one of these. They take the ground's attribute, not a
            # bare one, for the same reason Lapis' decor takes its ground's: a
            # decor block that disagrees with the floor it replaces is a patch
            # of different rules wearing the same paint.
            dict(name='decor1', sheet='howling_jungle', col=COL['ground_alt1'],
                 pal=7, attr=0x0000, varies='ground'),
            dict(name='decor2', sheet='howling_jungle', col=COL['ground_alt2'],
                 pal=7, attr=0x0000, varies='ground'),
            # 0x16 is MB_PUDDLE, and it is chosen rather than inherited. It is
            # in MetatileBehavior_IsReflective, so the player REFLECTS in it for
            # free, and its tile flags are TILE_FLAG_UNUSED alone - walkable,
            # NOT surfable, no encounters. MB_POND_WATER would also reflect but
            # is SURFABLE|HAS_ENCOUNTERS, which would put a water encounter
            # surface on an area whose long grass is a land one, and an area
            # may only feed one encounter branch.
            #
            # autotile: this block gets the same nine-mask treatment the walls
            # do, because it is laid as a patch region and needs its own edges.
            dict(name='water', sheet='howling_jungle', col=COL['water'],
                 pal=8, attr=0x0016, autotile=True, over='ground'),
            # The Sparkle column is still not imported - 98% transparent, a
            # different animation rate, and the user does not want it.
            #
            # Long grass, grafted from vanilla and recoloured into THIS tileset:
            # blades out of the wall palette so they are the same greens as the
            # foliage, ground out of the dirt palette so the fringe band reads
            # as dirt rather than as the route grass it was drawn against.
            dict(name='grass', graft='vanilla_long_grass', pal=9,
                 blades_from=6, ground_from=7),
            # A hollow dug under the roots - and drawn in slot 9, the long
            # grass, which is neither the floor it sits in nor the walls above
            # it. Both of those were tried and neither works: DIRT (slot 7) runs
            # 70 to 169 luminance and has no dark, so the void came out lighter
            # than the floor and the stairs read as a plate lying on the ground;
            # FOLIAGE (slot 6) reaches luminance 58 at #006300, dark enough on
            # paper, but it is a saturated green and reads as paint rather than
            # as shadow. Darkness is not only a luminance.
            #
            # Slot 9 is vanilla's palette 2 with two ramps swapped by the graft,
            # so it still carries #413931 - the exact colour the woods stairs
            # use for their void - and vanilla's tan ramp above it. The jungle's
            # descent is therefore the woods' descent in the woods' own tones,
            # which is the right echo: both are holes dug in forest floor.
            dict(name='stairs', pal=9, attr=0x0000, stairs=dict(
                rounded=True,
                roles=dict(d=(0x41, 0x39, 0x31), t=(0xDE, 0x94, 0x73),
                           e=(0xFF, 0xC5, 0x94), r=(0x5A, 0x4A, 0x21),
                           R=(0x94, 0x73, 0x31)))),
        ]),

    # A third sheet, imported the same way. Carved pillars and ochre rubble,
    # which is the only
    # sheet of the four that reads as somewhere BUILT rather than somewhere
    # grown, and the right note to end a run on.
    #
    # Its Ground Alt columns are named differently - "Ground Alt" and "Unused
    # Ground" rather than Alt 1 and Alt 2 - but they sit at the same grid
    # columns, so COL still addresses them. The second is art the original game
    # never used, which costs nothing to put back.
    'murky': dict(
        out='data/tilesets/secondary/rogue_murky_cave',
        symbol='RogueMurkyCave',
        prefix='MURKY',
        blocks=[
            # SEVENTEEN colours before reduction, the first block on any sheet
            # that does not fit 4bpp. Both wall Alt columns are free on top of
            # that - they add no colour the walls do not already have.
            dict(name='wall', sheet='murky_cave', col=COL['walls'], pal=6, attr=0x0008),
            dict(name='walldecor1', sheet='murky_cave', col=COL['wall_alt1'],
                 pal=6, attr=0x0008, varies='wall'),
            dict(name='walldecor2', sheet='murky_cave', col=COL['wall_alt2'],
                 pal=6, attr=0x0008, varies='wall'),
            # MB_CAVE here, unlike the jungle: this is a cave, and a cave's
            # floor is its encounter surface. There is no grass layer to take
            # that job, the way there is in the woods and the jungle.
            dict(name='ground', sheet='murky_cave', col=COL['ground'], pal=7, attr=0x0008),
            dict(name='decor1', sheet='murky_cave', col=COL['ground_alt1'],
                 pal=7, attr=0x0008, varies='ground'),
            dict(name='decor2', sheet='murky_cave', col=COL['ground_alt2'],
                 pal=7, attr=0x0008, varies='ground'),
            # MB_PUDDLE again: reflective, walkable, and off the water branch.
            dict(name='water', sheet='murky_cave', col=COL['water'],
                 pal=8, attr=0x0016, autotile=True, over='ground'),
            # THE ONE THAT IS CUT. Not rounded: it runs square to the tile edge
            # with no floor showing at any corner, because this is the only one
            # of the three tilesets that reads as somewhere BUILT, and a
            # stairwell in a built place was made rather than opened. Its own
            # floor stone has the full ramp needed - 46 to 215 luminance - so it
            # needs nothing appended and nothing borrowed.
            dict(name='stairs', pal=7, attr=0x0000, stairs=dict(
                rounded=False,
                roles=dict(d=(0x4A, 0x29, 0x00), t=(0xCE, 0xAD, 0x4A),
                           e=(0xEF, 0xDE, 0x73), r=(0x6B, 0x4A, 0x00),
                           R=(0x73, 0x6B, 0x00)))),
        ]),
}

# our PaintWalls slots, as neighbour masks. '#' wall, 'o' floor, '.' don't care
SLOTS = {
    'INTERIOR_MID':    ['###', '###', '###'],
    'INTERIOR_LEFT':   ['.##', 'o##', '.##'],
    'INTERIOR_RIGHT':  ['##.', '##o', '##.'],
    'FACE_MID':        ['###', '###', 'ooo'],
    'FACE_LEFT':       ['.##', 'o##', 'oo.'],
    'FACE_RIGHT':      ['##.', '##o', '.oo'],
    'NORTH_MID':       ['ooo', '###', '###'],
    'NORTH_LEFT':      ['oo.', 'o##', '.##'],
    'NORTH_RIGHT':     ['.oo', '##o', '##.'],
    'CORNER_OPEN_SE':  ['###', '###', '##o'],
    'CORNER_OPEN_SW':  ['###', '###', 'o##'],
    'CORNER_OPEN_NW':  ['o##', '###', '###'],
    'CORNER_OPEN_NE':  ['##o', '###', '###'],
    'SLIVER_VERT':     ['.#.', 'o#o', '.#.'],
    'SLIVER_HORZ':     ['.o.', '###', '.o.'],
    'SLIVER_VERT_TOP': ['.o.', 'o#o', '.#.'],
    'SLIVER_VERT_BOT': ['.#.', 'o#o', '.o.'],
    'SLIVER_HORZ_L':   ['.o.', 'o##', '.o.'],
    'SLIVER_HORZ_R':   ['.o.', '##o', '.o.'],
    'SLIVER_ISOLATED': ['.o.', 'o#o', '.o.'],
}


# ---------------------------------------------------------------- sheet reading

class Sheet:
    def __init__(self, spec):
        self.spec = spec
        path = SHEETS_DIR / spec['source']
        if not path.exists():
            raise SystemExit(
                f"sheet not found: {path}\n"
                f"No sheets ship with this toolset - see the note by SHEETS. "
                f"Put yours in {SHEETS_DIR} or set POKEDECOMP_SHEETS.")
        self.img = np.asarray(Image.open(path).convert('RGB'))
        self.bg = np.array(spec['background'])
        self.key = np.array(spec['colorkey'])
        ox, oy = spec['origin']
        p, c = spec['pitch'], spec['cell']
        self.xs = list(range(ox, self.img.shape[1] - c, p))
        self.ys = list(range(oy, self.img.shape[0] - c, p))
        self.cellsz = c

    def cell(self, cx, cy):
        x, y = self.xs[cx] + 1, self.ys[cy] + 1
        return self.img[y:y + self.cellsz, x:x + self.cellsz]

    def filled(self, cx, cy):
        c = self.cell(cx, cy)
        if c.shape[0] < self.cellsz or c.shape[1] < self.cellsz:
            return False
        bg = (np.abs(c - self.bg).sum(axis=2) < 30).mean()
        mg = (np.abs(c - self.key).sum(axis=2) < 30).mean()
        return 1 - bg - mg > 0.5

    def mask(self, row, k):
        """3x3 neighbour mask for terrain cell k of this row.

        Sheet convention, verified against cells whose art was already known:
        black = SAME terrain, teal = DIFFERENT terrain (not "don't care"),
        white = the centre marker. So all eight neighbours are specified.
        """
        x0 = self.xs[self.spec['legend_col']] + 1 + k * self.cellsz
        y0 = self.ys[row] + 1
        refs = (('#', np.array([0, 0, 0])), ('o', np.array([255, 255, 255])),
                ('.', self.bg))
        out = []
        for by in range(3):
            line = ''
            for bx in range(3):
                blk = self.img[y0 + by * 8:y0 + by * 8 + 8, x0 + bx * 8:x0 + bx * 8 + 8]
                if blk.size == 0:
                    line += '?'
                    continue
                line += min(refs, key=lambda r: np.abs(blk.astype(int) - r[1])
                            .sum(axis=2).mean())[0]
            out.append(line)
        return out


def match_slot(sheet_mask, want):
    score = 0
    for r in range(3):
        for c in range(3):
            if r == 1 and c == 1:
                continue
            w = want[r][c]
            if w == '.':
                continue
            if (sheet_mask[r][c] == '#') != (w == '#'):
                return None
            score += 1
    return score


# ---------------------------------------------------------------- conversion

def block_palette(cells, key, bg, label='', verbose=False):
    """Colour list for a block, from the ORIGINAL cells, reduced to fit 4bpp.

    Murky Cave's walls are the first block on any sheet to want more than the
    fifteen a 4bpp palette has - seventeen - so a palette that does not fit is a
    thing to SOLVE rather than to refuse.

    Reduction merges the pair minimising `distance * min(count)` - an estimate
    of the pixel error the merge introduces - and repeats. Ranking by error
    rather than by rarity alone is the point: a rare colour that is far from
    everything else is exactly the one worth keeping, because being far from
    everything else is what makes it a different colour rather than a shade.

    On Murky Cave's walls that costs one near-duplicate brown (distance 16, 187
    pixels) and then folds the two mossy greens together (distance 50). The
    greens are 0.5% of the block each and rarity alone would have deleted one
    outright; merging them keeps the moss and loses only a shade of it, which is
    the trade the weighting is there to make. Anything reduced is REPORTED, so
    art quietly losing a colour is never silent.
    """
    px = np.concatenate([c.reshape(-1, 3) for c in cells])
    px = px[np.abs(px - key).sum(axis=1) > 30]
    px = px[np.abs(px - bg).sum(axis=1) > 30]
    u, counts = np.unique(px, axis=0, return_counts=True)
    u, counts = u.astype(int), counts.astype(int)

    while len(u) > 15:
        best = None
        for i in range(len(u)):
            for j in range(i + 1, len(u)):
                dist = int(np.abs(u[i] - u[j]).sum())
                cost = dist * int(min(counts[i], counts[j]))
                if best is None or cost < best[0]:
                    best = (cost, dist, i, j)
        _, dist, i, j = best
        keep, drop = (i, j) if counts[i] >= counts[j] else (j, i)
        if verbose:
            a = tuple(int(v) for v in u[drop])
            b = tuple(int(v) for v in u[keep])
            print(f'    {label}: merged {a} x{int(counts[drop])} into '
                  f'{b} x{int(counts[keep])}  (distance {dist})')
        counts[keep] += counts[drop]
        u = np.delete(u, drop, axis=0)
        counts = np.delete(counts, drop)

    order = np.argsort(-counts)                     # commonest first
    return [tuple(int(v) for v in c) for c in u[order]]


def to_indices(cell24, palette, key, bg):
    """24x24 RGB -> 16x16 palette indices. Index 0 is transparent.

    TRANSPARENCY IS DECIDED AT SOURCE RESOLUTION and the mask downscaled, not
    the other way round. Testing the blended 16x16 for background colour looks
    equivalent and is not: BOX averaging two of the jungle water's dark teals -
    (0,99,107) and (8,115,140) - lands on (4,107,123), which is 30 away from the
    sheet's own (0,128,128) background and so was being read as a hole. The
    result was a dotted line of BLACK PIXELS along every water bank, from art
    that has no transparency there at all.

    A blend cannot be transparent, because transparency is not a colour. Only a
    pixel that was mostly hole in the source is one.
    """
    small = np.asarray(Image.fromarray(cell24).resize((16, 16), Image.BOX), dtype=int)
    pal = np.array(palette, dtype=int)
    flat = small.reshape(-1, 3)
    # nearest palette entry, so BOX blending cannot invent a colour
    d = np.abs(flat[:, None, :] - pal[None, :, :]).sum(axis=2)
    idx = d.argmin(axis=1) + 1                      # +1: 0 stays transparent

    src = cell24.astype(int)
    hole = ((np.abs(src - key).sum(axis=2) < 30)
            | (np.abs(src - bg).sum(axis=2) < 30)).astype(np.uint8) * 255
    # majority vote over the 1.5x1.5 source area each output pixel covers
    hole16 = np.asarray(Image.fromarray(hole).resize((16, 16), Image.BOX)) > 127
    idx[hole16.reshape(-1)] = 0
    return idx.reshape(16, 16).astype(np.uint8)


# ---------------------------------------------------------------- grafts
#
# Art that is on no sheet, assembled from VANILLA tiles and given a palette of
# this tileset's own. The point is section 5's palette-only trick: a tile stores
# palette-RELATIVE indices, so copying vanilla pixels verbatim and pointing them
# at different colours is a recolour with no pixel work at all.

def _tile_reader(png):
    """8x8 palette-index tiles out of a 4bpp tileset PNG, by tile number."""
    a = np.asarray(Image.open(REPO / png).convert('P'), dtype=np.uint8)
    per_row = a.shape[1] // 8

    def get(i):
        y, x = (i // per_row) * 8, (i % per_row) * 8
        return a[y:y + 8, x:x + 8]
    return get


def _quad(get, ids):
    """Four tile numbers, NW NE SW SE, into one 16x16 index block."""
    tl, tr, bl, br = (get(i) for i in ids)
    return np.vstack([np.hstack([tl, tr]), np.hstack([bl, br])])


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _ramp(palette, want, pick):
    """`want` colours out of `palette`, matching `pick`, spread over its range.

    Ranked by luminance and sampled evenly rather than nearest-matched, because
    what has to survive the recolour is the ORDER - a blade ramp that stops
    descending stops reading as blades.
    """
    cand = sorted([c for c in palette if pick(c)], key=_lum, reverse=True)
    if len(cand) < want:
        cand = sorted(palette, key=_lum, reverse=True)
    if len(cand) <= want:
        return cand + [cand[-1]] * (want - len(cand))
    step = (len(cand) - 1) / (want - 1) if want > 1 else 0
    return [cand[round(i * step)] for i in range(want)]


# Vanilla palette-2 indices, split by what they draw. Established by dumping the
# tiles: the blades never use a ground index and the ground band never uses a
# blade one, which is the whole reason this can be done with a palette.
GRASS_BLADE_IDX = [1, 2, 3, 4]     # lightest to darkest
GRASS_GROUND_IDX = [13, 14, 15]    # lightest to darkest


def graft_long_grass(palettes, cfg):
    """Vanilla long grass and its south fringe, recoloured onto this tileset.

    The fringe is the reason this graft exists. 0x208 was the ONLY
    MB_LONG_GRASS_SOUTH_EDGE metatile in the game, it lived in gTileset_Fortree,
    and its lower band is drawn as route grass - so an area that leaves Fortree
    loses its only long-grass edge, and an area standing on dirt would not want
    that band even if it kept it.
    """
    gen = _tile_reader('data/tilesets/primary/general/tiles.png')
    fortree = _tile_reader('data/tilesets/secondary/fortree/tiles.png')

    blades = _ramp(palettes[cfg['blades_from']], len(GRASS_BLADE_IDX),
                   lambda c: c[1] > c[0] and c[1] > c[2])
    ground = _ramp(palettes[cfg['ground_from']], len(GRASS_GROUND_IDX),
                   lambda c: c[0] >= c[1] > c[2])

    # Start from vanilla's own palette so untouched indices stay sane, then
    # overwrite only the two ramps the grass actually draws with.
    src = (REPO / 'data/tilesets/primary/general/palettes/02.pal').read_text()
    vanilla = [tuple(int(v) for v in line.split())
               for line in src.splitlines()[4:19]]
    pal = list(vanilla)
    for i, c in zip(GRASS_BLADE_IDX, blades):
        pal[i - 1] = c
    for i, c in zip(GRASS_GROUND_IDX, ground):
        pal[i - 1] = c

    return dict(palette=pal, units=[
        # MB_LONG_GRASS. The ground showing between the blades is the same three
        # indices the fringe uses for its band, so it turns to dirt with them.
        ('grass', _quad(gen, [0x012, 0x013, 0x022, 0x023]), 0x0003),
        # MB_LONG_GRASS_SOUTH_EDGE, carrying no encounters, exactly as vanilla.
        ('fringe', _quad(fortree, [0x10A, 0x10B, 0x11A, 0x11B]), 0x0009),
    ])


GRAFTS = {'vanilla_long_grass': graft_long_grass}


# ---------------------------------------------------------------- stairs
#
# The descent, drawn instead of borrowed. Lapis, the jungle and Murky Cave all
# fell back on gTileset_General's warp 0x0A7 - a PRIMARY id, so it survives any
# secondary, which is exactly why it was reached for three times. It is vanilla
# grey rock, and none of these three tilesets contains a grey.
#
# The whirlpool's rule applies again, and for the same reason: SHARE THE
# GEOMETRY, NEVER THE PALETTE. The exit is the one thing on a floor the player
# is hunting for, so all three are the same skeleton and the same step rhythm -
# but each is cut out of its own area's material, because a descent reads as
# belonging to a place only when it is made of that place.

def stairs_rows(rounded):
    """The 16 rows of a descent, as roles.

    Structure taken row for row from the woods stairs (`make_woods_stairs.py`),
    the one drawn descent in this project that already reads, and it is worth
    saying WHY it reads, because the first attempt here ignored all of it and
    came out as a framed rectangle lying on the floor:

      * THE RISER IS THE VOID, not a darker shade of the tread. What separates
        two steps is darkness. A mid-tone riser flattens the whole thing.
      * Each tread sits inside the void with a two-pixel margin either side, so
        the well has depth at its edges instead of butting against the rim.
      * A step is (void, tread, tread, lit edge) in that order, so the run ends
        on a lit edge - the tread nearest the player - and the dark always sits
        above the thing it shadows.
      * Two rim rows, not one: an outer that meets the floor and a darker inner
        that turns the corner into the well.

    `rounded` opens the four corners back up to the floor, which is what seats
    an opening into the ground instead of butting against it. Murky Cave is the
    one that does NOT: it is the only tileset here that reads as somewhere
    BUILT, so its descent is cut square and runs to the tile edge.

      d void   t tread   e lit leading edge   r inner rim   R outer rim
      .        the floor underneath shows through
    """
    o = '.' if rounded else 'R'
    rows = [f'{o}{o}R' + 'r' * 10 + f'R{o}{o}',
            f'{o}Rr' + 'd' * 10 + f'rR{o}']
    for _ in range(3):
        rows += ['r' + 'd' * 14 + 'r',
                 'r' + 'dd' + 't' * 10 + 'dd' + 'r',
                 'r' + 'dd' + 't' * 10 + 'dd' + 'r',
                 'r' + 'dd' + 'e' * 10 + 'dd' + 'r']
    rows += [f'{o}Rr' + 'd' * 10 + f'rR{o}',
             f'{o}{o}R' + 'r' * 10 + f'R{o}{o}']
    assert len(rows) == 16 and all(len(r) == 16 for r in rows)
    return rows


def draw_stairs(palettes, cfg, floor_cell, key, bg):
    """One stairs metatile, in this tileset's own colours.

    Every role colour must ALREADY be in the palette it names, and this raises
    if one is not - the check is the point. A stairs metatile is one of exactly
    two things in an area the player has to be able to find, so it must not be
    possible to bind it to a colour that merely quantises nearby.

    `append` is the exception, and Lapis is why it exists. Its snow palette runs
    157 to 240 luminance - it has no dark whatsoever - so a mouth cannot be
    drawn in it at all. The two colours it appends are lifted verbatim out of
    palette 6, the crystal walls, so the stairwell is lit by the same rock the
    walls are and nothing new is invented. Appending is safe because it only
    ever adds to the END of a palette: the colours already there keep their
    indices, so every block already quantised against this slot is untouched.
    """
    spec = cfg['stairs']
    pal = list(palettes[cfg['pal']])
    for c in spec.get('append', ()):
        if c in pal:
            continue
        if len(pal) >= 15:
            raise SystemExit(f'stairs: palette {cfg["pal"]} is full, '
                             f'cannot append {c}')
        pal.append(c)

    def index_of(rgb):
        if rgb not in pal:
            raise SystemExit(f'stairs: {rgb} is not in palette {cfg["pal"]}')
        return pal.index(rgb) + 1          # 0 is transparent

    roles = {k: index_of(v) for k, v in spec['roles'].items()}

    # The floor showing at the corners has to be expressed in the palette the
    # STAIRS are drawn in, which is not always the one the floor itself was
    # quantised into - the jungle draws in slot 9 over a slot 7 floor. Running
    # the plain fill back through to_indices against this palette is the whole
    # of it, and it is a no-op where the two agree.
    canvas = to_indices(floor_cell, pal, key, bg)
    for y, row in enumerate(stairs_rows(spec['rounded'])):
        for x, ch in enumerate(row):
            if ch != '.':
                canvas[y, x] = roles[ch]

    return dict(palette=pal, units=[('stairs', canvas, cfg['attr'])])


def drawn(b):
    """A block whose art is generated rather than read off a sheet."""
    return 'graft' in b or 'stairs' in b


class TileBank:
    """8x8 tiles, deduped per palette and across x/y flips."""

    def __init__(self):
        self.tiles = []                 # list of 8x8 uint8
        self.index = {}                 # (pal, bytes) -> (local index, xflip, yflip)

    def add(self, tile, pal):
        for xf in (0, 1):
            for yf in (0, 1):
                v = tile
                if xf:
                    v = v[:, ::-1]
                if yf:
                    v = v[::-1, :]
                hit = self.index.get((pal, v.tobytes()))
                if hit is not None:
                    # stored orientation -> ours needs the same flips back
                    return hit[0], xf, yf
        i = len(self.tiles)
        self.tiles.append(tile)
        self.index[(pal, tile.tobytes())] = (i, 0, 0)
        return i, 0, 0


def convert(ts, verbose=True):
    cache = {}

    def sheet(name):
        if name not in cache:
            cache[name] = Sheet({**SHEET_GEOMETRY, **SHEETS[name]})
        return cache[name]

    def plain_fill(b):
        """The cell of a block whose legend says every neighbour is the same."""
        sh = b['sh']
        for (r, k, cell) in b['cells']:
            m = sh.mask(r, k)
            if all(ch == '#' for j, row in enumerate(m)
                   for i, ch in enumerate(row) if not (i == 1 and j == 1)):
                return cell
        return None

    blocks = []
    for b in ts['blocks']:
        if drawn(b):
            blocks.append({**b, 'sh': None, 'cells': []})
            continue
        sh = sheet(b['sheet'])
        cells = [(r, k, sh.cell(b['col'] + k, r))
                 for r in range(len(sh.ys))
                 for k in range(3)
                 if b['col'] + k < len(sh.xs) and sh.filled(b['col'] + k, r)]

        # `over` flattens a block onto another block's plain fill BEFORE any
        # colour is extracted. These sheets draw a terrain's EDGE cells with
        # transparent corners, meant to be composited over whatever the terrain
        # borders - the sheets say so outright: "When Ground is adjacent to
        # Water, treat Water as though it were a Ground tile."
        #
        # A GBA metatile could do that with its top layer over a ground bottom
        # layer, and eventually should. Flattening here costs one thing and buys
        # two: the cost is that the composite is baked, so this water can only
        # ever border dirt; the gain is that it stays a one-layer metatile, with
        # no layer-type question about whether the player walks over or under.
        # Left unflattened, those corners are index 0 and render as BLACK
        # SPECKLES along every bank.
        if 'over' in b:
            base = plain_fill(next(x for x in blocks if x['name'] == b['over']))
            key, bg = sh.key, sh.bg
            flat = []
            for (r, k, cell) in cells:
                hole = ((np.abs(cell - key).sum(axis=2) < 30)
                        | (np.abs(cell - bg).sum(axis=2) < 30))
                merged = cell.copy()
                merged[hole] = base[hole]
                flat.append((r, k, merged))
            cells = flat

        blocks.append({**b, 'sh': sh, 'cells': cells})
        if verbose:
            print(f'  {b["name"]:<7} {len(cells):3d} cells  from {b["sheet"]:<11}'
                  f' palette slot {b["pal"]}')

    # Blocks sharing a palette slot share ONE palette, quantised from all their
    # cells together. The ground and its two decor variants are the case that
    # needs it: a tileset has one palette per slot, so quantising them apart
    # would give slot 7 whichever was written last and silently recolour the
    # other two. It also means the 15-colour budget is per SLOT, not per block.
    palettes = {}
    for b in blocks:
        if drawn(b):
            continue
        palettes.setdefault(b['pal'], []).extend(c for _, _, c in b['cells'])
    for slot in sorted(palettes):
        owner = next(b for b in blocks if b['pal'] == slot and not drawn(b))
        names = '+'.join(b['name'] for b in blocks
                         if b['pal'] == slot and not drawn(b))
        raw = len({tuple(int(v) for v in p)
                   for c in palettes[slot] for p in c.reshape(-1, 3)})
        palettes[slot] = block_palette(palettes[slot], owner['sh'].key,
                                       owner['sh'].bg, names, verbose)
        if verbose:
            note = f'   REDUCED from {raw - 2}' if raw - 2 > 15 else ''
            print(f'  palette {slot}  {len(palettes[slot]):2d} colours  ({names}){note}')

    # Grafts run AFTER the sheet palettes exist, because that is what they draw
    # their colours out of - the whole point is that grafted art is recoloured
    # into the tileset it is joining rather than carrying its own look in.
    # Stairs run here too, and for the same reason - they are cut out of the
    # area's own colours. They come last in the block list so that (a) their
    # metatile lands after every id your tables already name, and (b) the
    # jungle's, which draw in slot 9, see the palette the long-grass graft put
    # there rather than the one it replaced.
    for b in blocks:
        if 'graft' in b:
            b['graft_out'] = GRAFTS[b['graft']](palettes, b)
            note = 'grafted      from vanilla '
        elif 'stairs' in b:
            under = next(x for x in blocks
                         if x['name'] == b['stairs'].get('under', 'ground'))
            fill = plain_fill(under)
            if fill is None:
                raise SystemExit(f'stairs: {under["name"]} has no plain fill to '
                                 f'seat the corners in')
            b['graft_out'] = draw_stairs(palettes, b, fill,
                                         under['sh'].key, under['sh'].bg)
            note = f'drawn        over {under["name"]:<7}'
        else:
            continue
        palettes[b['pal']] = b['graft_out']['palette']
        if verbose:
            print(f'  {b["name"]:<7} {len(b["graft_out"]["units"]):3d} {note}'
                  f'  palette slot {b["pal"]}')

    bank = TileBank()
    metatiles = []
    for b in blocks:
        # A sheet block yields 24x24 RGB cells that have to be quantised; a
        # graft yields 16x16 index blocks already. Past this point they are the
        # same thing, so everything downstream sees one kind of metatile.
        if 'graft_out' in b:
            units = [(i, 0, idx, attr) for i, (_, idx, attr)
                     in enumerate(b['graft_out']['units'])]
        else:
            units = [(r, k, to_indices(cell, palettes[b['pal']],
                                       b['sh'].key, b['sh'].bg), b['attr'])
                     for (r, k, cell) in b['cells']]

        for (r, k, idx, attr) in units:
            entries = []
            for qy in (0, 1):
                for qx in (0, 1):
                    t = idx[qy * 8:qy * 8 + 8, qx * 8:qx * 8 + 8]
                    ti, xf, yf = bank.add(t, b['pal'])
                    entries.append((NUM_TILES_IN_PRIMARY + ti)
                                   | (xf << 10) | (yf << 11) | (b['pal'] << 12))
            metatiles.append(dict(block=b['name'], attr=attr, sh=b['sh'],
                                  row=r, k=k, entries=entries))

    # slot -> metatile local index, from the legend of the block's OWN sheet.
    # Any block may ask for this, not just the walls: a water body laid as a
    # patch region needs the same nine masks under different names.
    def autotile_of(block):
        out = {}
        for slot, want in SLOTS.items():
            best = None
            for li, mt in enumerate(metatiles):
                if mt['block'] != block or mt['sh'] is None:
                    continue
                s = match_slot(mt['sh'].mask(mt['row'], mt['k']), want)
                if s is not None and (best is None or s > best[0]):
                    best = (s, li)
            if best:
                out[slot] = best[1]
        return out

    slotmap = autotile_of('wall')
    autotiles = {b['name']: autotile_of(b['name'])
                 for b in blocks if b.get('autotile')}

    # the plain floor: ground fully surrounded by ground
    floor_li = None
    for li, mt in enumerate(metatiles):
        if mt['block'] == 'ground' and all(
                ch == '#' for j, row in enumerate(mt['sh'].mask(mt['row'], mt['k']))
                for i, ch in enumerate(row) if not (i == 1 and j == 1)):
            floor_li = li
            break

    # A block declaring `varies` is a column of alternates for another block,
    # and the sheet pairs them BY CELL POSITION: an alt at (row, k) is a variant
    # of whatever the base block draws at the same (row, k), because that is the
    # same legend mask - the same autotile case. Pairing on position rather than
    # on order is what makes an Alt column with holes in it safe.
    #
    # This is what feeds struct RogueDecor, whose first field is the metatile to
    # look for and whose rest are what to draw instead.
    where = {}
    for li, mt in enumerate(metatiles):
        where[(mt['block'], mt['row'], mt['k'])] = li
    decor = []
    for b in blocks:
        if 'varies' not in b:
            continue
        for (r, k, _) in b['cells']:
            base = where.get((b['varies'], r, k))
            alt = where[(b['name'], r, k)]
            if base is None:
                print(f'  WARNING: {b["name"]} at row {r} k {k} varies nothing '
                      f'in {b["varies"]} - dropped')
                continue
            decor.append((b['name'], base, alt))

    # Grafted units are named rather than autotiled, so they are addressed by
    # the label the graft gave them.
    grafted = {}
    for b in blocks:
        if 'graft_out' not in b:
            continue
        for i, (label, _, _) in enumerate(b['graft_out']['units']):
            grafted[label] = next(li for li, mt in enumerate(metatiles)
                                  if mt['block'] == b['name'] and mt['row'] == i)

    return dict(blocks=blocks, palettes=palettes, bank=bank, metatiles=metatiles,
                slotmap=slotmap, autotiles=autotiles, grafted=grafted,
                floor=floor_li, decor=decor)


# ---------------------------------------------------------------- writing

def write_tileset(spec, conv):
    out = REPO / spec['out']
    (out / 'palettes').mkdir(parents=True, exist_ok=True)

    # ---- tiles.png : 16 tiles per row, indices are palette-relative
    tiles = conv['bank'].tiles
    rows = (len(tiles) + 15) // 16
    sheet = np.zeros((rows * 8, 16 * 8), dtype=np.uint8)
    for i, t in enumerate(tiles):
        y, x = (i // 16) * 8, (i % 16) * 8
        sheet[y:y + 8, x:x + 8] = t
    img = Image.fromarray(sheet, mode='P')
    # the PNG carries one palette for humans; every tile stores raw indices, so
    # tiles on the other palettes look wrong in an editor. That is normal.
    first = conv['palettes'][min(conv['palettes'])]
    flat = [0, 0, 0]
    for c in first:
        flat += list(c)
    flat += [0, 0, 0] * (256 - len(flat) // 3)
    img.putpalette(flat)
    img.save(out / 'tiles.png', bits=4)

    # ---- palettes : JASC-PAL, CRLF, 16 entries. Secondary uses slots 6..12.
    for slot in range(16):
        cols = conv['palettes'].get(slot, [])
        lines = ['JASC-PAL', '0100', '16', '0 0 0']
        for c in cols:
            lines.append(f'{c[0]} {c[1]} {c[2]}')
        while len(lines) < 3 + 16:
            lines.append('0 0 0')
        (out / 'palettes' / f'{slot:02d}.pal').write_bytes(
            ('\r\n'.join(lines) + '\r\n').encode())

    # ---- metatiles.bin : 8 u16 per metatile, 0-3 middle layer, 4-7 top
    mt = bytearray()
    at = bytearray()
    for m in conv['metatiles']:
        for e in m['entries']:
            mt += int(e).to_bytes(2, 'little')
        for _ in range(4):
            mt += (0).to_bytes(2, 'little')      # empty top layer
        at += int(m['attr']).to_bytes(2, 'little')
    (out / 'metatiles.bin').write_bytes(bytes(mt))
    (out / 'metatile_attributes.bin').write_bytes(bytes(at))
    return len(tiles), len(conv['metatiles'])


def print_decls(spec, conv, ntiles):
    sym, path = spec['symbol'], spec['out']
    print(f'\n--- src/data/tilesets/graphics.h  (BEFORE the #else, Emerald block) ---')
    print(f'const u32 gTilesetTiles_{sym}[] = INCGFX_U32("{path}/tiles.png", '
          f'".4bpp.fastSmol", "-num_tiles {ntiles} -Wnum_tiles");\n')
    print(f'const u16 gTilesetPalettes_{sym}[][16] =\n{{')
    for i in range(16):
        print(f'    INCGFX_U16("{path}/palettes/{i:02d}.pal", ".gbapal"),')
    print('};')
    print(f'\n--- src/data/tilesets/metatiles.h ---')
    print(f'const u16 gMetatiles_{sym}[] = INCBIN_U16("{path}/metatiles.bin");')
    print(f'const u16 gMetatileAttributes_{sym}[] = '
          f'INCBIN_U16("{path}/metatile_attributes.bin");')
    print(f'\n--- src/data/tilesets/headers.h  (BEFORE the #else at ~line 899) ---')
    print(f'const struct Tileset gTileset_{sym} =\n{{')
    print('    .isCompressed = TRUE,\n    .isSecondary = TRUE,')
    print(f'    .tiles = gTilesetTiles_{sym},')
    print(f'    .palettes = gTilesetPalettes_{sym},')
    print(f'    .metatiles = gMetatiles_{sym},')
    print(f'    .metatileAttributes = gMetatileAttributes_{sym},')
    print('    .callback = NULL,\n};')

    print(f'\n--- metatile constants for your project header ---')
    base, p = 0x200, spec['prefix']
    print(f'#define {p}_METATILE_FLOOR{"":<12} 0x{base + conv["floor"]:03X}')
    for slot, li in conv['slotmap'].items():
        print(f'#define {p}_METATILE_{slot:<16} 0x{base + li:03X}')
    for i, (name, _, alt) in enumerate(conv['decor'], 1):
        print(f'#define {p}_METATILE_DECOR_{i}{"":<10} 0x{base + alt:03X}  // varies '
              f'0x{base + conv["decor"][i - 1][1]:03X}')
    for label, li in conv['grafted'].items():
        print(f'#define {p}_METATILE_{label.upper():<16} 0x{base + li:03X}')
    # A patch region wants nine of the twenty masks, under the patch pass's own
    # names. Printed in that order so the RoguePatchLayer can be pasted.
    PATCH = [('NW', 'NORTH_LEFT'), ('N', 'NORTH_MID'), ('NE', 'NORTH_RIGHT'),
             ('W', 'INTERIOR_LEFT'), ('MID', 'INTERIOR_MID'), ('E', 'INTERIOR_RIGHT'),
             ('SW', 'FACE_LEFT'), ('S', 'FACE_MID'), ('SE', 'FACE_RIGHT')]
    for nm, m in conv['autotiles'].items():
        print(f'\n// {nm} as a patch region')
        for patch, slot in PATCH:
            if slot in m:
                print(f'#define {p}_METATILE_{nm.upper()}_{patch:<9} '
                      f'0x{base + m[slot]:03X}')
    if conv['decor']:
        print('\n// struct RogueDecor entries: { base, replacement }')
        for name, b, a in conv['decor']:
            print(f'//   {{ 0x{base + b:03X}, 0x{base + a:03X} }},   // {name}')


def main(argv):
    name = argv[0] if argv else 'lapis'
    spec = TILESETS[name]
    print(f'=== {name} -> {spec["out"]} ===')
    conv = convert(spec)

    ntiles, nmt = len(conv['bank'].tiles), len(conv['metatiles'])
    print(f'\n  {nmt} metatiles  ({512 - nmt} slots spare)')
    print(f'  {ntiles} tiles      ({512 - ntiles} slots spare)'
          f'{"   OVER BUDGET" if ntiles > 512 else ""}')
    print(f'  dedupe saved {nmt * 4 - ntiles} of {nmt * 4} quadrants')

    missing = [s for s in SLOTS if s not in conv['slotmap']]
    print(f'\n  {len(conv["slotmap"])}/{len(SLOTS)} PaintWalls slots matched'
          + (f'   MISSING: {missing}' if missing else ''))
    print(f'  floor metatile: local {conv["floor"]}'
          if conv['floor'] is not None else '  floor: NOT FOUND')
    for nm, b, a in conv['decor']:
        print(f'  {nm}: local {a} varies local {b}')
    for nm, m in conv['autotiles'].items():
        miss = [s for s in SLOTS if s not in m]
        print(f'  {nm} autotile: {len(m)}/{len(SLOTS)} slots'
              + (f'   MISSING: {miss}' if miss else ''))
    for label, li in conv['grafted'].items():
        print(f'  grafted {label}: local {li}')

    if '--write' in argv:
        if ntiles > 512:
            raise SystemExit('refusing to write: over the 512-tile budget')
        if conv['floor'] is None:
            raise SystemExit('refusing to write: no plain floor found')
        n, m = write_tileset(spec, conv)
        print(f'\n  wrote {spec["out"]}  ({n} tiles, {m} metatiles)')
    if '--decls' in argv:
        print_decls(spec, conv, ntiles)


if __name__ == '__main__':
    main(sys.argv[1:])
