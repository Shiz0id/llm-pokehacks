"""
Metatile atlas builder for pokeemerald-expansion.

Renders every metatile of a (primary, secondary) tileset pair to a labelled
contact sheet, so procedural generation can pick metatile ids from a reference
instead of guessing.

Metatile encoding (8 x u16 per metatile, from include/global.fieldmap.h and the
tileset .bin layout):
    entries[0..3] = bottom layer, 2x2 of 8x8 tiles
    entries[4..7] = top layer,    2x2 of 8x8 tiles
    each u16: bits 0-9 tile index, bit 10 xflip, bit 11 yflip, bits 12-15 palette

Tile and palette indices address the COMBINED space: indices below the primary
count come from the primary tileset, the rest from the secondary. The split is
512/6 for Emerald-mode tilesets and 640/7 for FRLG-mode.
"""
import json, os, re, struct
from pathlib import Path
from PIL import Image, ImageDraw

from repo import REPO  # noqa: E402  (see repo.py)

# Renders go next to these scripts, NOT into the repo being inspected. Writing
# PNGs into somebody's decomp checkout puts noise in their git status and
# invites committing them by accident. Override with POKEDECOMP_OUT.
OUTDIR = Path(os.environ.get('POKEDECOMP_OUT',
                             Path(__file__).resolve().parent / '_out'))
OUTDIR.mkdir(parents=True, exist_ok=True)
OUT = OUTDIR

TILE_MASK, XFLIP_BIT, YFLIP_BIT, PAL_SHIFT = 0x03FF, 0x0400, 0x0800, 12
NUM_TILES_IN_PRIMARY, NUM_PALS_IN_PRIMARY = 512, 6
NUM_TILES_IN_PRIMARY_FRLG, NUM_PALS_IN_PRIMARY_FRLG = 640, 7


def parse_jasc_pal(path):
    """JASC-PAL text format -> list of 16 (r,g,b)."""
    lines = path.read_text(errors='replace').split('\n')
    n = int(lines[2].strip())
    out = []
    for ln in lines[3:3 + n]:
        parts = ln.split()
        if len(parts) >= 3:
            out.append((int(parts[0]), int(parts[1]), int(parts[2])))
    while len(out) < 16:
        out.append((0, 0, 0))
    return out[:16]


def parse_gbapal(path):
    """Raw GBA palette -> list of 16 (r,g,b).

    BGR555, one u16 per colour: bits 0-4 red, 5-9 green, 10-14 blue, each a
    5-bit value. Scaled to 8 bits with `v * 255 // 31` rather than `v << 3`,
    which would cap white at 248 and tint every render slightly dark.
    """
    raw = path.read_bytes()
    out = []
    for i in range(0, min(len(raw), 32), 2):
        v = raw[i] | (raw[i + 1] << 8)
        out.append((((v >> 0) & 31) * 255 // 31,
                    ((v >> 5) & 31) * 255 // 31,
                    ((v >> 10) & 31) * 255 // 31))
    while len(out) < 16:
        out.append((0, 0, 0))
    return out[:16]


def parse_palette(path):
    """Whichever of the two formats this decomp declares. See the note in
    tileset_resolve: pokeemerald names the JASC source, pokefirered names the
    compiled binary, and both are real files in a clean checkout."""
    return parse_gbapal(path) if path.suffix == '.gbapal' else parse_jasc_pal(path)


class Tileset:
    """Built from a resolved component dict (see tileset_resolve.TilesetResolver),
    because tiles, palettes, metatiles and attributes can each come from a
    different directory."""

    def __init__(self, res: dict):
        self.symbol = res['symbol']
        self.name = res['dir_hint']
        self.is_secondary = res['is_secondary']

        img = Image.open(res['tiles'])
        self.tiles_img = img.convert('P') if img.mode != 'P' else img
        w, h = self.tiles_img.size
        self.tiles_per_row = w // 8
        self.tile_count = (w // 8) * (h // 8)
        self.tile_px = self.tiles_img.load()

        self.palettes = [parse_palette(p) for p in res['palettes']]

        mt = res['metatiles'].read_bytes()
        self.metatile_count = len(mt) // 16
        self.metatiles = [struct.unpack('<8H', mt[i * 16:(i + 1) * 16])
                          for i in range(self.metatile_count)]

        ab = res['attributes'].read_bytes()
        self.attr_width = (len(ab) // self.metatile_count) if self.metatile_count else 2
        if self.attr_width == 4:
            self.attrs = list(struct.unpack(f'<{len(ab)//4}I', ab))
        else:
            self.attrs = list(struct.unpack(f'<{len(ab)//2}H', ab))

    def is_frlg(self):
        return self.attr_width == 4

    def tile_pixels(self, idx):
        """Return 8x8 list-of-rows of palette indices for local tile idx."""
        if idx >= self.tile_count:
            return None
        tx, ty = (idx % self.tiles_per_row) * 8, (idx // self.tiles_per_row) * 8
        return [[self.tile_px[tx + x, ty + y] for x in range(8)] for y in range(8)]


class TilesetPair:
    def __init__(self, primary: Tileset, secondary: Tileset | None):
        self.primary, self.secondary = primary, secondary
        frlg = primary.is_frlg()
        self.num_tiles_primary = NUM_TILES_IN_PRIMARY_FRLG if frlg else NUM_TILES_IN_PRIMARY
        self.num_pals_primary = NUM_PALS_IN_PRIMARY_FRLG if frlg else NUM_PALS_IN_PRIMARY
        self.frlg = frlg

    def total_metatiles(self):
        n = self.num_tiles_primary
        return n + (self.secondary.metatile_count if self.secondary else 0)

    def get_metatile(self, idx):
        if idx < self.num_tiles_primary:
            return self.primary.metatiles[idx] if idx < self.primary.metatile_count else None
        if not self.secondary:
            return None
        j = idx - self.num_tiles_primary
        return self.secondary.metatiles[j] if j < self.secondary.metatile_count else None

    def tile_pixels(self, idx):
        if idx < self.num_tiles_primary:
            return self.primary.tile_pixels(idx)
        if not self.secondary:
            return None
        return self.secondary.tile_pixels(idx - self.num_tiles_primary)

    def palette(self, idx):
        if idx < self.num_pals_primary:
            src, j = self.primary, idx
        else:
            src, j = (self.secondary or self.primary), idx
        return src.palettes[j] if j < len(src.palettes) else [(255, 0, 255)] * 16


def render_metatile(pair: TilesetPair, idx, scale=1):
    """Composite one metatile to a 16x16 (scaled) RGB image."""
    entries = pair.get_metatile(idx)
    img = Image.new('RGB', (16, 16), (255, 0, 255))
    if entries is None:
        return img.resize((16 * scale, 16 * scale), Image.NEAREST)
    px = img.load()
    for layer in (0, 1):                      # bottom then top
        for q in range(4):                    # 2x2 quadrants
            e = entries[layer * 4 + q]
            tile, pal = e & TILE_MASK, (e >> PAL_SHIFT) & 0xF
            xf, yf = bool(e & XFLIP_BIT), bool(e & YFLIP_BIT)
            rows = pair.tile_pixels(tile)
            if rows is None:
                continue
            colors = pair.palette(pal)
            ox, oy = (q % 2) * 8, (q // 2) * 8
            for y in range(8):
                sy = 7 - y if yf else y
                for x in range(8):
                    sx = 7 - x if xf else x
                    ci = rows[sy][sx]
                    if layer == 1 and ci == 0:      # index 0 transparent on top layer
                        continue
                    px[ox + x, oy + y] = colors[ci] if ci < len(colors) else (255, 0, 255)
    if scale != 1:
        img = img.resize((16 * scale, 16 * scale), Image.NEAREST)
    return img


def parse_labels():
    """-> {TilesetName: {metatile_id: LabelName}}"""
    txt = (REPO / 'include/constants/metatile_labels.h').read_text(errors='replace')
    out = {}
    for m in re.finditer(r'#define\s+METATILE_(\w+?)_(\w+)\s+(0x[0-9A-Fa-f]+|\d+)', txt):
        ts, label, val = m.group(1), m.group(2), int(m.group(3), 0)
        out.setdefault(ts, {})[val] = label
    return out


def parse_behaviors(frlg=False):
    """-> {value: MB_NAME}. The behaviors are a C enum with implicit numbering
    and occasional explicit '= N' assignments, not #defines."""
    name = 'metatile_behaviors_frlg.h' if frlg else 'metatile_behaviors.h'
    p = REPO / 'include/constants' / name
    if not p.exists():
        return {}
    txt = p.read_text(errors='replace')
    body = re.search(r'enum\s*\{(.*?)\}\s*;', txt, re.S)
    if not body:
        return {}
    out, nxt = {}, 0
    for raw in body.group(1).split(','):
        entry = re.sub(r'//.*|/\*.*?\*/', '', raw, flags=re.S).strip()
        if not entry:
            continue
        m = re.match(r'(MB_\w+)\s*(?:=\s*(0x[0-9A-Fa-f]+|\d+))?$', entry)
        if not m:
            continue
        val = int(m.group(2), 0) if m.group(2) else nxt
        out[val] = m.group(1)
        nxt = val + 1
    return out


def _label_key(dirname):
    """tileset directory name -> the prefix used in metatile_labels.h
    e.g. 'generic_building' -> 'GenericBuilding', 'general_frlg' -> 'GeneralFrlg'"""
    return ''.join(p.capitalize() for p in dirname.split('_'))


def behavior_of(pair: TilesetPair, idx):
    if idx < pair.num_tiles_primary:
        src, j = pair.primary, idx
    else:
        src, j = pair.secondary, idx - pair.num_tiles_primary
    if src is None or j >= len(src.attrs):
        return None
    a = src.attrs[j]
    return (a >> 0) & 0x1FF if src.attr_width == 4 else a & 0x00FF


def build_atlas(pair: TilesetPair, out_path: Path, labels=None, behaviors=None,
                scale=3, cols=16):
    labels = labels or {}
    behaviors = behaviors or {}
    total = pair.total_metatiles()
    cell_w, cell_h = 16 * scale + 8, 16 * scale + 36
    rows = (total + cols - 1) // cols
    sheet = Image.new('RGB', (cols * cell_w, rows * cell_h), (28, 28, 34))
    d = ImageDraw.Draw(sheet)

    prim_lbl = labels.get(_label_key(pair.primary.name), {})
    sec_lbl = labels.get(_label_key(pair.secondary.name), {}) if pair.secondary else {}

    for i in range(total):
        cx, cy = (i % cols) * cell_w, (i // cols) * cell_h
        if pair.get_metatile(i) is None:
            d.rectangle([cx + 3, cy + 3, cx + 3 + 16 * scale, cy + 3 + 16 * scale],
                        fill=(45, 45, 52))
        else:
            sheet.paste(render_metatile(pair, i, scale), (cx + 3, cy + 3))
        name = prim_lbl.get(i) or sec_lbl.get(i)
        bh = behavior_of(pair, i)
        bh_name = behaviors.get(bh, str(bh) if bh else '') if bh else ''
        base = cy + 4 + 16 * scale
        d.text((cx + 3, base), f'{i:03X}', fill=(210, 210, 220))
        if bh_name:
            d.text((cx + 3, base + 10), bh_name.replace('MB_', '')[:9], fill=(150, 150, 195))
        if name:
            d.text((cx + 3, base + 20), name[:9], fill=(120, 200, 140))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return sheet.size, total


def export_index(pair: TilesetPair, out_path: Path, labels=None, behaviors=None,
                 primary_sym='', secondary_sym=''):
    """Machine-readable companion to the contact sheet - this is what the
    generator queries when picking metatile ids."""
    labels = labels or {}
    behaviors = behaviors or {}
    prim_lbl = labels.get(_label_key(pair.primary.name), {})
    sec_lbl = labels.get(_label_key(pair.secondary.name), {}) if pair.secondary else {}

    records = []
    for i in range(pair.total_metatiles()):
        if pair.get_metatile(i) is None:
            continue
        bh = behavior_of(pair, i)
        records.append({
            'id': i,
            'hex': f'0x{i:03X}',
            'source': 'primary' if i < pair.num_tiles_primary else 'secondary',
            'behavior': bh,
            'behavior_name': behaviors.get(bh) if bh is not None else None,
            'label': prim_lbl.get(i) or sec_lbl.get(i),
        })
    doc = {
        'primary': primary_sym or pair.primary.name,
        'secondary': secondary_sym or (pair.secondary.name if pair.secondary else None),
        'frlg_mode': pair.frlg,
        'primary_split': pair.num_tiles_primary,
        'metatile_count': len(records),
        'metatiles': records,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=1), encoding='utf-8')
    return len(records)
