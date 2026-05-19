# mypeople — engineer's handbook

You're reading this because you're about to work on mypeople. **Read this first.** It is short.

## The product

mypeople is the v2 of tmux-boss — a small, opinionated runtime for orchestrating Claude Code agents across one or many machines via an HTTP queue. Per-host queue-client + central queue-server + per-spawn `tmux-boss-hooks` plugin. Everything goes through the queue; agents never bypass to raw tmux. See `plans/features.md` for the 12 capabilities and `plans/seed-plan.html` for the phased build.

## The doctrine you must internalize

We ship via **seeds** (`seeds/*.seed.md`) that one-shot the install into a fresh Debian-12 container with claude already present. The seed is the artifact; the running system is the proof. A seed without a passing `## Verify` from a brand-new container is a **draft**, not a release.

This project follows seedlab's *beloved engineer* doctrine — **read `~/workspace/seedlab/README.md` if you haven't.** TL;DR: trust the pane (the actually-rendered terminal), not the agent's self-report. Hold writer + operator + verifier in one head so the loop closes in five minutes.

## The development cycle (NON-NEGOTIABLE)

```
   ┌───── Idea (the next capability you're adding) ─────┐
   │                                                    │
   ▼                                                    │
  Write/extend the seed                                 │
   │                                                    │
   ▼                                                    │
  Paste into a CLEAN container, run it                  │
   │                                                    │
   ▼                                                    │
  Watch what breaks ← it WILL break.                    │
   │   (the seed doesn't know about every host quirk;   │
   │    the implementation surfaces them)               │
   ▼                                                    │
  Fold the findings BACK into the seed text             │
   │   (heredocs, Steps, Verify, Failure modes —        │
   │    whatever the bug was, encode the fix)           │
   ▼                                                    │
  Cleanup → CLEAN container → re-paste → re-verify ─────┘
```

You exit the loop when a **brand-new container** pastes-and-Verifies the seed with **zero ad-hoc fixes**. Only then is the seed done. Only then do you start the next seed.

## What this means in practice

- **Do not skip the "paste into a clean container" step.** A seed that "works in my dev box" is a draft.
- **Do not trust the agent's `SEED_RESULT=DONE`.** Always run `## Verify` from an independent shell (`docker exec` works) — the agent's exit code from inside its own session is suspect; the pane is the truth.
- **Every bug the implementation surfaces is a spec bug.** If claude inside the container had to patch `~/.claude.json` to make trust work, that patch belongs in the seed's Steps. If verify needed a longer wait because of an auto-update probe, that wait goes in the seed's queue-client. You don't get to leave bugs implicit "for the next person to figure out."
- **Never `git clone` mypeople from inside the container.** All custom code is inlined as heredocs in the seed. Paste-into-claude IS the install.

## Where the learnings live

| Kind of learning | Lives in |
|---|---|
| Per-seed bug / spec gap (e.g. `procps` missing, trust-dialog blocks spawn) | The seed's Steps / Failure modes / inlined code. The seed is self-documenting. |
| Container auth quirks (credentials.json vs claude.json, snapshot capture) | `~/workspace/seedlab/test-fresh/AUTH-FLOW.md` |
| Boss agent behavior (plan-gate, autonomous loop, fire-and-forget) | `plans/boss-claude.md` |
| Architectural decisions / identity scheme / what's in vs out | `plans/features.md`, `plans/capabilities.md` |
| Phased build plan | `plans/seed-plan.html` |
| **This document** | `CLAUDE.md` (the process itself) |

## Hard rules

1. **A seed is done only when a clean container one-shots it.** No exceptions for "almost works."
2. **The agent's transcript is not evidence.** `docker exec` into a separate shell and prove via Verify.
3. **Fold every finding back into the seed.** Do not let the next engineer rediscover the same bug.
4. **Read this doc before working on a seed.** If you skipped it, go back.

Do not start the next seed until the current one passes its Verify from a brand-new container. The shape of the cycle is not optional.
