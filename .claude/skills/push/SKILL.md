---
name: push
description: Stage all changes, create a commit with a descriptive message, and push to the main branch of https://github.com/APERF/cEDH_Simulator.
---

Commit all current changes and push to the remote repo. Follow these steps:

## 1. Gather context (run all three in parallel)

- `git status` — see what's changed and untracked
- `git diff HEAD` — see the full diff of all changes
- `git log --oneline -5` — see recent commit messages to match style

## 2. Stage everything

```
git add -A
```

Exclude any files that look like secrets (`.env`, `credentials.*`, `*.key`) — warn the user if any are present instead of staging them.

## 3. Draft a commit message

- One short subject line (≤72 chars) in imperative mood, e.g. `feat: add land-drop thinking timer`
- Summarise the *why*, not the *what*
- Match the style of recent commits shown in step 1

## 4. Commit

Use a HEREDOC so the message is passed cleanly:

```powershell
git commit -m "$(cat <<'EOF'
<your message here>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

On PowerShell (Windows) use a here-string instead:
```powershell
git commit -m @'
<your message here>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
'@
```

## 5. Push

```
git push origin main
```

## 6. Report

- On success: show the commit hash and "Pushed to https://github.com/APERF/cEDH_Simulator"
- On failure: show the error output and suggest what to fix (merge conflict, auth issue, etc.)
