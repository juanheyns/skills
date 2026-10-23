# PR description template

Use the repo's own PR template if it has one (G1). Otherwise use this one. Delete a section only if it does not apply,
and keep the headings so that reviewers find things in the same place each time. Keep it short: a reviewer should be
able to read it in two minutes (I guess).

Title: say what changes, in the imperative or as a statement of the new behavior. Not "Fix bug" or "Updates".

```markdown
## What and why

<One or two sentences: what this PR changes and why it is needed. Link the issue: "Closes #<n>".>

## Approach

<How you did it, and the alternatives you rejected, in a few lines. Say if the PR is one of a stack: which PR comes
before it, which comes after, and the merge order.>

## How I tested it

- <Command you ran> → <result>
- <Behavior you exercised directly (CLI call, request, page)> → <what you saw>
- <New or changed tests, and that they fail without the change>
- CI: <green / link / "no CI in this repo; ran <command> locally">

## Risk and rollback

<What could break, who or what is affected, and how to roll back (revert is enough / needs a data fix / feature flag).>

## Review focus

<Where you want the reviewer to look hardest, and what you are not sure about. Say what is generated or mechanical
(lock files, fixtures, renames) so that the reviewer can skim it.>

## Screenshots

<For UI changes only: before and after.>
```

Rules for the description (AU9, AU10):

- Write facts you checked. Do not write "should work" or "I think this fixes"; say what you ran and what you saw.
- Do not describe the diff line by line. The reviewer reads the diff. Explain what the diff cannot show: the reason,
  the alternatives, the risk.
- Do not put notes in the description that argue the code is correct. Show it with tests and evidence.
- No AI taglines (G6).
- Update the description when the PR changes during review.
