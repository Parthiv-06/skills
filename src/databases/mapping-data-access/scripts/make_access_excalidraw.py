"""Draw who reads and writes what in Excalidraw: writers left, tables middle, readers right.
One straight arrow per service-table pair, pointing the way data moves; order is searched."""
USAGE = """Usage:
  python3 make_access_excalidraw.py analysis.json page.json OUT.excalidraw [--split-at N] [--svg]

Columns alternate: services, one database's tables, services, the next database's tables, and so on.
Databases are ordered so a service that reads one and writes another sits between them; any other
service sits on whichever side of its database crosses fewer arrows. One straight arrow per service and
table, pointing the way data moves (both heads when it reads and writes). Solid when it writes, dashed
when it only reads, dotted when seen only in logs, thin grey for schema changes; write arrows carry their
operations. Reads through a view are drawn to the view, whose box names the tables behind it.
Above N services or 2N tables (default 12) it also writes OUT-<service>.excalidraw for each one.
Prints a self-check: overlapping boxes, arrows through boxes, arrow crossings."""
import json
import random
import re
import sys
import time
from collections import defaultdict

INK, GREY, FAINT, FLAME = "#1e1e1e", "#868e96", "#ced4da", "#c2410c"
HAND, MONO = 1, 3
PAD, HEAD, SLOT, V_GAP, BAND_GAP = 14, 46, 22, 26, 54
SEARCH_SECONDS = 12
random.seed(11)


def base(kind, x, y, w, h, **extra):
    el = {"type": kind, "id": extra.pop("id", f"{kind}-{random.getrandbits(40):x}"), "x": x, "y": y, "width": w,
          "height": h, "angle": 0, "strokeColor": INK, "backgroundColor": "transparent", "fillStyle": "solid",
          "strokeWidth": 1.5, "strokeStyle": "solid", "roughness": 0, "opacity": 100, "groupIds": [],
          "frameId": None, "roundness": None, "seed": random.getrandbits(30), "version": 1,
          "versionNonce": random.getrandbits(30), "isDeleted": False, "boundElements": [], "updated": 1,
          "link": None, "locked": False}
    el.update(extra)
    return el


def text(x, y, s, size=16, font=MONO, color=INK):
    return base("text", x, y, len(s) * size * (0.6 if font == MONO else 0.56) + 4, size * 1.25, text=s,
                originalText=s, fontSize=size, fontFamily=font, textAlign="left", verticalAlign="top",
                containerId=None, lineHeight=1.25, autoResize=True, strokeColor=color)


class Box:
    def __init__(self, key, title, sub, outside=False, view=False, table=False):
        self.key, self.title, self.sub, self.outside, self.view, self.table = key, title, sub, outside, view, table
        self.w = max(170, len(title) * 20 * 0.56 + 2 * PAD, len(sub) * 13 * 0.52 + 2 * PAD)
        self.x = self.y = 0
        self.col = 0


def pairs(links):
    """One drawn arrow per (participant, table): read and write merge into a two-headed arrow."""
    out = {}
    for lk in links:
        if lk["label"].startswith("via view"):
            continue
        k = (lk["participant"], lk["database"], lk["table"])
        e = out.setdefault(k, {"participant": k[0], "database": k[1], "table": k[2], "kinds": set(), "ops": [],
                               "labels": set(), "id": lk["id"]})
        e["kinds"].add(lk["kind"])
        e["labels"].add(lk["label"])
        if lk["kind"] != "read":
            e["ops"] += [o for o in lk["ops"] if o not in e["ops"]]
    return list(out.values())


def style(e):
    if e["kinds"] == {"ddl"}:
        return "solid", GREY, 1
    dotted = e["labels"] == {"logs only"}
    if "write" in e["kinds"]:
        return ("dotted" if dotted else "solid"), INK, 2
    return ("dotted" if dotted else "dashed"), INK, 1.5


def layout(boxes, arrows, cols, db_cols):
    """Place every column, then anchor each arrow on the box edges that face each other."""
    for ci, col in enumerate(cols):
        for k in col:
            boxes[k].col = ci
    count = defaultdict(int)
    for e in arrows:
        p, t = boxes[e["participant"]], boxes[(e["database"], e["table"])]
        count[(id(p), "R" if p.col < t.col else "L")] += 1
        count[(id(t), "L" if p.col < t.col else "R")] += 1
    for b in boxes.values():
        b.h = max(HEAD + 18, 22 + SLOT * max(count[(id(b), "L")], count[(id(b), "R")]) + 14)
    bands = []
    for ci in db_cols:
        y = 150 + 42
        for k in cols[ci]:
            boxes[k].y = y
            y += boxes[k].h + V_GAP
        bands.append((ci, cols[ci][0][0] if cols[ci] else "", 150, y - V_GAP + 18))
    for ci, col in enumerate(cols):
        if ci in db_cols:
            continue
        cur, placed = 150, []
        for k in col:
            ys = [boxes[(e["database"], e["table"])].y + boxes[(e["database"], e["table"])].h / 2
                  for e in arrows if e["participant"] == k]
            boxes[k].y = max(cur, sum(ys) / len(ys) - boxes[k].h / 2 if ys else cur)
            cur = boxes[k].y + boxes[k].h + V_GAP
            placed.append(k)
        for i in range(len(placed) - 2, -1, -1):
            a, nxt = boxes[placed[i]], boxes[placed[i + 1]]
            floor = 150 if i == 0 else boxes[placed[i - 1]].y + boxes[placed[i - 1]].h + V_GAP
            if a.y + a.h + V_GAP > nxt.y:
                a.y = max(floor, nxt.y - V_GAP - a.h)
    label_w = max([len(" · ".join(e["ops"])) * 7.4 for e in arrows] + [0])
    gap = max(230, label_w + 140)
    x = 60
    for ci, col in enumerate(cols):
        width = max([boxes[k].w for k in col] + [0])
        for k in col:
            boxes[k].x = x + (width - boxes[k].w if ci not in db_cols and ci == 0 else 0)
        if col:
            x += width + gap
    slots = defaultdict(list)
    for e in arrows:
        p, t = boxes[e["participant"]], boxes[(e["database"], e["table"])]
        pe, te = ("R", "L") if p.col < t.col else ("L", "R")
        slots[(id(p), pe)].append((t.y + t.h / 2, id(e), p))
        slots[(id(t), te)].append((p.y + p.h / 2, id(e), t))
    anchor = {}
    for (bid, edge), items in slots.items():
        items.sort(key=lambda it: it[0])
        box = items[0][2]
        start = box.y + (box.h - SLOT * (len(items) - 1)) / 2
        for i, (_, eid, _) in enumerate(items):
            anchor[(eid, bid)] = (box.x + (box.w if edge == "R" else 0), start + SLOT * i)
    routes = []
    for e in arrows:
        p, t = boxes[e["participant"]], boxes[(e["database"], e["table"])]
        routes.append((e, p, t, anchor[(id(e), id(p))], anchor[(id(e), id(t))]))
    rects = []
    for ci, name, top, bottom in bands:
        if cols[ci]:
            xs = [boxes[k].x for k in cols[ci]]
            ws = [boxes[k].x + boxes[k].w for k in cols[ci]]
            rects.append((name, min(xs) - 30, max(ws) + 30, top, bottom))
    return routes, rects


def cross(a, b, c, d):
    """True when segments ab and cd properly intersect (shared end points do not count)."""
    def o(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (v > 1e-9) - (v < -1e-9)
    if {a, b} & {c, d}:
        return False
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def crossings(routes):
    return sum(1 for i, r in enumerate(routes) for s in routes[i + 1:] if cross(r[3], r[4], s[3], s[4]))


def through(routes, boxes):
    n = 0
    for e, p, t, a, b in routes:
        for box in boxes:
            if box is p or box is t:
                continue
            for k in range(1, 20):
                x, y = a[0] + (b[0] - a[0]) * k / 20, a[1] + (b[1] - a[1]) * k / 20
                if box.x < x < box.x + box.w and box.y < y < box.y + box.h:
                    n += 1
                    break
    return n


def draw(title, an, parts_in, links, legend=True):
    arrows = pairs(links)
    view_of = defaultdict(set)
    for lk in links:
        if lk.get("via_view"):
            view_of[(lk["database"], lk["via_view"])].add(lk["table"])
    kinds = {(t["database"], t["name"]): t["kind"] for t in an["tables"]}
    boxes = {}
    for e in arrows:
        key = (e["database"], e["table"])
        if key not in boxes:
            kind = kinds.get(key, "table")
            view = kind not in ("table", "unknown")
            sub = f"view of {', '.join(sorted(view_of[key]))}" if view and view_of[key] else (kind if view else "")
            boxes[key] = Box(key, e["table"], sub, view=view, table=True)
    info = {}
    for p in parts_in:
        mine = [e for e in arrows if e["participant"] == p["name"]]
        if mine:
            sub = f"outside the repo: {p['kind']}" if p["external"] else p["kind"]
            boxes[p["name"]] = Box(p["name"], p["name"], sub, outside=p["external"])
            info[p["name"]] = mine

    dbs = sorted({k[0] for k in boxes if isinstance(k, tuple)}, key=lambda d: (-sum(
        1 for k in boxes if isinstance(k, tuple) and k[0] == d), d))
    after = defaultdict(set)
    for name, mine in info.items():
        reads = {e["database"] for e in mine if "read" in e["kinds"]}
        writes = {e["database"] for e in mine if e["kinds"] - {"read"}}
        for r in reads:
            for w in writes - {r}:
                after[w].add(r)
    order_db = []
    while len(order_db) < len(dbs):
        ready = [d for d in dbs if d not in order_db and after[d] <= set(order_db)] or \
            [d for d in dbs if d not in order_db]
        order_db.append(ready[0])
    db_index = {d: i for i, d in enumerate(order_db)}
    cols = [[] for _ in range(2 * len(order_db) + 1)]
    db_cols = [2 * i + 1 for i in range(len(order_db))]
    for k in sorted((k for k in boxes if isinstance(k, tuple)), key=lambda k: k[1]):
        cols[2 * db_index[k[0]] + 1].append(k)
    movable = {}
    for name, mine in info.items():
        idx = sorted({db_index[e["database"]] for e in mine})
        if len(idx) > 1:
            cols[2 * idx[0] + 2].append(name)
        else:
            writes = any(e["kinds"] - {"read"} for e in mine)
            home = 2 * idx[0] + (0 if writes else 2)
            cols[home].append(name)
            movable[name] = (2 * idx[0], 2 * idx[0] + 2)

    def score(c):
        r, _ = layout(boxes, arrows, c, db_cols)
        return crossings(r), sum(abs(b[1] - a[1]) for _, _, _, a, b in r)

    for _ in range(4):
        pos = {k: i for col in cols for i, k in enumerate(col)}
        for ci, col in enumerate(cols):
            def bary(k):
                mates = [pos[(e["database"], e["table"])] for e in arrows if e["participant"] == k] if \
                    not isinstance(k, tuple) else [pos[e["participant"]] for e in arrows
                                                   if (e["database"], e["table"]) == k]
                return sum(mates) / len(mates) if mates else 0
            col.sort(key=bary)
    def climb(cols, stop):
        best, improved = score(cols), True
        while improved and time.time() < stop and best[0]:
            improved = False
            for name, (a_col, b_col) in movable.items():
                cand = [list(c) for c in cols]
                src = a_col if name in cand[a_col] else b_col
                cand[src].remove(name)
                cand[b_col if src == a_col else a_col].append(name)
                s = score(cand)
                if s < best:
                    best, cols, improved = s, cand, True
            for ci in range(len(cols)):
                for i in range(len(cols[ci])):
                    for j in range(len(cols[ci])):
                        if i == j:
                            continue
                        cand = [list(c) for c in cols]
                        cand[ci].insert(j, cand[ci].pop(i))
                        s = score(cand)
                        if s < best:
                            best, cols, improved = s, cand, True
        return best, cols

    stop = time.time() + SEARCH_SECONDS
    best, cols = climb(cols, stop)
    rng = random.Random(5)
    while best[0] and time.time() < stop:
        start = [rng.sample(c, len(c)) for c in cols]
        cand_best, cand = climb(start, stop)
        if cand_best < best:
            best, cols = cand_best, cand
    routes, rects = layout(boxes, arrows, cols, db_cols)

    els = [text(60, 40, title, 28, HAND)]
    if legend:
        lx = 60
        for label, (st, col, w) in (("writes", ("solid", INK, 2)), ("reads", ("dashed", INK, 1.5)),
                                    ("seen only in logs", ("dotted", INK, 1.5)), ("schema change", ("solid", GREY, 1))):
            els.append(base("line", lx, 108, 34, 0, points=[[0, 0], [34, 0]], strokeStyle=st, strokeColor=col,
                            strokeWidth=w))
            els.append(text(lx + 42, 98, label, 15, HAND, GREY))
            lx += 64 + len(label) * 8.4
        els.append(text(lx + 10, 98, "arrows point the way data moves; two heads = reads and writes", 15, HAND, GREY))
    for name, x0, x1, top, bottom in rects:
        els.append(base("rectangle", x0, top, x1 - x0, bottom - top, strokeColor=FAINT, strokeStyle="dashed",
                        strokeWidth=1))
        els.append(text(x0 + 12, top + 8, name, 17, HAND, GREY))
    box_el = {}
    for b in boxes.values():
        stroke = GREY if b.outside else INK
        rect = base("rectangle", b.x, b.y, b.w, b.h, strokeColor=stroke, backgroundColor="#ffffff", roughness=1,
                    strokeWidth=1.5 if b.table else 2, strokeStyle="dashed" if b.outside or b.view else "solid",
                    roundness=None if b.table else {"type": 3})
        box_el[id(b)] = rect
        els += [rect, text(b.x + PAD, b.y + 10, b.title, 18 if b.table else 20, MONO if b.table else HAND, stroke)]
        if b.sub:
            els.append(text(b.x + PAD, b.y + 36, b.sub, 13, HAND, GREY))
    for e, p, t, pa, ta in routes:
        st, col, w = style(e)
        reads, writes = "read" in e["kinds"], bool(e["kinds"] - {"read"})
        src, dst, s_el, d_el = (pa, ta, p, t) if writes else (ta, pa, t, p)
        arrow = base("arrow", src[0], src[1], abs(dst[0] - src[0]), abs(dst[1] - src[1]), id=f"link-{e['id']}",
                     points=[[0, 0], [dst[0] - src[0], dst[1] - src[1]]], strokeStyle=st, strokeColor=col,
                     strokeWidth=w, lastCommittedPoint=None, startArrowhead="arrow" if reads and writes else None,
                     endArrowhead="arrow", elbowed=False,
                     startBinding={"elementId": box_el[id(s_el)]["id"], "focus": 0, "gap": 1},
                     endBinding={"elementId": box_el[id(d_el)]["id"], "focus": 0, "gap": 1})
        els.append(arrow)
        box_el[id(s_el)]["boundElements"].append({"id": arrow["id"], "type": "arrow"})
        box_el[id(d_el)]["boundElements"].append({"id": arrow["id"], "type": "arrow"})
        if writes:
            if e["kinds"] == {"ddl"}:
                short = {"CREATE TABLE": "create", "DROP TABLE": "drop", "CREATE INDEX": "index"}
                label = "schema: " + " · ".join(sorted({short.get(o, "alter") for o in e["ops"]}))
            else:
                label = " · ".join(o.replace("CREATE AS", "CTAS") for o in e["ops"][:3])
            width = len(label) * 7.6
            left_of_table = p.col < t.col
            lx = ta[0] - 16 - width if left_of_table else ta[0] + 16
            dy = (pa[1] - ta[1]) * (8 + width / 2) / max(1, abs(pa[0] - ta[0]))
            els.append(text(lx, ta[1] + dy - 17, label, 12, MONO, GREY if e["kinds"] == {"ddl"} else FLAME))
    allb = list(boxes.values())
    stats = {"boxes": len(allb), "arrows": len(routes), "crossings": crossings(routes), "through": through(routes, allb),
             "overlaps": sum(1 for i, a in enumerate(allb) for b in allb[i + 1:]
                             if a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h)}
    return els, stats


def svg(els, path):
    """Quick SVG preview of the scene for a visual check."""
    w = max(e["x"] + e["width"] for e in els) + 60
    h = max(e["y"] + e["height"] for e in els) + 60
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" style="background:#fff">',
           '<defs><marker id="a" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" markerHeight="8" '
           'orient="auto-start-reverse"><path d="M0,0L10,5L0,10" fill="none" stroke="#1e1e1e"/></marker></defs>']
    dash = {"dashed": "8 6", "dotted": "2 5", "solid": "none"}
    for e in els:
        st = f'stroke="{e["strokeColor"]}" stroke-width="{e["strokeWidth"]}" stroke-dasharray="{dash[e["strokeStyle"]]}"'
        if e["type"] == "rectangle":
            fill = e["backgroundColor"] if e["backgroundColor"] != "transparent" else "none"
            rx = 10 if e.get("roundness") else 0
            out.append(f'<rect x="{e["x"]:.1f}" y="{e["y"]:.1f}" width="{e["width"]:.1f}" height="{e["height"]:.1f}" '
                       f'rx="{rx}" fill="{fill}" {st}/>')
        elif e["type"] in ("line", "arrow"):
            pts = " ".join(f'{e["x"] + px:.1f},{e["y"] + py:.1f}' for px, py in e["points"])
            mk = (' marker-end="url(#a)"' + (' marker-start="url(#a)"' if e.get("startArrowhead") else "")) \
                if e["type"] == "arrow" else ""
            out.append(f'<polyline points="{pts}" fill="none" {st}{mk}/>')
        elif e["type"] == "text":
            fam = "Menlo,monospace" if e["fontFamily"] == MONO else "'Comic Sans MS',cursive"
            out.append(f'<text x="{e["x"]:.1f}" y="{e["y"] + e["fontSize"]:.1f}" font-size="{e["fontSize"]}" '
                       f'font-family="{fam}" fill="{e["strokeColor"]}" xml:space="preserve">'
                       f'{e["text"].replace("&", "&amp;").replace("<", "&lt;")}</text>')
    out.append("</svg>")
    open(path, "w").write("\n".join(out))


def write(path, els):
    with open(path, "w") as f:
        json.dump({"type": "excalidraw", "version": 2, "source": "mapping-data-access", "elements": els,
                   "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None}, "files": {}}, f, indent=1)


def main():
    a = sys.argv[1:]
    if len(a) < 3 or a[0] in ("-h", "--help"):
        sys.exit(USAGE)
    an, page, out = json.load(open(a[0])), json.load(open(a[1])), a[2]
    split = int(a[a.index("--split-at") + 1]) if "--split-at" in a else 12
    title = page.get("title") or "Who reads and writes what"
    jobs = [(out, title, an["participants"], an["links"])]
    inside = [p for p in an["participants"] if not p["external"]]
    if len(inside) > split or len(an["tables"]) > 2 * split:
        for p in an["participants"]:
            mine = [lk for lk in an["links"] if lk["participant"] == p["name"]]
            if mine:
                slug = re.sub(r"[^a-z0-9]+", "-", p["name"].lower()).strip("-")
                jobs.append((re.sub(r"\.excalidraw$", "", out) + f"-{slug}.excalidraw", f"{title}: {p['name']}",
                             [p], mine))
    for path, name, ps, ls in jobs:
        els, st = draw(name, an, ps, ls)
        write(path, els)
        if "--svg" in a:
            svg(els, re.sub(r"\.excalidraw$", "", path) + ".svg")
        print(f"Wrote {path}: {st['boxes']} boxes, {st['arrows']} arrows | overlapping boxes {st['overlaps']}, "
              f"arrows through boxes {st['through']}, arrow crossings {st['crossings']}")


if __name__ == "__main__":
    main()
