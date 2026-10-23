---
name: pr-review
description: Use when you open or prepare a pull request (PR) or patch, review someone else's PR (a human's or another agent's), or answer review findings on a PR. Covers PR scope and size, self-review, the PR description, the order of attention in a review, comment labels, blocking vs non-blocking, the verdict format, review rounds, and how to respond to review. Use it also when asked to "review this PR/diff", "get this ready for review", "write the PR description", or "address the review comments".
---

# PR review

This skill has three modes. Pick the one that matches your job, then follow its steps in order.

- **Author**: you prepare your own change for review (by a human or an agent).
- **Reviewer**: you review a change that you did not write.
- **Responder**: you are the author and you answer review findings.

The rule IDs in brackets, for example `(RV3)`, point to `references/sources.md`. That file gives the evidence for each
rule. You do not need to read it to follow the skill.

## Rules for all modes

1. **The repo's own rules come first.** Before you start, read the repo's AGENTS.md, CLAUDE.md, CONTRIBUTING, PR
   template, review checklist and the ADRs the change touches. If they disagree with this skill, follow the repo and
   say so in your output. (G1)
2. **Use evidence, not belief.** Check every claim against the code, a command you ran, or CI before you write it.
   Give `path:line`. Write "I guess" for anything you could not check. If you could not get to a source (no access,
   no login, tests would not run), say so at the top of your output. (G2)
3. **Do not merge, approve, close, tag or release** unless the person who gave you the task tells you to. A human
   owner decides what ships. A PASS from you is a recommendation, not a merge gate. (G3)
4. **Post nothing unless you were told to post.** If you were not told, return the text to the caller. (G4)
5. **Discuss the code, not the person.** Assume competence and goodwill. Ask rather than demand, offer alternatives,
   give the reason, and say what is your opinion and what is a principle. Do not exaggerate and do not bikeshed. Use
   the same tone with humans and agents. (G5)
6. **No AI taglines.** Do not add "Generated with", "Co-Authored-By" or similar lines to commits, PR text or comments
   unless the repo asks for them. Keep the repo's `git config user.email`. (G6)

## Mode 1: Author — prepare your own PR

1. **One purpose per PR.** A reviewer must be able to say in one sentence what the PR does. Keep refactoring,
   formatting and moves in a separate commit or PR from behavior changes. (AU1)
2. **Keep it small.** As a guide, aim for under about 200 changed lines of hand-written code, and split or explain
   anything over about 400. These numbers are a default that starts a conversation, not a hard gate: a change that
   is complete as an idea and hard to split can be larger if the description says why. Generated files, lock files
   and fixtures do not count, but say that they are there. (AU2)
3. **Stack large work.** Split it into a stack of dependent PRs that each build and pass tests. Say in each
   description what it depends on and in which order they must merge. (AU3)
4. **Ask early about design.** If the design is not settled, open a draft or ask the owner before you write all of
   the code. Do not wait for a perfect change to get the first feedback. (AU4)
5. **Do what the task asks, and nothing more.** If the task links an issue, check each "done when" item. Put
   unrelated fixes and out-of-scope ideas in a separate PR or a follow-up issue. (AU5)
6. **Prove that it works.** Run the tests. Exercise the changed behavior directly (run the command, call the
   endpoint, open the page). Add a regression test that fails without your change. Passing tests are necessary but
   not sufficient. (AU6)
7. **Self-review the diff before you ask for review.** Read the full diff as a reviewer would, with
   `references/checklist.md`. Remove debug code, dead code and unrelated changes. You must understand and be able to
   defend every line, including lines a tool or agent generated. (AU7)
8. **Let tools do the mechanical checks.** Run the repo's formatter, linter and type checker before review, so that
   reviewers spend their time on intent, design and tests. (AU8)
9. **Write the description with `references/pr-template.md`.** It says why, what changed (the approach), the context
   (for example the other PRs in a stack), how you tested it, and the risk and where to look first. Add screenshots
   for UI changes. Write a title that says what changes. (AU9)
10. **Point to the hard parts.** Tell the reviewer where the risk is and what you are not sure about. Do not use
    notes to argue that the code is correct; the code and tests must show that. (AU10)
11. **Ask the right reviewer.** Request the code owner or a person who knows the files. For security-sensitive
    changes, ask for a specialist review as well. (AU11)
12. **CI must be green** before you say the PR is ready. If the repo has no CI, run its tests locally and say so in
    the description. (AU12)

## Mode 2: Reviewer — review a PR you did not write

### Before you start

1. **Be a different session from the author.** Do not review your own change in the session that wrote it. A
   different model or session can find other problems, but it is not proof of independent assurance, so do not
   claim that it is. (RV1)
2. **Collect the inputs:** the PR title and description, the linked issue and its "done when", the full diff, the CI
   result, the repo rules from G1, and the code around the change (not only the diff hunks). If you can, check out the
   head in a separate worktree and run the tests; remove the worktree when you finish. All `path:line` references
   are to the PR head commit; write its short sha in your "Checked" line. If the material you were given does not
   match the PR head (other line numbers, a later branch), use the head and say so. (RV2)
3. **Review only this PR's diff against its base.** In a stack of PRs, the earlier PRs are reviewed on their own.
   Comment on their code only if this PR depends on a problem in it or makes it worse. (RV18)
4. **Understand the change before you judge it.** Write, for yourself, one or two sentences on what the PR does and
   why. If you cannot, that is your first finding: the description or the change is not clear enough. (RV3)

### Order of attention

Review in this order. Start with the large issues and finish with nits: a design problem can make the smaller
comments useless. Scale the depth of your review to the impact of the change and how hard it is to reverse. The
details for each step are in `references/checklist.md`. (RV4)

1. **Intent and scope.** Does it do what the description and the issue say? Is there one purpose? Is there anything
   that is not in scope?
2. **Design and fit.** Does it fit the system, the ADRs and the existing patterns? Is there a simpler way? Does it
   duplicate something that exists?
3. **Correctness and failure paths.** Logic, edge cases, error handling, resource leaks and limits, threading and
   concurrency, performance, data migrations, backward compatibility.
4. **Tests.** Do the tests prove the change? Would they fail without it? Watch for tests that only repeat the
   implementation, mocks that hide the behavior, and changed expectations without a reason.
5. **Security and privacy.** Input and data flows, authorization, secrets, injection, logging of private data. If the
   change touches authentication, credentials, cryptography or a sandbox, say that ordinary review is not a security
   review and recommend a specialist. Frame security review as defensive: does each rule match the spec, is any path
   not covered, does it fail closed.
6. **Readability.** Names, complexity, comments, docs, the CHANGELOG and ADRs that the repo requires.
7. **Nits.** Small style points that tools did not catch. These are `nitpick` at most. If the same nit occurs many
   times, write one finding that says a tool or a style rule should catch it.

### Rules for findings

1. **Every finding has five parts:** a label, `blocking` or `non-blocking`, a `path:line`, what is wrong and why it
   matters, and a suggested fix or a question. The labels are in `references/comment-labels.md`. (RV5)
2. **Blocking means:** the PR must not merge until this changes. Use it for wrong behavior, data loss, a security
   hole, a missing or false test of the main change, a broken repo rule, or a scope or design problem that will cost
   more to fix later. A preference is never blocking. A real defect can be `issue (non-blocking)` only if it is rare,
   its effect is small and contained, and a follow-up can fix it safely; say all three in the finding. (RV6)
3. **Verify each finding before you write it.** Read the code around it, follow the call sites, and run it if you can.
   Remove findings you cannot support. If a finding depends on something you could not check, write "I guess" and say
   what would confirm it. A wrong finding costs the author more time than a missed nit. (RV7)
4. **Give all your blocking findings in the first round.** Do not hold some back for later. (RV8)
5. **Keep it short.** At most 5 non-blocking findings; choose the most useful ones. Do not repeat what CI or a linter
   already reports. Do not write general advice that is not tied to a line. (RV9)
6. **Do not demand perfection.** The goal is better code health, not perfect code. If the change makes code health
   better and has no blocking finding, it can pass, even if you would have written it differently. Do not pass a
   change because of pressure without a real review. (RV10)
7. **Explain so that the author learns.** Give the principle or the rule behind a finding, not only the fix. One
   specific `praise` line is fine when it is true; do not add praise to fill space. (RV11)
8. **Do not fix the code yourself** unless you were told to. Suggest the fix; the author stays responsible for the
   change. (RV12)

### The verdict

The verdict is the first line of your output, exactly one of these: (RV13)

```
Review round <n>: PASS
Review round <n>: CHANGES NEEDED
```

- **PASS** means no blocking finding is open. Non-blocking findings can still be listed; the author can fix them
  without another review round.
- **CHANGES NEEDED** means at least one blocking finding is open.
- If something stops you from reviewing a material part, write a blocking `question` for it. Do not give PASS on code
  you could not review. A material part is code in the diff that you could not read or understand (no access, too
  large, generated without its source), or a claim that the verdict depends on and that neither you nor CI could
  check. A green CI run stands in for running the tests yourself; say so in "Not checked".
- Use GitHub's "approve" or "request changes" states only if the task tells you to. Otherwise put the verdict in a
  comment (or return it as text, see G4).

Use this format for the body. A complete example is in `examples/`.

```markdown
Review round 1: CHANGES NEEDED

Summary: <one or two sentences: what the PR does, as you understand it, and the main reason for the verdict.>
Checked: <what you read and ran, with the result>. Not checked: <what you could not check, and why>.

Blocking
1. issue (blocking): `src/cache.rs:88` — <what is wrong>. <why it matters>. Fix: <suggestion>.

Non-blocking
2. suggestion (non-blocking): `src/cache.rs:40` — <...>.
3. nitpick (non-blocking): `README.md:12` — <...>.

praise: <one specific thing that is good, optional>
```

Number the findings across both lists, so that the author can answer "finding 2". If there are no findings in a
list, write "None." under its heading. Keep "Summary" and "Checked" to a few lines each. A finding can wrap over
several lines. An optional `praise` line goes last, after the non-blocking list, without a number. Put inline
comments on lines only if the task asks for them; use the same labels there.

### Later rounds

1. Use the same reviewer session for the next round if you can. (RV14)
2. Check each open finding against the author's answer and the new commits. Then review the new diff since the last
   round with the same order of attention. (RV14)
3. Do not add new non-blocking findings on code that did not change. Add a new blocking finding on unchanged code only
   if it is real and serious, and say that you missed it in an earlier round. (RV15)
4. An answer "not fixed because ..." with a good reason closes a finding. If you do not agree, say why once; then RE7
   applies. (RV16)
5. **Stop after 3 rounds.** If blocking findings are still open after round 3, stop and give the open findings to the
   human owner (the code owner or the maintainer with merge authority) with both positions. Do not argue further in
   comments. (RV17)

## Mode 3: Responder — answer review findings

1. **Read all findings before you change anything.** Ask about a finding you do not understand; do not guess what
   the reviewer means. (RE1)
2. **Verify each finding.** A finding from a reviewer, human or agent, can be wrong. Reproduce it or read the code it
   points to. (RE2)
3. **Answer every finding, blocking or not:** fix it, or say why not. A reason must point to the task, a repo rule, an
   ADR, or evidence (a test, a measurement). "I prefer it this way" is not a reason for a blocking finding. You can
   decline a nit without a long reason. (RE3)
4. **Fix in new commits** during review, so that the reviewer can see what changed. Squash only if the repo asks for
   it. Run the tests and CI again. (RE4)
5. **Do not make unrelated changes** in a fix round. They make the next round larger. Before you ask for the next
   round, check that you made each correction you agreed to. (RE5)
6. **Split the PR** if review shows that it mixes refactoring with behavior, has grown past one idea, or that the
   reviewer cannot follow it. (RE9)
7. **Post one answer per round** (if you were told to post) in this format: (RE6)

   ```
   Fixes for review round <n>:
   1. fixed in <short sha> — <one line on what changed>
   2. not fixed because <reason, with the rule, ADR or evidence>
   3. fixed in <short sha>
   ```

8. **Disagree with reasons, not at length.** Give your reason once. If you and the reviewer still disagree after two
   exchanges (your reason and the reviewer's reply), stop and ask the human owner (the code owner or the maintainer
   with merge authority) to decide. Give both positions in two or three lines. (RE7)
9. **Review is not finished when you submit.** Watch CI and the next round. If you are an agent, your work is done
   when the PR is open, green and reviewed with PASS, or when the round limit sends it to the human. Do not wait for
   the merge. (RE8)

## Files in this skill

- `references/checklist.md`: the review checklist, in the order of attention. Use it in Author step 7 and in review.
- `references/comment-labels.md`: the label scheme and when each label is blocking.
- `references/pr-template.md`: the PR description template.
- `references/sources.md`: each rule ID with its evidence keys and the list of sources.
- `examples/`: a real review made with this skill.
- `DECISIONS.md`: why the skill is as it is.
