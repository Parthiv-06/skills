"""Draw analysis.json as an Excalidraw ER diagram: key rows only, each FK row arrowed to its PK row.
Layout is computed, not hand-placed: parents left, one lane per vertical run, no arrow in a box."""
USAGE = """Usage:
  python3 make_er_excalidraw.py analysis.json page.json OUT.excalidraw [--overview-at N] [--svg]

page.json supplies the title and the domains ({"name", "tables"}); tables in no domain go to "Other".
Up to N tables (default 15) one detailed diagram is drawn. Above N: OUT.excalidraw becomes an overview
(table names only) plus OUT-<domain>.excalidraw per domain, with linked tables from other domains in grey.
Layout search: start parents-left, then move one table at a time to any column (children may sit on
either side of a parent) while crossings drop; tried in domain bands and as one block, fewest wins. --svg also writes an OUT.svg preview. Prints a self-check: overlapping
boxes, arrows crossing a box, arrow crossings. Open the .excalidraw at https://excalidraw.com (menu, Open)."""
import itertools
import json
import random
import re
import sys
import time
from collections import defaultdict

INK, GREY, FAINT = "#1e1e1e", "#868e96", "#ced4da"
HAND, MONO = 1, 3
HEADER_H, ROW_H, PAD, V_GAP, BAND_GAP, BAND_TOP = 44, 28, 14, 46, 56, 46
GAP_PAD, LANE_W, MIN_GAP = 34, 14, 110
STYLE = {"declared": "solid", "inferred": "dashed", "guess": "dotted"}
SEARCH_SECONDS = 20
random.seed(7)


def base(kind, x, y, w, h, **extra):
    el = {"type": kind, "id": extra.pop("id", f"{kind}-{random.getrandbits(40):x}"), "x": x, "y": y, "width": w,
          "height": h, "angle": 0, "strokeColor": INK, "backgroundColor": "transparent", "fillStyle": "solid",
          "strokeWidth": 1.5, "strokeStyle": "solid", "roughness": 0, "opacity": 100, "groupIds": [],
          "frameId": None, "roundness": None, "seed": random.getrandbits(30), "version": 1,
          "versionNonce": random.getrandbits(30), "isDeleted": False, "boundElements": [], "updated": 1,
          "link": None, "locked": False}
    el.update(extra)
    return el


def text(x, y, s, size=16, font=MONO, color=INK, align="left"):
    w = len(s) * size * (0.6 if font == MONO else 0.56) + 4
    return base("text", x, y, w, size * 1.25, text=s, originalText=s, fontSize=size, fontFamily=font,
                textAlign=align, verticalAlign="top", containerId=None, lineHeight=1.25, autoResize=True,
                strokeColor=color)


class Box:
    def __init__(self, t, ghost=False, keep=None, overview=False, grain=""):
        self.name, self.kind, self.ghost, self.grain = t["name"], t["kind"], ghost, grain
        types = {c["name"]: re.sub(r"\(.*\)", "", c["type"] or "")[:14] for c in t["columns"]}
        self.view = t["kind"] != "table"
        self.types = {} if self.view else types
        self.rows = []
        if overview:
            pass
        elif self.view:
            self.rows = [("<-", r) for r in t.get("reads", [])]
        else:
            fk = set(t.get("fk_columns", []))
            for c in t["columns"]:
                n = c["name"]
                if keep is not None and n not in keep:
                    continue
                tag = ("PK " if n in t["primary_key"] else "") + ("FK" if n in fk else "")
                if tag.strip():
                    self.rows.append((tag.strip(), n))
            for extra in sorted(keep or []):
                if extra not in [r[1] for r in self.rows] and any(c["name"] == extra for c in t["columns"]):
                    self.rows.append(("UQ", extra))
            if not self.rows and keep is None:
                self.rows.append(("", "(no key)"))
        self.inbound = defaultdict(int)
        self.slots = defaultdict(int)

    def row_text(self, tag, n):
        width = max([len(name) for _, name in self.rows] + [0])
        kind = self.types.get(n, "")
        return f"{tag:<5} {n:<{width}}  {kind}".rstrip() if kind else f"{tag:<5} {n}"

    def layout(self):
        self.head_h = HEADER_H + (20 if self.grain else 0)
        head = max(len(self.name) * 20 * 0.56, len(self.grain) * 14 * 0.52) + 2 * PAD + (54 if self.view else 0)
        body = max([len(self.row_text(tag, n)) * 15 * 0.6 + 2 * PAD for tag, n in self.rows] + [0])
        self.w = max(150, head, body)
        self.row_h = {n: max(ROW_H, 22 * self.inbound[n] + 10) for _, n in self.rows}
        self.h = self.head_h + sum(self.row_h.values()) + (8 if self.rows else 0)
        if not self.rows:
            self.h = max(self.head_h + 8, 22 * self.inbound["*"] + 16)

    def anchor_y(self, column):
        """Next free y on this row for an arrow end; several arrows into one row are spread evenly."""
        if column not in self.row_h:
            k, i = self.inbound["*"] or 1, self.slots["*"]
            self.slots["*"] += 1
            return self.y + (self.h - 22 * (k - 1)) / 2 + 22 * i
        top = self.y + self.head_h
        for _, n in self.rows:
            if n == column:
                break
            top += self.row_h[n]
        k, i = max(self.inbound[column], 1), self.slots[column]
        self.slots[column] += 1
        return top + (self.row_h[column] - 22 * (k - 1)) / 2 + 22 * i


def layers(names, edges):
    """Column per table: a table sits one column right of everything it references (parents left).
    Tables nothing references are pulled right next to their nearest child, so arrows stay short."""
    parents = defaultdict(set)
    for a, b in edges:
        if a != b:
            parents[a].add(b)
    memo, active = {}, set()

    def depth(n):
        if n in memo:
            return memo[n]
        active.add(n)
        d = 0
        for p in parents[n]:
            if p not in active:
                d = max(d, depth(p) + 1)
        active.discard(n)
        memo[n] = d
        return d

    for n in names:
        depth(n)
    children = defaultdict(set)
    for a, bs in parents.items():
        for b in bs:
            children[b].add(a)
    for n in names:
        if not parents[n] and children[n]:
            memo[n] = max(memo[n], min(memo[c] for c in children[n]) - 1)
    return memo


def corridor(sy, ey, lo_c, hi_c, boxes, used):
    """A y for the horizontal run of a long hop: clear of every box in the columns it passes over."""
    blockers = [b for b in boxes if lo_c < b.col < hi_c]
    cands = sorted({sy, ey} | {b.y - V_GAP / 2 for b in blockers} | {b.y + b.h + V_GAP / 2 for b in blockers},
                   key=lambda y: abs(y - sy) + abs(y - ey))
    for y in cands:
        if all(not (b.y - 6 < y < b.y + b.h + 6) for b in blockers):
            while any(abs(y - uy) < 10 and ulo < hi_c and uhi > lo_c for uy, ulo, uhi in used):
                y += 12
            used.append((y, lo_c, hi_c))
            return y
    return sy


def order_lanes(segs):
    """Left-to-right lane order in one gap that keeps arrow crossings low (pairwise swap until stable).
    Each seg: (id, low y, high y, [(side, y)...]) where side L/R says which way its horizontal runs."""
    def cost(a, b):
        n = sum(1 for side, y in a[3] if side == "R" and b[1] - 3 <= y <= b[2] + 3)
        n += sum(1 for side, y in b[3] if side == "L" and a[1] - 3 <= y <= a[2] + 3)
        return n + sum(2 for sa, ya in a[3] for sb, yb in b[3] if sa == "R" and sb == "L" and abs(ya - yb) < 4)
    order = sorted(segs, key=lambda s: (s[1] + s[2]) / 2)
    changed = True
    while changed:
        changed = False
        for i in range(len(order) - 1):
            if cost(order[i + 1], order[i]) < cost(order[i], order[i + 1]):
                order[i], order[i + 1] = order[i + 1], order[i]
                changed = True
    return [s[0] for s in order]


def draw(title, boxes, rels, bands, view_band, legend=True, cols=None):
    """Place boxes, route arrows, and return (excalidraw elements, self-check counts)."""
    table_boxes = {n: b for n, b in boxes.items() if not b.view}
    edges = [(r["from"], r["to"]) for r in rels]
    for r in rels:
        tb = table_boxes[r["to"]]
        tb.inbound[r["to_columns"][0] if r["to_columns"][0] in [n for _, n in tb.rows] else "*"] += 1
    for b in boxes.values():
        b.layout()
    col = layers(list(table_boxes), edges)
    col.update({n: c for n, c in (cols or {}).items() if n in col})
    dense = {c: i for i, c in enumerate(sorted(set(col.values())))}
    col = {n: dense[c] for n, c in col.items()}
    ncols = max(col.values(), default=0) + 1

    band_cols = []
    for name, members in bands:
        cols = defaultdict(list)
        for n in members:
            if n in table_boxes:
                cols[col[n]].append(n)
        band_cols.append((name, cols))
    band_of = {n: i for i, (_, cols) in enumerate(band_cols) for ns in cols.values() for n in ns}
    if 2 < len(band_cols) <= 7:
        def cost(order):
            rank = {bi: i for i, bi in enumerate(order)}
            return sum(abs(rank[band_of[p]] - rank[band_of[q]]) for p, q in edges if p in band_of and q in band_of)
        band_cols = [band_cols[i] for i in min(itertools.permutations(range(len(band_cols))), key=cost)]
    pos_y = {}
    for _ in range(4):
        for name, cols in band_cols:
            for c in sorted(cols):
                def bary(n):
                    ys = [pos_y[o] for a, bb in edges for o in ((bb,) if a == n else (a,) if bb == n else ())
                          if o in pos_y and o != n]
                    return sum(ys) / len(ys) if ys else pos_y.get(n, 0)
                cols[c].sort(key=bary)
                for i, n in enumerate(cols[c]):
                    pos_y[n] = i + 0.001 * c
    col_w = [max([table_boxes[n].w for n in table_boxes if col[n] == c] + [150]) for c in range(ncols)]

    y = 150 if legend else 90
    band_rects = []
    for name, cols in band_cols:
        if not cols:
            continue
        stack_h = {c: sum(table_boxes[n].h for n in ns) + V_GAP * (len(ns) - 1) for c, ns in cols.items()}
        height = max(stack_h.values())
        for c, ns in cols.items():
            yy = y + BAND_TOP + (height - stack_h[c]) / 2
            for n in ns:
                table_boxes[n].y, table_boxes[n].col = yy, c
                yy += table_boxes[n].h + V_GAP
        band_rects.append((name, y, y + BAND_TOP + height + 24))
        y += BAND_TOP + height + 24 + BAND_GAP
    for _ in range(3):
        for (name, cols), (_, top, bottom) in zip([bc for bc in band_cols if bc[1]], band_rects):
            for c, ns in cols.items():
                stack = sum(table_boxes[n].h for n in ns) + V_GAP * (len(ns) - 1)
                ys = [table_boxes[o].y + table_boxes[o].h / 2 for n in ns for p, q in edges
                      for o in ((q,) if p == n else (p,) if q == n else ()) if table_boxes[o].col != c]
                if ys:
                    yy = min(max(sum(ys) / len(ys) - stack / 2, top + BAND_TOP), bottom - 24 - stack)
                    for n in ns:
                        table_boxes[n].y = yy
                        yy += table_boxes[n].h + V_GAP

    lanes = defaultdict(list)
    plans, used, src_y = [], [], {}
    for r in rels:
        a = table_boxes[r["from"]]
        src_y[r["id"]] = a.anchor_y(r["from_columns"][0] if r["from_columns"][0] in a.row_h else "*")
    for r in sorted(rels, key=lambda r: src_y[r["id"]]):
        a, b = table_boxes[r["from"]], table_boxes[r["to"]]
        sy = src_y[r["id"]]
        ey = b.anchor_y(r["to_columns"][0] if r["to_columns"][0] in b.row_h else "*")
        cy = None
        if abs(a.col - b.col) > 1:
            cy = corridor(sy, ey, min(a.col, b.col), max(a.col, b.col), list(table_boxes.values()), used)
        if b.col < a.col:
            sside, eside = "L", "R"
            hops = [(a.col - 1, [("R", sy), ("L", cy if cy is not None else ey)])]
            if cy is not None:
                hops.append((b.col, [("R", cy), ("L", ey)]))
        elif b.col == a.col:
            sside, eside, hops = "R", "R", [(a.col, [("L", sy), ("L", ey)])]
        else:
            sside, eside = "R", "L"
            hops = [(a.col, [("L", sy), ("R", cy if cy is not None else ey)])]
            if cy is not None:
                hops.append((b.col - 1, [("L", cy), ("R", ey)]))
        plans.append((r, a, b, sy, ey, cy, sside, eside, [gi for gi, _ in hops]))
        for gi, hs in hops:
            ys = [y for _, y in hs]
            lanes[gi].append((r["id"], min(ys), max(ys), hs))
    lane_of, lane_count = {}, defaultdict(int)
    for gi, segs in lanes.items():
        for k, rid in enumerate(order_lanes(segs)):
            lane_of[(rid, gi)] = k
        lane_count[gi] = len(segs)
    gap_w = [max(MIN_GAP, 2 * GAP_PAD + lane_count[i] * LANE_W) for i in range(ncols)]
    col_x, x = [], 60
    for c in range(ncols):
        col_x.append(x)
        x += col_w[c] + gap_w[c]
    for b in table_boxes.values():
        b.x = col_x[b.col]
    right_edge = x

    els = [text(60, 40, title, 28, HAND)]
    if legend:
        lx = 60
        for label, style in (("declared FK", "solid"), ("inferred FK", "dashed"), ("guess: check it", "dotted")):
            els.append(base("line", lx, 108, 34, 0, points=[[0, 0], [34, 0]], strokeStyle=style, strokeColor=INK))
            els.append(text(lx + 42, 98, label, 15, HAND, GREY))
            lx += 70 + len(label) * 8.5
        els.append(text(lx + 10, 98, "PK key · FK points to a key · N many · 1 one · 0..1 optional", 15, HAND, GREY))
    for name, top, bottom in band_rects:
        els.append(base("rectangle", 30, top, right_edge - 60, bottom - top, strokeColor=FAINT, strokeStyle="dashed",
                        strokeWidth=1))
        els.append(text(46, top + 10, name, 18, HAND, GREY))

    box_el = {}
    for b in list(table_boxes.values()):
        els += box_elements(b, box_el)
    arrows = []
    for r, a, b, sy, ey, cy, sside, eside, g in plans:
        start = (a.x if sside == "L" else a.x + a.w, sy)
        end = (b.x + b.w if eside == "R" else b.x, ey)
        lx = [col_x[gi] + col_w[gi] + GAP_PAD + lane_of[(r["id"], gi)] * LANE_W for gi in g]
        pts = [start, (lx[0], sy)] + ([(lx[0], cy), (lx[1], cy), (lx[1], ey)] if cy is not None else
                                       [(lx[0], ey)]) + [end]
        pts = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
        arrows.append((r, pts))
        x0, y0 = pts[0]
        arrow = base("arrow", x0, y0, max(p[0] for p in pts) - min(p[0] for p in pts),
                     max(p[1] for p in pts) - min(p[1] for p in pts), id=f"rel-{r['id']}",
                     points=[[px - x0, py - y0] for px, py in pts], strokeStyle=STYLE[r["confidence"]],
                     strokeColor=GREY if a.ghost or b.ghost else INK, lastCommittedPoint=None,
                     startArrowhead=None, endArrowhead="arrow", elbowed=False,
                     startBinding={"elementId": box_el[a.name], "focus": 0, "gap": 1},
                     endBinding={"elementId": box_el[b.name], "focus": 0, "gap": 1})
        els.append(arrow)
        for el in els:
            if el["id"] in (box_el[a.name], box_el[b.name]):
                el["boundElements"].append({"id": arrow["id"], "type": "arrow"})
        near = "0..1" if r["cardinality"] == "1:1" else "N"
        far = "0..1" if r["optional"] else "1"
        dx_s = -6 - len(near) * 8 if sside == "L" else 6
        dx_e = 14 if eside == "R" else -14 - len(far) * 8
        els.append(text(start[0] + dx_s, sy - 17, near, 13, MONO, GREY))
        els.append(text(end[0] + dx_e, ey - 17, far, 13, MONO, GREY))
        if r.get("type_mismatch"):
            els.append(text(start[0] + dx_s - (40 if sside == "L" else 0), sy + 3, "≠ type", 13, MONO, "#c92a2a"))

    if view_band:
        vy = y
        depth = {}
        names = [n for n in view_band if n in boxes]
        for _ in names:
            for n in names:
                depth[n] = max([depth.get(s, -1) + 1 for _, s in boxes[n].rows if s in names] + [0])
        vcols = defaultdict(list)
        for n in names:
            vcols[depth[n]].append(n)
        height = max(sum(boxes[n].h for n in ns) + V_GAP * (len(ns) - 1) for ns in vcols.values())
        vx = 60
        for d in sorted(vcols):
            yy = vy + BAND_TOP
            for n in vcols[d]:
                boxes[n].x, boxes[n].y = vx, yy
                yy += boxes[n].h + V_GAP
            vx += max(boxes[n].w for n in vcols[d]) + 130
        els.append(base("rectangle", 30, vy, max(right_edge, vx) - 60, BAND_TOP + height + 24, strokeColor=FAINT,
                        strokeStyle="dashed", strokeWidth=1))
        els.append(text(46, vy + 10, "Views (rows list what each view reads)", 18, HAND, GREY))
        for n in names:
            els += box_elements(boxes[n], box_el)
        for n in names:
            for _, src in boxes[n].rows:
                if src in names:
                    s, d = boxes[src], boxes[n]
                    sy0, ey0 = s.y + s.head_h / 2, d.anchor_y(src)
                    mid = s.x + s.w + 40
                    pts = [(s.x + s.w, sy0), (mid, sy0), (mid, ey0), (d.x, ey0)]
                    els.append(base("arrow", pts[0][0], pts[0][1], 1, 1, points=[[px - pts[0][0], py - pts[0][1]]
                                                                                for px, py in pts],
                                    strokeColor=GREY, strokeStyle="dotted", endArrowhead="arrow",
                                    startArrowhead=None, lastCommittedPoint=None, elbowed=False))
    stats = check(table_boxes, arrows)
    stats["cols"] = col
    return els, stats


def box_elements(b, box_el):
    stroke = GREY if b.ghost else INK
    rect = base("rectangle", b.x, b.y, b.w, b.h, strokeColor=stroke, backgroundColor="#ffffff",
                strokeStyle="dashed" if b.view else "solid", roughness=1, strokeWidth=2 if not b.ghost else 1)
    box_el[b.name] = rect["id"]
    out = [rect, text(b.x + PAD, b.y + 10, b.name, 20, HAND, stroke)]
    if b.grain:
        out.append(text(b.x + PAD, b.y + 38, b.grain, 14, HAND, GREY))
    if b.view:
        out.append(text(b.x + b.w - PAD - 40, b.y + 14, "VIEW", 13, MONO, GREY))
    if b.rows:
        out.append(base("line", b.x, b.y + b.head_h, b.w, 0, points=[[0, 0], [b.w, 0]], strokeColor=FAINT,
                        strokeWidth=1))
        yy = b.y + b.head_h
        for tag, n in b.rows:
            h = b.row_h.get(n, ROW_H) if hasattr(b, "row_h") else ROW_H
            out.append(text(b.x + PAD, yy + h / 2 - 9, b.row_text(tag, n), 15, MONO, GREY if b.view or b.ghost
                            else stroke))
            yy += h
    return out


def check(boxes, arrows):
    """Self-check counts: overlapping boxes, arrow segments passing through a box, arrow crossings."""
    bs = list(boxes.values())
    overlaps = sum(1 for i, a in enumerate(bs) for b in bs[i + 1:]
                   if a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h)
    through = 0
    segs = []
    for r, pts in arrows:
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            segs.append((r["id"], min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
            for b in bs:
                if b.x + 2 < max(x1, x2) and min(x1, x2) < b.x + b.w - 2 and \
                        b.y + 2 < max(y1, y2) and min(y1, y2) < b.y + b.h - 2:
                    through += 1
    crossings = 0
    for i, s in enumerate(segs):
        for t in segs[i + 1:]:
            if s[0] == t[0]:
                continue
            h, v = (s, t) if s[2] == s[4] else (t, s)
            if h[2] == h[4] and v[1] == v[3] and h[1] < v[1] < h[3] and v[2] < h[2] < v[4]:
                crossings += 1
    length = sum(abs(x2 - x1) + abs(y2 - y1) for _, pts in arrows for (x1, y1), (x2, y2) in zip(pts, pts[1:]))
    return {"boxes": len(bs), "arrows": len(arrows), "overlapping_boxes": overlaps,
            "arrow_segments_through_boxes": through, "arrow_crossings": crossings, "length": length}


def svg(els, path):
    """Rough SVG preview of the scene (rectangles, lines, arrows, text) for a quick visual check."""
    xs = [e["x"] + e["width"] for e in els] + [0]
    ys = [e["y"] + e["height"] for e in els] + [0]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{max(xs) + 60:.0f}" height="{max(ys) + 60:.0f}" '
           'style="background:#fff;font-family:Menlo,monospace">']
    dash = {"dashed": "8 6", "dotted": "2 5", "solid": "none"}
    for e in els:
        st = f'stroke="{e["strokeColor"]}" stroke-width="{e["strokeWidth"]}" stroke-dasharray="{dash[e["strokeStyle"]]}"'
        if e["type"] == "rectangle":
            out.append(f'<rect x="{e["x"]:.1f}" y="{e["y"]:.1f}" width="{e["width"]:.1f}" height="{e["height"]:.1f}" '
                       f'fill="{e["backgroundColor"] if e["backgroundColor"] != "transparent" else "none"}" {st}/>')
        elif e["type"] in ("line", "arrow"):
            pts = " ".join(f'{e["x"] + px:.1f},{e["y"] + py:.1f}' for px, py in e["points"])
            mk = ' marker-end="url(#a)"' if e["type"] == "arrow" else ""
            out.append(f'<polyline points="{pts}" fill="none" {st}{mk}/>')
        elif e["type"] == "text":
            fam = "Menlo,monospace" if e["fontFamily"] == MONO else "'Comic Sans MS',cursive"
            out.append(f'<text x="{e["x"]:.1f}" y="{e["y"] + e["fontSize"]:.1f}" font-size="{e["fontSize"]}" '
                       f'font-family="{fam}" fill="{e["strokeColor"]}" xml:space="preserve">{e["text"].replace("<", "&lt;")}</text>')
    out.insert(1, '<defs><marker id="a" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" markerHeight="8" '
                  'orient="auto-start-reverse"><path d="M0,0L10,5L0,10" fill="none" stroke="#1e1e1e"/></marker></defs>')
    out.append("</svg>")
    open(path, "w").write("\n".join(out))


def write(path, els):
    scene = {"type": "excalidraw", "version": 2, "source": "mapping-database-schemas",
             "elements": els, "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None}, "files": {}}
    with open(path, "w") as f:
        json.dump(scene, f, indent=1)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main():
    a = sys.argv[1:]
    if len(a) < 3 or a[0] in ("-h", "--help"):
        sys.exit(USAGE)
    an, page, out = json.load(open(a[0])), json.load(open(a[1])), a[2]
    limit = int(a[a.index("--overview-at") + 1]) if "--overview-at" in a else 15
    tables = {t["name"]: t for t in an["tables"]}
    real = [n for n, t in tables.items() if t["kind"] == "table"]
    views = [n for n, t in tables.items() if t["kind"] != "table"]
    domains = [(d["name"], [n for n in d["tables"] if n in real]) for d in page.get("domains", [])]
    placed = {n for _, ns in domains for n in ns}
    if any(n not in placed for n in real):
        domains.append(("Other", [n for n in real if n not in placed]))
    title = page.get("title") or an["source"]["name"]
    rels = an["relationships"]
    grain = {n: (page.get("tables", {}).get(n, {}).get("grain") or "").rstrip(".") for n in tables}
    files = []

    def best(make, name, sub, bands, vs):
        """Hill-climb table columns to cut crossings; arrow length breaks ties so layouts stay compact."""
        tries = [bands] + ([[("Tables", [n for _, ns in bands for n in ns])]] if len(bands) > 1 else [])
        score = lambda st: (st["arrow_crossings"] + 5 * st["arrow_segments_through_boxes"], st["length"])
        winners, stop = [], time.time() + SEARCH_SECONDS
        for b in tries:
            cur = draw(name, make(), sub, b, vs)
            improved = True
            while improved and time.time() < stop:
                improved = False
                cols = dict(cur[1]["cols"])
                span = max(cols.values(), default=0)
                for n in sorted(cols):
                    for c in range(-1, span + 2):
                        if c == cols[n] or time.time() > stop:
                            continue
                        cand = draw(name, make(), sub, b, vs, cols=dict(cols, **{n: c}))
                        if score(cand[1]) < score(cur[1]):
                            cur, improved = cand, True
                            cols = dict(cur[1]["cols"])
                            span = max(cols.values(), default=0)
            winners.append(cur)
        return min(winners, key=lambda r: score(r[1])[0])

    bands = [d for d in domains if d[1]]
    if len(real) <= limit:
        files.append((out, best(lambda: {n: Box(tables[n], grain=grain[n]) for n in real + views}, title, rels,
                                bands, views)))
    else:
        files.append((out, best(lambda: {n: Box(tables[n], overview=True) for n in real}, f"{title}: overview",
                                rels, bands, [])))
        for name, members in domains:
            if not members:
                continue
            inside = set(members)
            sub = [r for r in rels if r["from"] in inside or r["to"] in inside]
            ghosts = defaultdict(set)
            for r in sub:
                for side, cols in ((r["from"], r["from_columns"]), (r["to"], r["to_columns"])):
                    if side not in inside:
                        ghosts[side] |= set(cols)
            dviews = [v for v in views if set(tables[v].get("reads", [])) & inside]

            def make(members=members, ghosts=ghosts, dviews=dviews):
                boxes = {n: Box(tables[n], grain=grain[n]) for n in members}
                boxes.update({n: Box(tables[n], ghost=True, keep=cols) for n, cols in ghosts.items()})
                boxes.update({v: Box(tables[v], grain=grain[v]) for v in dviews})
                return boxes
            dbands = [(name, members)] + ([("Linked from other areas", sorted(ghosts))] if ghosts else [])
            files.append((re.sub(r"\.excalidraw$", "", out) + f"-{slug(name)}.excalidraw",
                          best(make, f"{title}: {name}", sub, dbands, dviews)))
    for path, (els, stats) in files:
        write(path, els)
        if "--svg" in a:
            svg(els, re.sub(r"\.excalidraw$", "", path) + ".svg")
        print(f"Wrote {path}: {stats['boxes']} tables, {stats['arrows']} arrows | overlapping boxes "
              f"{stats['overlapping_boxes']}, arrows through boxes {stats['arrow_segments_through_boxes']}, "
              f"arrow crossings {stats['arrow_crossings']}")


if __name__ == "__main__":
    main()
