# Decisions for the github-org-setup skill

This file records each decision and trade-off made while writing the skill. "I guess" marks my judgment.

## Inputs from the user (2026-10-30)

- **Apply mode: audit, then apply.** The skill reads with `gh api`, shows the gap, and applies only what the user
  approves. No Terraform or safe-settings output.
- **Plans: Free and Team.** Enterprise Cloud, EMU and GHE.com are out of scope.
- **Repos: new and existing.** Org-level defaults cover new repos where the plan allows; per-repo checks cover
  existing ones.
- **Costs: always fetch live.** No price is stored. The catalog stores only *which* items are paid, the billing
  unit, and the price pages to read.
- **Security baseline: OpenSSF Scorecard.** Each check names the Scorecard checks it raises.

## Design

1. **The baseline is data, the script is generic.** Each check in `data/checks.json` is one of six kinds (`field`,
   `status_endpoint`, `file_any`, `branch_rules`, `workflows`, `list_match`, plus `manual`). Adding a check rarely
   needs code. The cost is a small schema to learn; `references/checks.md` and the catalog test keep it readable and
   valid.
2. **Python standard library plus `gh`.** No install step, and the user's `gh auth` login is used, so no token
   handling. YAML is not parsed (no stdlib parser): the workflow lint is a line-based heuristic. It finds missing
   top-level `permissions:` and unpinned `uses:`; it does not find dangerous `pull_request_target` patterns. The
   `scorecard` command covers those (Dangerous-Workflow).
3. **Paid items are gated in code, not only in the instructions.** `apply` refuses a `paid:` finding without
   `--accept-cost <product>`. An agent that skips a step still cannot start billing by accident.
4. **Destructive items are never in `--all-free`.** They need an explicit `--select`.
5. **Required parameters have a null default.** `apply` refuses to plan the fix (exit 3) until the user gives the
   value, so the skill cannot invent a security contact or a budget amount.
6. **One finding per check and target, keyed `ID@target`.** The user approves keys; globs select groups.
7. **De-duplication of identical steps.** On Team, the branch protection fix is one org ruleset; without this, the
   script would create it once per repo.
8. **Merge steps for PUT endpoints.** Actions permission endpoints replace the whole object. The fix reads the
   current object first so that it changes only the baseline's fields.

## Baseline choices

| Choice | Why | Basis |
| --- | --- | --- |
| A failed precondition blocks `--execute`; `--override <key>` accepts the risk | Same idea as `--accept-cost`: the code stops a known break, the user decides. Dry runs exit 4 too, so the agent sees it before it asks. | J |
| Rulesets, not classic branch protection | GitHub prefers rulesets (more flexible, conversion tools, org-level on Team). Scorecard reads rulesets with a non-admin token. The audit accepts classic protection too, so existing repos are not flagged just for using it. | docs; Scorecard action README |
| Default `review_count=1`, no bypass, last-push approval on, stale reviews dismissed | Scorecard Branch-Protection tiers 1, 2 and 5. Code-owner review is off by default because it needs a CODEOWNERS file first. | Scorecard checks.md; J for the defaults |
| Org ruleset covers `~ALL` repos with `protected: false` | Covers new repos automatically. `protected: true` would block repo renames; that is a separate policy. | REST docs; J |
| `GitHub recommended` configuration as default for **public** repos only | It enables `advanced_security`; on private Team repos that starts metered billing. On public repos its features are free. | docs + live read |
| Cost-guard check `ORG-SECCONFIG-NO-SURPRISE-COST` | A paid configuration as the default for new private repos bills every new repo's committers. It fails unless the user chose it. | billing docs; J |
| Budgets as checks | With no budget, metered overage has no limit. GitHub documents no default $0 budget, so the skill reads what exists. | budgets docs |
| `approval_policy=all_external_contributors` | The strictest of the three values. No doc recommends a value. | I guess |
| Require SHA pinning and selected actions | GitHub secure-use guidance. Both are marked destructive because unpinned or unlisted actions stop. | secure-use docs |
| Immutable releases enforced for all repos | Locks release tags and assets; Scorecard counts tags backed by immutable releases as pinned. Marked destructive for release workflows that edit assets. | docs; Scorecard checks.md |
| Two-factor authentication is `manual` and destructive | No API to set it. Outside collaborators without 2FA are removed. | docs |

## Left out, and why

| Left out | Why |
| --- | --- |
| Restricting members to private-only repo creation | Enterprise Cloud only; on Free/Team the choice is "public and private" or "public only". |
| Restricting outside collaborator invites to owners | Enterprise Cloud only. |
| Deploy key policy | Turning it off disables existing deploy keys in every repo, and Free/Team availability is not clear in the docs. I guess the risk is larger than the value for this baseline. |
| Push rulesets, metadata rules, `evaluate` mode, custom repo roles, audit log API | Team private-repo only, or Enterprise only. |
| Required reviewers / wait timers on environments | Public repos only on Free and Team; too repo-specific for a baseline. |
| GitHub Models | Retired on 2026-07-30. |
| Copilot settings and seats | Not a security baseline item. `costs` shows Copilot seats so the user sees the spend; note that Copilot Business has paid AI-credit overage on by default. |
| Artifact attestations, signed releases, fuzzing, CII badge | Need changes in the build or a human process; Scorecard reports them. |
| Auto-creating `CODEOWNERS`, `LICENSE`, required status check names | Need owner decisions (teams, legal choice, CI check names). These are `manual`. |

## Changes after the first test run (2026-10-30)

The first run on `brnrhq` (Free plan) found five ways the fixes could break things. Each one is now a precondition
in code (`PRECONDITIONS` in `scripts/ghsetup.py`), not only a sentence in SKILL.md.

1. **Branch protection updated the wrong thing.** The fix created a second ruleset with no bypass. On
   `homebrew-tap` that would have blocked the DeployKey push that `release.yml` uses. Now the fix reads
   `rules/branches/{default}` to find the ruleset that applies, and updates it in place with `PUT`. It never lowers
   a value, keeps the other rules (required_status_checks, merge methods) and the bypass actors, and lists
   non-admin bypass actors as `[warn]` so the agent asks. If nothing applies, it creates one as before. If the
   ruleset that applies is an org ruleset, the fix updates the org ruleset and warns that it covers other repos;
   I guess that is better than adding a repo ruleset next to it.
2. **No help for the Actions allow list.** `patterns_allowed` defaulted to `[]`, and the test session found the 11
   owners, the subdirectory paths and the nested composite actions by hand. Now `actions-in-use <org>` builds the
   list through the API, and the `actions_allowlist` precondition blocks while an action in use is not allowed.
   Marketplace verification cannot be read through the API, so the check assumes an action is not verified; that
   can block an action that would still run. I chose a false block over a broken workflow.
3. **Required approvals could block all merges.** With `review_count=1`, a user can merge their own PR only if
   another account with write access approves (`alexshellbot` had read access on two repos). The `reviewers`
   precondition counts other accounts with write access (accounts of type `Bot` do not count) and blocks if there
   are fewer than the required approvals. The `deploy_keys` precondition blocks a ruleset without a DeployKey bypass
   when the repo has write deploy keys.
4. **2FA did not say who is affected.** The `explain` field on `ORG-2FA` now lists members and outside
   collaborators without 2FA, and with SMS only, in the finding detail.
5. **Immutable releases had no precondition.** The `release_assets` precondition reads every workflow: it blocks
   on uploads to a published release (`gh release upload` without a draft, a workflow on the `release` event that
   uploads, `actions/upload-release-asset`) and warns on draft flows and on `softprops/action-gh-release` without
   `draft: true`. `gh release create` with the files passes: gh uploads before it publishes. This is a line-based
   heuristic, not a YAML parser; it can miss uploads done through scripts or other actions.

**Scorecard's docs and code disagree on bot reviews.** `docs/checks.md` (v5.6.0, lines 221–223) says reviews by
bots do not count as code review. The code counts any `APPROVED` review whose author is not the changeset author
(`probes/codeApproved/impl.go`, `approved()`), with no bot test on the reviewer. It marks only *authors* as bots,
and only GitHub Apps (`/apps/` resource path, `clients/githubrepo/graphql.go`). So an approval from a machine user
(a normal account such as `alexshellbot`) raises Code-Review today, though the docs say it should not. The skill
does not count a machine user as a real reviewer in its advice, and it does not suggest bot approvals to raise the
score: the docs state the intent, and the code may change.

## Known limits

- The Team plan path (`plan.name` value, org ruleset creation, paid enablement) is covered by unit tests with a fake
  GitHub, not by a live Team org. Run a dry run first on a real Team org.
- The first version's fixes were executed on `brnrhq` (Free plan) by a separate test session on 2026-10-30. The
  preconditions, the in-place ruleset update and `actions-in-use` were then tested with unit tests, live reads and
  dry runs on `brnrhq`, not with `--execute`.
