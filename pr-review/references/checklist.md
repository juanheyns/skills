# Review checklist

Use this list in the order of attention from SKILL.md (RV4). Authors use it for self-review (AU7). The list is a
reminder, not a form to fill in: you do not have to write an answer for each line. Report only what you find.

The repo's own checklist (in AGENTS.md, CONTRIBUTING, the PR template or a review doc) comes first (G1). When a
problem gets past review and is found later, add a line for it to the repo's checklist, not to a longer list here
(CL1).

## 0. Understand the change

- [ ] I can say in one or two sentences what the PR does and why.
- [ ] I read the linked issue, its "done when" items and the ADRs the change touches.
- [ ] I read the code around each hunk, the callers of changed functions, and the tests.
- [ ] I know the CI result. I ran the tests myself, or I say that I did not.

## 1. Intent and scope

- [ ] The change does what the title, description and issue say. Each "done when" item is met.
- [ ] There is one purpose. Refactors, moves and formatting are in separate commits or PRs.
- [ ] Nothing is in the diff that the task did not ask for (scope creep, drive-by changes).
- [ ] The size is reviewable. If it is over about 400 changed lines of hand-written code, the description says why
      it cannot be split.

## 2. Design and fit

- [ ] It fits the existing architecture, ADRs and patterns, or the PR says why it does not.
- [ ] There is no simpler way that does the same job.
- [ ] It does not duplicate code, a helper or a dependency that already exists.
- [ ] Public interfaces (APIs, CLI flags, file formats, schemas) change only on purpose, with a migration path.
- [ ] The change is easy to roll back, or the description says how to roll back.

## 3. Correctness and failure paths

- [ ] Edge cases: empty, one, many, maximum, duplicates, unicode, time zones, negative, missing.
- [ ] Errors are handled where they occur, not swallowed. Error messages help the user.
- [ ] No resource leaks; resources are bounded and released: memory, file handles, connections, locks, caches,
      queues.
- [ ] Concurrency: shared state, ordering, races, retries, idempotency, timeouts.
- [ ] Data: migrations are safe to run on real data and to run twice; old and new versions can run at the same time
      during a deploy.
- [ ] Backward compatibility for stored data, config and callers.
- [ ] Performance: no new work in a hot path that grows with input size without a reason.

## 4. Tests

- [ ] A test covers the main behavior change and would fail without the change.
- [ ] Tests check behavior, not the implementation line by line. They are not tautological (they do not assert what
      they just set up).
- [ ] Mocks do not hide the behavior under test.
- [ ] Changed or deleted test expectations have a reason in the PR.
- [ ] Error paths and edge cases from section 3 have tests where the risk is high.
- [ ] The author shows that they ran the changed behavior directly, not only the test suite.

## 5. Security and privacy

- [ ] Untrusted input is validated where it enters. No injection (SQL, shell, path, template, HTML).
- [ ] Authorization is checked on each path, not only in the UI. It fails closed.
- [ ] No secrets, tokens or private data in code, logs, tests, fixtures or error messages.
- [ ] Session, credential and key handling is correct, if touched.
- [ ] New dependencies are needed, maintained and pinned as the repo requires.
- [ ] If the change touches authentication, credentials, cryptography or a sandbox: say that a specialist security
      review is needed.

## 6. Readability and docs

- [ ] Names say what things are and do.
- [ ] Functions are short enough to understand; complexity has a reason.
- [ ] Comments explain why, not what. No commented-out code.
- [ ] Docs, README, CHANGELOG and ADRs are updated where the repo requires it.

## 7. Nits

- [ ] Small style points are `nitpick (non-blocking)` at most.
- [ ] A nit that occurs many times is one finding that asks for a tool or a style rule.
