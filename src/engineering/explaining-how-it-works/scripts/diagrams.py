"""Turns a diagram spec into a laid-out .excalidraw file and a matching SVG (spec: diagram-style.md).
Usage: diagrams.py SPEC.json OUT_BASE; invalid specs raise SpecError listing every problem."""
import json
import math
import random
import sys

INK, GRAY, LIGHT, WHITE = "#1e1e1e", "#868e96", "#ced4da", "#ffffff"
FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"
LEVEL = {"context": "Level 1 · System context", "containers": "Level 2 · Containers", "components": "Level 3 · Components",
         "sequence": "Dynamic · Sequence", "state": "State", "data": "Data", "deployment": "Deployment"}
KINDS = {  # kind -> (stereotype line, legend label)
    "person": ("person", "Person"), "system": ("system", "Software system"), "service": (None, "Service / app"),
    "component": ("component", "Component"), "database": ("database", "Database"), "queue": ("queue", "Queue / stream"),
    "cache": ("cache", "Cache"), "storage": ("storage", "File / object storage"), "external": ("external", "External system"),
    "scheduler": ("cron", "Scheduler"), "state": (None, "State"), "entity": ("entity", "Entity"),
    "start": (None, "Start"), "end": (None, "End"),
}
MAX_ELEMENTS, MAX_PARTICIPANTS, MAX_MESSAGES = 15, 10, 32
BOX_W, COL_GAP, ROW_GAP, TOP = 230, 190, 70, 96
ZPAD, ZTOP = 26, 40


class SpecError(Exception):
    pass


def text_w(s, size):
    return len(s) * size * 0.56


def wrap(s, width_chars):
    words, lines, cur = (s or "").split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width_chars:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + ([cur] if cur else [])



def check(spec):
    errs, warn = [], []
    view = spec.get("view")
    if view not in LEVEL:
        errs.append(f"view: one of {', '.join(LEVEL)}")
    for k in ("title", "caption"):
        if not str(spec.get(k, "")).strip():
            errs.append(f"{k}: required")
    if view == "sequence":
        ps = spec.get("participants") or []
        ids = [p.get("id") for p in ps]
        if not 2 <= len(ps) <= MAX_PARTICIPANTS:
            errs.append(f"participants: 2-{MAX_PARTICIPANTS} (split the flow into two diagrams if more)")
        if len(set(ids)) != len(ids):
            errs.append("participants: ids must be unique")
        for i, p in enumerate(ps):
            if p.get("kind") not in KINDS:
                errs.append(f"participants[{i}].kind: one of {', '.join(KINDS)}")
            if not p.get("name"):
                errs.append(f"participants[{i}].name: required")
        msgs = spec.get("messages") or []
        if not msgs or len(msgs) > MAX_MESSAGES:
            errs.append(f"messages: 1-{MAX_MESSAGES}")
        last = None
        for i, m in enumerate(msgs):
            if "note" in m:
                over = m.get("over")
                for o in over if isinstance(over, list) else [over]:
                    if o not in ids:
                        errs.append(f"messages[{i}].over: unknown participant {o!r}")
                continue
            for end in ("from", "to"):
                if m.get(end) not in ids:
                    errs.append(f"messages[{i}].{end}: unknown participant {m.get(end)!r}")
            if not str(m.get("label", "")).strip():
                errs.append(f"messages[{i}].label: every message needs a label (verb + protocol)")
            if m.get("step") is not None:
                key = step_key(m["step"])
                if key is None:
                    errs.append(f"messages[{i}].step: like '3' or '3a'")
                elif last is not None and key < last:
                    errs.append(f"messages[{i}].step: {m['step']} comes after a later step; steps must not go backwards")
                else:
                    last = key
        for i, f in enumerate(spec.get("frames") or []):
            if f.get("type") not in ("alt", "opt", "loop", "par"):
                errs.append(f"frames[{i}].type: alt, opt, loop, or par")
            if not (isinstance(f.get("start"), int) and isinstance(f.get("end"), int) and 0 <= f["start"] <= f["end"] < len(msgs)):
                errs.append(f"frames[{i}]: start and end must be message indexes with start <= end")
            if f.get("type") == "alt" and not f.get("else"):
                errs.append(f"frames[{i}]: alt needs at least one else branch; use opt for a single optional block")
    else:
        els = spec.get("elements") or []
        ids = [e.get("id") for e in els]
        if not els:
            errs.append("elements: required")
        if len(els) > MAX_ELEMENTS:
            errs.append(f"elements: {len(els)} is too many for one diagram (max {MAX_ELEMENTS}); split it into two views or a lower level")
        if len(set(ids)) != len(ids):
            errs.append("elements: ids must be unique")
        zones = {z.get("id") for z in spec.get("zones") or []}
        for i, e in enumerate(els):
            if e.get("kind") not in KINDS:
                errs.append(f"elements[{i}].kind: one of {', '.join(KINDS)}")
            if not e.get("name") and e.get("kind") not in ("start", "end"):
                errs.append(f"elements[{i}].name: required")
            if e.get("zone") and e["zone"] not in zones:
                errs.append(f"elements[{i}].zone: unknown zone {e['zone']!r}")
        for i, l in enumerate(spec.get("links") or []):
            for end in ("from", "to"):
                if l.get(end) not in ids:
                    errs.append(f"links[{i}].{end}: unknown element {l.get(end)!r}")
            if not str(l.get("label", "")).strip() and spec.get("view") != "state":
                errs.append(f"links[{i}].label: every arrow needs a label (verb + protocol)")
            if l.get("step") is not None and step_key(l["step"]) is None:
                errs.append(f"links[{i}].step: like '3' or '3a'")
    if errs:
        raise SpecError("Diagram spec problems ({}):\n  ".format(spec.get("title", "untitled")) + "\n  ".join(errs))
    return warn


def step_key(s):
    s = str(s)
    num = "".join(ch for ch in s if ch.isdigit())
    rest = s[len(num):]
    if not num or not s.startswith(num) or len(rest) > 1 or (rest and not rest.isalpha()):
        return None
    return (int(num), rest)


# Every view is laid out into these, then emitted twice (Excalidraw JSON and SVG).

def P(t, **kw):
    kw["t"] = t
    return kw


def box_lines(e):
    stereo = KINDS[e["kind"]][0]
    lines = []
    if stereo and e["kind"] not in ("start", "end"):
        lines.append(("stereo", f"«{stereo}»"))
    if e.get("name"):
        lines.append(("name", e["name"]))
    if e.get("tech"):
        lines.append(("tech", f"[{e['tech']}]"))
    for ln in wrap(e.get("does"), 30)[:3]:
        lines.append(("does", ln))
    return lines


def box_size(e, w=BOX_W):
    if e["kind"] in ("start", "end"):
        return 28, 28
    lines = box_lines(e)
    fields = e.get("fields") or []
    h = 22 + 19 * len(lines) + (14 + 18 * len(fields) if fields else 0)
    if e["kind"] == "database":
        h += 22
    return w, max(h, 64)


def shape_prims(e, x, y, w, h):
    """Outline primitives for an element's kind, plus its label lines."""
    k, out = e["kind"], []
    gid = "g_" + e["id"]
    if k == "start":
        return [P("ellipse", id=e["id"], x=x, y=y, w=w, h=h, fill=INK, stroke=INK, group=gid)]
    if k == "end":
        return [P("ellipse", id=e["id"], x=x, y=y, w=w, h=h, fill=WHITE, stroke=INK, group=gid),
                P("ellipse", x=x + 6, y=y + 6, w=w - 12, h=h - 12, fill=INK, stroke=INK, group=gid)]
    if k == "storage":
        c = min(18, w / 4, h / 3)
        out.append(P("poly", points=[(x, y), (x + w - c, y), (x + w, y + c), (x + w, y + h), (x, y + h)], closed=True,
                     fill=WHITE, stroke=INK, group=gid))
        out.append(P("poly", points=[(x + w - c, y), (x + w - c, y + c), (x + w, y + c)], stroke=INK, group=gid))
        out.append(P("rect", id=e["id"], x=x, y=y, w=w, h=h, stroke=None, fill=None, group=gid, container=True))
    elif k == "database":
        ry = 11
        pts = [(x, y + ry)] + [(x + w / 2 - w / 2 * math.cos(a), y + h - ry + ry * math.sin(a))
                               for a in [i * math.pi / 12 for i in range(13)]] + [(x + w, y + ry)] + \
              [(x + w / 2 + w / 2 * math.cos(a), y + ry - ry * math.sin(a)) for a in [i * math.pi / 12 for i in range(13)]]
        out.append(P("poly", points=pts, closed=True, fill=WHITE, stroke=INK, group=gid))
        out.append(P("ellipse", x=x, y=y, w=w, h=2 * ry, fill=WHITE, stroke=INK, group=gid))
        out.append(P("rect", id=e["id"], x=x, y=y + 2 * ry, w=w, h=h - 3 * ry, stroke=None, fill=None, group=gid, container=True))
    else:
        out.append(P("rect", id=e["id"], x=x, y=y, w=w, h=h, stroke=INK, fill=WHITE, group=gid,
                     dashed=k == "external", rounded=k in ("person", "state"), heavy=k == "system", container=True))
        if k == "queue":
            out += [P("poly", points=[(x + 10, y), (x + 10, y + h)], stroke=INK, group=gid),
                    P("poly", points=[(x + w - 10, y), (x + w - 10, y + h)], stroke=INK, group=gid)]
        if k == "component":  # UML component icon, scaled down for the legend swatch
            s = 1 if w >= 60 else 0.55
            ix, iy = x + w - 24 * s - 4, y + 7 * s
            out += [P("rect", x=ix, y=iy, w=16 * s, h=12 * s, stroke=INK, fill=WHITE, group=gid),
                    P("rect", x=ix - 4 * s, y=iy + 2 * s, w=8 * s, h=3 * s, stroke=INK, fill=WHITE, group=gid),
                    P("rect", x=ix - 4 * s, y=iy + 7 * s, w=8 * s, h=3 * s, stroke=INK, fill=WHITE, group=gid)]
    out.append(P("label", x=x, y=y + (22 if k == "database" else 0), w=w, h=h - (33 if k == "database" else 0),
                 lines=box_lines(e), fields=e.get("fields") or [], owner=e["id"], group=gid))
    return out


def legend_prims(kinds, arrows, zones_used, x, y, steps=False):
    out, cx = [], x
    out.append(P("text", x=x, y=y, text="LEGEND", size=11, color=GRAY, weight=700))
    y += 22
    for k in kinds:
        e = {"id": "lg_" + k, "kind": k, "name": ""}
        if k in ("start", "end"):
            out += shape_prims(e, cx, y + 2, 16, 16)
        else:
            sub = shape_prims(e, cx, y, 34, 20)
            out += [p for p in sub if p["t"] != "label"]
        out.append(P("text", x=cx + 42, y=y + 3, text=KINDS[k][1], size=12, color=INK))
        cx += 42 + text_w(KINDS[k][1], 12) + 26
    for name, dashed, head in arrows:
        out.append(P("arrow", points=[(cx, y + 10), (cx + 34, y + 10)], dashed=dashed, head=head))
        out.append(P("text", x=cx + 42, y=y + 3, text=name, size=12, color=INK))
        cx += 42 + text_w(name, 12) + 26
    if zones_used:
        out.append(P("rect", x=cx, y=y, w=34, h=20, stroke=GRAY, fill=None, dashed=True))
        out.append(P("text", x=cx + 42, y=y + 3, text="Boundary", size=12, color=INK))
        cx += 42 + text_w("Boundary", 12) + 26
    if steps:
        out.append(P("badge", x=cx + 10, y=y + 10, text="1"))
        out.append(P("text", x=cx + 28, y=y + 3, text="Step (matches the trace table)", size=12, color=INK))
    return out


def frame_prims(spec):
    return [P("text", x=0, y=0, text=spec["title"], size=24, color=INK, weight=700),
            P("text", x=0, y=34, text=LEVEL[spec["view"]].upper(), size=12, color=GRAY, weight=600)]



def layout_boxes(spec):
    els = spec["elements"]
    zones = {z["id"]: z for z in spec.get("zones") or []}
    cols, col_of = [], {}
    for e in els:
        key = e.get("zone") or "_" + e["id"]
        if "col" in e:
            key = ("col", e["col"])
        if key not in col_of:
            col_of[key] = len(cols)
            cols.append([])
        cols[col_of[key]].append(e)
    if any(isinstance(k, tuple) for k in col_of):  # explicit columns sort by their number
        order = sorted(col_of, key=lambda k: k[1] if isinstance(k, tuple) else 10_000 + col_of[k])
        cols = [cols[col_of[k]] for k in order]

    sizes = {e["id"]: box_size(e, BOX_W if e["kind"] != "component" else 200) for e in els}
    row_h = max(h for _, h in sizes.values()) + ROW_GAP
    pos, x = {}, 0
    for col in cols:
        cw = max(sizes[e["id"]][0] for e in col)
        for i, e in enumerate(col):
            w, h = sizes[e["id"]]
            r = e.get("row", i)
            pos[e["id"]] = (x + (cw - w) / 2, TOP + ZTOP + r * row_h + (row_h - ROW_GAP - h) / 2, w, h)
        x += cw + COL_GAP

    prims = frame_prims(spec)
    zrects = {}
    for zid, z in zones.items():
        inside = [pos[e["id"]] for e in els if e.get("zone") == zid]
        if not inside:
            continue
        x0 = min(p[0] for p in inside) - ZPAD
        y0 = min(p[1] for p in inside) - ZTOP
        x1 = max(p[0] + p[2] for p in inside) + ZPAD
        y1 = max(p[1] + p[3] for p in inside) + ZPAD
        zrects[zid] = (x0, y0, x1, y1)
        prims.append(P("rect", x=x0, y=y0, w=x1 - x0, h=y1 - y0, stroke=GRAY, fill=None, dashed=True, zone=True))
        label = z.get("label", zid).upper() + ("  ·  TRUST BOUNDARY" if z.get("trust") else "")
        prims.append(P("text", x=x0 + 12, y=y0 + 12, text=label, size=11, color=GRAY, weight=700))
    clash = []
    for a in zrects:
        for b in zrects:
            ra, rb = zrects[a], zrects[b]
            if a < b and ra[0] < rb[2] and rb[0] < ra[2] and ra[1] < rb[3] and rb[1] < ra[3]:
                clash.append(f"zones {a!r} and {b!r} overlap; give their elements separate col/row ranges")
    if clash:
        raise SpecError("Diagram layout problems ({}):\n  ".format(spec["title"]) + "\n  ".join(clash))

    for e in els:
        prims += shape_prims(e, *pos[e["id"]])

    links = spec.get("links") or []
    routes = route_all(links, pos)
    pairs, lanes = {}, []
    for l in links:
        pk = frozenset((l["from"], l["to"]))
        pairs[pk] = pairs.get(pk, 0) + 1
        lanes.append(pairs[pk] - 1)
    for l, pts, lane in zip(links, routes, lanes):
        shared = pairs[frozenset((l["from"], l["to"]))] > 1
        prims.append(P("arrow", points=pts, dashed=bool(l.get("async")), head="arrow", lane=lane if shared else None,
                       src=l["from"], dst=l["to"], label=l.get("label"), step=l.get("step")))

    warn = []
    boxes = {e["id"]: pos[e["id"]] for e in els}
    for l, pts in zip(links, routes):
        for oid, (bx, by, bw, bh) in boxes.items():
            if oid in (l["from"], l["to"]):
                continue
            if any(seg_hits_box(p, q, (bx + 4, by + 4, bw - 8, bh - 8)) for p, q in zip(pts, pts[1:])):
                warn.append(f"arrow {l['from']} -> {l['to']} passes through {oid}; set row/col to reroute")
    kinds = list(dict.fromkeys(e["kind"] for e in els))
    arrows = [("Synchronous", False, "arrow")] + ([("Async / event", True, "arrow")] if any(l.get("async") for l in links) else [])
    bottom = max(p[1] + p[3] for p in pos.values()) + ZPAD + 50
    prims += legend_prims(kinds, arrows, bool(zones), 0, bottom, any(l.get("step") for l in links))
    return prims, warn


PORT_GAP, TURN = 16, 30


def route_all(links, pos):
    """Orthogonal routes with one port per arrow end, spread along each side so arrows never share a point.
    Ports aim level with the other box, so arrows between aligned boxes stay straight."""
    center = {k: (x + w / 2, y + h / 2) for k, (x, y, w, h) in pos.items()}
    ends, sides = {}, []
    for i, l in enumerate(links):
        (acx, acy), (bcx, bcy) = center[l["from"]], center[l["to"]]
        if abs(acx - bcx) < 1:
            sa, sb = ("bottom", "top") if bcy > acy else ("top", "bottom")
        else:
            sa, sb = ("right", "left") if bcx > acx else ("left", "right")
        sides.append((sa, sb))
        ends.setdefault((l["from"], sa), []).append((i, 0, l["to"]))
        ends.setdefault((l["to"], sb), []).append((i, 1, l["from"]))

    port = {}
    for (eid, side), items in ends.items():
        x, y, w, h = pos[eid]
        horiz = side in ("left", "right")
        lo, hi = (y + 10, y + h - 10) if horiz else (x + 14, x + w - 14)
        want = sorted(((min(max(center[o][1 if horiz else 0], lo), hi), i, which) for i, which, o in items))
        placed = []
        for v, i, which in want:
            placed.append([max(v, placed[-1][0] + PORT_GAP) if placed else v, i, which])
        for k in range(len(placed) - 1, -1, -1):  # pull back from the far edge, moving only the ends that must move
            cap = hi if k == len(placed) - 1 else placed[k + 1][0] - PORT_GAP
            placed[k][0] = min(placed[k][0], cap)
        if placed and placed[0][0] < lo:  # too many ends for this side: spread them evenly instead
            n = len(placed)
            for k, p in enumerate(placed):
                p[0] = lo + (hi - lo) * (k + 0.5) / n
        for v, i, which in placed:
            edge = {"left": x, "right": x + w, "top": y, "bottom": y + h}[side]
            port[(i, which)] = (edge, v) if horiz else (v, edge)

    # Elbows leaving one side toward the same vertical direction never cross if the port nearest
    # their targets turns first: going down, the lowest port turns closest to the box.
    fans = {}
    for i, l in enumerate(links):
        (sx, sy), (ex, ey) = port[(i, 0)], port[(i, 1)]
        if sides[i][0] in ("left", "right") and abs(sy - ey) >= 1:
            fans.setdefault((l["from"], sides[i][0], ey > sy), []).append((sy, i))
    turn_k = {}
    for (_, _, down), items in fans.items():
        for k, (_, i) in enumerate(sorted(items, reverse=down)):
            turn_k[i] = k

    routes = []
    for i, l in enumerate(links):
        (sx, sy), (ex, ey) = port[(i, 0)], port[(i, 1)]
        if sides[i][0] in ("left", "right"):
            if abs(sy - ey) < 1:
                routes.append([(sx, sy), (ex, ey)])
                continue
            d = 1 if ex > sx else -1
            mid = sx + d * (TURN + 14 * turn_k[i])
            routes.append([(sx, sy), (mid, sy), (mid, ey), (ex, ey)])
        else:
            if abs(sx - ex) < 1:
                routes.append([(sx, sy), (ex, ey)])
                continue
            mid = (sy + ey) / 2
            routes.append([(sx, sy), (sx, mid), (ex, mid), (ex, ey)])
    return routes


def seg_hits_box(p, q, box):
    x, y, w, h = box
    for i in range(21):
        t = i / 20
        px, py = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        if x < px < x + w and y < py < y + h:
            return True
    return False



def layout_sequence(spec):
    ps, msgs = spec["participants"], spec["messages"]
    idx = {p["id"]: i for i, p in enumerate(ps)}
    widest = 0
    for m in msgs:
        if "note" in m:
            continue
        span = max(1, abs(idx[m["to"]] - idx[m["from"]]))
        lbl = (f"{m['step']}  " if m.get("step") else "") + m["label"]
        widest = max(widest, text_w(lbl, 13) / span + 50)
    pw = 190
    gap = max(250, min(420, widest))
    cx = {p["id"]: pw / 2 + i * gap for i, p in enumerate(ps)}

    prims = frame_prims(spec)
    top = TOP
    heights = [box_size(dict(p, does=None), pw)[1] for p in ps]
    ph = max(heights)
    for p in ps:
        prims += shape_prims(dict(p, does=None), cx[p["id"]] - pw / 2, top, pw, ph)

    frames = spec.get("frames") or []
    rows, y = [], top + ph + 56
    for i, m in enumerate(msgs):
        y += 34 * sum(1 for f in frames if f["start"] == i) + 26 * sum(1 for f in frames for el in f.get("else") or [] if el["at"] == i)
        rows.append(y)
        y += 58 if "note" in m else 70 if m["from"] == m["to"] else 50
        y += 22 * sum(1 for f in frames if f["end"] == i)
    end_y = y + 10

    for p in ps:
        prims.append(P("poly", points=[(cx[p["id"]], top + ph), (cx[p["id"]], end_y)], stroke=GRAY, dashed=True, lifeline=True))

    for f in frames:  # inner frames inset by their nesting depth
        depth = sum(1 for g in frames if g is not f and g["start"] <= f["start"] and f["end"] <= g["end"])
        involved = set()
        for m in msgs[f["start"]:f["end"] + 1]:
            if "note" in m:
                over = m["over"] if isinstance(m["over"], list) else [m["over"]]
                involved.update(over)
            else:
                involved.update((m["from"], m["to"]))
        xs = [cx[i] for i in involved]
        x0, x1 = min(xs) - 120 + depth * 10, max(xs) + 120 - depth * 10
        y0 = rows[f["start"]] - 44 + depth * 8
        y1 = rows[f["end"]] + (28 if "note" not in msgs[f["end"]] else 36) + (40 if msgs[f["end"]].get("from") == msgs[f["end"]].get("to") else 0) - depth * 6
        prims.append(P("rect", x=x0, y=y0, w=x1 - x0, h=y1 - y0, stroke=INK, fill=None))
        tag = f["type"]
        prims.append(P("poly", points=[(x0, y0 + 20), (x0 + text_w(tag, 12) + 16, y0 + 20), (x0 + text_w(tag, 12) + 24, y0 + 12),
                                       (x0 + text_w(tag, 12) + 24, y0)], stroke=INK))
        prims.append(P("text", x=x0 + 6, y=y0 + 4, text=tag, size=12, color=INK, weight=700))
        prims.append(P("text", x=x0 + text_w(tag, 12) + 32, y=y0 + 4, text=f"[{f.get('label', '')}]", size=12, color=INK))
        for el in f.get("else") or []:
            ey = rows[el["at"]] - 30
            prims.append(P("poly", points=[(x0, ey), (x1, ey)], stroke=INK, dashed=True))
            prims.append(P("text", x=x0 + 8, y=ey + 4, text=f"[{el.get('label', 'else')}]", size=12, color=INK))

    for m, y in zip(msgs, rows):
        if "note" in m:
            over = m["over"] if isinstance(m["over"], list) else [m["over"]]
            xs = [cx[o] for o in over]
            w = max(max(xs) - min(xs) + 120, min(300, text_w(m["note"], 12) + 24))
            mx = (max(xs) + min(xs)) / 2
            lines = wrap(m["note"], int(w / 6.8))[:2]
            h = 14 + 16 * len(lines)
            prims.append(P("rect", x=mx - w / 2, y=y - 14, w=w, h=h, stroke=GRAY, fill="#f8f9fa", note=True))
            for i, ln in enumerate(lines):
                prims.append(P("text", x=mx, y=y - 7 + 16 * i, text=ln, size=12, color=INK, align="center"))
            continue
        x1, x2 = cx[m["from"]], cx[m["to"]]
        dashed = bool(m.get("async") or m.get("return"))
        head = "open" if m.get("return") else "arrow"
        if x1 == x2:
            pts = [(x1, y), (x1 + 60, y), (x1 + 60, y + 26), (x1 + 4, y + 26)]
            lx = x1 + 68
            align = "left"
        else:
            d = 1 if x2 > x1 else -1
            pts = [(x1 + d * 2, y), (x2 - d * 4, y)]
            lx, align = (x1 + x2) / 2, "center"
        prims.append(P("arrow", points=pts, dashed=dashed, head=head, label=None, step=m.get("step")))
        lbl = m["label"]
        if align == "center":
            prims.append(P("text", x=lx + (11 if m.get("step") else 0), y=y - 19, text=lbl, size=13, color=INK, align="center", bg=True))
        else:
            prims.append(P("text", x=lx, y=y + 4, text=lbl, size=13, color=INK, bg=True))

    kinds = list(dict.fromkeys(p["kind"] for p in ps))
    arrows = [("Call", False, "arrow")]
    if any(m.get("async") for m in msgs if "note" not in m):
        arrows.append(("Async message", True, "arrow"))
    if any(m.get("return") for m in msgs if "note" not in m):
        arrows.append(("Return", True, "open"))
    prims += legend_prims(kinds, arrows, False, 0, end_y + 40, any(m.get("step") for m in msgs))
    return prims, []


def layout(spec):
    check(spec)
    return layout_sequence(spec) if spec["view"] == "sequence" else layout_boxes(spec)



def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def bounds(prims):
    xs, ys = [], []
    for p in prims:
        if "points" in p:
            xs += [q[0] for q in p["points"]]
            ys += [q[1] for q in p["points"]]
        elif p["t"] == "text":
            xs += [p["x"] - (text_w(p["text"], p["size"]) / 2 if p.get("align") == "center" else 0),
                   p["x"] + text_w(p["text"], p["size"])]
            ys += [p["y"], p["y"] + p["size"] * 1.3]
        elif "w" in p:
            xs += [p["x"], p["x"] + p["w"]]
            ys += [p["y"], p["y"] + p["h"]]
    return min(xs), min(ys), max(xs), max(ys)


def step_badge(pts):
    (x1, y1), (x2, y2) = pts[0], pts[1]
    L = math.hypot(x2 - x1, y2 - y1) or 1
    d = min(20, L / 2)
    return x1 + (x2 - x1) / L * d, y1 + (y2 - y1) / L * d


def label_anchor(pts, lane=None):
    """Where an arrow's label goes, as (x, y, mode); mode is above, below, center, left or right of x.
    Lane 1 of two arrows between the same boxes takes the other side of its line, so labels never stack."""
    if len(pts) == 4:
        (x2, y2), (x3, y3) = pts[2], pts[3]
        if abs(y2 - y3) < 1:  # elbow ending in a long horizontal run: label it there
            return (x2 + x3) / 2, y3 + (13 if lane == 1 else -13), "below" if lane == 1 else "above"
        return (pts[1][0] + pts[2][0]) / 2, (pts[1][1] + pts[2][1]) / 2, "center"
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    if abs(y1 - y2) < 1:
        return (x1 + x2) / 2 + 10, y1 + (13 if lane == 1 else -13), "below" if lane == 1 else "above"
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    if lane is None:
        return mx, my, "center"
    return (mx + 10, my, "right") if lane == 1 else (mx - 10, my, "left")


def to_svg(prims, title=""):
    x0, y0, x1, y1 = bounds(prims)
    m = 32
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0 - m:.0f} {y0 - m:.0f} {x1 - x0 + 2 * m:.0f} {y1 - y0 + 2 * m:.0f}" '
           f'role="img" aria-label="{esc(title)}" font-family="{FONT}">',
           '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">'
           f'<path d="M0,0 L10,5 L0,10 z" fill="{INK}"/></marker>'
           '<marker id="ao" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">'
           f'<path d="M0,0 L10,5 L0,10" fill="none" stroke="{INK}" stroke-width="1.4"/></marker></defs>',
           f'<rect x="{x0 - m:.0f}" y="{y0 - m:.0f}" width="{x1 - x0 + 2 * m:.0f}" height="{y1 - y0 + 2 * m:.0f}" fill="{WHITE}"/>']
    late = []
    for p in prims:
        t = p["t"]
        dash = ' stroke-dasharray="6 5"' if p.get("dashed") else ""
        if t == "rect":
            if not p.get("stroke") and not p.get("fill"):
                continue
            rx = ' rx="12"' if p.get("rounded") else ""
            sw = 2.4 if p.get("heavy") else (1 if p.get("zone") or p.get("note") else 1.6)
            out.append(f'<rect x="{p["x"]:.1f}" y="{p["y"]:.1f}" width="{p["w"]:.1f}" height="{p["h"]:.1f}"{rx} '
                       f'fill="{p.get("fill") or "none"}" stroke="{p.get("stroke") or "none"}" stroke-width="{sw}"{dash}/>')
        elif t == "ellipse":
            out.append(f'<ellipse cx="{p["x"] + p["w"] / 2:.1f}" cy="{p["y"] + p["h"] / 2:.1f}" rx="{p["w"] / 2:.1f}" ry="{p["h"] / 2:.1f}" '
                       f'fill="{p.get("fill") or "none"}" stroke="{p.get("stroke") or INK}" stroke-width="1.6"/>')
        elif t == "poly":
            pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in p["points"])
            tag = "polygon" if p.get("closed") else "polyline"
            out.append(f'<{tag} points="{pts}" fill="{p.get("fill") or "none"}" stroke="{p.get("stroke") or INK}" '
                       f'stroke-width="{1 if p.get("lifeline") else 1.6}"{dash}/>')
        elif t == "arrow":
            pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in p["points"])
            mk = "ao" if p.get("head") == "open" else "ah"
            out.append(f'<polyline points="{pts}" fill="none" stroke="{INK}" stroke-width="1.5"{dash} marker-end="url(#{mk})"/>')
            if p.get("label"):
                lx, ly, mode = label_anchor(p["points"], p.get("lane"))
                w = text_w(p["label"], 12.5) + 12
                bx = lx - w if mode == "left" else lx if mode == "right" else lx - w / 2
                late.append(f'<rect x="{bx:.1f}" y="{ly - 10:.1f}" width="{w:.1f}" height="20" fill="{WHITE}"/>'
                            f'<text x="{bx + w / 2:.1f}" y="{ly + 4.5:.1f}" font-size="12.5" text-anchor="middle" '
                            f'fill="{INK}">{esc(p["label"])}</text>')
            if p.get("step"):
                late.append(svg_badge(*step_badge(p["points"]), p["step"]))
        elif t == "badge":
            out.append(svg_badge(p["x"], p["y"], p["text"]))
        elif t == "text":
            anchor = ' text-anchor="middle"' if p.get("align") == "center" else ""
            weight = f' font-weight="{p["weight"]}"' if p.get("weight") else ""
            spacing = ' letter-spacing="0.06em"' if p.get("weight") and p["size"] <= 12 else ""
            txt = (f'<text x="{p["x"]:.1f}" y="{p["y"] + p["size"]:.1f}" font-size="{p["size"]}"{weight}{anchor}{spacing} '
                   f'fill="{p.get("color", INK)}">{esc(p["text"])}</text>')
            if p.get("bg"):
                w = text_w(p["text"], p["size"]) + 10
                bx = p["x"] - w / 2 if p.get("align") == "center" else p["x"] - 5
                late.append(f'<rect x="{bx:.1f}" y="{p["y"] - 2:.1f}" width="{w:.1f}" height="{p["size"] + 8}" fill="{WHITE}"/>' + txt)
            else:
                out.append(txt)
        elif t == "label":
            out.append(svg_label(p))
    return "\n".join(out + late + ["</svg>"])


def svg_badge(x, y, step):
    size = 10.5 if len(str(step)) < 3 else 9
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="{INK}"/><text x="{x:.1f}" y="{y + 4:.1f}" font-size="{size}" '
            f'font-weight="700" text-anchor="middle" fill="{WHITE}">{esc(step)}</text>')


STYLE = {"stereo": (11.5, 400, GRAY), "name": (15, 700, INK), "tech": (12.5, 400, GRAY), "does": (13, 400, INK)}


def svg_label(p):
    lines, fields = p["lines"], p["fields"]
    total = 19 * len(lines) + (14 + 18 * len(fields) if fields else 0)
    y = p["y"] + (p["h"] - total) / 2 + 14
    cx = p["x"] + p["w"] / 2
    out = []
    for kind, txt in lines:
        size, weight, color = STYLE[kind]
        out.append(f'<text x="{cx:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" text-anchor="middle" fill="{color}">{esc(txt)}</text>')
        y += 19
    if fields:
        out.append(f'<line x1="{p["x"]:.1f}" x2="{p["x"] + p["w"]:.1f}" y1="{y - 8:.1f}" y2="{y - 8:.1f}" stroke="{INK}" stroke-width="1"/>')
        y += 8
        for f in fields:
            out.append(f'<text x="{p["x"] + 14:.1f}" y="{y:.1f}" font-size="12" font-family="ui-monospace, Menlo, monospace" fill="{INK}">{esc(f)}</text>')
            y += 18
    return "".join(out)



def to_excalidraw(prims):
    rnd = random.Random(7)
    els, by_id = [], {}

    def base(kind, x, y, w, h, **kw):
        el = {"type": kind, "id": kw.pop("id", None) or f"el{len(els)}", "x": x, "y": y, "width": w, "height": h, "angle": 0,
              "strokeColor": INK, "backgroundColor": "transparent", "fillStyle": "solid", "strokeWidth": 1,
              "strokeStyle": "solid", "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None, "roundness": None,
              "seed": rnd.randint(1, 2 ** 31), "version": 1, "versionNonce": rnd.randint(1, 2 ** 31), "isDeleted": False,
              "boundElements": [], "updated": 1, "link": None, "locked": False}
        el.update(kw)
        els.append(el)
        return el

    def text(x, y, s, size, color=INK, align="left", container=None, w=None, h=None):
        lines = s.split("\n")
        tw = w or max(text_w(ln, size) for ln in lines)
        th = h or len(lines) * size * 1.25
        return base("text", x, y, tw, th, text=s, originalText=s, fontSize=size, fontFamily=2, textAlign=align,
                    verticalAlign="middle" if container else "top", containerId=container, lineHeight=1.25,
                    autoResize=True, strokeColor=color)

    def exc_badge(x, y, step, grp):
        badge = base("ellipse", x - 10, y - 10, 20, 20, backgroundColor=INK, groupIds=list(grp))
        t2 = text(x - 10, y - 10, str(step), 10, color=WHITE, align="center", container=badge["id"], w=20, h=20)
        t2["groupIds"] = list(grp)
        badge["boundElements"].append({"type": "text", "id": t2["id"]})

    for p in prims:
        t = p["t"]
        group = [p["group"]] if p.get("group") else []
        style = "dashed" if p.get("dashed") else "solid"
        if t == "rect":
            transparent = not p.get("stroke")
            el = base("rectangle", p["x"], p["y"], p["w"], p["h"], id=p.get("id"), groupIds=group,
                      strokeColor="transparent" if transparent else p["stroke"],
                      backgroundColor=p.get("fill") or "transparent", strokeStyle=style,
                      strokeWidth=2 if p.get("heavy") else 1,
                      roundness={"type": 3} if p.get("rounded") else None)
            if p.get("id"):
                by_id[p["id"]] = el
        elif t == "ellipse":
            el = base("ellipse", p["x"], p["y"], p["w"], p["h"], id=p.get("id"), groupIds=group,
                      strokeColor=p.get("stroke") or INK, backgroundColor=p.get("fill") or "transparent")
            if p.get("id"):
                by_id[p["id"]] = el
        elif t == "poly":
            x0, y0 = p["points"][0]
            pts = [[a - x0, b - y0] for a, b in p["points"]] + ([[0, 0]] if p.get("closed") else [])
            xs, ys = [q[0] for q in pts], [q[1] for q in pts]
            base("line", x0, y0, max(xs) - min(xs), max(ys) - min(ys), points=pts, groupIds=group, strokeStyle=style,
                 strokeColor=p.get("stroke") or INK, backgroundColor=p.get("fill") or "transparent",
                 lastCommittedPoint=None, startBinding=None, endBinding=None, startArrowhead=None, endArrowhead=None,
                 polygon=bool(p.get("closed")))
        elif t == "arrow":
            x0, y0 = p["points"][0]
            pts = [[a - x0, b - y0] for a, b in p["points"]]
            xs, ys = [q[0] for q in pts], [q[1] for q in pts]
            arrow = base("arrow", x0, y0, max(xs) - min(xs), max(ys) - min(ys), points=pts, strokeStyle=style,
                         lastCommittedPoint=None, startArrowhead=None,
                         endArrowhead="arrow" if p.get("head") == "open" else "triangle",
                         startBinding=None, endBinding=None)
            for end, key in ((p.get("src"), "startBinding"), (p.get("dst"), "endBinding")):
                box = by_id.get(end)
                if box:
                    px, py = p["points"][0] if key == "startBinding" else p["points"][-1]
                    arrow[key] = {"elementId": box["id"], "focus": 0, "gap": 1,
                                  "fixedPoint": [round((px - box["x"]) / box["width"], 3), round((py - box["y"]) / box["height"], 3)]}
                    box["boundElements"].append({"type": "arrow", "id": arrow["id"]})
            grp = [arrow["id"] + "_g"]  # label and badge are free elements grouped with the arrow, so they move together
            arrow["groupIds"] = grp
            if p.get("label"):
                lx, ly, mode = label_anchor(p["points"], p.get("lane"))
                tw = text_w(p["label"], 13)
                tx = lx - tw - 6 if mode == "left" else lx + 6 if mode == "right" else lx - tw / 2
                if mode not in ("above", "below"):
                    base("rectangle", tx - 5, ly - 10, tw + 10, 20, strokeColor="transparent",
                         backgroundColor=WHITE, groupIds=grp)
                text(tx, ly - 8, p["label"], 13, align="center")["groupIds"] = grp
            if p.get("step"):
                exc_badge(*step_badge(p["points"]), p["step"], grp)
        elif t == "badge":
            exc_badge(p["x"], p["y"], p["text"], [])
        elif t == "text":
            x = p["x"] - (text_w(p["text"], p["size"]) / 2 if p.get("align") == "center" else 0)
            if p.get("bg"):
                w = text_w(p["text"], p["size"]) + 10
                base("rectangle", x - 5, p["y"] - 2, w, p["size"] + 8, strokeColor="transparent", backgroundColor=WHITE)
            text(x, p["y"], p["text"], p["size"], color=p.get("color", INK))
        elif t == "label":
            owner = by_id.get(p["owner"])
            body = "\n".join(txt for _, txt in p["lines"])
            if p["fields"]:
                body += "\n\n" + "\n".join(p["fields"])
            if owner is not None and body:
                lbl = text(p["x"] + 8, p["y"] + 8, body, 13, align="center", container=owner["id"], w=p["w"] - 16, h=p["h"] - 16)
                lbl["groupIds"] = group
                owner["boundElements"].append({"type": "text", "id": lbl["id"]})
    return {"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": els,
            "appState": {"viewBackgroundColor": WHITE, "gridSize": None, "currentItemRoughness": 0, "currentItemFontFamily": 2},
            "files": {}}


def render(spec):
    """Returns (svg_text, excalidraw_dict, warnings)."""
    prims, warn = layout(spec)
    return to_svg(prims, spec["title"]), to_excalidraw(prims), warn


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    with open(argv[0], encoding="utf-8") as f:
        spec = json.load(f)
    try:
        svg, exc, warn = render(spec)
    except SpecError as e:
        sys.exit(str(e))
    with open(argv[1] + ".svg", "w", encoding="utf-8") as f:
        f.write(svg)
    with open(argv[1] + ".excalidraw", "w", encoding="utf-8") as f:
        json.dump(exc, f, indent=1)
    for w in warn:
        print("warning:", w)
    print(f"Wrote {argv[1]}.svg and {argv[1]}.excalidraw")


if __name__ == "__main__":
    main(sys.argv[1:])
