# Sources for each rule

Each rule in SKILL.md and the other reference files has an ID. This file gives the evidence for each one. The keys
(`P01`–`P34` before 2023, `A01`–`A18` for 2024–2026) come from a literature review on code review best practices
(stage 1 report, research cutoff 2026-10-23). The full list of sources is at the end of this file.

**Basis** says how strong the support is:

- **D**: documented. A source in the list recommends it. This does not make it proven: most sources are guides,
  case studies and correlations, not experiments.
- **I**: the review's own inference from several sources.
- **U**: the review found the question unresolved; the skill had to choose.
- **S**: taken from an existing agent review loop that this skill must fit (supervisor practice, not a published
  source).
- **J**: my judgment ("I guess"). No source supports the exact rule.

Many sources share an origin (P05/P06, P09/P10, P12–P14, P15→P16), so a long key list is not the same as many
independent votes.

## Rules for all modes

| ID | Rule | Keys | Basis |
| --- | --- | --- | --- |
| G1 | The repo's own rules come first | P31 (team and language guidance), P13/P23 (style guides), P20 (adapt labels to the team) | D; J that the repo wins over this skill |
| G2 | Check each claim; `path:line`; "I guess" when not checked | A12 (evidence that it works), A14 (passing tests is not merge readiness), agent-era inference (findings are useful only if trustworthy) | I, S |
| G3 | Do not merge or approve unless told to; a human owner decides | P16 (reviewer and maintainer roles are separate), P14 (separate approval duties), P31 (no self-approval), P09 (self-approved changes are a warning signal); A13 and P32 disagree with a universal gate | D, U (safety of unattended merging); J for the side taken |
| G4 | Post nothing unless told to | — | S, J |
| G5 | Discuss code, not the person; ask, explain, no hyperbole | P03, P13, P15, P20, P23, P24, P25, P29 | D |
| G6 | No AI taglines; keep the repo's commit email | A01 (judge the code on its merits, not presumed authorship) | S, J |

## Author

| ID | Rule | Keys | Basis |
| --- | --- | --- | --- |
| AU1 | One purpose; refactors separate from behavior changes | P13, P17, P21, P28 | D |
| AU2 | Aim under ~200 changed lines, split or explain over ~400 | P06 (Cisco: under 200, max 400, context-specific), P21 (conceptual completeness), P11 (more files, fewer useful comments), P34 (size affects perceived quality), P27, P31 | D; U (no universal ceiling); J for using Cisco as a signal only |
| AU3 | Stack large work; say the merge order | P21, P22, P28, A16; the review's inference to link stacked dependencies | D, I |
| AU4 | Ask early about design; do not wait for perfection | P03 (preparation must not delay early feedback), P32 (discuss design early), A01 (prior design discussion) | D |
| AU5 | Do what the task asks and nothing more | P13, P23 (respect scope) | D, S |
| AU6 | Prove it works: run, exercise directly, regression test | A12, A14, P28 (self-test), P04 (combine review with testing) | D |
| AU7 | Self-review the diff; understand every line, also generated ones | P06, P28, P18; A06 and A12 (accountable author); caveat in P06 that annotations can reduce reviewer scrutiny | D |
| AU8 | Tools do formatting, lint and type checks | P13, P23, P24, P28, P31 | D |
| AU9 | Description: what, why, approach, tests, risk; screenshots for UI | P13, P17, P27, P29, P05/P06 (annotate changes), P07 (understanding is the bottleneck) | D; template layout J |
| AU10 | Point to the risk; notes are not proof | the review's inference to flag risk explicitly; P06 (annotation is not proof of correctness) | I, D |
| AU11 | Ask the owner or a person who knows the files; security specialist | P10, P11 (file familiarity), P12, P14, P25, P30, P19 | D |
| AU12 | CI green before "ready"; else local tests, and say so | P15 (sign-off and green CI), P31 (passing checks) | D, S |

## Reviewer

| ID | Rule | Keys | Basis |
| --- | --- | --- | --- |
| RV1 | A different session from the author; no claim of independence | A04 (agent-to-agent review is an anecdote, not proof); agent-era inference (separate agents do not by themselves give independent failure modes) | I, S |
| RV2 | Collect the inputs, read code around the hunks, run tests if possible; `path:line` at the head sha | P07 (understanding), P24 (larger-system fit), P26 | D, S; head-sha rule J (from the self-test) |
| RV3 | Understand before judging; unclear change is a finding | P07, P13 | D; J for "first finding" |
| RV4 | Order: intent, design, correctness, tests, security, readability, polish | P23 (design before polish, the only ordering claim), P13, P14, P26, P28 (what to inspect), P19, P26 (security, privacy, threading, resources) | D for the items and "large first"; J for the exact order |
| RV5 | Five parts per finding: label, decoration, `path:line`, what and why, fix | P20 (labels and decorations, explain the next step), P13 (explain comments), P15 (actionable), P01 (record defects) | D; format S |
| RV6 | What blocking means; a preference never blocks; when a real defect can be non-blocking | P13 (non-blocking nits), P24 (identify blocking issues), P28 (required vs suggestion), P20 | D; definition and the three conditions J |
| RV7 | Verify each finding; drop what you cannot support | agent-era inference (evaluate false positives and trust), A02 (AI review noise), A03 (verbose AI reviews) | I, S |
| RV8 | All blocking findings in round 1 | P16 (reduce avoidable iterations) | D, J |
| RV9 | At most 5 non-blocking findings; nothing CI already says | A02, A03 (noise, verbosity), P23, P24 (recurring nits are a tooling problem) | D; the number 5 is J |
| RV10 | Do not demand perfection | P13, P23 | D |
| RV11 | Explain the principle; praise only when specific and true | P07, P12, P14, P24 (knowledge sharing), P20 (sincere praise), P11 (narrow "useful comment" measure) | D; J for one praise line |
| RV12 | Do not fix the code yourself unless told to | A15 (wants reviewer agents to make fixes; rejected), A12 (author stays accountable) | J |
| RV13 | Verdict line: `Review round <n>: PASS` or `CHANGES NEEDED`; an unreviewable material part is a blocking `question`; green CI stands in for running tests | P02 (document findings, exit conditions), P13 (a response is not an approval), P15 and P31 (green CI) | S, J |
| RV14 | Same reviewer next round; check open findings, then the new diff | P01, P03 (follow up rework), P04 (verify corrections) | D, S |
| RV15 | No new nits on unchanged code in later rounds | P16, P13, P23 | J |
| RV16 | A good "not fixed because" closes a finding | P15 (opinion vs principle), P25 (bring to a resolution) | D, J |
| RV17 | Stop after 3 rounds; send open findings to the human | P24 (take long disagreements to a conversation), P25; no source gives a round limit | S, J |
| RV18 | In a stack, review this PR's diff against its base only | P21, P22 (stacked changes have dependencies; review each on its own) | D, J |

## Responder

| ID | Rule | Keys | Basis |
| --- | --- | --- | --- |
| RE1 | Read all findings first; ask when unclear | P29 (acknowledge feedback, ask for clarification) | D |
| RE2 | Verify each finding; reviewers can be wrong | agent-era inference (false positives), A02, P33 (some feedback is discarded) | I, J |
| RE3 | Answer every finding: fixed, or why not, with a reason | P15, P17, P18 (respond to feedback) | D, S |
| RE4 | Fix in new commits; run tests again | P18 (revise patches clearly) | D, J |
| RE5 | No unrelated changes in a fix round | P13, P17 (one logical change) | D, J |
| RE6 | `Fixes for review round <n>:` one line per finding | — | S |
| RE7 | Disagree once with reasons, then ask the human owner | P15 (move hard exchanges to a conversation), P24 (discuss long disagreements in person) | D; J for the human owner as the tie-breaker |
| RE8 | Review is not finished at submit; do not wait for merge | P18 (submission is not completion) | D, S |

## Reference files

| ID | Rule | Keys | Basis |
| --- | --- | --- | --- |
| CL1 | Repo checklist first; add escapes to it; keep the list short | P03, P04, P19, P31 (checklists); the review's inference (update from escapes; a giant list distracts); no universal checklist | D, I, U |
| CL-items | Checklist content | P13, P14, P26, P28 (design, correctness, tests, names, complexity, docs), P19, P26 (security, privacy, resources, threading), A14, A15 (tests that pass but do not prove; tautological tests) | D |
| LB1 | Intent label plus blocking decoration | P20 | D; the five label names J |
| LB2 | Always write the decoration | the review's note that a label alone does not settle blocking policy; inference to agree semantics before automating | D, I |
| TPL | PR description template | AU9, AU10 above | D; layout J |

## Source list

Pre-2023 sources:

| Key | Source | Author / org | Year | Type |
| --- | --- | --- | --- | --- |
| P01 | [Design and Code Inspections to Reduce Errors in Program Development](https://doi.org/10.1147/sj.153.0182) | Michael E. Fagan, IBM | 1976 | paper |
| P02 | [IEEE Std 1028-2008, Software Reviews and Audits](https://doi.org/10.1109/IEEESTD.2008.4601584) | IEEE | 2008 | standard |
| P03 | [Peer Reviews in Software: A Practical Guide](https://www.informit.com/store/peer-reviews-in-software-a-practical-guide-9780201734850) | Karl E. Wiegers | 2001/2002 | book |
| P04 | [Code Complete, ch. 21, Collaborative Construction](https://ptgmedia.pearsoncmg.com/images/9780735619678/samplepages/9780735619678.pdf) | Steve McConnell | 2004 | book chapter |
| P05 | [Best Kept Secrets of Peer Code Review](https://static1.smartbear.co/smartbear/media/pdfs/best-kept-secrets-of-peer-code-review_redirected.pdf) | Jason Cohen et al., SmartBear | 2006 | vendor book |
| P06 | [A Case Study at Cisco Systems](https://static1.smartbear.co/support/media/resources/cc/book/code-review-cisco-case-study.pdf) | Cohen, SmartBear and Cisco | 2006 | book chapter |
| P07 | [Expectations, Outcomes, and Challenges of Modern Code Review](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/ICSE202013-codereview.pdf) | Bacchelli, Bird | 2013 | paper |
| P08 | [Convergent Contemporary Software Peer Review Practices](https://cabird.com/pdfs/rigby2013convergent.pdf) | Rigby, Bird | 2013 | paper |
| P09 | [The Impact of Code Review Coverage and Participation on Software Quality](https://rebels.cs.uwaterloo.ca/papers/msr2014_mcintosh.pdf) | McIntosh et al. | 2014 | paper |
| P10 | [An Empirical Study of the Impact of Modern Code Review Practices on Software Quality](https://rebels.cs.uwaterloo.ca/papers/emse2016_mcintosh.pdf) | McIntosh et al. | 2016 | paper |
| P11 | [Characteristics of Useful Code Reviews](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/bosu2015useful.pdf) | Bosu, Greiler, Bird | 2015 | paper |
| P12 | [Modern Code Review: A Case Study at Google](https://sback.it/publications/icse2018seip.pdf) | Sadowski et al. | 2018 | paper |
| P13 | [Code Review Developer Guide](https://google.github.io/eng-practices/review/) | Google | 2019 | company guide |
| P14 | [Software Engineering at Google, ch. 9, Code Review](https://abseil.io/resources/swe-book/html/ch09.html) | Manshreck, Sadowski | 2020 | book chapter |
| P15 | [Code Review guide](https://github.com/thoughtbot/guides/tree/main/code-review) | thoughtbot | 2013 | company guide |
| P16 | [Code Review Guidelines](https://docs.gitlab.com/ee/development/code_review.html) | GitLab | 2016 | company guide |
| P17 | [Submitting Patches](https://www.kernel.org/doc/html/latest/process/submitting-patches.html) | Linux kernel community | by 2005 | project guide |
| P18 | [Posting Patches](https://www.kernel.org/doc/html/latest/process/5.Posting.html) | Jonathan Corbet, Linux kernel | 2008 | project guide |
| P19 | [OWASP Code Review Guide v2](https://owasp.org/www-pdf-archive/OWASP_Code_Review_Guide_v2.pdf) | OWASP | 2017 | guide |
| P20 | [Conventional Comments](https://conventionalcomments.org/) | Paul Slaughter | 2020 | practitioner spec |
| P21 | [Writing Reviewable Code](https://secure.phabricator.com/book/phabflavor/article/writing_reviewable_code/) | Evan Priestley, Phabricator | by 2012 | tool guide |
| P22 | [Stacked Changes](https://web.archive.org/web/20211117165405/https://graphite.dev/blog/post/DThX8ffP1gmxWJChEv0y) | Graphite | 2021 | vendor blog |
| P23 | [How to Do Code Reviews Like a Human](https://mtlynch.io/human-code-reviews-1/) | Michael Lynch | 2017 | blog |
| P24 | [Good Code Reviews, Better Code Reviews](https://blog.pragmaticengineer.com/good-code-reviews-better-code-reviews/) | Gergely Orosz | 2019 | blog |
| P25 | [Code Reviews / Respectful Code Reviews](https://chromium.googlesource.com/chromium/src/+/main/docs/code_reviews.md) | Chromium | 2017 | project guide |
| P26 | [Reviewer Checklist](https://firefox-source-docs.mozilla.org/contributing/reviewer_checklist.html) | Mozilla | 2014 | project guide |
| P27 | [The (Written) Unwritten Guide to Pull Requests](https://www.atlassian.com/blog/git/written-unwritten-guide-pull-requests) | Atlassian | 2016 | vendor blog |
| P28 | [Code Review Best Practices](https://blog.palantir.com/code-review-best-practices-19e02780015f) | Robert Fink, Palantir | 2018 | company blog |
| P29 | [How to Write the Perfect Pull Request](https://github.blog/2015-01-21-how-to-write-the-perfect-pull-request/) | Keavy McMinn, GitHub | 2015 | company blog |
| P30 | [Introducing Code Owners](https://github.blog/2017-07-06-introducing-code-owners/) | GitHub | 2017 | product post |
| P31 | [Code with Engineering Playbook: Code Reviews](https://microsoft.github.io/code-with-engineering-playbook/code-reviews/) | Microsoft CSE | 2018/2020 | company guide |
| P32 | [Ship / Show / Ask](https://martinfowler.com/articles/ship-show-ask.html) | Rouan Wilsenach | 2021 | essay |
| P33 | [Modern Code Reviews in Open-Source Projects: Which Problems Do They Fix?](https://inventitech.com/assets/publications/2014_beller_bacchelli_zaidman_juergens_modern_code_reviews_in_open-source_projects_which_problems_do_they_fix.pdf) | Beller et al. | 2014 | paper |
| P34 | [Code Review Quality: How Developers See It](https://olgabaysal.com/pdf/Kononenko_ICSE2016.pdf) | Kononenko, Baysal, Godfrey | 2016 | paper |

Agent-era sources (2024–2026; trends and opinions, not established practice):

| Key | Source | Author / org | Date | Type |
| --- | --- | --- | --- | --- |
| A01 | [Reviewing 2000 Line AI Slop Pull Request](https://www.reddit.com/r/ExperiencedDevs/comments/1osyyci/reviewing_2000_line_ai_slop_pull_request/) | r/ExperiencedDevs | 2025-11-09 | forum thread |
| A02 | [Why AI Will Never Replace Human Code Review](https://www.reddit.com/r/programming/comments/1je6zti/why_ai_will_never_replace_human_code_review/) | r/programming | 2025-03-18 | forum thread |
| A03 | [My Feedback on 6 Months Full AI Development](https://www.reddit.com/r/cscareerquestions/comments/1x5oa0d/my_feedback_on_6_months_full_ai_development/) | r/cscareerquestions | 2026-10-14 | forum thread |
| A04 | [How You Review Code?](https://www.reddit.com/r/ClaudeAI/comments/1mj7k1o/how_you_review_code/) | r/ClaudeAI | 2025-08-06 | forum thread |
| A05 | [Open Source AI Code Review Agent That's Aware of Your Entire Codebase](https://www.reddit.com/r/ChatGPTCoding/comments/1kl6jw5/open_source_ai_code_review_agent_thats_aware_of/) | r/ChatGPTCoding (vendor) | 2025-05-12 | forum thread |
| A06 | [Ask HN: Teams Using AI — How Do You Prevent It from Breaking Your Codebase?](https://news.ycombinator.com/item?id=42701745) | Hacker News | 2025-01-14 | forum thread |
| A07 | [Copilot Code Review Now Generally Available](https://github.blog/changelog/2025-04-04-copilot-code-review-now-generally-available/) | GitHub | 2025-04-04 | vendor changelog |
| A08 | [Graphite Raises $52M and Launches Diamond](https://graphite.dev/blog/series-b-diamond-launch) | Graphite | 2025-03-17 | vendor post |
| A09 | [State of AI vs Human Code Generation Report](https://www.coderabbit.ai/blog/state-of-ai-vs-human-code-generation-report) | CodeRabbit | 2025-12-17 | vendor report |
| A10 | [Highlights from the 10th DORA Report](https://cloud.google.com/blog/products/devops-sre/announcing-the-2024-dora-report) | Google Cloud DORA | 2024-10-22 | observational |
| A11 | [Announcing the 2025 DORA Report](https://cloud.google.com/blog/products/ai-machine-learning/announcing-the-2025-dora-report) | Google Cloud DORA | 2025-09-23 | observational |
| A12 | [Your Job Is to Deliver Code You Have Proven to Work](https://simonwillison.net/2025/dec/18/code-proven-to-work/) | Simon Willison | 2025-12-18 | essay |
| A13 | [Harness Engineering: Leveraging Codex in an Agent-first World](https://openai.com/index/harness-engineering/) | OpenAI | 2026-02-11 | vendor case report |
| A14 | [Many SWE-bench-Passing PRs Would Not Be Merged into Main](https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/) | METR | 2026-03-10 | research note |
| A15 | [Fixing the PR Bottleneck](https://www.youtube.com/watch?v=LlgiOCmFG_w) | Matt Pocock | 2026-09-25 | talk |
| A16 | [If Code Generation Is Solved What's Next?](https://www.youtube.com/watch?v=VeRQuEmLTUM) | Greg Foster, Graphite | 2025-09-24 | talk (vendor) |
| A17 | [The AI Productivity Paradox Report 2025](https://www.faros.ai/blog/ai-software-engineering) | Faros | 2025-07 | vendor observational |
| A18 | [Ignore the Slop](https://daniel.haxx.se/blog/2026/10/22/ignore-the-slop/) | Daniel Stenberg | 2026-10-22 | maintainer blog |
