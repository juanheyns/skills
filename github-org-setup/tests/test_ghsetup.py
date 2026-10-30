"""Offline tests for scripts/ghsetup.py. Run: python3 -m unittest discover -s github-org-setup/tests"""

import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import ghsetup  # noqa: E402


class FakeGitHub:
    """Answers `gh api` argument lists from a dict {(METHOD, path): (status, body)}."""

    def __init__(self, routes):
        self.routes = routes
        self.writes = []

    def __call__(self, args, stdin=None):
        method = args[args.index("--method") + 1]
        path = next(a for a in args[1:] if a.startswith("/"))
        if method != "GET":
            self.writes.append((method, path, json.loads(stdin) if stdin else None))
        status, body = self.routes.get((method, path), (404, {"message": "Not Found"}))
        if status >= 400:
            return 1, "", f"gh: {body.get('message')} (HTTP {status})"
        if "--paginate" in args and isinstance(body, list):
            body = [body]
        return 0, "" if body is None else json.dumps(body), ""


ORG = {"login": "acme", "plan": {"name": "free", "seats": 1, "filled_seats": 1},
       "default_repository_permission": "write", "two_factor_requirement_enabled": False}
REPOS = [{"name": "api", "visibility": "public", "default_branch": "main", "archived": False, "fork": False},
         {"name": "secret", "visibility": "private", "default_branch": "main", "archived": False, "fork": False},
         {"name": "old", "visibility": "public", "default_branch": "main", "archived": True, "fork": False}]


def base_routes(extra=None):
    routes = {
        ("GET", "/orgs/acme"): (200, ORG),
        ("GET", "/user"): (200, {"login": "me"}),
        ("GET", "/orgs/acme/memberships/me"): (200, {"role": "admin"}),
        ("GET", "/orgs/acme/repos?type=all&per_page=100"): (200, REPOS),
    }
    routes.update(extra or {})
    return routes


CATALOG = {
    "verified_on": "2026-10-30",
    "plans": ["free", "team"],
    "products": {"secret_protection": {"name": "GitHub Secret Protection", "billing_unit": "active committer",
                                       "pricing_urls": ["https://github.com/pricing"]}},
    "checks": [
        {"id": "ORG-BASE-PERM", "scope": "org", "title": "Base permission is read or none", "kind": "field",
         "availability": {"free": "free", "team": "free"},
         "read": {"path": "/orgs/{org}", "pointer": "default_repository_permission"},
         "expect": {"op": "in", "value": ["read", "none"]},
         "fix": {"kind": "api", "steps": [{"method": "PATCH", "path": "/orgs/{org}",
                                           "body": {"default_repository_permission": "read"}}]}},
        {"id": "REPO-VULN-ALERTS", "scope": "repo", "title": "Dependabot alerts on", "kind": "status_endpoint",
         "availability": {"free": "free", "team": "free"},
         "read": {"path": "/repos/{owner}/{repo}/vulnerability-alerts"}, "expect": {"value": True},
         "fix": {"kind": "api", "steps": [{"method": "PUT", "path": "/repos/{owner}/{repo}/vulnerability-alerts"}]}},
        {"id": "REPO-SECRET-SCAN", "scope": "repo", "title": "Secret scanning on", "kind": "field",
         "availability": {"free": {"public": "free", "private": "unavailable"},
                          "team": {"public": "free", "private": "paid:secret_protection"}},
         "read": {"path": "/repos/{owner}/{repo}", "pointer": "security_and_analysis.secret_scanning.status"},
         "expect": {"op": "eq", "value": "enabled"},
         "fix": {"kind": "api", "steps": [{"method": "PATCH", "path": "/repos/{owner}/{repo}",
                                           "body": {"security_and_analysis": {"secret_scanning": {"status": "enabled"}}}}]}},
        {"id": "REPO-SECURITY-MD", "scope": "repo", "title": "Security policy", "kind": "file_any",
         "availability": {"free": "free", "team": "free"},
         "read": {"paths": ["SECURITY.md", ".github/SECURITY.md"], "org_fallback": True},
         "fix": {"kind": "manual"}},
        {"id": "REPO-BRANCH-RULES", "scope": "repo", "title": "Default branch protected", "kind": "branch_rules",
         "availability": {"free": {"public": "free", "private": "unavailable"}, "team": "free"},
         "expect": {"rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
                              {"type": "pull_request", "params": [
                                  {"param": "required_approving_review_count", "op": "gte", "value": 1}]}]},
         "fix": {"kind": "manual"}},
        {"id": "ORG-2FA", "scope": "org", "title": "Require 2FA", "kind": "manual", "manual": "UI only",
         "availability": {"free": "free", "team": "free"}},
    ],
}


def run_audit(routes, plan=None, catalog=CATALOG):
    fake = FakeGitHub(routes)
    return ghsetup.audit(ghsetup.Gh(fake), catalog, "acme", plan=plan), fake


def by_key(findings):
    return {r["key"]: r for r in findings["results"]}


class TestHelpers(unittest.TestCase):
    def test_pointer_and_fill(self):
        self.assertEqual(ghsetup.pointer({"a": {"b": 1}}, "a.b"), 1)
        self.assertIsNone(ghsetup.pointer({"a": 1}, "a.b"))
        self.assertEqual(ghsetup.fill({"p": "/repos/{owner}/{repo}", "x": ["{nope}"]}, {"owner": "o", "repo": "r"}),
                         {"p": "/repos/o/r", "x": ["{nope}"]})

    def test_availability(self):
        c = CATALOG["checks"][2]
        self.assertEqual(ghsetup.availability(c, "free", "private"), "unavailable")
        self.assertEqual(ghsetup.availability(c, "team", "private"), "paid:secret_protection")
        self.assertEqual(ghsetup.availability(c, "team", "public"), "free")
        self.assertEqual(ghsetup.availability(c, "enterprise", "public"), "unavailable")

    def test_gh_parses_http_status(self):
        gh = ghsetup.Gh(lambda args, stdin=None: (1, "", "gh: Not Found (HTTP 404)"))
        with self.assertRaises(ghsetup.ApiError) as cm:
            gh.get("/x")
        self.assertEqual(cm.exception.status, 404)


class TestAudit(unittest.TestCase):
    def test_org_and_repo_checks(self):
        routes = base_routes({
            ("GET", "/repos/acme/api/vulnerability-alerts"): (204, None),
            ("GET", "/repos/acme/api"): (200, {"security_and_analysis": {"secret_scanning": {"status": "disabled"}}}),
            ("GET", "/repos/acme/.github/contents/SECURITY.md"): (200, {"sha": "x"}),
            ("GET", "/repos/acme/api/rules/branches/main"): (200, [
                {"type": "deletion"}, {"type": "non_fast_forward"},
                {"type": "pull_request", "parameters": {"required_approving_review_count": 1}}]),
        })
        findings, _ = run_audit(routes)
        r = by_key(findings)
        self.assertEqual(findings["plan"], "free")
        self.assertNotIn("old", findings["repos"], "archived repos are skipped by default")
        self.assertEqual(r["ORG-BASE-PERM@acme"]["status"], "fail")
        self.assertEqual(r["ORG-2FA@acme"]["status"], "manual")
        self.assertEqual(r["REPO-VULN-ALERTS@acme/api"]["status"], "pass")
        self.assertEqual(r["REPO-VULN-ALERTS@acme/secret"]["status"], "fail", "404 means off")
        self.assertEqual(r["REPO-SECRET-SCAN@acme/api"]["status"], "fail")
        self.assertEqual(r["REPO-SECRET-SCAN@acme/secret"]["status"], "unavailable")
        self.assertEqual(r["REPO-SECURITY-MD@acme/api"]["status"], "pass")
        self.assertIn(".github", r["REPO-SECURITY-MD@acme/api"]["current"])
        self.assertEqual(r["REPO-BRANCH-RULES@acme/api"]["status"], "pass")
        self.assertEqual(r["REPO-BRANCH-RULES@acme/secret"]["status"], "unavailable")

    def test_branch_rules_missing_and_classic(self):
        routes = base_routes({
            ("GET", "/repos/acme/api/rules/branches/main"): (200, [{"type": "deletion"}]),
            ("GET", "/repos/acme/api/branches/main/protection"): (200, {
                "allow_force_pushes": {"enabled": False}, "allow_deletions": {"enabled": False}}),
        })
        r = by_key(run_audit(routes)[0])["REPO-BRANCH-RULES@acme/api"]
        self.assertEqual(r["status"], "fail")
        self.assertIn("pull_request", r["detail"])
        self.assertNotIn("non_fast_forward", r["detail"], "classic protection blocks force pushes")

    def test_permission_errors_are_unknown(self):
        routes = base_routes({("GET", "/repos/acme/api/vulnerability-alerts"): (403, {"message": "Forbidden"})})
        r = by_key(run_audit(routes)[0])["REPO-VULN-ALERTS@acme/api"]
        self.assertEqual(r["status"], "unknown")

    def test_plan_override_and_unsupported_plan(self):
        routes = base_routes()
        routes[("GET", "/orgs/acme")] = (200, dict(ORG, plan={"name": "enterprise"}))
        with self.assertRaises(SystemExit):
            run_audit(routes)
        findings, _ = run_audit(routes, plan="team")
        self.assertEqual(by_key(findings)["REPO-SECRET-SCAN@acme/secret"]["availability"], "paid:secret_protection")


class TestApply(unittest.TestCase):
    def setUp(self):
        routes = base_routes({
            ("GET", "/repos/acme/api"): (200, {"security_and_analysis": {"secret_scanning": {"status": "disabled"}}}),
            ("GET", "/repos/acme/secret"): (200, {"security_and_analysis": {"secret_scanning": {"status": "disabled"}}}),
        })
        self.findings, _ = run_audit(routes, plan="team")

    def test_dry_run_writes_nothing(self):
        fake = FakeGitHub({})
        out = io.StringIO()
        ghsetup.apply(ghsetup.Gh(fake), CATALOG, self.findings, [], True, set(), execute=False, out=out)
        self.assertEqual(fake.writes, [])
        self.assertIn("[dry run] ORG-BASE-PERM@acme: gh api --method PATCH /orgs/acme", out.getvalue())

    def test_paid_needs_accept_cost(self):
        fake = FakeGitHub({("PATCH", "/repos/acme/secret"): (200, {})})
        out = io.StringIO()
        ghsetup.apply(ghsetup.Gh(fake), CATALOG, self.findings, ["REPO-SECRET-SCAN"], False, set(), True, out)
        self.assertIn("Refused", out.getvalue())
        self.assertNotIn(("PATCH", "/repos/acme/secret"), [(m, p) for m, p, _ in fake.writes])

        fake = FakeGitHub({("PATCH", "/repos/acme/secret"): (200, {}), ("PATCH", "/repos/acme/api"): (200, {})})
        ghsetup.apply(ghsetup.Gh(fake), CATALOG, self.findings, ["REPO-SECRET-SCAN"], False,
                      {"secret_protection"}, True, io.StringIO())
        self.assertIn(("PATCH", "/repos/acme/secret"), [(m, p) for m, p, _ in fake.writes])

    def test_all_free_skips_paid_and_manual(self):
        fake = FakeGitHub({("PATCH", "/orgs/acme"): (200, {}), ("PATCH", "/repos/acme/api"): (200, {}),
                           ("PUT", "/repos/acme/api/vulnerability-alerts"): (204, None),
                           ("PUT", "/repos/acme/secret/vulnerability-alerts"): (204, None)})
        ghsetup.apply(ghsetup.Gh(fake), CATALOG, self.findings, [], True, set(), True, io.StringIO())
        paths = sorted(p for _, p, _ in fake.writes)
        self.assertEqual(paths, ["/orgs/acme", "/repos/acme/api", "/repos/acme/api/vulnerability-alerts",
                                 "/repos/acme/secret/vulnerability-alerts"])


class TestEngineFeatures(unittest.TestCase):
    """list_match, #wrap, merge steps, resolve, required params, by_plan and de-duplication."""

    CAT = {
        "verified_on": "x", "plans": ["free", "team"], "products": {},
        "checks": [
            {"id": "ORG-DEFAULTS", "scope": "org", "title": "t", "kind": "list_match",
             "availability": {"free": "free", "team": "free"},
             "read": {"path": "/orgs/{org}/defaults", "label": "configuration.name"},
             "expect": {"any": [[{"pointer": "default_for_new_repos", "op": "in", "value": ["public", "all"]}]]},
             "fix": {"kind": "api",
                     "resolve": {"cid": {"path": "/orgs/{org}/configs", "find": {"name": "GitHub recommended"},
                                         "pointer": "id"}},
                     "steps": [{"method": "PUT", "path": "/orgs/{org}/configs/{cid}/defaults",
                                "body": {"default_for_new_repos": "public"}}]}},
            {"id": "ORG-FORK", "scope": "org", "title": "t", "kind": "list_match",
             "availability": {"free": "free", "team": "free"},
             "read": {"path": "/orgs/{org}/fork", "pointer": "#wrap"},
             "expect": {"none": [[{"pointer": "send_secrets", "op": "eq", "value": True}]]},
             "fix": {"kind": "api", "steps": [{"method": "PUT", "path": "/orgs/{org}/fork",
                                               "body": {"send_secrets": False}, "merge": True}]}},
            {"id": "ORG-BUDGET", "scope": "org", "title": "t", "kind": "list_match",
             "availability": {"free": "free", "team": "free"},
             "read": {"path": "/orgs/{org}/budgets", "pointer": "budgets"},
             "expect": {"any": [[{"pointer": "sku", "op": "eq", "value": "actions"}]]},
             "fix": {"kind": "api", "params": {"amount": None},
                     "steps": [{"method": "POST", "path": "/orgs/{org}/budgets", "body": {"amount": "{amount}"}}]}},
            {"id": "REPO-RULES", "scope": "repo", "title": "t", "kind": "branch_rules",
             "availability": {"free": "free", "team": "free"},
             "expect": {"rules": [{"type": "deletion"}]},
             "fix": {"kind": "ruleset", "params": {"review_count": 1, "require_code_owner_review": False,
                                                   "require_last_push_approval": True, "bypass_actors": []},
                     "by_plan": {"free": {"template": "ruleset-repo-default-branch.json",
                                          "path": "/repos/{owner}/{repo}/rulesets"},
                                 "team": {"template": "ruleset-org-default-branch.json",
                                          "path": "/orgs/{org}/rulesets"}}}},
        ],
    }

    def routes(self, plan="free"):
        org = dict(ORG, plan={"name": plan})
        r = base_routes({
            ("GET", "/orgs/acme"): (200, org),
            ("GET", "/orgs/acme/defaults"): (200, [{"default_for_new_repos": "private_and_internal",
                                                    "configuration": {"name": "custom"}}]),
            ("GET", "/orgs/acme/configs"): (200, [{"id": 7, "name": "other"}, {"id": 17, "name": "GitHub recommended"}]),
            ("GET", "/orgs/acme/fork"): (200, {"run": True, "send_secrets": True}),
            ("GET", "/orgs/acme/budgets"): (200, {"budgets": [{"sku": "packages"}]}),
            ("GET", "/repos/acme/api/rules/branches/main"): (200, []),
            ("GET", "/repos/acme/secret/rules/branches/main"): (200, []),
        })
        return r

    def test_list_match_any_none_and_wrap(self):
        findings, _ = run_audit(self.routes(), catalog=self.CAT)
        r = by_key(findings)
        self.assertEqual(r["ORG-DEFAULTS@acme"]["status"], "fail")
        self.assertEqual(r["ORG-FORK@acme"]["status"], "fail")
        self.assertEqual(r["ORG-BUDGET@acme"]["status"], "fail")

    def test_resolve_merge_and_required_params(self):
        routes = self.routes()
        findings, _ = run_audit(routes, catalog=self.CAT)
        routes.update({("PUT", "/orgs/acme/configs/17/defaults"): (200, {}), ("PUT", "/orgs/acme/fork"): (200, {}),
                       ("POST", "/orgs/acme/budgets"): (201, {})})
        fake = FakeGitHub(routes)
        out = io.StringIO()
        log = ghsetup.apply(ghsetup.Gh(fake), self.CAT, findings, ["ORG-*"], False, set(), True, out)
        writes = {(m, p): b for m, p, b in fake.writes}
        self.assertIn(("PUT", "/orgs/acme/configs/17/defaults"), writes, "id resolved by name")
        self.assertEqual(writes[("PUT", "/orgs/acme/fork")], {"run": True, "send_secrets": False},
                         "merge keeps fields the baseline does not own")
        self.assertNotIn(("POST", "/orgs/acme/budgets"), writes, "a required param was not given")
        self.assertIn("needs --set amount=...", out.getvalue())
        self.assertTrue(any(e.get("ok") is False for e in log))

        fake = FakeGitHub(routes)
        ghsetup.apply(ghsetup.Gh(fake), self.CAT, findings, ["ORG-BUDGET"], False, set(), True, io.StringIO(),
                      overrides=ghsetup.parse_sets(["amount=0"]))
        self.assertEqual(fake.writes, [("POST", "/orgs/acme/budgets", {"amount": 0})], "--set values are typed")

    def test_by_plan_and_dedupe(self):
        free, _ = run_audit(self.routes("free"), catalog=self.CAT)
        fake = FakeGitHub({("POST", "/repos/acme/api/rulesets"): (201, {}),
                           ("POST", "/repos/acme/secret/rulesets"): (201, {})})
        ghsetup.apply(ghsetup.Gh(fake), self.CAT, free, ["REPO-RULES"], False, set(), True, io.StringIO())
        self.assertEqual(sorted(p for _, p, _ in fake.writes), ["/repos/acme/api/rulesets", "/repos/acme/secret/rulesets"])

        team, _ = run_audit(self.routes("team"), catalog=self.CAT)
        fake = FakeGitHub({("POST", "/orgs/acme/rulesets"): (201, {})})
        log = ghsetup.apply(ghsetup.Gh(fake), self.CAT, team, ["REPO-RULES"], False, set(), True, io.StringIO())
        self.assertEqual([p for _, p, _ in fake.writes], ["/orgs/acme/rulesets"], "one org ruleset for all repos")
        body = fake.writes[0][2]
        self.assertEqual(body["conditions"]["repository_name"]["include"], ["~ALL"])
        self.assertTrue(any("already planned" in e.get("note", "") for e in log))

    def test_parse_sets(self):
        self.assertEqual(ghsetup.parse_sets(["a=1", "b=true", 'c=["x"]', "d=team-x"]),
                         {"a": 1, "b": True, "c": ["x"], "d": "team-x"})


class TestWorkflows(unittest.TestCase):
    WF = ("name: ci\non: push\njobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n"
          "      - uses: actions/checkout@v4\n"
          "      - uses: actions/setup-node@1d0ff469b7ec7b3cb9d8673fde0c81c44821de2a # v4.2.0\n"
          "      - uses: ./local-action\n"
          "      - uses: docker://alpine:3\n")

    def test_lint(self):
        probs = ghsetup.lint_workflow_text(self.WF)
        self.assertTrue(any("permissions" in p for p in probs))
        self.assertTrue(any("actions/checkout@v4" in p for p in probs))
        self.assertFalse(any("setup-node" in p for p in probs))
        self.assertFalse(any("local-action" in p for p in probs))
        self.assertTrue(any("docker://alpine:3" in p for p in probs))
        self.assertEqual(ghsetup.lint_workflow_text("permissions:\n  contents: read\n"), [])
        self.assertTrue(ghsetup.lint_workflow_text("permissions: write-all\n"))

    def test_pin(self):
        sha = "a" * 40
        new, changes = ghsetup.pin_text(self.WF, lambda o, r, ref: sha)
        self.assertEqual(changes, [("actions/checkout@v4", f"actions/checkout@{sha}")])
        self.assertIn(f"      - uses: actions/checkout@{sha} # v4\n", new)
        self.assertIn("setup-node@1d0ff469b7ec7b3cb9d8673fde0c81c44821de2a # v4.2.0", new)

    def test_pin_subpath_action(self):
        new, _ = ghsetup.pin_text("  - uses: github/codeql-action/init@v3\n", lambda o, r, ref: (o, r) and "b" * 40)
        self.assertIn("github/codeql-action/init@" + "b" * 40 + " # v3", new)


class TestCatalogFile(unittest.TestCase):
    """The real catalog must be well formed: unique IDs, known kinds, known products, sources for every check."""

    def test_real_catalog(self):
        if not os.path.exists(ghsetup.CHECKS_FILE):
            self.skipTest("no data/checks.json yet")
        cat = ghsetup.load_catalog()
        ids = [c["id"] for c in cat["checks"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate check IDs")
        for c in cat["checks"]:
            with self.subTest(c["id"]):
                self.assertIn(c["kind"], ghsetup.KINDS)
                self.assertIn(c["scope"], ("org", "repo"))
                self.assertTrue(c.get("source"), "every check needs a source URL")
                for plan, av in c.get("availability", {}).items():
                    self.assertIn(plan, cat["plans"])
                    for val in (av.values() if isinstance(av, dict) else [av]):
                        if val.startswith("paid:"):
                            self.assertIn(val.split(":", 1)[1], cat["products"])
                fix = c.get("fix", {})
                variants = list(fix.get("by_plan", {}).values()) or [fix]
                for variant in variants:
                    if fix.get("kind") in ("ruleset", "pr_file"):
                        self.assertTrue(os.path.exists(os.path.join(ghsetup.TEMPLATES_DIR, variant["template"])))
                if c.get("kind") == "manual" or fix.get("kind") == "manual":
                    self.assertTrue(c.get("manual"), "manual items must say what the human does")

    def test_checks_md_is_current(self):
        path = os.path.join(ghsetup.SKILL_DIR, "references", "checks.md")
        with open(path) as f:
            self.assertEqual(f.read(), ghsetup.catalog_markdown(ghsetup.load_catalog()),
                             "run: python3 scripts/ghsetup.py catalog > references/checks.md")

    def test_templates_fill_to_valid_rulesets(self):
        """Filled ruleset templates must hold typed values, not placeholder strings."""
        params = {"review_count": 1, "require_code_owner_review": False, "require_last_push_approval": True,
                  "bypass_actors": []}
        for name in ("ruleset-repo-default-branch.json", "ruleset-org-default-branch.json"):
            with self.subTest(name), open(os.path.join(ghsetup.TEMPLATES_DIR, name)) as f:
                body = ghsetup.fill(json.load(f), params)
                self.assertNotRegex(json.dumps(body), r'"\{[a-z_]+\}"')
                pr = next(r for r in body["rules"] if r["type"] == "pull_request")["parameters"]
                self.assertEqual(pr["required_approving_review_count"], 1)
                self.assertIs(pr["require_last_push_approval"], True)
                self.assertEqual(body["bypass_actors"], [])


if __name__ == "__main__":
    unittest.main()
