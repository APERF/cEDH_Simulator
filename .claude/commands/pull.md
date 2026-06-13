Pull the latest changes from the remote GitHub repository (https://github.com/APERF/cEDH_Simulator) into the current branch.

Steps:
1. Run `git fetch origin` to fetch remote changes.
2. Run `git status` to show the current branch and any local changes.
3. Run `git pull origin main` to merge the latest changes from main.
4. Report what changed: how many commits were pulled, and a brief `git log --oneline` of any new commits.

If there are uncommitted local changes that would cause a conflict, warn the user and do NOT proceed with the pull — show them what's dirty and ask how to proceed.
