"""Bug-triage agent with six planted token problems. The audit should find exactly these.

1. History is resent untrimmed every turn.
2. read_file returns the whole 40 KB export into context.
3. No prompt caching, and a timestamp in the system prompt would break it anyway.
4. Repeated tool calls are re-executed instead of deduplicated.
5. A non-JSON answer is retried by replaying the identical full request.
6. The prompt asks for detail and allows 8,000 output tokens.

Run: ANTHROPIC_BASE_URL=http://127.0.0.1:8788 python3 wasteful_agent.py
"""
from datetime import datetime

from agent_tools import RUN, TOOLS, call_model, is_json, text_of

SYSTEM = (f"You are a bug triage assistant. Current time: {datetime.now().isoformat()}. "   # (3)
          "Summarize the open bugs and their likely cause. Explain in detail. Reply in JSON.")  # (6)


def main():
    messages = [{"role": "user", "content": "Summarize the open bugs in bugs.json and find the cause in the logs."}]
    while True:                                                    # no turn limit
        body = {"model": "claude-sonnet-5-5", "max_tokens": 8000,  # (6)
                "system": SYSTEM, "tools": TOOLS, "messages": messages}
        resp = call_model(body)
        messages.append({"role": "assistant", "content": resp["content"]})  # (1) never trimmed
        if resp["stop_reason"] != "tool_use":
            break
        results = [{"type": "tool_result", "tool_use_id": b["id"], "content": RUN[b["name"]](b["input"])}  # (2) (4)
                   for b in resp["content"] if b["type"] == "tool_use"]
        messages.append({"role": "user", "content": results})

    answer = text_of(resp)
    for _ in range(5):                                             # (5) replay the same full request
        if is_json(answer):
            break
        answer = text_of(call_model(body))
    print(answer[:200])


if __name__ == "__main__":
    main()
