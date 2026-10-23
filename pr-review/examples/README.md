# Self-test: a real review made with this skill

`brnr-366-review-round-1.md` is the output of the reviewer mode, unchanged, on a real merged PR:
[brnrhq/brnr#366](https://github.com/brnrhq/brnr/pull/366) ("The host keeps at most 1024 requests the agent cancelled
under the editor, and drops a session's as it closes"). It is +126 / −27 lines in 5 files: Rust code, an ADR and the
CHANGELOG. The `#362` and `#364` in the review are PRs and issues of that repo, not of this one.

The review was not posted anywhere. It is here to show the format.

## How it was run

- A fresh agent session read only `SKILL.md`, `references/checklist.md` and `references/comment-labels.md`. It did
  not see `DECISIONS.md`, `references/sources.md` or the PR's existing reviews, so the test was blind.
- Its inputs were the PR title, body and commits, the full diff, the repo's AGENTS.md, CONTRIBUTING.md and review-bot
  config, the linked issue, the CI result, and the code at the PR head (read-only).
- It did not build or run the project; CI was green. It says both in the "Checked" and "Not checked" lines.

## What it showed

- **Verdict: PASS, with 2 non-blocking findings and 1 praise line.** The owner merged the PR, so PASS matches the
  owner's decision (that does not prove the review was right).
- **Finding 1 is real.** At the PR head, `give_up` adds the cancelled request to the capped queue (and so can push
  out the oldest entry, from a session that is still open), and only after that does `agent_cancel` remove the new
  entry because its session is closed. I checked this against the code at commit `9111792`. It matters only at the
  cap, so non-blocking is the right decoration.
- **Comparison with the repo's review bot.** The bot reviewed an earlier head and posted two findings. One (a cancel
  kept past its session's close) was fixed in `9111792`, the head this test reviewed, so the skill could not find
  it. The other (a reopened session) the bot withdrew after the author's answer; the skill did not raise it. The
  skill's finding 1 is about the fix in `9111792` itself, which the bot did not comment on.
- **The "verify each finding" rule (RV7) removed one false blocker** before it was written: an answered request
  after a close that cannot happen, because control answers need an open session.

## What the test changed in the skill

The reviewing agent reported where the skill was unclear. These changes were made after the test:

1. `path:line` is at the PR head commit, and the "Checked" line gives its sha; use the head if the given material
   does not match it (RV2).
2. A definition of "material part" for the blocking `question` rule, and "a green CI run stands in for running the
   tests yourself" (RV13).
3. The three conditions under which a real defect can be `issue (non-blocking)` (RV6).
4. Where praise goes, and that findings can wrap (format block).
5. In a stack, review only this PR's diff against its base (RV18).

One tip from the test that is not in the skill, because the skill gives no shell commands: in zsh, quote
`"${sha}:path"` in `git show`, because `$sha:s...` is read as a history modifier.
