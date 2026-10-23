# Decisions for the pr-review skill

This file records each decision and trade-off made while writing the skill, with the evidence keys. The keys are
listed in `references/sources.md`. "I guess" marks a decision that is my judgment and not supported by a source.

## Inputs

- **Only the stage 1 report was used.** The task allowed the stage 2 guide for humans if it had landed when work
  started. On 2026-10-23 it was not on the main branch of the research repo, so this skill is built from the stage 1
  report only (34 pre-2023 sources, 18 agent-era sources). When the guide lands, compare the two and open an issue
  for any gap.
- **The report is not public.** For this reason, `references/sources.md` repeats the source list with public links,
  so a reader of this repo can check each key without the report.
- **The report paraphrases its sources.** It quotes no prose from them. The skill also paraphrases. Where a rule says
  "P13", it means "the report says P13 recommends this", not a quote.
- **The report tags claims D / I / U** (documented, inferred, unresolved). The skill keeps these tags and adds two:
  **S** (taken from the existing agent review loop that the skill must fit) and **J** (my judgment). The table in
  `references/sources.md` gives one of these for each rule.

## Scope

1. **One skill with three modes (author, reviewer, responder), not three skills.** The three jobs use the same
   vocabulary: the labels, the blocking decoration, the verdict line and the round numbers. One agent is often
   author and responder on the same PR. With three skills, the label and verdict files would be copied or
   cross-linked, and the triggers would overlap ("review comments" can mean "write" or "answer"). One folder is also
   one install. The cost is a larger SKILL.md (about 200 lines, under the 500-line limit) and a name, `pr-review`,
   that is narrower than the content; the trigger description names all three jobs to fix that. I guess.
2. **Same standard for human and agent authors.** The skill does not ask for a different review of agent PRs. A01
   says to judge code on its merits, not on presumed authorship; A09's "1.7x more problems" is a vendor number on
   classified samples that the report does not endorse as a general effect. The agent-era risks (large PRs, unread
   code, tests that do not prove) are covered by rules that apply to everyone: AU2, AU6, AU7 and the test checklist.
3. **The skill is for one review by one reviewer.** It does not decide how many reviewers a team needs, who routes
   reviews, or code-owner settings. Reviewer count is unresolved in the report (P08, P12, P14, P28, P01, P03, P16),
   and routing is a team or supervisor job. AU11 only asks the author to request the right person.

## Left out, and why

| Left out | Why | Keys |
| --- | --- | --- |
| Turnaround times (one business day, two working days, "hours not days") | The report finds no universal SLA. An agent reviews when it is asked, so a response deadline is the caller's concern. I guess. | P13, P16, P28; U |
| Time limits per review session (under 60, max 90 minutes) | These are for human attention in one study. Agents do not tire in the same way, but long diffs still lose attention, which AU2 covers. I guess. | P06 |
| Review rates (lines per hour) and defect-detection rates | The report gives no numbers that it accepts as general. | P01, P04, P06 |
| Formal inspection roles, meetings and entry/exit criteria | Too heavy for PR review by an agent. The skill keeps two parts of inspections: a checklist (CL1) and recording findings (RV5). I guess. | P01, P02, P03 |
| Team metrics (coverage, comment counts, approval quotas) | These are team-level, correlational, and invite gaming. | P09, P10, P33; I |
| Choosing ship / show / ask per change | That choice belongs to the human owner, not to the reviewing agent (G3). | P32 |
| Sign-off and trailer tags (DCO, Reviewed-by, Tested-by) | Repo-specific; G1 sends the agent to the repo rules. | P17 |
| A full security review method | Ordinary review is not a specialist security review. The skill asks the reviewer to say so and recommend one. | P19, P26 |
| Mentoring programs, pairing new reviewers | Team practice, not something one agent does in one review. | P24; I |
| Tool or vendor choice (review bots, stacking tools) | No source in the report establishes comparative accuracy or net time saved. | A05, A07, A08, A16 |

## Where the sources disagree, and the side taken

1. **Merge gates.** P31 wants required review and passing checks for each change. P32 says choose per change, and
   A13 reports agents merging with optional human review. The skill takes neither side for teams. For the agent it
   takes a strict side: never merge or approve unless told to, and a PASS is a recommendation (G3). Reasons: the
   author stays accountable (A12), the report finds the safety of unattended merging unresolved, and it fits the
   current review loop. I guess.
2. **Size limits vs judgment.** P06 (Cisco) gives under 200 and at most 400 lines. P21 prefers changes that are
   complete in concept. The report finds no universal ceiling. The skill uses 200/400 as a signal and lets a larger
   change through with a reason in the description (AU2). Size is not blocking by itself; it blocks only when it
   stops a real review (the `question (blocking)` rule under the verdict). I guess.
3. **Formality.** P01 and P03 favor formal inspections; P08 and P12 describe light, asynchronous review as a success;
   P02 is neutral. The skill is light and asynchronous with a short checklist. I guess.
4. **Self-review notes.** P06 links author preparation with fewer defects found, but notes that annotations could
   also reduce the reviewer's scrutiny. The skill asks for self-review (AU7) and for notes that point to risk, but
   says notes are not proof (AU10).
5. **Praise.** P20 asks for sincere praise. The current review loop is "critical only". P11's usefulness measure
   does not show that praise is useless. The skill allows one specific `praise` line and does not number it, so it
   cannot be mistaken for a finding (RV11). I guess.
6. **Knowledge sharing when the author did not write the code.** A06 asks whether review still teaches when the
   author did not understand generated code; P07 and P14 count learning as a main outcome. The skill keeps "explain
   the principle" (RV11) and makes the author responsible for understanding every line (AU7).
7. **Conventional Comments vocabulary.** P20's wording for nitpicks changed over time, and the report says a label
   alone does not settle blocking policy. The skill uses its own five labels and always writes the decoration (LB1,
   LB2).

## Agent-era practices

Adopted:

- **Prove it works** before review: run it, exercise it directly, add a regression test (A12 → AU6).
- **Passing tests are not merge readiness** (A14 → AU6, the test checklist).
- **The author understands and answers for every line, also generated lines** (A06, A12 → AU7).
- **No claim of independence** from a second model or session (A04 and the report's inference → RV1). The skill
  still asks for a different session, because the author session is the worst place to look for its own mistakes.
  I guess.
- **Verify each finding, cap the noise** (A02, A03 and the report's inference on false positives → RV7, RV9, RE2).
- **Watch for tautological tests** (A15 → the test checklist).
- **Stack large work** (P21, P22, A16 → AU3).

Rejected:

- **Reviewer agents that make the fixes themselves** (A15). The canon is comment-centered and the author stays
  accountable (A12). Allowed only if the task asks for it (RV12). I guess.
- **Agent review with human review optional** (A13). See disagreement 1.
- **Using vendor or survey numbers as rules** (A09, A10, A11, A17). They are observational, and their results
  conflict (DORA's faster reviews vs Faros' 91% longer review time). No rule depends on them.

## Gaps in the report, filled by the review loop or judgment

The report has no rule for these, so each one is S or J:

- the verdict states and the exact verdict line (RV13);
- the number of rounds and when to stop (RV15, RV17);
- the escalation path to a human (RE7, RV17);
- a PR description template (only the content is sourced; the layout is J);
- how an author handles review findings from an agent, and wrong findings (RE2);
- the limit of 5 non-blocking findings (RV9: I guess, to answer the "verbose AI review" complaint in A03).

## Format choices

- **SKILL.md holds the steps; reference files hold the detail.** The checklist, labels, template and sources load
  only when needed. Rule IDs in brackets link each step to `references/sources.md`, so the evidence does not clutter
  the steps.
- **Short sentences and simple words.** The skill is read by agents and by people for whom English is a second
  language. I guess.
- **The verdict is the first line and has two values.** A caller (a human or a supervisor script) can read the
  verdict without parsing the body. A third value for "could not review" was considered and rejected: an
  unreviewable part becomes a blocking `question`, which keeps two values and makes the gap visible. I guess.
- **One summary comment, not inline comments, by default.** It works when there is nothing to post to (a local diff,
  a text reply) and when the reviewer may not post. Inline comments are allowed on request, with the same labels.
- **Findings are numbered across the blocking and non-blocking lists**, so that the answer can say "finding 3".
- **DECISIONS.md is in the skill folder**, so it stays with the skill when the repo has more skills. Agents that
  load the skill only read SKILL.md, so it costs nothing at run time.

## Fit with the current supervisor review process

The owner's agent supervisor already runs reviews with its own process document. The skill must fit it.

Same as the current process:

- A different session from the author reviews, and the same reviewer session does the next round.
- The first line is exactly `Review round <n>: PASS` or `Review round <n>: CHANGES NEEDED`.
- Numbered findings, each with `file:line`, what is wrong, why, and a fix. PASS means no blocking finding.
- Check every claim; write "I guess" when not checked; say at the top when a source is not reachable.
- The order of checks covers the same items: correctness, edge cases, errors, concurrency, tests that prove the
  change, security, scope, required docs and ADRs, and "does it do what the issue asks".
- Defensive wording for security reviews ("does each rule match the spec, is any path not covered, does it fail
  closed").
- Later rounds check the open findings and the new diff. The limit is 3 rounds, then the human decides.
- The author answers with `Fixes for review round <n>:` and `fixed in <sha>` or `not fixed because ...`.
- No approve, merge or close by agents; no AI taglines; an open, green, reviewed PR is done for the worker.

Different from the current process:

- **Labels.** The current process has two levels, blocking (the default) and `nit`. The skill has five labels and an
  explicit decoration on each finding. It stays compatible: a nit is still written `nit`, and the verdict rule is the
  same. A supervisor that counts blocking findings can count `(blocking)`.
- **Order.** The current list starts with correctness. The skill puts intent, scope and design first, because P23
  says to start with large design problems and P07 says understanding is the main difficulty. Scope moves from near
  the end to near the start.
- **A cap on non-blocking findings** (5), and no new nits on unchanged code in later rounds. These are new.
- **An unreviewable part is a blocking `question`.** The current process only says to report it at the top.
- **One praise line is allowed.** The current process is critical only.
- **Posting.** The current process always posts one comment per round. The skill posts only when told to (G4); the
  supervisor's brief tells the reviewer to post, so the result is the same.
- **Author guidance.** The current process has no size guide or description template; the skill adds both (AU2,
  AU9).
- **Not in the skill:** repos where a review bot is the only reviewer, the supervisor's board and scoring, which
  model reviews which, and whether to use subagents. These are the supervisor's choices. The current process
  documents also disagree about subagents, so the skill says nothing about them.

## Self-test

The reviewer mode was run blind, by a fresh agent session that saw only the skill, on a real merged PR of a public
repo (`examples/`). The result: PASS with one real non-blocking defect that the repo's review bot had not raised, and
one false blocker that rule RV7 removed before it was written. The test found five gaps in the skill, which are now
fixed: which commit `path:line` refers to (RV2), what a "material part" is and that green CI stands in for running
tests (RV13), when a real defect can be non-blocking (RV6), where praise goes, and how to treat stacked PRs (RV18).
One test is not proof that the skill works in general; the author and responder modes were not tested. I guess the
next useful test is a PR with a real blocking defect, to check that the skill gives CHANGES NEEDED.
