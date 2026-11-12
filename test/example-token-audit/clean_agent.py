"""The same bug-triage agent with the six problems fixed. The audit should find nothing serious.

Run: ANTHROPIC_BASE_URL=http://127.0.0.1:8788 python3 clean_agent.py
"""
import json

from agent_tools import RUN, TOOLS, call_model, is_json, text_of

SYSTEM = [{"type": "text", "cache_control": {"type": "ephemeral"},     # stable prefix, cached
           "text": "You are a bug triage assistant. Summarize the open bugs and their likely cause. "
                   "Be brief. Reply in JSON."}]
MAX_RESULT = 1500   # chars of a tool result the model sees
MAX_TURNS = 8


def run_tool(name, args, seen):
    key = (name, json.dumps(args, sort_keys=True))
    if key in seen:
        return "Duplicate call: same result as above."
    seen.add(key)
    out = RUN[name](args)
    return out if len(out) <= MAX_RESULT else out[:MAX_RESULT] + f"\n... (truncated, {len(out)} chars total)"


def trim(messages):
    """Keep only the latest tool results in full; older ones become a one-line stub."""
    for m in messages[:-1]:
        if m["role"] == "user" and isinstance(m["content"], list):
            for b in m["content"]:
                if b.get("type") == "tool_result" and len(b["content"]) > 200:
                    b["content"] = b["content"][:200] + " ... (trimmed)"


def main():
    messages = [{"role": "user", "content": "Summarize the open bugs in bugs.json and find the cause in the logs."}]
    seen = set()
    for _ in range(MAX_TURNS):
        resp = call_model({"model": "claude-sonnet-5-5", "max_tokens": 500,
                           "system": SYSTEM, "tools": TOOLS, "messages": messages})
        messages.append({"role": "assistant", "content": resp["content"]})
        if resp["stop_reason"] != "tool_use":
            break
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": b["id"], "content": run_tool(b["name"], b["input"], seen)}
            for b in resp["content"] if b["type"] == "tool_use"]})
        trim(messages)

    answer = text_of(resp)
    if not is_json(answer):   # small repair call instead of replaying the whole conversation
        answer = text_of(call_model({"model": "claude-haiku-5-5", "max_tokens": 300,
                                     "messages": [{"role": "user", "content": "Convert to JSON: " + answer}]}))
    print(answer[:200])


if __name__ == "__main__":
    main()
