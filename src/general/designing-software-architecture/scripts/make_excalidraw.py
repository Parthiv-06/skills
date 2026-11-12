"""Turn a small JSON spec of boxes and arrows into an .excalidraw file.

Usage: python3 make_excalidraw.py spec.json out.excalidraw

Spec:
  {"nodes": [{"id": "api", "label": "API", "x": 300, "y": 100,
              "w": 160, "h": 70, "shape": "rectangle"}],
   "edges": [{"from": "web", "to": "api", "label": "HTTPS", "dashed": false}]}
shape: rectangle | ellipse | diamond (use ellipse for datastores/queues, diamond for decisions).
All shapes are filled plain white; any "color" in the spec is ignored.
"""
import json
import random
import sys

FONT_HAND = 1  # Virgil, the hand-drawn Excalidraw font


def base(kind, id_, x, y, w, h, **extra):
    el = {
        "type": kind, "id": id_, "x": x, "y": y, "width": w, "height": h,
        "angle": 0, "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": None, "seed": random.randint(1, 2**31), "version": 1,
        "versionNonce": random.randint(1, 2**31), "isDeleted": False,
        "boundElements": [], "updated": 1, "link": None, "locked": False,
    }
    el.update(extra)
    return el


def text_el(id_, container, label, x, y, w, h):
    return base(
        "text", id_, x, y, w, h, text=label, originalText=label,
        fontSize=18, fontFamily=FONT_HAND, textAlign="center",
        verticalAlign="middle", containerId=container, lineHeight=1.25,
        autoResize=True,
    )


def anchor(n, other):
    """Edge point of node n facing node other, plus its fixedPoint."""
    dx = (other["x"] + other["w"] / 2) - (n["x"] + n["w"] / 2)
    dy = (other["y"] + other["h"] / 2) - (n["y"] + n["h"] / 2)
    if abs(dx) >= abs(dy):
        right = dx > 0
        return (n["x"] + (n["w"] if right else 0), n["y"] + n["h"] / 2), [1 if right else 0, 0.5]
    down = dy > 0
    return (n["x"] + n["w"] / 2, n["y"] + (n["h"] if down else 0)), [0.5, 1 if down else 0]


def build(spec):
    nodes = {n["id"]: n for n in spec["nodes"]}
    elements = []
    by_id = {}
    for n in spec["nodes"]:
        n.setdefault("w", 160)
        n.setdefault("h", 70)
        box = base(
            n.get("shape", "rectangle"), n["id"], n["x"], n["y"], n["w"], n["h"],
            backgroundColor="#ffffff",
            roundness={"type": 3} if n.get("shape", "rectangle") == "rectangle" else None,
        )
        tid = n["id"] + "_t"
        box["boundElements"].append({"type": "text", "id": tid})
        elements += [box, text_el(tid, n["id"], n["label"], n["x"] + 10, n["y"] + n["h"] / 2 - 11, n["w"] - 20, 22)]
        by_id[n["id"]] = box

    for i, e in enumerate(spec.get("edges", [])):
        a, b = nodes[e["from"]], nodes[e["to"]]
        (x1, y1), fp1 = anchor(a, b)
        (x2, y2), fp2 = anchor(b, a)
        aid = f"edge{i}"
        arrow = base(
            "arrow", aid, x1, y1, x2 - x1, y2 - y1,
            points=[[0, 0], [x2 - x1, y2 - y1]], roundness={"type": 2},
            strokeStyle="dashed" if e.get("dashed") else "solid",
            startBinding={"elementId": a["id"], "fixedPoint": fp1, "focus": 0, "gap": 1},
            endBinding={"elementId": b["id"], "fixedPoint": fp2, "focus": 0, "gap": 1},
            startArrowhead=None, endArrowhead="arrow", lastCommittedPoint=None,
        )
        by_id[a["id"]]["boundElements"].append({"type": "arrow", "id": aid})
        by_id[b["id"]]["boundElements"].append({"type": "arrow", "id": aid})
        elements.append(arrow)
        if e.get("label"):
            tid = aid + "_t"
            arrow["boundElements"].append({"type": "text", "id": tid})
            elements.append(text_el(tid, aid, e["label"], (x1 + x2) / 2 - 40, (y1 + y2) / 2 - 22, 80, 22))

    return {
        "type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
        "files": {},
    }


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        spec = json.load(f)
    with open(sys.argv[2], "w") as f:
        json.dump(build(spec), f, indent=2)
    print(f"wrote {sys.argv[2]} - open it by dragging onto https://excalidraw.com")
