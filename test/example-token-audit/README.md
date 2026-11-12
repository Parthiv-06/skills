# Example: auditing a wasteful agent

A bug-triage agent with six planted token problems, audited with the `auditing-agent-token-usage` skill against a fake API (no key, no cost).

| File | What it is |
|---|---|
| `wasteful_agent.py` | The agent under audit. Its docstring lists the six problems |
| `clean_agent.py` | The same agent with all six fixed. Measured as the Ideal number |
| `agent_tools.py` | Tools and API plumbing shared by both |
| `traces/` | Proxy traces: 3 runs of each agent |
| `analysis.json`, `analysis-clean.json` | `analyze_trace.py` output for each |
| `token-audit.json` | The audit: findings confirmed in the code, with waste worked out |
| `report.html` | The report page. Open it in a browser |

**Result:** 168,068 tokens per task (measured). The code predicts 41,085 in its best case, and the fixed agent uses 2,103: 80× less. The analyzer found all six planted problems, plus the timestamp that defeats caching (`unstable-prefix`, part of problem 3), and nothing else. On the clean agent it found one low-severity item: the model repeats a search, which the agent now answers cheaply.

## Re-run it

From the repo root:

```bash
H=src/agents/auditing-agent-token-usage
python3 $H/tests/harness.py test/example-token-audit/wasteful_agent.py 3 test/example-token-audit/traces
python3 $H/scripts/analyze_trace.py test/example-token-audit/traces/wasteful_agent-run*.jsonl > test/example-token-audit/analysis.json
python3 $H/scripts/build_report.py test/example-token-audit/token-audit.json test/example-token-audit/report.html
```

`harness.py` starts the fake API and the proxy for each run. Against a real API, start `usage_proxy.py` yourself as described in the skill.
