# skills

Agent skills (Claude Code / Agent Skills format). Each folder is one skill.

| Skill | What it does |
| --- | --- |
| [pr-review](pr-review/SKILL.md) | Author, review and answer review on pull requests, with a checklist, comment labels, a verdict format and a PR template, each rule traced to sources. |
| [github-org-setup](github-org-setup/SKILL.md) | Audit and harden a GitHub Free or Team organization and its repositories against a baseline from the GitHub docs and OpenSSF Scorecard. Shows free vs paid items, asks for opt-in with live prices, and applies only approved changes. |

## Install

Clone the repo, then link a skill into your personal skills folder (or into `.claude/skills/` of one project):

```sh
git clone https://github.com/juanheyns/skills.git ~/src/skills
mkdir -p ~/.claude/skills
ln -s ~/src/skills/pr-review ~/.claude/skills/pr-review
ln -s ~/src/skills/github-org-setup ~/.claude/skills/github-org-setup
```

Claude Code finds the skill by its description. You can also call it by name: `/pr-review`.
