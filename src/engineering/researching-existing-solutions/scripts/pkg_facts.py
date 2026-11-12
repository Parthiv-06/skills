"""Pull live, dated facts about PyPI packages so recommendations rest on evidence, not memory.

Usage:
  python3 pkg_facts.py NAME [NAME ...] [--project DIR] [--json]

Sources (no API keys needed; set GITHUB_TOKEN to raise GitHub's rate limit):
  PyPI JSON API      version, release dates, license, requires-python, dependencies
  deps.dev           SPDX license, OpenSSF Scorecard, project status
  pypistats.org      downloads in the last month
  GitHub API         stars, archived, last push, open issues
  OSV                known vulnerabilities in the latest version

--project DIR also reports whether each package is already declared in pyproject.toml
or pinned in a lock/requirements file under DIR.

Flags printed per package: ARCHIVED, STALE (no release in 18 months), VULNS, COPYLEFT,
SOURCE-AVAILABLE (not open source), NO-PY312 (requires-python excludes 3.12), FEW-RELEASES.
Every flag is a prompt to look closer, not a verdict.
"""
import datetime as dt
import glob
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

NOW = dt.datetime.now(dt.timezone.utc)
PYPISTATS_LOCK = threading.Lock()
COPYLEFT = re.compile(r"\b(A?GPL|LGPL|MPL|EUPL|OSL|CC-BY-SA)|General Public License|Mozilla Public", re.I)
SOURCE_AVAILABLE = re.compile(r"\b(BUSL|BSL-1|SSPL|Elastic|Commons Clause|PolyForm|FSL)", re.I)


def get(url, data=None):
    headers = {"User-Agent": "pkg-facts/1.0", "Accept": "application/json"}
    if "api.github.com" in url and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.load(r)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return {"_error": str(e)}


def days_ago(iso):
    if not iso:
        return None
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return (NOW - t).days


def license_family(text):
    """'MIT License', 'MIT' -> 'mit'; 'BSD License', 'BSD-3-Clause' -> 'bsd'. Order matters: AGPL before GPL."""
    t = text.lower().replace("affero general public", "agpl").replace("lesser general public", "lgpl").replace("general public", "gpl")
    for fam in ("agpl", "lgpl", "gpl", "apache", "mit", "bsd", "mpl", "mozilla", "isc", "psf", "python", "unlicense",
                "zlib", "cc0", "eupl", "busl", "sspl", "elastic", "polyform"):
        if fam in t:
            return {"mozilla": "mpl", "python": "psf"}.get(fam, fam)
    return None


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def project_deps(root):
    """Map normalized name -> where it appears (declared / pinned version)."""
    found = {}
    py = os.path.join(root, "pyproject.toml")
    if os.path.exists(py):
        text = open(py).read()
        for m in re.finditer(r'^\s*"([A-Za-z0-9_.\-]+)', text, re.M):
            found.setdefault(norm(m.group(1)), []).append("declared in pyproject.toml")
    patterns = ["*.lock", "requirements*.txt", "requirements/*.txt", "uv.lock", "poetry.lock", "Pipfile.lock"]
    for pat in patterns:
        for path in glob.glob(os.path.join(root, pat)):
            text = open(path).read()
            rel = os.path.relpath(path, root)
            for m in re.finditer(r'^([A-Za-z0-9_.\-]+)==([^\s;#]+)', text, re.M):
                found.setdefault(norm(m.group(1)), []).append(f"pinned {m.group(2)} in {rel}")
            for m in re.finditer(r'name = "([^"]+)"\s*\nversion = "([^"]+)"', text):
                found.setdefault(norm(m.group(1)), []).append(f"pinned {m.group(2)} in {rel}")
    return found


def facts(name):
    f = {"package": name, "checked": NOW.strftime("%Y-%m-%d"), "flags": [], "sources": []}
    pypi = get(f"https://pypi.org/pypi/{name}/json")
    if "_error" in pypi or "info" not in pypi:
        f["error"] = "not found on PyPI"
        return f
    info = pypi["info"]
    f["sources"].append(f"https://pypi.org/project/{name}/")
    f["version"] = info.get("version")
    f["summary"] = info.get("summary")
    f["requires_python"] = info.get("requires_python")
    f["pypi_license"] = (info.get("license_expression") or info.get("license") or "").strip()[:80] or None
    f["dependencies"] = len([r for r in (info.get("requires_dist") or []) if "extra ==" not in r])

    uploads = {}
    for ver, files in pypi.get("releases", {}).items():
        times = [x["upload_time_iso_8601"] for x in files if not x.get("yanked")]
        if times:
            uploads[ver] = min(times)
    latest = uploads.get(f["version"])
    f["latest_release_days_ago"] = days_ago(latest)
    f["releases_last_12_months"] = sum(1 for t in uploads.values() if days_ago(t) <= 365)
    f["first_release_days_ago"] = days_ago(min(uploads.values())) if uploads else None

    dd = get(f"https://api.deps.dev/v3/systems/pypi/packages/{urllib.parse.quote(name)}/versions/{urllib.parse.quote(f['version'])}")
    classifier_lic = [c.split("::")[-1].strip() for c in info.get("classifiers") or [] if c.startswith("License ::")]
    lic_votes = {
        "deps.dev": ", ".join(x for x in dd.get("licenses") or [] if x.lower() != "non-standard"),
        "pypi": f["pypi_license"] if f["pypi_license"] and len(f["pypi_license"]) < 60 else "",
        "classifiers": ", ".join(classifier_lic),
    }
    f["deprecated"] = dd.get("isDeprecated")
    repo = None
    for link in dd.get("links") or []:
        if link.get("label") == "SOURCE_REPO" and "github.com" in link.get("url", ""):
            repo = link["url"]
    if not repo:
        for url in (info.get("project_urls") or {}).values():
            if url and re.match(r"https://github\.com/[^/]+/[^/#?]+", url):
                repo = url
                break
    f["sources"].append(f"https://deps.dev/pypi/{name}")

    if repo:
        m = re.match(r"https://github\.com/([^/]+)/([^/#?]+)", repo)
        owner, rname = m.group(1), m.group(2).removesuffix(".git")
        f["repo"] = f"https://github.com/{owner}/{rname}"
        gh = get(f"https://api.github.com/repos/{owner}/{rname}")
        if "_error" not in gh and "stargazers_count" in gh:
            f["stars"] = gh["stargazers_count"]
            f["open_issues"] = gh["open_issues_count"]
            f["archived"] = gh["archived"]
            f["last_push_days_ago"] = days_ago(gh["pushed_at"])
            spdx = (gh.get("license") or {}).get("spdx_id")
            if spdx and spdx != "NOASSERTION":
                lic_votes["github"] = spdx
            f["sources"].append(f["repo"])
        proj = get("https://api.deps.dev/v3/projects/" + urllib.parse.quote(f"github.com/{owner}/{rname}", safe=""))
        sc = proj.get("scorecard") or {}
        if sc:
            f["scorecard"] = sc.get("overallScore")
            checks = {c["name"]: c.get("score") for c in sc.get("checks", [])}
            f["scorecard_maintained"] = checks.get("Maintained")

    # License: first source that gives a real answer; keep all of them so disagreements are visible.
    vals = [v for v in lic_votes.values() if v]
    f["license"] = vals[0] if vals else None
    f["license_sources"] = {k: v for k, v in lic_votes.items() if v}
    families = {fam for fam in (license_family(v) for v in vals) if fam}
    if len(families) > 1:
        f["flags"].append("LICENSE-MISMATCH")

    with PYPISTATS_LOCK:  # pypistats rate-limits concurrent callers
        for wait in (0, 2, 5):
            time.sleep(wait)
            stats = get(f"https://pypistats.org/api/packages/{norm(name)}/recent")
            if "_error" not in stats:
                break
    f["downloads_last_month"] = (stats.get("data") or {}).get("last_month")
    if f["downloads_last_month"] is not None:
        f["sources"].append(f"https://pypistats.org/packages/{norm(name)}")

    osv = get("https://api.osv.dev/v1/query", {"package": {"name": name, "ecosystem": "PyPI"}, "version": f["version"]})
    f["vulns_in_latest"] = [v["id"] for v in osv.get("vulns", [])]
    f["sources"].append(f"https://osv.dev/list?ecosystem=PyPI&q={name}")

    lic = " ".join(f["license_sources"].values())
    if f.get("archived"):
        f["flags"].append("ARCHIVED")
    if f["latest_release_days_ago"] is not None and f["latest_release_days_ago"] > 548:
        f["flags"].append("STALE")
    if f["vulns_in_latest"]:
        f["flags"].append("VULNS")
    if COPYLEFT.search(lic):
        f["flags"].append("COPYLEFT")
    if SOURCE_AVAILABLE.search(lic):
        f["flags"].append("SOURCE-AVAILABLE")
    if f["deprecated"]:
        f["flags"].append("DEPRECATED")
    rp = f["requires_python"] or ""
    if re.search(r"<\s*3\.(\d+)", rp) and int(re.search(r"<\s*3\.(\d+)", rp).group(1)) <= 12:
        f["flags"].append("NO-PY312")
    if f["releases_last_12_months"] == 0 and (f["first_release_days_ago"] or 0) < 365:
        f["flags"].append("FEW-RELEASES")
    return f


def fmt(n):
    if n is None:
        return "?"
    if isinstance(n, int) and n >= 1000:
        for unit, size in (("M", 1_000_000), ("k", 1_000)):
            if n >= size:
                return f"{n / size:.1f}{unit}"
    return str(n)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        sys.exit(__doc__)
    as_json = "--json" in args
    project = None
    if "--project" in args:
        i = args.index("--project")
        project = args[i + 1]
        del args[i:i + 2]
    names = [a for a in args if not a.startswith("--")]
    have = project_deps(project) if project else {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(facts, names))
    if project:
        for f in rows:
            f["in_project"] = have.get(norm(f["package"]), [])
    if as_json:
        print(json.dumps(rows, indent=1))
        return
    print(f"Checked {NOW:%Y-%m-%d} (live data)\n")
    print("| Package | Latest | Last release | Releases/12mo | Downloads/mo | Stars | Last push | Scorecard | License | Deps | Vulns | In project | Flags |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for f in rows:
        if "error" in f:
            print(f"| {f['package']} | {f['error']} |" + " |" * 11)
            continue
        print("| " + " | ".join([
            f["package"], f["version"] or "?",
            f"{f['latest_release_days_ago']}d ago", str(f["releases_last_12_months"]),
            fmt(f.get("downloads_last_month")), fmt(f.get("stars")),
            f"{f['last_push_days_ago']}d ago" if f.get("last_push_days_ago") is not None else "?",
            str(f.get("scorecard", "?")), f["license"] or "?", str(f["dependencies"]),
            ", ".join(f["vulns_in_latest"]) or "none",
            "; ".join(f.get("in_project", [])) or ("no" if project else "-"),
            " ".join(f["flags"]) or "-",
        ]) + " |")
    print("\nSources:")
    for f in rows:
        if f.get("sources"):
            print(f"- {f['package']}: " + " · ".join(f["sources"]))


if __name__ == "__main__":
    main()
