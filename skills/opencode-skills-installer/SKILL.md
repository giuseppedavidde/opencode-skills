---
name: opencode-skills-installer
description: >
  Use when adding, creating, installing, or syncing opencode skills. Manages
  the opencode-skills GitHub repo where all skills live. Triggers: 'add a skill',
  'install skill', 'create skill', 'new skill', 'sync skills', 'update skills',
  'installare una skill', 'nuova skill', 'aggiungi skill', 'crea skill'.
orchestrator:
  parallel: false
---

# Opencode Skills Installer

This skill manages the central `opencode-skills` repository where all opencode
skills are stored and version-controlled.

## Repository Location

```
/home/giuseppe/Progetti/Github/opencode-skills/
```

## Symlink Setup

The global opencode config and skills directory are symlinked to this repo:

```
~/.config/opencode/opencode.json  →  opencode-skills/config/opencode.json
~/.config/opencode/skills/        →  opencode-skills/skills/
```

This means any change to the repo is immediately reflected in opencode
(no copy needed). After modifying skills, commit and push to sync across PCs.

## Adding a New Skill

When asked to create or install a new skill:

1. **Create the skill directory** inside the repo:
   ```
   opencode-skills/skills/<skill-name>/SKILL.md
   ```

2. **Follow the standard SKILL.md format**:
   ```markdown
   ---
   name: <skill-name>
   description: >
     One sentence covering what this skill does AND when to trigger it.
     Front-load the literal keywords the user is likely to say.
   ---

   # <Skill Name>

   (skill body in markdown: instructions, examples, references)
   ```

   - `name` is required, lowercase hyphen-separated, up to 64 chars, matches folder name
   - `description` is effectively required. Cover both **what** the skill does
     and **when** to use it. Front-load concrete trigger keywords.
     Use "Use ONLY when..." if the skill should stay quiet on adjacent topics.

3. **Copy any bundled files** (scripts, references, templates) into the same
   skill directory.

4. **Verify the skill is picked up** by opencode — after a restart it should
   appear in the available skills list.

## Removing or Disabling a Skill

- To remove: delete the skill directory from the repo.
- To disable without deleting: add `"disable": true` or mark it in
  `opencode.json` agent config.

## Cross-PC Sync Workflow

Since the repo is cloned on multiple machines:

1. Add/update skills locally → they work immediately via symlink
2. Commit and push to GitHub
3. On other machines: `git pull` in the repo
4. Restart opencode — skills are live
