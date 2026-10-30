#!/usr/bin/env python3
"""Audit a GitHub organization and its repositories against a baseline, then apply the fixes that the user chose.

Standard library only. All GitHub calls go through the `gh` CLI, so the user's `gh auth` login is used.
The baseline is data, not code: every check is defined in ../data/checks.json.

Subcommands:
  detect     print the org facts that choose the baseline (plan, visibility counts, your role, token scopes)
  audit      read the current settings, compare them with the baseline, write findings JSON
  report     render findings JSON as a markdown table
  apply      print (dry run) or run (--execute) the fixes for selected findings; paid items need --accept-cost
  catalog    render the check catalog as markdown (for references/checks.md)
  workflows  lint workflow files in a local checkout (top-level permissions, actions pinned to a full SHA)
  pin        rewrite `uses: owner/repo@tag` to `uses: owner/repo@<sha> # tag` in a local checkout
  costs      read the current plan, this month's usage, budgets and Copilot seats (read only)
  scorecard  get OpenSSF Scorecard results for a repo (local CLI if installed, else api.scorecard.dev)

Exit codes: 0 ok, 1 usage or API error, 2 audit found failures (only with --fail-on-findings),
3 apply skipped a fix that needs a --set value from the user.
"""

import argparse
import base64
import datetime
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
CHECKS_FILE = os.path.join(SKILL_DIR, "data", "checks.json")
TEMPLATES_DIR = os.path.join(SKILL_DIR, "templates")

PASS, FAIL, UNAVAILABLE, UNKNOWN, MANUAL, SKIPPED = "pass", "fail", "unavailable", "unknown", "manual", "skipped"


# ---------------------------------------------------------------------------------------------------------------
# GitHub access


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(f"HTTP {status}: {message}" if status else message)
        self.status = status
        self.message = message


class Gh:
    """Thin wrapper around `gh api`. Replace `run` in tests to fake GitHub."""

    def __init__(self, runner=None):
        self.run = runner or self._run_gh
        self.calls = []

    @staticmethod
    def _run_gh(args, stdin=None):
        proc = subprocess.run(["gh"] + args, input=stdin, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def api(self, method, path, body=None, paginate=False):
        args = ["api", "--method", method, path]
        if paginate:
            args[3:3] = ["--paginate", "--slurp"]
        stdin = None
        if body is not None:
            args += ["--input", "-"]
            stdin = json.dumps(body)
        self.calls.append((method, path, body))
        code, out, err = self.run(args, stdin)
        if code != 0:
            m = re.search(r"\(HTTP (\d{3})\)", err) or re.search(r"HTTP (\d{3})", err)
            raise ApiError(int(m.group(1)) if m else None, err.strip() or out.strip())
        if not out.strip():
            return None
        data = json.loads(out)
        if paginate and isinstance(data, list) and all(isinstance(p, list) for p in data):
            return [item for page in data for item in page]
        return data

    def get(self, path, paginate=False):
        return self.api("GET", path, paginate=paginate)


# ---------------------------------------------------------------------------------------------------------------
# Small helpers


def load_catalog(path=CHECKS_FILE):
    with open(path) as f:
        return json.load(f)


def pointer(data, dotted):
    """Read `a.b.c` from nested dicts. Missing keys give None.

    `#length` gives the length of a list. `#wrap` puts an object in a one-item list (for list_match on an object).
    """
    if not dotted:
        return data
    for part in dotted.split("."):
        if part == "#length":
            data = len(data) if isinstance(data, list) else None
            continue
        if part == "#wrap":
            data = [data] if data is not None else []
            continue
        if not isinstance(data, dict):
            return None
        data = data.get(part)
    return data


def fill(value, variables):
    """Replace {name} placeholders in strings, recursively in dicts and lists.

    A string that is only one placeholder, for example "{review_count}", takes the variable's own type (int, bool,
    list), so JSON templates can hold typed parameters.
    """
    if isinstance(value, str):
        whole = re.fullmatch(r"\{([a-z_]+)\}", value)
        if whole and whole.group(1) in variables:
            return variables[whole.group(1)]
        def sub(m):
            key = m.group(1)
            return str(variables[key]) if key in variables else m.group(0)
        return re.sub(r"\{([a-z_]+)\}", sub, value)
    if isinstance(value, list):
        return [fill(v, variables) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, variables) for k, v in value.items()}
    return value


def compare(op, current, expected):
    if op == "eq":
        return current == expected
    if op == "ne":
        return current != expected
    if op == "in":
        return current in expected
    if op == "gte":
        return current is not None and current >= expected
    if op == "lte":
        return current is not None and current <= expected
    if op == "truthy":
        return bool(current)
    if op == "falsy":
        return not current
    raise ValueError(f"unknown op {op}")


def availability(check, plan, visibility):
    """Return 'free', 'paid:<product>' or 'unavailable' for this plan and repo visibility."""
    avail = check.get("availability", {}).get(plan)
    if avail is None:
        return "unavailable"
    if isinstance(avail, dict):
        return avail.get(visibility or "org", "unavailable")
    return avail


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------------------------------------------
# Check kinds. Each returns (status, current, detail).


def kind_field(gh, check, v, cache):
    read = check["read"]
    path = fill(read["path"], v)
    if path not in cache:
        cache[path] = gh.get(path)
    data = cache[path]
    current = pointer(data, read.get("pointer"))
    if current is None and read.get("missing_is") is not None:
        current = read["missing_is"]
    if current is None and not read.get("allow_none"):
        return UNKNOWN, None, f"field `{read.get('pointer')}` not returned by {path} (no permission, or plan lacks it)"
    exp = check["expect"]
    return (PASS if compare(exp["op"], current, exp.get("value")) else FAIL), current, ""


def kind_status_endpoint(gh, check, v, cache):
    """Endpoints that answer 2xx when a feature is on and 404 when it is off."""
    path = fill(check["read"]["path"], v)
    try:
        data = gh.get(path)
        on = True
        if data is not None and check["read"].get("pointer"):
            on = bool(pointer(data, check["read"]["pointer"]))
    except ApiError as e:
        if e.status != 404:
            raise
        on = False
    want = check["expect"].get("value", True)
    return (PASS if on == want else FAIL), on, ""


def _file_exists(gh, owner, repo, path):
    try:
        gh.get(f"/repos/{owner}/{repo}/contents/{path}")
        return True
    except ApiError as e:
        if e.status == 404:
            return False
        raise


def kind_file_any(gh, check, v, cache):
    """Pass if any listed path exists in the repo, or (optionally) in the org's `.github` repo."""
    owner, repo = v["owner"], check["read"].get("repo") or v["repo"]
    for p in check["read"]["paths"]:
        if _file_exists(gh, owner, repo, p):
            return PASS, p, ""
    if check["read"].get("org_fallback"):
        key = f"org-dotgithub:{owner}"
        if key not in cache:
            cache[key] = {}
        for p in check["read"].get("org_paths", check["read"]["paths"]):
            if p not in cache[key]:
                try:
                    cache[key][p] = _file_exists(gh, owner, ".github", p)
                except ApiError:
                    cache[key][p] = False
            if cache[key][p]:
                return PASS, f"{owner}/.github:{p}", "inherited from the org .github repo"
    return FAIL, None, "none of: " + ", ".join(check["read"]["paths"])


def kind_branch_rules(gh, check, v, cache):
    """Check the rules that apply to the default branch (repo + org rulesets) and classic protection."""
    owner, repo, branch = v["owner"], v["repo"], v["default_branch"]
    rules = gh.get(f"/repos/{owner}/{repo}/rules/branches/{branch}", paginate=True) or []
    by_type = {}
    for r in rules:
        by_type.setdefault(r["type"], []).append(r.get("parameters") or {})
    classic = None
    try:
        classic = gh.get(f"/repos/{owner}/{repo}/branches/{branch}/protection")
    except ApiError as e:
        if e.status not in (403, 404):
            raise
    missing = []
    for req in check["expect"]["rules"]:
        rtype = req["type"]
        params_list = by_type.get(rtype, [])
        ok = any(all(compare(c["op"], p.get(c["param"]), c.get("value")) for c in req.get("params", []))
                 for p in params_list)
        if not ok and classic and _classic_satisfies(classic, req):
            ok = True
        if not ok:
            missing.append(rtype + "".join(f" {c['param']} {c['op']} {c.get('value')}" for c in req.get("params", [])))
    current = {"ruleset_rules": sorted(by_type), "classic_protection": bool(classic)}
    return (PASS if not missing else FAIL), current, ("missing: " + "; ".join(missing)) if missing else ""


def _classic_satisfies(classic, req):
    """Map a ruleset rule requirement to the classic branch protection response."""
    t = req["type"]
    if t == "deletion":
        return not pointer(classic, "allow_deletions.enabled")
    if t == "non_fast_forward":
        return not pointer(classic, "allow_force_pushes.enabled")
    if t == "required_linear_history":
        return bool(pointer(classic, "required_linear_history.enabled"))
    if t == "required_signatures":
        return bool(pointer(classic, "required_signatures.enabled"))
    if t == "pull_request":
        pr = classic.get("required_pull_request_reviews")
        if not pr:
            return False
        mapped = {
            "required_approving_review_count": pr.get("required_approving_review_count", 0),
            "dismiss_stale_reviews_on_push": pr.get("dismiss_stale_reviews", False),
            "require_code_owner_review": pr.get("require_code_owner_reviews", False),
            "require_last_push_approval": pr.get("require_last_push_approval", False),
        }
        return all(compare(c["op"], mapped.get(c["param"]), c.get("value")) for c in req.get("params", []))
    if t == "required_status_checks":
        return bool(pointer(classic, "required_status_checks.contexts") or
                    pointer(classic, "required_status_checks.checks"))
    return False


USES_RE = re.compile(r"^(\s*-?\s*uses:\s*)([\"']?)([^\s\"'#]+)\2(\s*#.*)?$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def lint_workflow_text(text):
    """Return a list of problems for one workflow file. Heuristic, no YAML parser (stdlib only)."""
    problems = []
    if not re.search(r"^permissions:", text, re.M):
        problems.append("no top-level `permissions:` block (GITHUB_TOKEN keeps the repo/org default)")
    elif re.search(r"^permissions:\s*write-all\s*$", text, re.M):
        problems.append("top-level `permissions: write-all`")
    for n, line in enumerate(text.splitlines(), 1):
        m = USES_RE.match(line)
        if not m:
            continue
        ref = m.group(3)
        if ref.startswith("./") or ref.startswith("docker://"):
            if ref.startswith("docker://") and "@sha256:" not in ref:
                problems.append(f"line {n}: container `{ref}` not pinned to a digest")
            continue
        if "@" not in ref:
            problems.append(f"line {n}: `{ref}` has no ref")
        elif not SHA_RE.match(ref.rsplit("@", 1)[1]):
            problems.append(f"line {n}: `{ref}` not pinned to a full commit SHA")
    return problems


def kind_workflows(gh, check, v, cache):
    owner, repo = v["owner"], v["repo"]
    try:
        entries = gh.get(f"/repos/{owner}/{repo}/contents/.github/workflows")
    except ApiError as e:
        if e.status == 404:
            return PASS, "no workflows", ""
        raise
    findings = []
    for entry in entries or []:
        if not entry.get("name", "").endswith((".yml", ".yaml")):
            continue
        f = gh.get(f"/repos/{owner}/{repo}/contents/{entry['path']}")
        text = base64.b64decode(f.get("content", "")).decode("utf-8", "replace")
        for p in lint_workflow_text(text):
            if check["read"].get("only") == "permissions" and "permissions" not in p:
                continue
            if check["read"].get("only") == "pinning" and "permissions" in p:
                continue
            findings.append(f"{entry['path']}: {p}")
    return (PASS if not findings else FAIL), len(findings), "\n".join(findings)


def _matches(item, group):
    return all(compare(c["op"], pointer(item, c["pointer"]), c.get("value")) for c in group)


def kind_list_match(gh, check, v, cache):
    """Read a list. `expect.any`: pass if an item matches one condition group. `expect.none`: fail if one does."""
    read = check["read"]
    path = fill(read["path"], v)
    if path not in cache:
        cache[path] = gh.get(path, paginate=read.get("paginate", False))
    items = pointer(cache[path], read.get("pointer")) or []
    exp = check["expect"]
    groups = exp.get("any") or exp.get("none")
    hits = [i for i in items if any(_matches(i, g) for g in groups)]
    label = read.get("label")
    current = [pointer(i, label) for i in hits] if label else len(hits)
    ok = bool(hits) if "any" in exp else not hits
    return (PASS if ok else FAIL), current, "" if ok else exp.get("fail_note", "")


def kind_manual(gh, check, v, cache):
    return MANUAL, None, check.get("manual", "")


KINDS = {
    "field": kind_field,
    "status_endpoint": kind_status_endpoint,
    "file_any": kind_file_any,
    "branch_rules": kind_branch_rules,
    "workflows": kind_workflows,
    "list_match": kind_list_match,
    "manual": kind_manual,
}


# ---------------------------------------------------------------------------------------------------------------
# detect / audit


def detect(gh, org):
    o = gh.get(f"/orgs/{org}")
    me = gh.get("/user")
    try:
        membership = gh.get(f"/orgs/{org}/memberships/{me['login']}")
        role = membership.get("role")
    except ApiError:
        role = None
    repos = gh.get(f"/orgs/{org}/repos?type=all&per_page=100", paginate=True) or []
    vis = {}
    for r in repos:
        if r.get("archived"):
            vis["archived"] = vis.get("archived", 0) + 1
            continue
        vis[r.get("visibility", "unknown")] = vis.get(r.get("visibility", "unknown"), 0) + 1
    plan = (o.get("plan") or {}).get("name")
    return {
        "org": org,
        "plan": plan,
        "plan_seats": (o.get("plan") or {}).get("seats"),
        "plan_filled_seats": (o.get("plan") or {}).get("filled_seats"),
        "your_login": me.get("login"),
        "your_role": role,
        "two_factor_requirement_enabled": o.get("two_factor_requirement_enabled"),
        "repo_counts": vis,
        "checked_at": now(),
        "notes": [] if plan else ["`plan` is only returned to org owners; pass --plan free|team to audit"],
    }


def normalize_plan(plan):
    """Map the API plan name to a catalog plan key."""
    if not plan:
        return None
    p = plan.lower()
    if p == "free":
        return "free"
    if p in ("team", "team_plan"):
        return "team"
    return p


def list_repos(gh, org, selectors, include_archived=False, include_forks=False):
    repos = gh.get(f"/orgs/{org}/repos?type=all&per_page=100", paginate=True) or []
    out = []
    for r in repos:
        if r.get("archived") and not include_archived:
            continue
        if r.get("fork") and not include_forks:
            continue
        if selectors and not any(fnmatch.fnmatch(r["name"], s) for s in selectors):
            continue
        out.append(r)
    return out


def run_check(gh, check, variables, plan, visibility, cache):
    avail = availability(check, plan, visibility)
    target = variables.get("target")
    base = {
        "id": check["id"],
        "key": f"{check['id']}@{target}",
        "target": target,
        "scope": check["scope"],
        "title": check["title"],
        "severity": check.get("severity", "medium"),
        "availability": avail,
        "scorecard": check.get("scorecard", []),
        "source": check.get("source", []),
        "fixable": bool(check.get("fix")) and check.get("fix", {}).get("kind") != "manual",
        "destructive": check.get("destructive", ""),
    }
    if avail == "unavailable":
        return dict(base, status=UNAVAILABLE, current=None, detail=f"not available on the {plan} plan for this target")
    when = check.get("when")
    if when and not all(compare(c["op"], variables.get(c["var"]), c.get("value")) for c in when):
        return dict(base, status=SKIPPED, current=None, detail=check.get("when_note", "condition not met"))
    try:
        # Another way to meet the check, for example an advanced CodeQL workflow instead of default setup.
        for p in check.get("pass_if_files", []):
            if _file_exists(gh, variables["owner"], variables["repo"], p):
                return dict(base, status=PASS, current=p, detail="met by file")
        status, current, detail = KINDS[check["kind"]](gh, check, variables, cache)
    except ApiError as e:
        status, current = UNKNOWN, None
        detail = {403: "no permission to read (need org owner / repo admin, or token scope)",
                  404: "not found (no permission, feature off for this plan, or endpoint not on this target)"}.get(
            e.status, str(e))
    return dict(base, status=status, current=current, detail=detail)


def audit(gh, catalog, org, plan=None, repo_selectors=None, scopes=("org", "repo"), only=None,
          include_archived=False, include_forks=False):
    info = detect(gh, org)
    plan = normalize_plan(plan or info["plan"])
    if plan not in catalog["plans"]:
        raise SystemExit(f"plan {plan!r} is not covered by this baseline (covered: {', '.join(catalog['plans'])})")
    results = []
    cache = {}
    checks = [c for c in catalog["checks"] if not only or any(fnmatch.fnmatch(c["id"], p) for p in only)]
    if "org" in scopes:
        v = {"org": org, "owner": org, "target": org, "plan": plan}
        for c in checks:
            if c["scope"] == "org":
                results.append(run_check(gh, c, v, plan, None, cache))
    repos = []
    if "repo" in scopes:
        repos = list_repos(gh, org, repo_selectors, include_archived, include_forks)
        for r in repos:
            rcache = {}
            v = {"org": org, "owner": org, "repo": r["name"], "target": f"{org}/{r['name']}", "plan": plan,
                 "default_branch": r.get("default_branch") or "main", "visibility": r.get("visibility"),
                 "archived": r.get("archived"), "fork": r.get("fork")}
            vis = "public" if r.get("visibility") == "public" else "private"
            for c in checks:
                if c["scope"] == "repo":
                    res = run_check(gh, c, v, plan, vis, rcache)
                    res["visibility"] = r.get("visibility")
                    res["default_branch"] = v["default_branch"]
                    results.append(res)
    return {
        "org": org,
        "plan": plan,
        "detect": info,
        "catalog_verified_on": catalog.get("verified_on"),
        "generated_at": now(),
        "repos": [r["name"] for r in repos],
        "results": results,
        "summary": summarize(results),
    }


def summarize(results):
    s = {}
    for r in results:
        k = r["status"]
        if k == FAIL and r["availability"].startswith("paid:"):
            k = "fail_paid"
        s[k] = s.get(k, 0) + 1
    return s


# ---------------------------------------------------------------------------------------------------------------
# report / catalog


def _cell(x):
    if x is None:
        return ""
    if not isinstance(x, str):
        x = json.dumps(x)
    return x.replace("|", "\\|").replace("\n", "<br>")


def report(findings, catalog, show=("fail", "unknown", "manual")):
    products = catalog.get("products", {})
    lines = [f"# Baseline audit: {findings['org']} ({findings['plan']} plan)", "",
             f"Generated {findings['generated_at']}. Catalog verified on {findings['catalog_verified_on']}.", "",
             "Summary: " + ", ".join(f"{k} {v}" for k, v in sorted(findings["summary"].items())), ""]
    paid = sorted({r["availability"].split(":", 1)[1] for r in findings["results"]
                   if r["status"] == FAIL and r["availability"].startswith("paid:")})
    if paid:
        lines += ["## Paid items (need the user's opt-in; fetch live prices before you ask)", ""]
        for p in paid:
            prod = products.get(p, {})
            lines.append(f"- **{prod.get('name', p)}** ({p}): billed per {prod.get('billing_unit', '?')}. "
                         f"Price pages: {', '.join(prod.get('pricing_urls', []))}")
        lines.append("")
    for scope in ("org", "repo"):
        rows = [r for r in findings["results"] if r["scope"] == scope and r["status"] in show]
        if not rows:
            continue
        lines += [f"## {scope.capitalize()} findings", "",
                  "| Key | Status | Cost | Fix | Title | Current | Detail |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for r in sorted(rows, key=lambda r: (r["status"], r["id"], r["target"])):
            fix = "auto" if r["fixable"] else "manual"
            if r["destructive"]:
                fix += " (destructive)"
            lines.append("| " + " | ".join(_cell(x) for x in (
                r["key"], r["status"], r["availability"], fix, r["title"], r["current"], r["detail"])) + " |")
        lines.append("")
    return "\n".join(lines)


def catalog_markdown(catalog):
    lines = [f"# Check catalog (verified on {catalog.get('verified_on')})", "",
             "Generated by `scripts/ghsetup.py catalog`. Do not edit by hand; edit `data/checks.json`.", ""]
    for scope in ("org", "repo"):
        lines += [f"## {scope.capitalize()} checks", "",
                  "| ID | Title | Free plan | Team plan | Fix | Scorecard | Source |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for c in catalog["checks"]:
            if c["scope"] != scope:
                continue
            av = c.get("availability", {})
            def fmt(x):
                if x is None:
                    return "no"
                if isinstance(x, dict):
                    return ", ".join(f"{k}: {val}" for k, val in x.items())
                return x
            fix = c.get("fix", {}).get("kind", "none")
            cells = [_cell(x) for x in (c["id"], c["title"], fmt(av.get("free")), fmt(av.get("team")), fix,
                                        ", ".join(c.get("scorecard", [])))]
            cells.append(" ".join(f"[{i + 1}]({u})" for i, u in enumerate(c.get("source", []))))
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    lines += ["## Paid products", "", "| Key | Name | Billing unit | Live price pages |", "| --- | --- | --- | --- |"]
    for k, p in catalog.get("products", {}).items():
        lines.append(f"| {k} | {p['name']} | {p.get('billing_unit', '')} | {' '.join(p.get('pricing_urls', []))} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# apply


def select_findings(findings, patterns, all_free=False):
    out = []
    for r in findings["results"]:
        if r["status"] != FAIL or not r["fixable"]:
            continue
        if all_free and r["availability"] == "free" and not r["destructive"]:
            out.append(r)
        elif patterns and any(fnmatch.fnmatch(r["key"], p) or fnmatch.fnmatch(r["id"], p) for p in patterns):
            out.append(r)
    return out


class MissingParams(Exception):
    pass


def resolve_vars(gh, specs, v):
    """Look up values that only exist at run time, for example the id of the "GitHub recommended" configuration."""
    out = {}
    for name, spec in (specs or {}).items():
        items = gh.get(fill(spec["path"], v)) or []
        hit = next((i for i in items if all(pointer(i, k) == val for k, val in spec["find"].items())), None)
        if hit is None:
            raise ApiError(None, f"could not resolve {name}: nothing in {spec['path']} matches {spec['find']}")
        out[name] = pointer(hit, spec["pointer"])
    return out


def plan_fix(check, r, findings, overrides=None, gh=None):
    """Turn a finding into concrete steps: dicts with method, path, body and merge.

    Template parameters come from the fix's `params` defaults, then from --set overrides. A param with a null
    default is required: the user must choose it (for example a security contact or a budget amount).
    `merge: true` on a step means: GET the path first and send the current object updated with the body, so a
    PUT does not reset fields that the baseline does not own.
    """
    owner, _, repo = r["target"].partition("/")
    fix = check["fix"]
    if "by_plan" in fix:
        fix = dict({k: val for k, val in fix.items() if k != "by_plan"}, **fix["by_plan"][findings["plan"]])
    v = dict(fix.get("params", {}))
    v.update(overrides or {})
    missing = sorted(k for k in fix.get("params", {}) if v.get(k) is None)
    if missing:
        raise MissingParams(f"{r['key']} needs --set " + " ".join(f"{k}=..." for k in missing))
    v.update({"org": findings["org"], "owner": owner, "repo": repo, "target": r["target"],
              "default_branch": r.get("default_branch") or "main"})
    if fix.get("resolve"):
        v.update(resolve_vars(gh, fix["resolve"], v))
    kind = fix["kind"]
    if kind == "api":
        return [{"method": s["method"], "path": fill(s["path"], v), "body": fill(s.get("body"), v),
                 "merge": s.get("merge", False)} for s in fix["steps"]]
    if kind == "ruleset":
        with open(os.path.join(TEMPLATES_DIR, fix["template"])) as f:
            body = fill(json.load(f), v)
        return [{"method": "POST", "path": fill(fix["path"], v), "body": body, "merge": False}]
    if kind == "pr_file":
        with open(os.path.join(TEMPLATES_DIR, fix["template"])) as f:
            content = fill(f.read(), v)
        target_repo = fix.get("repo") or repo
        return [{"method": "PR_FILE", "path": f"/repos/{owner}/{target_repo}", "merge": False,
                 "body": {"path": fix["path"], "content": content,
                          "branch": fix.get("branch", "baseline/" + check["id"].lower()),
                          "message": fix.get("message", check["title"]), "create_repo": fix.get("create_repo")}}]
    raise ValueError(f"no automatic fix for kind {kind}")


def open_file_pr(gh, repo_path, spec, org):
    """Create a branch, commit one file and open a PR. Never pushes to the default branch."""
    owner, repo = repo_path.split("/")[2:4]
    try:
        info = gh.get(f"/repos/{owner}/{repo}")
    except ApiError as e:
        if e.status != 404 or not spec.get("create_repo"):
            raise
        info = gh.api("POST", f"/orgs/{org}/repos", spec["create_repo"])
        if spec["create_repo"].get("auto_init"):
            info = gh.get(f"/repos/{owner}/{repo}")
    base = info["default_branch"]
    sha = gh.get(f"/repos/{owner}/{repo}/git/ref/heads/{base}")["object"]["sha"]
    try:
        gh.api("POST", f"/repos/{owner}/{repo}/git/refs", {"ref": f"refs/heads/{spec['branch']}", "sha": sha})
    except ApiError as e:
        if e.status != 422:  # 422: branch exists already; reuse it
            raise
    body = {"message": spec["message"], "branch": spec["branch"],
            "content": base64.b64encode(spec["content"].encode()).decode()}
    try:
        existing = gh.get(f"/repos/{owner}/{repo}/contents/{spec['path']}?ref={spec['branch']}")
        body["sha"] = existing["sha"]
    except ApiError as e:
        if e.status != 404:
            raise
    gh.api("PUT", f"/repos/{owner}/{repo}/contents/{spec['path']}", body)
    pr = gh.api("POST", f"/repos/{owner}/{repo}/pulls",
                {"title": spec["message"], "head": spec["branch"], "base": base,
                 "body": "Adds `" + spec["path"] + "` from the org baseline. Review before you merge."})
    return pr.get("html_url")


def parse_sets(pairs):
    """Parse --set key=value pairs. Values are JSON if they parse (1, true, ["a"]), else strings."""
    out = {}
    for pair in pairs or []:
        key, sep, raw = pair.partition("=")
        if not sep:
            raise SystemExit(f"--set needs key=value, got {pair!r}")
        try:
            out[key] = json.loads(raw)
        except ValueError:
            out[key] = raw
    return out


def apply(gh, catalog, findings, patterns, all_free, accept_cost, execute, out=sys.stdout, overrides=None):
    by_id = {c["id"]: c for c in catalog["checks"]}
    chosen = select_findings(findings, patterns, all_free)
    log = []
    if not chosen:
        print("Nothing selected. Only findings with status `fail` and an automatic fix can be applied.", file=out)
        return log
    blocked = []
    for r in chosen:
        av = r["availability"]
        if av.startswith("paid:") and av.split(":", 1)[1] not in accept_cost:
            blocked.append(r)
    if blocked:
        print("Refused: these fixes enable a paid product. Ask the user, show the live price, then pass "
              "--accept-cost <product> for each product they accept:", file=out)
        for r in blocked:
            print(f"  {r['key']}  ({r['availability']})", file=out)
        chosen = [r for r in chosen if r not in blocked]
    seen = set()
    for r in chosen:
        check = by_id[r["id"]]
        try:
            steps = plan_fix(check, r, findings, overrides, gh)
        except (MissingParams, ApiError) as e:
            print(f"[skipped] {e}", file=out)
            log.append({"key": r["key"], "ok": False, "error": str(e), "executed": False,
                        "needs_input": isinstance(e, MissingParams)})
            continue
        for step in steps:
            method, path, body = step["method"], step["path"], step["body"]
            # One org-level fix (for example an org ruleset) can close the same finding on many repos: run it once.
            sig = (method, path, json.dumps(body, sort_keys=True))
            if sig in seen:
                log.append({"key": r["key"], "method": method, "path": path, "executed": False,
                            "ok": True, "note": "same step already planned for another finding"})
                continue
            seen.add(sig)
            entry = {"key": r["key"], "method": method, "path": path, "body": body, "executed": execute}
            if not execute:
                shown = json.dumps(body) if body is not None else ""
                if method == "PR_FILE":
                    print(f"[dry run] {r['key']}: open PR on {path} adding {body['path']}", file=out)
                else:
                    print(f"[dry run] {r['key']}: gh api --method {method} {path}"
                          + (f" --input - <<< '{shown}'" if shown else "")
                          + ("   (merged into the current value)" if step["merge"] else ""), file=out)
            else:
                try:
                    if method == "PR_FILE":
                        entry["result"] = open_file_pr(gh, path, body, findings["org"])
                    else:
                        if step["merge"]:
                            # GET can return read-only links (for example selected_actions_url); do not send them.
                            current = {k: val for k, val in (gh.get(path) or {}).items() if not k.endswith("_url")}
                            body = dict(current, **body)
                            entry["body"] = body
                        entry["result"] = gh.api(method, path, body)
                    entry["ok"] = True
                    print(f"[done] {r['key']}: {method} {path}", file=out)
                except ApiError as e:
                    entry["ok"] = False
                    entry["error"] = str(e)
                    print(f"[error] {r['key']}: {method} {path}: {e}", file=out)
            log.append(entry)
    return log


def verify(gh, catalog, findings, keys):
    """Re-run the checks for the given finding keys after apply."""
    by_id = {c["id"]: c for c in catalog["checks"]}
    out = []
    for r in findings["results"]:
        if r["key"] not in keys:
            continue
        owner, _, repo = r["target"].partition("/")
        v = {"org": findings["org"], "owner": owner, "repo": repo, "target": r["target"], "plan": findings["plan"],
             "default_branch": r.get("default_branch") or "main", "visibility": r.get("visibility")}
        vis = None if r["scope"] == "org" else ("public" if r.get("visibility") == "public" else "private")
        out.append(run_check(gh, by_id[r["id"]], v, findings["plan"], vis, {}))
    return out


# ---------------------------------------------------------------------------------------------------------------
# workflows / pin (local checkout)


def iter_workflow_files(root):
    wf = os.path.join(root, ".github", "workflows")
    if not os.path.isdir(wf):
        return
    for name in sorted(os.listdir(wf)):
        if name.endswith((".yml", ".yaml")):
            yield os.path.join(wf, name)


def pin_text(text, resolve):
    """Pin `uses: owner/repo[/path]@ref` lines to a full SHA. `resolve(owner, repo, ref)` returns a SHA."""
    out, changes = [], []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        nl = line[len(body):]
        m = USES_RE.match(body)
        if m and "@" in m.group(3) and not m.group(3).startswith(("./", "docker://")):
            action, ref = m.group(3).rsplit("@", 1)
            if not SHA_RE.match(ref):
                parts = action.split("/")
                sha = resolve(parts[0], parts[1], ref)
                new = f"{m.group(1)}{m.group(2)}{action}@{sha}{m.group(2)} # {ref}"
                changes.append((m.group(3), f"{action}@{sha}"))
                out.append(new + nl)
                continue
        out.append(line)
    return "".join(out), changes


def make_resolver(gh):
    cache = {}

    def resolve(owner, repo, ref):
        key = (owner, repo, ref)
        if key not in cache:
            cache[key] = gh.get(f"/repos/{owner}/{repo}/commits/{ref}")["sha"]
        return cache[key]
    return resolve


# ---------------------------------------------------------------------------------------------------------------
# scorecard


def scorecard(repo, gh=None):
    """Return normalized Scorecard JSON for owner/repo. Prefer the local CLI (works for private repos)."""
    if shutil.which("scorecard"):
        env = dict(os.environ)
        if not env.get("GITHUB_AUTH_TOKEN"):
            tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
            if tok:
                env["GITHUB_AUTH_TOKEN"] = tok
        proc = subprocess.run(["scorecard", f"--repo=github.com/{repo}", "--format=json"],
                              capture_output=True, text=True, env=env)
        if proc.returncode == 0:
            return normalize_scorecard(json.loads(proc.stdout), "cli")
        sys.stderr.write(proc.stderr)
    url = f"https://api.scorecard.dev/projects/github.com/{repo}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return normalize_scorecard(json.load(resp), "api.scorecard.dev")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"repo": repo, "source": "api.scorecard.dev", "error":
                    "no published result (repo not public, or not in the Scorecard index); "
                    "install the scorecard CLI or add the scorecard action"}
        raise


def normalize_scorecard(data, source):
    checks = [{"name": c.get("name"), "score": c.get("score"), "reason": c.get("reason"),
               "doc": (c.get("documentation") or {}).get("url")} for c in data.get("checks", [])]
    return {"repo": (data.get("repo") or {}).get("name"), "source": source, "date": data.get("date"),
            "score": data.get("score"), "version": (data.get("scorecard") or {}).get("version"),
            "checks": sorted(checks, key=lambda c: (c["score"] if c["score"] is not None else 99, c["name"]))}


def scorecard_markdown(sc, catalog):
    if sc.get("error"):
        return f"Scorecard for {sc['repo']}: {sc['error']}\n"
    mapping = {}
    for c in catalog["checks"]:
        for name in c.get("scorecard", []):
            mapping.setdefault(name, []).append(c["id"])
    lines = [f"# OpenSSF Scorecard: {sc['repo']} — {sc['score']}/10", "",
             f"Source {sc['source']}, date {sc['date']}, scorecard {sc['version']}.", "",
             "| Check | Score | Reason | Baseline checks that help |", "| --- | --- | --- | --- |"]
    for c in sc["checks"]:
        score = "n/a" if c["score"] in (None, -1) else c["score"]
        lines.append(f"| {c['name']} | {score} | {_cell(c['reason'])} | {', '.join(mapping.get(c['name'], [])) or '—'} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# costs (read only)


def costs(gh, org):
    """Collect what the org pays for now: plan seats, this month's billed usage, budgets, Copilot seats."""
    out = {"org": org, "checked_at": now(), "errors": {}}

    def safe(key, fn):
        try:
            out[key] = fn()
        except ApiError as e:
            out[key] = None
            out["errors"][key] = str(e)

    safe("plan", lambda: (gh.get(f"/orgs/{org}").get("plan") or {}))
    safe("usage", lambda: gh.get(f"/organizations/{org}/settings/billing/usage/summary"))
    safe("budgets", lambda: (gh.get(f"/organizations/{org}/settings/billing/budgets") or {}).get("budgets", []))
    safe("copilot", lambda: gh.get(f"/orgs/{org}/copilot/billing"))
    return out


def costs_markdown(c, catalog):
    lines = [f"# Current costs: {c['org']}", "", f"Checked {c['checked_at']}. Read only; nothing was changed.", ""]
    plan = c.get("plan") or {}
    lines += [f"- Plan: **{plan.get('name')}**, seats {plan.get('seats')}, filled seats {plan.get('filled_seats')}"]
    cp = c.get("copilot")
    if cp:
        lines.append(f"- Copilot: plan_type {cp.get('plan_type')}, seat management {cp.get('seat_management_setting')}, "
                     f"seats {pointer(cp, 'seat_breakdown.total')}")
    lines.append("")
    usage = c.get("usage") or {}
    items = usage.get("usageItems") or []
    if items:
        period = usage.get("timePeriod") or {}
        lines += [f"## Usage this period ({period.get('year')}-{period.get('month')})", "",
                  "| Product | SKU | Quantity | Unit | Gross | Discount | Net (billed) |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for i in sorted(items, key=lambda i: -(i.get("netAmount") or 0)):
            lines.append(f"| {i.get('product')} | {i.get('sku')} | {i.get('grossQuantity')} | {i.get('unitType')} | "
                         f"{i.get('grossAmount')} | {i.get('discountAmount')} | {i.get('netAmount')} |")
        lines.append("")
    budgets = c.get("budgets")
    if budgets is not None:
        lines += ["## Budgets", ""]
        if not budgets:
            lines.append("No budgets. Metered usage beyond the included amount is billed with no limit.")
        else:
            lines += ["| SKU / product | Scope | Amount | Stops usage | Alerts |", "| --- | --- | --- | --- | --- |"]
            for b in budgets:
                lines.append(f"| {b.get('budget_product_sku')} | {b.get('budget_scope')} | {b.get('budget_amount')} | "
                             f"{b.get('prevent_further_usage')} | {pointer(b, 'budget_alerting.will_alert')} |")
        lines.append("")
    if c["errors"]:
        lines += ["## Could not read", ""] + [f"- {k}: {v}" for k, v in c["errors"].items()] + [""]
    lines += ["## Live price pages (read these before you ask the user to opt in)", ""]
    lines += [f"- {u}" for u in catalog.get("pricing_pages", [])]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------------------------------------------
# CLI


def main(argv=None, gh=None):
    p = argparse.ArgumentParser(prog="ghsetup", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--catalog", default=CHECKS_FILE, help="check catalog JSON (default: data/checks.json)")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detect", help="print plan, role, repo counts")
    d.add_argument("org")

    a = sub.add_parser("audit", help="compare org and repos with the baseline")
    a.add_argument("org")
    a.add_argument("--plan", choices=["free", "team"], help="override the detected plan")
    a.add_argument("--repos", nargs="*", help="repo name globs (default: all non-archived, non-fork)")
    a.add_argument("--scope", choices=["org", "repo", "all"], default="all")
    a.add_argument("--only", nargs="*", help="check ID globs, e.g. ORG-ACTIONS-*")
    a.add_argument("--include-archived", action="store_true")
    a.add_argument("--include-forks", action="store_true")
    a.add_argument("--out", help="write findings JSON here (default: stdout)")
    a.add_argument("--fail-on-findings", action="store_true", help="exit 2 if any free check fails")

    r = sub.add_parser("report", help="markdown from findings JSON")
    r.add_argument("findings")
    r.add_argument("--all", action="store_true", help="also show pass, unavailable and skipped")

    ap = sub.add_parser("apply", help="apply fixes for selected findings (dry run unless --execute)")
    ap.add_argument("findings")
    ap.add_argument("--select", nargs="*", default=[], help="finding key or check ID globs, e.g. 'REPO-*@org/api'")
    ap.add_argument("--all-free", action="store_true", help="select every free, non-destructive fixable failure")
    ap.add_argument("--accept-cost", nargs="*", default=[], help="paid product keys the user accepted")
    ap.add_argument("--execute", action="store_true", help="really call the API (default is a dry run)")
    ap.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE",
                    help="template parameters, e.g. review_count=0 (values parsed as JSON when possible)")
    ap.add_argument("--log", help="write the apply log JSON here")

    sub.add_parser("catalog", help="markdown of all checks")

    w = sub.add_parser("workflows", help="lint .github/workflows in a local checkout")
    w.add_argument("path", nargs="?", default=".")

    pn = sub.add_parser("pin", help="pin actions to full commit SHAs in a local checkout")
    pn.add_argument("path", nargs="?", default=".")
    pn.add_argument("--write", action="store_true", help="rewrite files (default: show changes only)")

    co = sub.add_parser("costs", help="read current plan, usage, budgets and Copilot seats (read only)")
    co.add_argument("org")
    co.add_argument("--json", action="store_true")

    s = sub.add_parser("scorecard", help="OpenSSF Scorecard for owner/repo")
    s.add_argument("repo")
    s.add_argument("--json", action="store_true")

    args = p.parse_args(argv)
    gh = gh or Gh()

    try:
        if args.cmd == "workflows":
            bad = 0
            for f in iter_workflow_files(args.path):
                with open(f) as fh:
                    for prob in lint_workflow_text(fh.read()):
                        print(f"{os.path.relpath(f, args.path)}: {prob}")
                        bad += 1
            print(f"{bad} problem(s)")
            return 1 if bad else 0
        if args.cmd == "pin":
            resolve = make_resolver(gh)
            total = 0
            for f in iter_workflow_files(args.path):
                with open(f) as fh:
                    text = fh.read()
                new, changes = pin_text(text, resolve)
                for old, pinned in changes:
                    print(f"{os.path.relpath(f, args.path)}: {old} -> {pinned}")
                total += len(changes)
                if changes and args.write:
                    with open(f, "w") as fh:
                        fh.write(new)
            print(f"{total} reference(s) {'pinned' if args.write else 'to pin (run with --write)'}")
            return 0

        catalog = load_catalog(args.catalog)
        if args.cmd == "catalog":
            sys.stdout.write(catalog_markdown(catalog))
            return 0
        if args.cmd == "detect":
            print(json.dumps(detect(gh, args.org), indent=2))
            return 0
        if args.cmd == "audit":
            scopes = ("org", "repo") if args.scope == "all" else (args.scope,)
            result = audit(gh, catalog, args.org, args.plan, args.repos, scopes, args.only,
                           args.include_archived, args.include_forks)
            text = json.dumps(result, indent=2)
            if args.out:
                with open(args.out, "w") as f:
                    f.write(text + "\n")
                print(f"wrote {args.out}: " + ", ".join(f"{k} {v}" for k, v in sorted(result["summary"].items())))
            else:
                print(text)
            if args.fail_on_findings and any(x["status"] == FAIL and x["availability"] == "free"
                                             for x in result["results"]):
                return 2
            return 0
        if args.cmd == "report":
            with open(args.findings) as f:
                findings = json.load(f)
            show = (PASS, FAIL, UNKNOWN, MANUAL, UNAVAILABLE, SKIPPED) if args.all else (FAIL, UNKNOWN, MANUAL)
            print(report(findings, catalog, show))
            return 0
        if args.cmd == "apply":
            with open(args.findings) as f:
                findings = json.load(f)
            log = apply(gh, catalog, findings, args.select, args.all_free, set(args.accept_cost), args.execute,
                        overrides=parse_sets(args.set))
            if args.execute and log:
                keys = {e["key"] for e in log if e.get("ok")}
                for res in verify(gh, catalog, findings, keys):
                    print(f"[verify] {res['key']}: {res['status']} {res['detail']}".rstrip())
            if args.log:
                with open(args.log, "w") as f:
                    json.dump(log, f, indent=2)
            if any(e.get("ok") is False and not e.get("needs_input") for e in log):
                return 1
            return 3 if any(e.get("needs_input") for e in log) else 0
        if args.cmd == "costs":
            c = costs(gh, args.org)
            print(json.dumps(c, indent=2) if args.json else costs_markdown(c, catalog))
            return 0
        if args.cmd == "scorecard":
            sc = scorecard(args.repo)
            print(json.dumps(sc, indent=2) if args.json else scorecard_markdown(sc, catalog))
            return 0
    except ApiError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
