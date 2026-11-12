"""Turn usage_proxy traces into stats, a token attribution, and detector findings.

Usage: python3 analyze_trace.py RUN1.jsonl [RUN2.jsonl ...] > analysis.json
Each file is one run of the same task. Use 3+ runs; the median run (by total tokens) is the one
whose calls and attribution are shown.

Findings are leads, not verdicts: each says which calls show the pattern and how many tokens
those calls involve. Several findings can involve the same tokens (a huge tool result is also
resent history), so tokens_involved must never be summed. Confirm each finding in the code and
decide the real waste there. Detector ids and what they mean: references/issue-catalog.md.
"""
import json
import statistics
import sys

# Thresholds. Starting points; adjust when a real agent shows they are off.
HUGE_RESULT_TOKENS = 2000      # a tool result this big is always worth a look
HUGE_RESULT_SHARE = 0.30       # ...or one that is this share of its call's input
HISTORY_RESENT_SHARE = 0.20    # resent history above this share of the run's tokens
CACHEABLE_MIN = 2000           # repeated prefix+history tokens that caching could have served
VERBOSE_OUTPUT = 800           # median output tokens of final answers
TOOL_SCHEMA_TOKENS = 1500
SYSTEM_PROMPT_TOKENS = 1500
REASONING_TOKENS = 2000
THINKING_BUDGET = 8000
PER_ITEM_CALLS = 5
RUNAWAY_CALLS = 25
SEVERITY = [(0.25, "high"), (0.08, "medium"), (0.0, "low")]


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def total(r):
    u = r.get("usage")
    return u["input"] + u["output"] + u["cache_write"] + u["cache_read"] if u else 0


def measured_in(r):
    u = r["usage"]
    return u["input"] + u["cache_write"] + u["cache_read"]


def scaled_blocks(r):
    """Estimated block sizes scaled so they add up to the measured input of the call."""
    est = r.get("blocks") or {}
    s = sum(est.values())
    k = measured_in(r) / s if s else 0
    return {name: round(v * k) for name, v in est.items()}


def finding(fid, title, tokens, calls, evidence, run_total):
    share = tokens / run_total if run_total else 0
    sev = next(s for t, s in SEVERITY if share >= t)
    return {"id": fid, "title": title, "severity": sev, "tokens_involved": round(tokens),
            "share": round(share, 3), "calls": calls, "evidence": evidence}


def detect_run(run):
    ok = [r for r in run if r.get("usage")]
    if not ok:
        return []
    T = sum(total(r) for r in ok)
    out = []

    # history resent every turn
    hist = [r["blocks"]["history"] for r in ok]
    resent = sum(hist) - max(hist)
    if len(ok) >= 3 and resent >= HISTORY_RESENT_SHARE * T:
        out.append(finding("history-growth", "Conversation history is resent on every call", resent,
                           [r["call"] for r in ok if r["blocks"]["history"]],
                           f"history grew from {hist[0]:,} to {max(hist):,} est. tokens over {len(ok)} calls; "
                           f"{resent:,} tokens of earlier turns were sent again", T))

    # huge tool results, counted in every call that carries them
    seen = {}
    for r in ok:
        for b in r.get("big_blocks", []):
            if b["source"] == "tool_result" and (b["tokens"] >= HUGE_RESULT_TOKENS or b["tokens"] >= HUGE_RESULT_SHARE * measured_in(r)):
                seen.setdefault(b["hash"], {"tokens": b["tokens"], "calls": []})["calls"].append(r["call"])
    if seen:
        tok = sum(v["tokens"] * len(set(v["calls"])) for v in seen.values())
        biggest = max(v["tokens"] for v in seen.values())
        out.append(finding("huge-tool-result", "A tool result is very large and stays in context", tok,
                           sorted({c for v in seen.values() for c in v["calls"]}),
                           f"{len(seen)} large tool result(s), biggest ~{biggest:,} tokens, carried in "
                           f"{max(len(set(v['calls'])) for v in seen.values())} calls", T))

    # caching
    cw = sum(r["usage"]["cache_write"] for r in ok)
    cr = sum(r["usage"]["cache_read"] for r in ok)
    cacheable = sum(r["blocks"]["system"] + r["blocks"]["tools"] + r["blocks"]["history"] for r in ok[1:])
    if len(ok) >= 2 and cw == 0 and cr == 0 and cacheable >= CACHEABLE_MIN:
        out.append(finding("no-cache", "Prompt caching is not used", cacheable, [r["call"] for r in ok[1:]],
                           f"0 cached tokens across {len(ok)} calls; ~{cacheable:,} tokens repeated a previous call's prefix", T))
    writes = [r for r in ok if r["usage"]["cache_write"]]
    if len(writes) >= 2 and cr < cw:
        out.append(finding("cache-broken", "Cache is written but rarely read", sum(r["usage"]["cache_write"] for r in writes[1:]),
                           [r["call"] for r in writes], f"cache written in {len(writes)} calls, read {cr:,} vs written {cw:,} tokens", T))
    same_size = [(a, b) for a, b in zip(ok, ok[1:]) if a["prefix_hash"] != b["prefix_hash"]
                 and abs((a["blocks"]["system"] + a["blocks"]["tools"]) - (b["blocks"]["system"] + b["blocks"]["tools"]))
                 <= 0.1 * max(1, a["blocks"]["system"] + a["blocks"]["tools"])]
    if same_size:
        out.append(finding("unstable-prefix", "System prompt or tools change between calls", sum(b["blocks"]["system"] + b["blocks"]["tools"] for _, b in same_size),
                           [b["call"] for _, b in same_size], "same-size prefix with a different hash: likely a timestamp, ID, or reordered tools", T))

    # repeated identical tool calls
    first, repeats = {}, []
    for i, r in enumerate(ok):
        for tc in r.get("tool_calls", []):
            key = (tc["name"], tc["args_hash"])
            if key in first:
                repeats.append((i, tc["name"]))
            else:
                first[key] = r["call"]
    if repeats:
        tok = sum(ok[i + 1]["blocks"]["tool_results"] * (len(ok) - i - 1) for i, _ in repeats if i + 1 < len(ok))
        names = sorted({n for _, n in repeats})
        out.append(finding("repeated-tool-call", "The same tool is called again with the same arguments", tok,
                           [ok[i]["call"] for i, _ in repeats],
                           f"{len(repeats)} repeat call(s) of {', '.join(names)}; each repeat's result is resent in later calls", T))

    # retries and duplicates
    storm = [b for a, b in zip(run, run[1:]) if a["request_hash"] == b["request_hash"]]
    if storm:
        out.append(finding("retry-storm", "Identical requests are sent back to back", sum(total(r) for r in storm),
                           [r["call"] for r in storm], f"{len(storm)} call(s) repeat the previous request exactly", T))
    storm_ids = {r["call"] for r in storm}
    seen_req, dups = {}, []
    for r in run:
        if r["request_hash"] in seen_req and r["call"] not in storm_ids:
            dups.append(r)
        seen_req.setdefault(r["request_hash"], r["call"])
    if dups:
        out.append(finding("duplicate-call", "The same request is made more than once", sum(total(r) for r in dups),
                           [r["call"] for r in dups], f"{len(dups)} request(s) identical to an earlier, non-adjacent call", T))
    fresh = {}
    for r in ok:
        if r["blocks"]["history"] == 0:
            fresh.setdefault(r["prefix_hash"], []).append(r)
    for group in fresh.values():
        if len(group) >= PER_ITEM_CALLS:
            fixed = sum(r["blocks"]["system"] + r["blocks"]["tools"] for r in group[1:])
            out.append(finding("per-item-calls", "One model call per item instead of a batch", fixed, [r["call"] for r in group],
                               f"{len(group)} single-turn calls share the same prompt; the fixed prompt is paid each time", T))

    # fixed cost
    tools_tok = max(r["blocks"]["tools"] for r in ok)
    if tools_tok >= TOOL_SCHEMA_TOKENS:
        defined = set(ok[0].get("tool_names") or [])
        used = {tc["name"] for r in ok for tc in r.get("tool_calls", [])}
        unused = 1 - len(used & defined) / len(defined) if defined else 0
        out.append(finding("tool-schema-bloat", "Tool definitions are large and mostly unused", tools_tok * len(ok) * unused,
                           [r["call"] for r in ok], f"~{tools_tok:,} tokens of tool schemas per call; {len(used & defined)} of {len(defined)} tools used", T))
    sys_tok = max(r["blocks"]["system"] for r in ok)
    if sys_tok >= SYSTEM_PROMPT_TOKENS:
        out.append(finding("system-prompt-bloat", "System prompt is long", sys_tok * len(ok), [r["call"] for r in ok],
                           f"~{sys_tok:,} tokens of system prompt on every call; run compressing-agent-prompts on it", T))

    # output side
    reasoning = sum(r["usage"]["reasoning"] or 0 for r in ok)
    budgets = [r["thinking_budget"] for r in ok if r.get("thinking_budget")]
    if reasoning >= REASONING_TOKENS or (budgets and max(budgets) >= THINKING_BUDGET):
        out.append(finding("overthinking", "Reasoning or thinking budget is high for the task", reasoning,
                           [r["call"] for r in ok if (r["usage"]["reasoning"] or 0) or r.get("thinking_budget")],
                           f"{reasoning:,} reasoning tokens; max thinking budget {max(budgets) if budgets else 0:,}", T))
    finals = [r for r in ok if r.get("stop_reason") in ("end_turn", "stop", "max_tokens")]
    if finals and statistics.median(r["usage"]["output"] for r in finals) >= VERBOSE_OUTPUT:
        out.append(finding("verbose-output", "Answers are longer than the task needs", sum(r["usage"]["output"] for r in finals),
                           [r["call"] for r in finals],
                           f"median final answer {statistics.median(r['usage']['output'] for r in finals):,.0f} tokens; "
                           f"max_tokens {max((r.get('max_tokens') or 0) for r in finals):,}", T))

    # context copied around
    owners = {}
    for r in ok:
        for b in r.get("big_blocks", []):
            owners.setdefault(b["hash"], []).append(r)
    copied = {h: rs for h, rs in owners.items() if len({r["prefix_hash"] for r in rs}) > 1}
    if copied:
        tok = sum(next(b["tokens"] for b in rs[0]["big_blocks"] if b["hash"] == h) * (len(rs) - 1) for h, rs in copied.items())
        out.append(finding("context-duplication", "The same large context is passed to different agents", tok,
                           sorted({r["call"] for rs in copied.values() for r in rs}),
                           f"{len(copied)} large block(s) appear under different system prompts (subagents or chains)", T))
    media = {h: rs for h, rs in owners.items() if len(rs) > 1 and any(b["source"] == "media" and b["hash"] == h for b in rs[0]["big_blocks"])}
    if media:
        tok = sum(next(b["tokens"] for b in rs[0]["big_blocks"] if b["hash"] == h) * (len(rs) - 1) for h, rs in media.items())
        out.append(finding("media-resent", "Images or files are resent in later calls", tok, sorted({r["call"] for rs in media.values() for r in rs}),
                           f"{len(media)} image/file block(s) sent in more than one call", T))
    flagged = [(r, b) for r in ok for b in r.get("big_blocks", []) if b.get("flags")]
    if flagged:
        out.append(finding("debug-in-context", "Stack traces or object dumps are sent to the model", sum(b["tokens"] for _, b in flagged),
                           sorted({r["call"] for r, _ in flagged}), ", ".join(sorted({f for _, b in flagged for f in b["flags"]})) + " found in large blocks", T))

    if len(run) >= RUNAWAY_CALLS or any(r.get("blocked") for r in run):
        out.append(finding("runaway", "The run hit the budget cap or a very high call count", T, [run[-1]["call"]],
                           f"{len(run)} calls; " + ("stopped by the proxy budget cap" if any(r.get("blocked") for r in run) else "no budget stop"), T))
    return out


def summarize(values):
    return {"median": statistics.median(values), "min": min(values), "max": max(values)} if values else None


def analyze(paths):
    runs = [load(p) for p in paths]
    runs = [r for r in runs if r]
    if not runs:
        return {"runs": 0, "findings": [], "note": "no calls recorded"}
    totals = [sum(total(r) for r in run) for run in runs]
    order = sorted(range(len(runs)), key=lambda i: totals[i])
    mi = order[(len(order) - 1) // 2]
    median_run = runs[mi]
    ok = [r for r in median_run if r.get("usage")]

    per_call, attribution = [], {}
    for r in ok:
        blocks = scaled_blocks(r)
        for k, v in blocks.items():
            attribution[k] = attribution.get(k, 0) + v
        attribution["output"] = attribution.get("output", 0) + r["usage"]["output"]
        per_call.append({"call": r["call"], "model": r.get("model"), "input": r["usage"]["input"], "output": r["usage"]["output"],
                         "cache_read": r["usage"]["cache_read"], "cache_write": r["usage"]["cache_write"],
                         "stop_reason": r.get("stop_reason"), "tools": [t["name"] for t in r.get("tool_calls", [])], "blocks": blocks})

    per_run = [detect_run(run) for run in runs]
    findings = []
    for fid in dict.fromkeys(f["id"] for fs in per_run for f in fs):
        hits = [(i, next(f for f in fs if f["id"] == fid)) for i, fs in enumerate(per_run) if any(f["id"] == fid for f in fs)]
        if len(hits) * 2 < len(runs):
            continue
        shown = next((f for i, f in hits if i == mi), hits[0][1])
        shown = dict(shown, hit_runs=f"{len(hits)}/{len(runs)}",
                     tokens_involved=round(statistics.median(f["tokens_involved"] for _, f in hits)))
        findings.append(shown)

    firsts = [run[0] for run in runs if run]
    if len({r["prefix_hash"] for r in firsts}) > 1 and len({r["blocks"]["system"] + r["blocks"]["tools"] for r in firsts}) <= len(firsts) and \
            max(r["blocks"]["system"] for r in firsts) - min(r["blocks"]["system"] for r in firsts) <= 0.1 * max(1, max(r["blocks"]["system"] for r in firsts)) and \
            not any(f["id"] == "unstable-prefix" for f in findings):
        findings.append({"id": "unstable-prefix", "title": "System prompt or tools differ between runs", "severity": "medium",
                         "tokens_involved": sum(r["blocks"]["system"] + r["blocks"]["tools"] for r in ok), "share": None,
                         "calls": [r["call"] for r in ok], "hit_runs": f"{len(runs)}/{len(runs)}",
                         "evidence": "the first call's prefix differs between runs at the same size: likely a timestamp or ID, which defeats caching across requests"})

    rank = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (rank[f["severity"]], -f["tokens_involved"]))
    sum_kind = lambda k: summarize([sum(r["usage"][k] for r in run if r.get("usage")) for run in runs])  # noqa: E731
    cache_den = sum(r["usage"]["input"] + r["usage"]["cache_read"] + r["usage"]["cache_write"] for r in ok)
    return {
        "runs": len(runs),
        "median_run": paths[mi] if len(paths) == len(runs) else mi,
        "calls": summarize([len(run) for run in runs]),
        "tokens": {"total": summarize(totals), "input": sum_kind("input"), "output": sum_kind("output"),
                   "cache_read": sum_kind("cache_read"), "cache_write": sum_kind("cache_write")},
        "models": sorted({r.get("model") for run in runs for r in run if r.get("model")}),
        "errors": sum(1 for run in runs for r in run if r.get("status", 200) >= 400),
        "cache_hit_rate": round(sum(r["usage"]["cache_read"] for r in ok) / cache_den, 3) if cache_den else 0,
        "attribution": attribution,
        "per_call": per_call,
        "findings": findings,
        "note": "tokens_involved overlap between findings; never add them up. Attribution blocks are estimates scaled to measured input.",
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print(json.dumps(analyze(sys.argv[1:]), indent=1))
