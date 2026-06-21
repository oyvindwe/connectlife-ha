# AGENTS.md

Guidance for AI coding agents working in this repository. See `CLAUDE.md` for
architecture and commands.

## Git and pull requests

- **Don't amend, drop, or squash commits on an open PR.** Once a branch has an
  open pull request, only add new commits — never rewrite its history with
  `git commit --amend`, `git rebase`, `git reset`, or a force-push. Rewriting a
  pushed PR branch loses review context and can leave CI running against a stale
  merge ref.
- Don't `git push` until the user explicitly asks for it.
