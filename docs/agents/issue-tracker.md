# Issue Tracker

This repository uses **GitHub Issues** to track work.

## Commands

Skills use the `gh` CLI to interact with issues:

- `gh issue list` - list open issues
- `gh issue view <number>` - view issue details  
- `gh issue create` - create new issue
- `gh issue edit <number>` - update existing issue
- `gh issue close <number>` - close an issue

## Prerequisites

1. This repository must be pushed to GitHub
2. The `gh` CLI must be installed and authenticated
3. Run `gh auth login` if not already authenticated

## Workflow

When skills like `to-tickets` or `triage` run, they will:
- Read issues via `gh issue list --json`
- Create issues via `gh issue create`
- Update labels and status via `gh issue edit`

## PRs as a request surface

**Disabled.** External pull requests are not automatically added to the triage queue.

If you want to treat incoming PRs as triage items, edit this file and enable that behavior.
