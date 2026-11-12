"""Run an example agent N times through usage_proxy against a fresh fake API. Returns trace paths.

Usage: python3 harness.py AGENT.py RUNS OUT_DIR
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import fake_api  # noqa: E402
import usage_proxy  # noqa: E402


def run(agent, runs, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    name = os.path.splitext(os.path.basename(agent))[0]
    paths = []
    for i in range(1, runs + 1):
        path = os.path.join(out_dir, f"{name}-run{i}.jsonl")
        if os.path.exists(path):
            os.remove(path)
        api = fake_api.serve()
        proxy = usage_proxy.serve("anthropic", f"http://127.0.0.1:{api.server_address[1]}", 0, path, budget=500_000)
        env = dict(os.environ, ANTHROPIC_BASE_URL=f"http://127.0.0.1:{proxy.server_address[1]}")
        subprocess.run([sys.executable, os.path.basename(agent)], cwd=os.path.dirname(os.path.abspath(agent)),
                       env=env, check=True, capture_output=True, timeout=120)
        for s in (proxy, api):
            s.shutdown()
            s.server_close()
        paths.append(path)
    return paths


if __name__ == "__main__":
    for p in run(sys.argv[1], int(sys.argv[2]), sys.argv[3]):
        print(p)
