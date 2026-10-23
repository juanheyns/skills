# PR description template

Use the repo's own PR template if it has one (G1). Otherwise use this one. Delete a section only if it does not apply,
and keep the headings so that reviewers find things in the same place each time. Keep it short: a reviewer should be
able to read it in two minutes (I guess).

Title: say what changes, in the imperative or as a statement of the new behavior. Not "Fix bug" or "Updates".

```markdown
## Why

<The problem or goal, in one or two sentences. Link the issue: "Closes #<n>".>

## What changed

<The approach, in a few lines. Other options you rejected, if useful.>

## Context

<Background the reviewer needs. If this PR is one of a stack: the other PRs, in merge order.>

## How I tested it

- <Command you ran> → <result>
- <Behavior you exercised directly (CLI call, request, page)> → <what you saw>
- <New or changed tests, and that they fail without the change>
- CI: <green / link / "no CI in this repo; ran <command> locally">

## Screenshots

<For UI changes only: before and after. Delete if not needed.>

## Risk and where to look first

<What could break and who or what is affected. How to roll back (revert is enough / needs a data fix / feature
flag). Where you want the reviewer to look hardest, and what you are not sure about. What is generated or mechanical
(lock files, fixtures, renames), so that the reviewer can skim it.>

## Checklist

- [ ] One logical change; refactoring is in a different PR or commit
- [ ] I read my own diff and tested the change
- [ ] Tests added or updated; CI is green
- [ ] If an agent wrote part of this: I read it, I understand it, and I ran it
```

Rules for the description (AU9, AU10):

- Write facts you checked. Do not write "should work" or "I think this fixes"; say what you ran and what you saw.
- Do not describe the diff line by line. The reviewer reads the diff. Explain what the diff cannot show: the reason,
  the alternatives, the risk.
- Do not put notes in the description that argue the code is correct. Show it with tests and evidence.
- Tick a checklist box only if it is true. If one is not true, say why under it.
- No AI taglines (G6).
- Update the description when the PR changes during review.
