# Comment labels

Each finding starts with a label and a decoration, then a colon: `<label> (blocking):` or `<label> (non-blocking):`.
The label says what kind of comment it is. The decoration says if the PR can merge with the comment still open. The
format, the `praise` and `nitpick` labels, and the decorations come from Conventional Comments (LB1). The `issue`,
`suggestion` and `question` names are a common choice, not confirmed by the sources (I guess).

Conventional Comments makes the decoration optional. This skill writes it on every numbered finding, because a label
alone does not say if a comment blocks, and a caller may count the `(blocking)` findings (LB2).

| Label | Use it for | Decoration |
| --- | --- | --- |
| `praise` | Something specific that is good and worth keeping. At most one per review, only if true. | none; not numbered |
| `issue` | Something is wrong: a bug, a missing test, a broken rule, a security hole, a design problem. | `(blocking)` by default |
| `suggestion` | A better way. Give the reason. | `(non-blocking)` by default |
| `question` | You need an answer before you can judge. Also use it for a material part you could not review. | `(blocking)` if the answer can change the verdict, else `(non-blocking)` |
| `nitpick` | A small style point that tools did not catch. | always `(non-blocking)` |

Rules:

1. An `issue` can be `(non-blocking)` only if the defect is rare, its effect is small and contained, and a follow-up
   can fix it safely (RV6). Say all three in the finding.
2. A `suggestion` can be `(blocking)` only if the current way breaks a repo rule or the task. Say which.
3. `nitpick` is never blocking. If a nit matters enough to block, it is an `issue`, and you must say why.
4. Write the number, the label, the decoration and a colon, then `path:line`, then the text:
   `1. issue (blocking): src/cache.rs:88 — ...`. Give the problem, the reason, and the next step.
5. If the repo has its own labels (for example a team's Conventional Comments set, or `nit:` prefixes only), use the
   repo's labels and keep the blocking decoration (G1).

## Examples

```
1. issue (blocking): src/limits.py:57 — The window resets on each request, not on a fixed
   interval, so a client that sends one request per second is never limited. Fix: store the window
   start and reset only when `now - start >= WINDOW`.
2. question (blocking): src/signup.py:120 — What happens when the email service times out? The
   user row is already committed, so a retry fails with "email exists". Is that intended?
3. suggestion (non-blocking): src/limits.py:30 — `count_recent` and `prune` both scan the list;
   one pass that prunes and counts removes the second scan.
4. nitpick (non-blocking): CHANGELOG.md:8 — "throttle" here and "rate limit" in the docs; use one word.

praise: The test at tests/test_limits.py:14 that moves a fake clock across the window edge is
exactly the right test.
```
