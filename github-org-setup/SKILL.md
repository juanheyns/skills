---
name: github-org-setup
description: Use when you set up, harden or audit a GitHub organization or its repositories on the GitHub Free or GitHub Team plan. It audits org settings, Actions policies, security features, rulesets and repo files against a baseline from the GitHub docs and OpenSSF Scorecard, shows what is free and what costs money, asks the user to opt in to each paid item with live prices, and applies only the changes the user approves. Use it also for "secure our GitHub org", "set up branch protection for all repos", "improve our Scorecard score", "what does GitHub Advanced Security cost us", or "check our org against best practices".
---

# GitHub org setup

This skill audits a GitHub organization and its repositories, then applies the fixes that the user approves. The
script `scripts/ghsetup.py` does the deterministic work: it reads, compares, plans and applies. You do the judgment:
you ask the user, explain the impact, read live prices, and choose what to select.

The baseline is data: `data/checks.json`. Each check has a plan matrix (Free/Team, public/private), a cost, a fix
and its sources. `references/checks.md` is the same catalog as a table. The rule IDs in brackets, for example
`(S3)`, point to `references/sources.md`.

## Scope

- **In scope:** organizations on github.com on the **GitHub Free** or **GitHub Team** plan, and their repositories.
- **Out of scope:** GitHub Enterprise Cloud, Enterprise Managed Users, GHE.com and GitHub Enterprise Server. If
  `detect` shows another plan, stop and tell the user. (S1)

## Rules

1. **Read first, change later.** `detect`, `audit`, `report`, `costs`, `scorecard` and `workflows` only read.
   `apply` is a dry run unless you add `--execute`. Run `--execute` only for the finding keys that the user approved
   in this session. Approval for one change is not approval for the next. (S2)
2. **No cost without an opt-in.** A finding with availability `paid:<product>` enables a paid product. Before you
   ask the user, read the live price pages for that product (the `report` lists them) with your web tool, and tell
   the user the price, the billing unit and when billing starts. Do not use a price from memory or from this skill.
   If you cannot read the page, say so and give the link; do not guess. Pass `--accept-cost <product>` only after
   the user says yes to that product. The script refuses paid fixes without it. (S3)
3. **Destructive changes are asked one by one.** A finding marked `destructive` can break workflows or remove
   access. `--all-free` never selects them. Explain the text in the `destructive` field and check the precondition
   it names (for example, run `pin` before you require SHA pinning). (S4)
4. **The user decides policy values.** Ask, do not assume: how many people can review a PR, the security contact,
   budget amounts and recipients, and which repositories are in scope. (S5)
5. **Facts come from the docs, and they move.** The catalog was verified on the date in its `verified_on` field.
   If that date is more than 90 days old, or the API answers differently from the catalog (for example a 404 on an
   endpoint the catalog uses), check the current page on docs.github.com before you act, and say what changed.
   Never fill a gap from memory. (S6)
6. **Changes to repo content go through a PR.** The script never pushes to a default branch. File fixes open a PR
   on a new branch. Do not merge it unless the user tells you to. Do not add AI taglines to PRs or commits. (S7)
7. **Report faithfully.** After `apply --execute`, read the `[verify]` lines. Say what passed, what failed and
   what still needs a human. A `manual` item is not done until the user says they did it. (S8)

## Before you start

- `gh auth status` must show a login with the scopes `admin:org`, `repo` and `workflow` (`workflow` lets the PR
  fixes add workflow files). Refresh with `gh auth refresh -s admin:org,repo,workflow`.
- The user must be an **org owner**. Some reads (plan, `security_and_analysis`, billing) return nothing for others;
  those checks show `unknown`.
- Python 3.10 or later and the `gh` CLI. No other packages.

Run the script from the skill folder: `python3 scripts/ghsetup.py <command> ...`.

## Steps

### 1. Detect

```sh
python3 scripts/ghsetup.py detect <org>
```

Confirm the plan (`free` or `team`), the user's role (`admin` means owner) and the repo counts. If the plan is
missing, the user is not an owner: ask them to run it as an owner, or pass `--plan` only if they confirm the plan.

### 2. Ask the policy questions

Ask in one round (use your question tool if you have one). Recommended defaults are in brackets.

- Which repositories are in scope? [all non-archived, non-fork repos]
- How many people can review PRs? This sets `review_count` [1]. With one maintainer, use `review_count=0`; the
  Branch-Protection and Code-Review findings then stay open, and that is a known trade-off.
- Can anyone bypass the default-branch ruleset? [nobody: `bypass_actors=[]`, which Scorecard needs for its top
  tier. Org owners can still edit the ruleset in an emergency.]
- The security contact for `SECURITY.md` (an email address or URL). [no default]
- Budgets: for each metered product without a budget, the amount in whole USD and who gets alerts. [ask]

### 3. Read the current costs

```sh
python3 scripts/ghsetup.py costs <org>
```

Show the user what the org pays now (plan seats, this month's net usage, budgets, Copilot seats). If there is no
budget, metered usage beyond the included amount is billed with no limit.

### 4. Audit

```sh
python3 scripts/ghsetup.py audit <org> --out /tmp/<org>-audit.json      # add --repos 'api*' to limit
python3 scripts/ghsetup.py report /tmp/<org>-audit.json                  # --all also shows passes
```

Status values: `pass`, `fail`, `unavailable` (the plan does not have it for this repo), `skipped` (condition not
met), `unknown` (no permission or the endpoint failed; read the detail), `manual` (UI only; the detail says what to
do).

For public repos, also get the OpenSSF Scorecard result. It uses the local `scorecard` CLI if it is installed (this
also works for private repos), else api.scorecard.dev:

```sh
python3 scripts/ghsetup.py scorecard <org>/<repo>
```

The last column shows which baseline checks raise each Scorecard check. Scorecard checks with no baseline check
(Maintained, Contributors, Fuzzing, Signed-Releases, Binary-Artifacts, CII-Best-Practices, Dangerous-Workflow) are
code or process work: report them, do not try to fix them with settings.

### 5. Present the plan

Group the failed findings like this, and give the finding keys:

1. **Free and safe:** `fail`, availability `free`, an automatic fix, not destructive. One approval can cover the
   group.
2. **Free but destructive:** give the impact from the `destructive` field and its precondition for each one.
3. **Paid:** for each product, the live price (rule 2), the billing unit, which repos it would cover, and that
   billing starts at once. On Team, enabling Secret Protection or Code Security on private repos is metered per
   active committer.
4. **Needs input:** fixes with a required parameter (for example `security_contact`, `budget_amount`).
5. **Manual:** UI-only items, with the exact settings path from the detail.

### 6. Apply

Always dry run first and show the output to the user:

```sh
python3 scripts/ghsetup.py apply /tmp/<org>-audit.json --select 'ORG-ACTIONS-FORK-APPROVAL' 'REPO-DEPENDABOT-*'
python3 scripts/ghsetup.py apply /tmp/<org>-audit.json --all-free
python3 scripts/ghsetup.py apply /tmp/<org>-audit.json --select 'REPO-BRANCH-PROTECTION' --set review_count=0
python3 scripts/ghsetup.py apply /tmp/<org>-audit.json --select ORG-SECURITY-MD --set security_contact=security@example.com
python3 scripts/ghsetup.py apply /tmp/<org>-audit.json --select 'REPO-SECRET-SCANNING@<org>/<repo>' --accept-cost secret_protection
```

After approval, run the same command with `--execute --log /tmp/<org>-apply.json`. Exit code 3 means a selected fix
needs a `--set` value; 1 means an API call failed (read the `[error]` line).

How fixes behave:

- **Rulesets:** on Free, one repo ruleset for each public repo. On Team, **one org ruleset** for the default branch
  of all repos (new repos included); the script creates it only once.
- **Merge steps** (Actions permissions) read the current value and change only the baseline's fields.
- **PR fixes** (`SECURITY.md`, `dependabot.yml`, `scorecard.yml`) open a PR. `ORG-SECURITY-MD` creates the public
  `.github` repo if it does not exist. Edit `dependabot.yml` in the PR to add the repo's package ecosystems.
- **Workflow fixes** are local: clone the repo, then

  ```sh
  python3 scripts/ghsetup.py workflows <checkout>          # top-level permissions, unpinned actions
  python3 scripts/ghsetup.py pin <checkout> --write        # tags -> full SHAs, tag kept as a comment
  ```

  Review the diff, add `permissions:` blocks by hand, and open a PR.

### 7. Verify and report

`apply --execute` re-runs the checks for what it changed and prints `[verify]` lines. Run `audit` and `report` again
at the end. Tell the user, in this order: what changed, what failed and why, what is still open (paid items they
declined, destructive items they postponed, manual items), and what a new repo gets by default:

- On **Team**: the org ruleset, the org security configuration default, Actions policies and the org `SECURITY.md`
  apply to new repos automatically.
- On **Free**: the security configuration default, Actions policies and the org `SECURITY.md` apply automatically;
  rulesets do not. Run `audit <org> --repos <new-repo>` and apply `REPO-BRANCH-PROTECTION` for each new public repo.

## Change the baseline

Edit `data/checks.json`, then run:

```sh
python3 scripts/ghsetup.py catalog > references/checks.md
python3 -m unittest discover -s tests
```

Give every check a source URL on docs.github.com (or the Scorecard source) and update `verified_on`. Record the
reason in `DECISIONS.md`.
