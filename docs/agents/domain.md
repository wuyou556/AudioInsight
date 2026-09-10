# Domain Documentation

This repository uses a **single-context** layout for domain documentation.

## Structure

- **`CONTEXT.md`** (repo root) - Core domain knowledge, business context, architectural overview, and key concepts that agents should understand before working on this codebase.

- **`docs/adr/`** - Architecture Decision Records (ADRs). Each ADR documents a significant architectural decision, its context, considered alternatives, and rationale.

## Consumer rules

When an agent works on this repository:

1. **Read `CONTEXT.md` first** - Understand the domain, key concepts, and architectural patterns before making changes.

2. **Check relevant ADRs** - If working in an area covered by an ADR, read it to understand the decision history and constraints.

3. **Propose new ADRs** - For significant architectural changes, suggest creating a new ADR to document the decision.

4. **Keep docs updated** - If you discover that `CONTEXT.md` or an ADR is outdated, update it or flag it for review.

## ADR Format

ADRs should follow a standard format:
- Title: "ADR-NNN: [Decision Title]"
- Status: Proposed | Accepted | Deprecated | Superseded
- Context: What is the issue we're addressing?
- Decision: What did we decide?
- Consequences: What are the positive and negative outcomes?
