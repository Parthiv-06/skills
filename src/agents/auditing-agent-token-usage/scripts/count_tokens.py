"""Count tokens as exactly as this machine allows, and say how the number was made.

Usage: python3 count_tokens.py FILE [--provider anthropic|openai] [--model MODEL]
       python3 count_tokens.py --request REQUEST.json [--model MODEL]

Prints JSON {"tokens": N, "method": M}. M is one of:
  counted:anthropic-api   exact, via the Messages count_tokens endpoint (needs ANTHROPIC_API_KEY)
  counted:tiktoken        exact for OpenAI models (needs the tiktoken package)
  estimated:chars/4       rough; label it "estimated" wherever it is shown

--request counts a whole Messages request body (system + tools + messages) through the API,
which is the exact fixed cost per call. Without a key it falls back to chars/4 of the JSON.
"""
import json
import os
import sys
import urllib.request

try:
    import tiktoken
except ImportError:
    tiktoken = None

DEFAULT_MODEL = "claude-sonnet-5-5"


def _anthropic_count(body):
    req = urllib.request.Request(
        os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/") + "/v1/messages/count_tokens",
        data=json.dumps(body).encode(),
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["input_tokens"]


def count_request(body, model=None):
    """Exact input tokens for a full Messages request body, or a labeled estimate."""
    body = {k: v for k, v in body.items() if k in ("system", "tools", "messages", "tool_choice", "thinking")}
    body["model"] = model or DEFAULT_MODEL
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _anthropic_count(body), "counted:anthropic-api"
        except Exception:
            pass
    return round(len(json.dumps(body)) / 4), "estimated:chars/4"


def count(text, provider="anthropic", model=None):
    if not text:
        return 0, "estimated:chars/4"
    if provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            m = model or DEFAULT_MODEL
            full = _anthropic_count({"model": m, "messages": [{"role": "user", "content": text}]})
            base = _anthropic_count({"model": m, "messages": [{"role": "user", "content": "x"}]})
            return max(full - base + 1, 0), "counted:anthropic-api"
        except Exception:
            pass
    if provider == "openai" and tiktoken is not None:
        try:
            enc = tiktoken.encoding_for_model(model) if model else tiktoken.get_encoding("o200k_base")
        except KeyError:
            enc = tiktoken.get_encoding("o200k_base")
        return len(enc.encode(text)), "counted:tiktoken"
    return round(len(text) / 4), "estimated:chars/4"


def main(argv):
    args = dict(zip(argv[::2], argv[1::2])) if argv and argv[0].startswith("--") else {}
    if "--request" in args:
        with open(args["--request"], encoding="utf-8") as f:
            n, method = count_request(json.load(f), args.get("--model"))
    elif argv and not argv[0].startswith("--"):
        args = dict(zip(argv[1::2], argv[2::2]))
        with open(argv[0], encoding="utf-8") as f:
            n, method = count(f.read(), args.get("--provider", "anthropic"), args.get("--model"))
    else:
        sys.exit(__doc__)
    print(json.dumps({"tokens": n, "method": method}))


if __name__ == "__main__":
    main(sys.argv[1:])
