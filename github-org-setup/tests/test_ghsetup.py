"""Offline tests for scripts/ghsetup.py. Run: python3 -m unittest discover -s github-org-setup/tests"""

import base64
import copy
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
        fake = FakeGitHub({**self.routes("free"), ("POST", "/repos/acme/api/rulesets"): (201, {}),
                           ("POST", "/repos/acme/secret/rulesets"): (201, {})})
        ghsetup.apply(ghsetup.Gh(fake), self.CAT, free, ["REPO-RULES"], False, set(), True, io.StringIO())
        self.assertEqual(sorted(p for _, p, _ in fake.writes), ["/repos/acme/api/rulesets", "/repos/acme/secret/rulesets"])

        team, _ = run_audit(self.routes("team"), catalog=self.CAT)
        fake = FakeGitHub({**self.routes("team"), ("POST", "/orgs/acme/rulesets"): (201, {})})
        log = ghsetup.apply(ghsetup.Gh(fake), self.CAT, team, ["REPO-RULES"], False, set(), True, io.StringIO())
        self.assertEqual([p for _, p, _ in fake.writes], ["/orgs/acme/rulesets"], "one org ruleset for all repos")
        body = fake.writes[0][2]
        self.assertEqual(body["conditions"]["repository_name"]["include"], ["~ALL"])
        self.assertTrue(any("already planned" in e.get("note", "") for e in log))

    def test_parse_sets(self):
        self.assertEqual(ghsetup.parse_sets(["a=1", "b=true", 'c=["x"]', "d=team-x"]),
                         {"a": 1, "b": True, "c": ["x"], "d": "team-x"})


def b64(text):
    return {"content": base64.b64encode(text.encode()).decode(), "sha": "x"}


RULESET_PARAMS = {"review_count": 1, "require_code_owner_review": False, "require_last_push_approval": True,
                  "bypass_actors": []}
BRANCH_CHECK = {"id": "REPO-BP", "scope": "repo", "title": "t", "kind": "branch_rules",
                "availability": {"free": "free", "team": "free"},
                "expect": {"rules": [{"type": "pull_request", "params": [
                    {"param": "required_approving_review_count", "op": "gte", "value": 1}]}]},
                "fix": {"kind": "ruleset", "params": RULESET_PARAMS, "preconditions": ["reviewers", "deploy_keys"],
                        "by_plan": {"free": {"template": "ruleset-repo-default-branch.json",
                                             "path": "/repos/{owner}/{repo}/rulesets"},
                                    "team": {"template": "ruleset-org-default-branch.json",
                                             "path": "/orgs/{org}/rulesets"}}}}
BP_CAT = {"verified_on": "x", "plans": ["free", "team"], "products": {}, "checks": [BRANCH_CHECK]}

# The homebrew-tap ruleset from the test session: 0 approvals, status checks, a DeployKey bypass.
TAP_RULESET = {
    "id": 24881204, "name": "main", "target": "branch", "source_type": "Repository", "source": "acme/api",
    "enforcement": "active", "node_id": "RRS_x", "created_at": "c", "updated_at": "u",
    "conditions": {"ref_name": {"exclude": [], "include": ["~DEFAULT_BRANCH"]}},
    "bypass_actors": [{"actor_id": None, "actor_type": "DeployKey", "bypass_mode": "always"}],
    "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
              {"type": "pull_request", "parameters": {
                  "required_approving_review_count": 0, "dismiss_stale_reviews_on_push": False,
                  "require_code_owner_review": False, "require_last_push_approval": False,
                  "required_review_thread_resolution": True, "allowed_merge_methods": ["merge", "squash", "rebase"]}},
              {"type": "required_status_checks", "parameters": {
                  "strict_required_status_checks_policy": False,
                  "required_status_checks": [{"context": "formulae (ubuntu-latest)", "integration_id": 15368}]}}]}
APPLIED = [dict(r, ruleset_source_type="Repository", ruleset_id=24881204) for r in TAP_RULESET["rules"]]


class TestRulesetInPlace(unittest.TestCase):
    def routes(self, writers=("me", "alice"), keys=(), applied=APPLIED, ruleset=TAP_RULESET):
        r = base_routes({
            ("GET", "/orgs/acme/repos?type=all&per_page=100"): (200, REPOS[:1]),
            ("GET", "/repos/acme/api/rules/branches/main"): (200, list(applied)),
            ("GET", "/repos/acme/api/rulesets/24881204"): (200, ruleset),
            ("GET", "/orgs/acme/rulesets/99"): (200, dict(ruleset, id=99, source_type="Organization")),
            ("GET", "/repos/acme/api/collaborators?permission=push&affiliation=all&per_page=100"): (
                200, [{"login": w, "type": "User"} for w in writers]),
            ("GET", "/repos/acme/api/keys?per_page=100"): (200, list(keys)),
            ("PUT", "/repos/acme/api/rulesets/24881204"): (200, {}),
            ("PUT", "/orgs/acme/rulesets/99"): (200, {}),
            ("POST", "/repos/acme/api/rulesets"): (201, {}),
        })
        return r

    def run_apply(self, routes, execute=True, **kw):
        findings, _ = run_audit(routes, catalog=BP_CAT)
        fake = FakeGitHub(routes)
        out = io.StringIO()
        log = ghsetup.apply(ghsetup.Gh(fake), BP_CAT, findings, ["REPO-BP"], False, set(), execute, out, **kw)
        return fake, out.getvalue(), log

    def test_updates_existing_ruleset_and_keeps_checks_and_bypass(self):
        fake, out, _ = self.run_apply(self.routes())
        self.assertEqual([(m, p) for m, p, _ in fake.writes], [("PUT", "/repos/acme/api/rulesets/24881204")])
        body = fake.writes[0][2]
        for k in ("id", "node_id", "source", "source_type", "created_at", "updated_at"):
            self.assertNotIn(k, body)
        rules = {r["type"]: r for r in body["rules"]}
        pr = rules["pull_request"]["parameters"]
        self.assertEqual(pr["required_approving_review_count"], 1)
        self.assertTrue(pr["dismiss_stale_reviews_on_push"] and pr["require_last_push_approval"])
        self.assertEqual(pr["allowed_merge_methods"], ["merge", "squash", "rebase"], "other params kept")
        self.assertIn("required_status_checks", rules, "status checks kept")
        self.assertEqual(body["bypass_actors"], TAP_RULESET["bypass_actors"], "bypass kept")
        self.assertIn("[warn]", out)
        self.assertIn("DeployKey(always)", out)
        self.assertNotIn("parameters", rules["deletion"], "no empty parameters added to rules without them")

    def test_no_put_when_ruleset_already_meets_baseline(self):
        ok = copy.deepcopy(TAP_RULESET)
        ok["rules"][2]["parameters"].update(required_approving_review_count=1, dismiss_stale_reviews_on_push=True,
                                            require_last_push_approval=True)
        routes = self.routes(ruleset=ok)
        findings, _ = run_audit(self.routes(), catalog=BP_CAT)  # audit sees the weak ruleset: fail
        fake = FakeGitHub(routes)                               # by apply time it was fixed
        out = io.StringIO()
        ghsetup.apply(ghsetup.Gh(fake), BP_CAT, findings, ["REPO-BP"], False, set(), True, out)
        self.assertEqual(fake.writes, [])
        self.assertIn("[no change]", out.getvalue())

    def test_never_weakens(self):
        strong = copy.deepcopy(TAP_RULESET)
        strong["rules"][2]["parameters"]["required_approving_review_count"] = 2
        body, _ = ghsetup.upgrade_ruleset(strong, {"rules": [{"type": "pull_request", "parameters": {
            "required_approving_review_count": 0, "dismiss_stale_reviews_on_push": False}}]})
        pr = next(r for r in body["rules"] if r["type"] == "pull_request")["parameters"]
        self.assertEqual(pr["required_approving_review_count"], 2)

    def test_org_ruleset_is_updated_at_org_level(self):
        applied = [dict(r, ruleset_source_type="Organization", ruleset_id=99) for r in TAP_RULESET["rules"]]
        fake, out, _ = self.run_apply(self.routes(applied=applied))
        self.assertEqual([p for _, p, _ in fake.writes], ["/orgs/acme/rulesets/99"])
        self.assertIn("applies to every repo it targets", out)

    def test_blocks_when_nobody_else_can_approve(self):
        fake, out, log = self.run_apply(self.routes(writers=("me",)))
        self.assertEqual(fake.writes, [])
        self.assertIn("[blocked]", out)
        self.assertIn("only 0 other account(s)", out)
        fake, out, _ = self.run_apply(self.routes(writers=("me",)), override_blocks=["REPO-BP@acme/api"])
        self.assertEqual(len(fake.writes), 1, "--override lets the user accept the risk")
        self.assertIn("block, overridden", out)

    def test_bots_do_not_count_as_reviewers(self):
        routes = self.routes()
        routes[("GET", "/repos/acme/api/collaborators?permission=push&affiliation=all&per_page=100")] = (
            200, [{"login": "me", "type": "User"}, {"login": "dependabot[bot]", "type": "Bot"}])
        fake, out, _ = self.run_apply(routes)
        self.assertEqual(fake.writes, [])

    def test_new_ruleset_blocked_by_write_deploy_key(self):
        routes = self.routes(applied=[], keys=[{"title": "release workflow", "read_only": False},
                                               {"title": "ro", "read_only": True}])
        fake, out, _ = self.run_apply(routes)
        self.assertEqual(fake.writes, [])
        self.assertIn("deploy keys with write access: release workflow", out)
        self.assertNotIn(", ro", out)

    def test_new_ruleset_without_keys_is_created(self):
        fake, out, _ = self.run_apply(self.routes(applied=[]))
        self.assertEqual([(m, p) for m, p, _ in fake.writes], [("POST", "/repos/acme/api/rulesets")])

    def test_dry_run_exit_code_for_blocks(self):
        routes = self.routes(writers=("me",))
        fake = FakeGitHub(routes)
        with open(os.devnull, "w") as devnull:
            findings, _ = run_audit(routes, catalog=BP_CAT)
            path = os.path.join(os.environ.get("TMPDIR", "/tmp"), "ghsetup-test-findings.json")
            with open(path, "w") as f:
                json.dump(findings, f)
            catalog = os.path.join(os.environ.get("TMPDIR", "/tmp"), "ghsetup-test-catalog.json")
            with open(catalog, "w") as f:
                json.dump(BP_CAT, f)
            old = sys.stdout
            sys.stdout = devnull
            try:
                code = ghsetup.main(["--catalog", catalog, "apply", path, "--select", "REPO-BP"], gh=ghsetup.Gh(fake))
            finally:
                sys.stdout = old
        self.assertEqual(code, 4)


class TestActionsScan(unittest.TestCase):
    CI = ("permissions:\n  contents: read\njobs:\n  a:\n    steps:\n"
          "      - uses: actions/checkout@" + "a" * 40 + "\n"
          "      - uses: dtolnay/rust-toolchain@stable\n"
          "      - uses: ./.github/actions/setup\n"
          "      - uses: google/clusterfuzzlite/actions/build_fuzzers@" + "b" * 40 + "\n"
          "  b:\n    uses: other/shared/.github/workflows/lint.yml@v1\n")
    LOCAL = "runs:\n  using: composite\n  steps:\n    - uses: Swatinem/rust-cache@v2\n"
    REMOTE = "runs:\n  using: composite\n  steps:\n    - uses: nested/inner@v3\n"
    REUSABLE = "jobs:\n  l:\n    steps:\n      - uses: raven-actions/actionlint@v2\n"

    def routes(self):
        return base_routes({
            ("GET", "/orgs/acme/repos?type=all&per_page=100"): (200, REPOS[:1]),
            ("GET", "/repos/acme/api/contents/.github/workflows"): (200, [{"name": "ci.yml",
                                                                           "path": ".github/workflows/ci.yml"}]),
            ("GET", "/repos/acme/api/contents/.github/workflows/ci.yml"): (200, b64(self.CI)),
            ("GET", "/repos/acme/api/contents/.github/actions/setup/action.yml"): (200, b64(self.LOCAL)),
            ("GET", "/repos/google/clusterfuzzlite/contents/actions/build_fuzzers/action.yml?ref=" + "b" * 40): (
                200, b64(self.REMOTE)),
            ("GET", "/repos/other/shared/contents/.github/workflows/lint.yml?ref=v1"): (200, b64(self.REUSABLE)),
        })

    def summary(self):
        gh = ghsetup.Gh(FakeGitHub(self.routes()))
        uses = list(ghsetup.WorkflowScan(gh, "acme").uses(["api"]))
        return uses, ghsetup.summarize_uses(uses, "acme")

    def test_follows_local_remote_and_reusable(self):
        uses, summary = self.summary()
        actions = {a["action"]: a for a in summary}
        for name in ("dtolnay/rust-toolchain", "Swatinem/rust-cache", "google/clusterfuzzlite/actions/build_fuzzers",
                     "nested/inner", "other/shared/.github/workflows/lint.yml", "raven-actions/actionlint"):
            self.assertIn(name, actions)
        self.assertTrue(actions["Swatinem/rust-cache"]["nested"])
        self.assertTrue(actions["nested/inner"]["nested"])
        self.assertEqual(actions["other/shared/.github/workflows/lint.yml"]["kind"], "reusable")
        self.assertEqual(actions["actions/checkout"]["class"], "github")
        self.assertIn("google/clusterfuzzlite/actions/build_fuzzers@*", ghsetup.suggested_patterns(summary))
        self.assertNotIn("actions/checkout@*", ghsetup.suggested_patterns(summary))

    def test_blocked_and_allowed(self):
        _, summary = self.summary()
        pats = ghsetup.suggested_patterns(summary)
        self.assertEqual(ghsetup.blocked_actions(summary, pats), [])
        blocked = {a["action"] for a in ghsetup.blocked_actions(summary, [p for p in pats if "rust-cache" not in p])}
        self.assertEqual(blocked, {"Swatinem/rust-cache"})
        self.assertTrue(ghsetup.allowed_by_patterns("Swatinem/rust-cache", "v2", ["swatinem/*"]))
        self.assertFalse(ghsetup.allowed_by_patterns("Swatinem/rust-cache", "v2", ["!Swatinem/rust-cache@*"]))

    def test_allowlist_and_pinning_preconditions(self):
        cat = {"verified_on": "x", "plans": ["free", "team"], "products": {}, "checks": [
            {"id": "ORG-AA", "scope": "org", "title": "t", "kind": "field", "availability": {"free": "free"},
             "read": {"path": "/orgs/{org}", "pointer": "default_repository_permission"},
             "expect": {"op": "eq", "value": "read"},
             "fix": {"kind": "api", "preconditions": ["actions_allowlist", "sha_pinning"],
                     "params": {"patterns_allowed": []},
                     "steps": [{"method": "PUT", "path": "/orgs/{org}/actions/permissions/selected-actions",
                                "body": {"github_owned_allowed": True, "verified_allowed": True,
                                         "patterns_allowed": "{patterns_allowed}"}}]}}]}
        routes = self.routes()
        routes[("PUT", "/orgs/acme/actions/permissions/selected-actions")] = (204, None)
        findings, _ = run_audit(routes, catalog=cat)
        fake = FakeGitHub(routes)
        out = io.StringIO()
        ghsetup.apply(ghsetup.Gh(fake), cat, findings, ["ORG-AA"], False, set(), True, out)
        text = out.getvalue()
        self.assertEqual(fake.writes, [])
        self.assertIn("action(s) in use are not allowed", text)
        self.assertIn("Marketplace-verified", text)
        self.assertIn("unpinned action reference(s) in workflows", text)
        self.assertIn("dtolnay/rust-toolchain@stable", text)
        self.assertIn("inside composite actions", text, "nested tags are a warning, not a block")


class TestReleaseLint(unittest.TestCase):
    def levels(self, text):
        return [level for level, _ in ghsetup.lint_release_text(text)]

    def test_release_event_upload_blocks(self):
        wf = "on:\n  release:\n    types: [published]\njobs:\n  a:\n    steps:\n      - run: gh release upload v1 x\n"
        self.assertEqual(self.levels(wf), ["block"])

    def test_upload_after_publish_blocks_and_draft_warns(self):
        self.assertEqual(self.levels("on: push\nsteps:\n  - run: gh release create v1\n  - run: gh release upload v1 a\n"),
                         ["block"])
        self.assertEqual(self.levels("steps:\n  - run: gh release create v1 --draft\n  - run: gh release upload v1 a\n"
                                     "  - run: gh release edit v1 --draft=false\n"), ["warn"])

    def test_job_named_release_is_not_a_trigger(self):
        wf = ("on:\n  push:\n    tags: ['v*']\njobs:\n  release:\n    steps:\n"
              "      - run: gh release create v1 --draft\n      - run: gh release upload v1 a\n")
        self.assertEqual(self.levels(wf), ["warn"], "a job named release must not read as the release event")

    def test_create_with_files_is_safe(self):
        self.assertEqual(self.levels("on: push\nsteps:\n  - run: gh release create v1 dist/*\n"), [])

    def test_upload_actions(self):
        self.assertEqual(self.levels("on: push\nsteps:\n  - uses: softprops/action-gh-release@v2\n"), ["warn"])
        self.assertEqual(self.levels("on: push\nsteps:\n  - uses: softprops/action-gh-release@v2\n"
                                     "    with:\n      draft: true\n"), [])
        self.assertEqual(self.levels("on: push\nsteps:\n  - uses: actions/upload-release-asset@v1\n"), ["block"])


class TestExplain(unittest.TestCase):
    def test_2fa_names_people(self):
        cat = {"verified_on": "x", "plans": ["free", "team"], "products": {}, "checks": [
            {"id": "ORG-2FA", "scope": "org", "title": "t", "kind": "field", "availability": {"free": "free"},
             "read": {"path": "/orgs/{org}", "pointer": "two_factor_requirement_enabled"},
             "expect": {"op": "eq", "value": True}, "fix": {"kind": "manual"}, "manual": "UI",
             "explain": [{"label": "members without 2FA", "path": "/orgs/{org}/members?filter=2fa_disabled",
                          "pluck": "login"},
                         {"label": "outside collaborators without 2FA (removed)",
                          "path": "/orgs/{org}/outside_collaborators?filter=2fa_disabled", "pluck": "login"}]}]}
        routes = base_routes({("GET", "/orgs/acme/members?filter=2fa_disabled"): (200, [{"login": "bob"}]),
                              ("GET", "/orgs/acme/outside_collaborators?filter=2fa_disabled"): (200, [])})
        findings, _ = run_audit(routes, catalog=cat)
        detail = by_key(findings)["ORG-2FA@acme"]["detail"]
        self.assertIn("members without 2FA: bob", detail)
        self.assertIn("outside collaborators without 2FA (removed): none", detail)


class TestPinRefresh(unittest.TestCase):
    TEXT = ("      - uses: actions/checkout@" + "1" * 40 + " # v7.0.1\n"
            "      - uses: github/codeql-action/upload-sarif@" + "2" * 40 + " # v4.39.1\n"
            "      - uses: ./local\n")

    def gh(self, broken=False):
        routes = {("GET", "/repos/actions/checkout/tags?per_page=100"): (200, [
            {"name": "v8.0.0", "commit": {"sha": "8" * 40}}, {"name": "v7.1.0", "commit": {"sha": "7" * 40}},
            {"name": "v7.0.1", "commit": {"sha": "1" * 40}}, {"name": "v7", "commit": {"sha": "x" * 40}}])}
        if not broken:
            routes[("GET", "/repos/github/codeql-action/tags?per_page=100")] = (200, [
                {"name": "codeql-bundle-v2.27.3", "commit": {"sha": "b" * 40}},
                {"name": "v4.39.1", "commit": {"sha": "2" * 40}}])
        return ghsetup.Gh(FakeGitHub(routes))

    def test_same_major_latest(self):
        new, notes = ghsetup.refresh_pins(self.TEXT, self.gh())
        self.assertIn("actions/checkout@" + "7" * 40 + " # v7.1.0\n", new, "latest v7, not v8")
        self.assertIn("upload-sarif@" + "2" * 40 + " # v4.39.1", new, "already latest: unchanged")
        self.assertIn("./local", new)
        self.assertEqual([lvl for lvl, _ in notes], ["info"])

    def test_lookup_failure_keeps_pin(self):
        new, notes = ghsetup.refresh_pins(self.TEXT, self.gh(broken=True))
        self.assertIn("upload-sarif@" + "2" * 40, new)
        self.assertIn("warn", [lvl for lvl, _ in notes])

    def test_scorecard_template_has_read_permissions(self):
        with open(os.path.join(ghsetup.TEMPLATES_DIR, "scorecard.yml")) as f:
            text = f.read()
        job = text.split("jobs:", 1)[1]
        for perm in ("contents: read", "actions: read", "security-events: write", "id-token: write"):
            self.assertIn(perm, job)
        self.assertEqual(len([l for l in text.splitlines() if ghsetup.PIN_RE.match(l)]), 4, "every pin is refreshable")


class TestSecurityContact(unittest.TestCase):
    FINDINGS = {"results": [{"scope": "repo", "target": "acme/secret", "visibility": "private"},
                            {"scope": "repo", "target": "acme/api", "visibility": "public"}]}

    def test_modes(self):
        line, notes = ghsetup.derive_security_contact({"security_contact": "sec@acme.org"}, self.FINDINGS)
        self.assertEqual(line, "If that is not available, send an email to <sec@acme.org>.")
        line, _ = ghsetup.derive_security_contact({"security_contact": "https://acme.org/security"}, self.FINDINGS)
        self.assertIn("<https://acme.org/security>", line)
        line, notes = ghsetup.derive_security_contact({"security_contact": "advisories"}, self.FINDINGS)
        self.assertEqual(line, "")
        self.assertIn("acme/secret", notes[0][1])
        with self.assertRaises(ghsetup.MissingParams):
            ghsetup.derive_security_contact({"security_contact": "call Bob"}, self.FINDINGS)

    def test_file_always_has_a_link(self):
        with open(os.path.join(ghsetup.TEMPLATES_DIR, "SECURITY.md")) as f:
            template = f.read()
        for contact in ("advisories", "sec@acme.org", "https://acme.org/security"):
            line, _ = ghsetup.derive_security_contact({"security_contact": contact}, {"results": []})
            text = ghsetup.fill(template, {"contact_line": line, "ack_days": 3, "assess_days": 10})
            self.assertRegex(text, r"https://docs\.github\.com/\S+report-privately")
            self.assertNotRegex(text, r"\{[a-z_]+\}")


class TestVerify(unittest.TestCase):
    CAT = {"verified_on": "x", "plans": ["free", "team"], "products": {}, "checks": [
        {"id": "REPO-DEL", "scope": "repo", "title": "t", "kind": "field", "availability": {"free": "free"},
         "read": {"path": "/repos/{owner}/{repo}", "pointer": "delete_branch_on_merge"},
         "expect": {"op": "eq", "value": True}, "fix": {"kind": "api", "steps": []}},
        {"id": "REPO-FILE", "scope": "repo", "title": "t", "kind": "file_any", "availability": {"free": "free"},
         "read": {"paths": ["SECURITY.md"]}, "fix": {"kind": "pr_file"}}]}

    def findings(self):
        return {"org": "acme", "plan": "free", "results": [
            {"key": "REPO-DEL@acme/api", "id": "REPO-DEL", "target": "acme/api", "scope": "repo", "visibility": "public"},
            {"key": "REPO-FILE@acme/api", "id": "REPO-FILE", "target": "acme/api", "scope": "repo",
             "visibility": "public"}]}

    def test_retries_stale_reads(self):
        answers = iter([{"delete_branch_on_merge": False}, {"delete_branch_on_merge": True}])

        def runner(args, stdin=None):
            return 0, json.dumps(next(answers)), ""
        slept = []
        res = ghsetup.verify(ghsetup.Gh(runner), self.CAT, self.findings(), {"REPO-DEL@acme/api"},
                             delay=0.5, sleep=slept.append)
        self.assertEqual(res[0]["status"], "pass")
        self.assertEqual(slept, [0.5])

    def test_pr_fix_is_pending(self):
        gh = ghsetup.Gh(FakeGitHub({}))
        res = ghsetup.verify(gh, self.CAT, self.findings(), {"REPO-FILE@acme/api"},
                             {"REPO-FILE@acme/api": "https://github.com/acme/api/pull/7"}, sleep=lambda s: None)
        self.assertEqual(res[0]["status"], "pending-pr")
        self.assertIn("/pull/7", res[0]["detail"])


class TestDependencyCoverage(unittest.TestCase):
    CHECK = {"id": "REPO-COV", "scope": "repo", "title": "t", "kind": "dependency_coverage",
             "availability": {"free": "free", "team": "free"},
             "read": {"lockfiles": ["Cargo.lock", "bun.lock", "package-lock.json"]}, "fix": {"kind": "manual"},
             "manual": "m"}
    CAT = {"verified_on": "x", "plans": ["free", "team"], "products": {}, "checks": [CHECK]}

    def routes(self, manifests):
        tree = {"truncated": False, "tree": [{"path": "Cargo.lock", "type": "blob"},
                                             {"path": "adapters/bun.lock", "type": "blob"},
                                             {"path": "adapters/package.json", "type": "blob"},
                                             {"path": "src", "type": "tree"}]}
        data = {"data": {"repository": {"dependencyGraphManifests": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [{"filename": m, "parseable": True} for m in manifests]}}}}
        return base_routes({
            ("GET", "/orgs/acme/repos?type=all&per_page=100"): (200, REPOS[:2]),
            ("GET", "/repos/acme/api/git/trees/main?recursive=1"): (200, tree),
            ("GET", "/repos/acme/secret/git/trees/main?recursive=1"): (200, tree),
            ("POST", "/graphql"): (200, data),
            ("GET", "/repos/acme/api/dependabot/alerts?state=open&per_page=100"): (200, []),
        })

    def test_uncovered_lockfile_and_osv_gap(self):
        real = ghsetup.scorecard_vulnerabilities
        ghsetup.scorecard_vulnerabilities = lambda repo: {"count": 12, "date": "2026-10-30T00:00:00Z"}
        try:
            findings, _ = run_audit(self.routes(["Cargo.lock", "adapters/package.json"]), catalog=self.CAT)
        finally:
            ghsetup.scorecard_vulnerabilities = real
        r = by_key(findings)
        pub, priv = r["REPO-COV@acme/api"], r["REPO-COV@acme/secret"]
        self.assertEqual(pub["status"], "fail")
        self.assertEqual(pub["current"]["uncovered"], ["adapters/bun.lock"])
        self.assertIn("Scorecard (OSV) found 12 vulnerabilities", pub["detail"])
        self.assertIn("Dependabot has 0 open alert(s)", pub["detail"])
        self.assertNotIn("Scorecard", priv["detail"], "no Scorecard lookup for private repos")

    def test_all_covered_passes(self):
        real = ghsetup.scorecard_vulnerabilities
        ghsetup.scorecard_vulnerabilities = lambda repo: None
        try:
            findings, _ = run_audit(self.routes(["Cargo.lock", "adapters/bun.lock"]), catalog=self.CAT)
        finally:
            ghsetup.scorecard_vulnerabilities = real
        self.assertEqual(by_key(findings)["REPO-COV@acme/api"]["status"], "pass")


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
                for name in fix.get("preconditions", []):
                    self.assertIn(name, ghsetup.PRECONDITIONS)
                for spec in c.get("explain", []):
                    self.assertTrue(spec["label"] and spec["path"] and spec["pluck"])
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
