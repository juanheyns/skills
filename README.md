# skills

Agent skills (Claude Code / Agent Skills format). Each folder is one skill.

| Skill | What it does |
| --- | --- |
| [pr-review](pr-review/SKILL.md) | Author, review and answer review on pull requests, with a checklist, comment labels, a verdict format and a PR template, each rule traced to sources. |

## Install

Clone the repo, then link a skill into your personal skills folder (or into `.claude/skills/` of one project):

```sh
git clone https://github.com/juanheyns/skills.git ~/src/skills
mkdir -p ~/.claude/skills
ln -s ~/src/skills/pr-review ~/.claude/skills/pr-review
```

Claude Code finds the skill by its description. You can also call it by name: `/pr-review`.
