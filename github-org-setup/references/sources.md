# Sources

The sources for each **check** are in `data/checks.json` (field `source`) and in `references/checks.md`. This file
gives the sources for the **rules** in SKILL.md, the facts that were checked against the live API, and the facts
that the docs did not confirm. Research date: 2026-10-30.

**Basis:** **D** documented on docs.github.com, the GitHub changelog or the Scorecard source; **A** seen in a live
read-only API response (org `brnrhq`, Free plan, 2026-10-30); **J** my judgment ("I guess").

## Rules in SKILL.md

| ID | Rule | Sources | Basis |
| --- | --- | --- | --- |
| S1 | Free and Team only | User's scope decision; plan detection with `GET /orgs/{org}` `plan.name` (https://docs.github.com/en/rest/orgs/orgs#get-an-organization). The docs do not list the values; `free` was seen live. | D, A; `team` value J |
| S2 | Read first; dry run; execute only approved keys | User's choice "audit, then apply" | J |
| S3 | No cost without an opt-in; live prices only | User's choice "always fetch live". Metered billing starts when you enable it: https://docs.github.com/en/billing/how-tos/products/buy-advanced-security | D |
| S4 | Destructive changes one by one | Each `destructive` text cites its page, for example 2FA removes outside collaborators: https://docs.github.com/en/organizations/keeping-your-organization-secure/managing-two-factor-authentication-for-your-organization/requiring-two-factor-authentication-in-your-organization | D; grouping J |
| S5 | The user decides policy values | Scorecard Branch-Protection tiers need ≥1 reviewer and no bypass: https://github.com/ossf/scorecard/blob/v5.6.0/docs/checks.md#branch-protection. A solo maintainer cannot approve their own PR. | D, J |
| S6 | Re-verify when the catalog is old or the API disagrees | Many docs URLs moved in 2025–2026 (for example the "GitHub-recommended configuration" page now returns 404); the REST default version is now `2026-03-10`: https://docs.github.com/en/rest/about-the-rest-api/api-versions | D; 90 days J |
| S7 | Content changes go through a PR; no AI taglines | Repo owner's instructions; matches `pr-review` G3/G6 in this repo | J |
| S8 | Report faithfully; manual is not done | — | J |

## Facts checked against the live API (basis A)

- `GET /orgs/{org}/rulesets` on a Free org returns 403 "Upgrade to GitHub Team to enable this feature."
- `GET /orgs/{org}/actions/permissions` returns `enabled_repositories`, `allowed_actions`, `sha_pinning_required`.
- `GET .../actions/permissions/selected-actions` returns 409 when `allowed_actions` is `all`.
- `GET .../fork-pr-contributor-approval` returns `approval_policy`; `.../fork-pr-workflows-private-repos` returns
  the four booleans; `.../self-hosted-runners` returns `enabled_repositories`.
- `GET /orgs/{org}/code-security/configurations` lists "GitHub recommended" with `target_type: global` and
  `advanced_security: enabled`; `.../defaults` returns `[{default_for_new_repos, configuration}]`.
- `GET /orgs/{org}/settings/immutable-releases` returns `{"enforced_repositories": "none"}`.
- `GET /organizations/{org}/settings/billing/budgets` returns `{"budgets": [...]}` with SKUs `actions`, `packages`,
  `codespaces`, `git_lfs`; `.../usage/summary` returns `usageItems` with `netAmount`.
- Repo: `vulnerability-alerts` answers 204 when on; `automated-security-fixes`, `private-vulnerability-reporting`
  and `immutable-releases` answer `{"enabled": ...}`; `code-scanning/default-setup` returns `state`.
- A repo ruleset made in the UI uses `{"actor_type": "RepositoryRole", "actor_id": 5}` for the admin role. The
  docs do not list role ids, so the templates use `OrganizationAdmin` (documented) when a bypass is needed.
- `GET /repos/{o}/{r}/rules/branches/{branch}` returns `ruleset_source_type` and `ruleset_id` for each active rule,
  so the fix can find the ruleset to update. A `PUT /repos/{o}/{r}/rulesets/{id}` with the GET body (read-only
  fields removed) and raised `pull_request` parameters updated `brnrhq/homebrew-tap` in place in the test session
  (ruleset `24881204`, status checks and DeployKey bypass kept).
- `GET /orgs/{org}/members?filter=2fa_disabled` and `?filter=2fa_insecure`, and the same filters on
  `/orgs/{org}/outside_collaborators`, return the affected logins (owner token).
- `GET /repos/{o}/{r}/collaborators?permission=push&affiliation=all` lists accounts with write access (with
  `type`); `GET /repos/{o}/{r}/keys` returns deploy keys with `read_only`.
- `actions-in-use brnrhq` gave the same 12 third-party patterns that the test session found by hand, including
  subdirectory actions (`google/clusterfuzzlite/actions/build_fuzzers`) and actions nested in composite actions.
- GraphQL `Repository.dependencyGraphManifests` (public schema, https://docs.github.com/public/fpt/schema.docs.graphql)
  lists the files the dependency graph parsed. For `brnrhq/brnr` it lists `adapters/package.json` but not
  `adapters/bun.lock`; Dependabot had 0 open alerts and Scorecard (OSV) 12 vulnerabilities on 2026-10-30.
- Scorecard Branch-Protection was 0 ("not enabled") on `homebrew-tap` and `.github` (template workflow: job
  permissions `security-events: write`, `id-token: write` only) and 5 on `brnr` (job permissions add
  `contents: read`, `actions: read`), with rulesets in place before the runs. scorecard-action v2.5.0 README lines
  100–108 recommend `contents`, `issues`, `pull-requests` and `checks: read` in the job.
- The private reporting docs moved: the old URL answers 301 to
  `https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately`.
- Scorecard v5.6.0 reads `SECURITY.md` from the org `.github` repo if the repo has none
  (`checks/raw/security_policy.go`, lines 61–79), and counts `.github/dependabot.yml` and Renovate files
  (`checks/raw/dependency_update_tool.go`). Pinned action SHAs from the template were resolved live with `pin`.

## Not confirmed by the docs (the skill works around them)

| Fact | How the skill handles it |
| --- | --- |
| `plan.name` value for Team (`team`?) | `normalize_plan` accepts `team`; else the user passes `--plan` after they confirm |
| Enabling standalone Secret Protection on one repo with `PATCH security_and_analysis.secret_scanning` | The fix uses it, then `[verify]` re-reads. If it does not take effect, enable through a code security configuration or the UI |
| A default $0 budget for new accounts | Not assumed. `ORG-BUDGET-*` checks read what exists |
| `workflows` (required workflows) rule on Team | Not used |
| Free-plan availability of org roles, custom properties, immutable releases | Not used, or read at run time (a 403/404 gives `unknown`) |
| REST API for 2FA, OAuth app restrictions, PAT policy, member privileges | Treated as UI only (`manual`) |
| How GitHub matches `patterns_allowed` (case, `owner/*`, subpaths) | `allowed_by_patterns` approximates it with case-insensitive globs; the suggested list uses exact `owner/repo[/path]@*` entries |
| Whether the Actions allow policy and SHA pinning apply inside third-party composite actions | The scan follows them; for SHA pinning, nested tags are a `warn`, not a `block` |
| That the missing job-level reads caused Branch-Protection 0 | Most likely cause (see DECISIONS.md item 6); confirm after the next Scorecard runs |
| Marketplace "verified creator" status | No API. With `verified_allowed=true` the blocked list can include actions that would still run; the skill says so |
| Whether Scorecard counts the repo/org "read-only GITHUB_TOKEN default" | It does not (Scorecard: "no API available"); the skill checks both the setting and the workflow files |

## Research inputs

- docs.github.com pages and REST reference, fetched 2026-10-30 (URLs per check in `data/checks.json`).
- GitHub changelog posts 2024–2026 cited per check.
- OpenSSF Scorecard v5.6.0 (2026-10-12): https://github.com/ossf/scorecard/releases/tag/v5.6.0, and
  scorecard-action v2.5.0 (`fa7117db83c52d787ae5a89f350999701505d78e`).
- Live price pages: listed in `data/checks.json` → `pricing_pages`. They are read at run time, never stored.
