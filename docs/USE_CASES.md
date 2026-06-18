# mypeople — use cases and orchestration examples

This document shows concrete ways to use mypeople. All examples assume the queue server is running and `mp` is installed.

## 1. Parallel workstreams

Run three independent tasks on the same codebase without losing context.

```bash
mp spawn pedro/app:tests --cwd ./my-app
mp spawn pedro/app:refactor --cwd ./my-app
mp spawn pedro/app:docs --cwd ./my-app

mp send pedro/app:tests "Write unit tests for the auth module"
mp send pedro/app:refactor "Refactor user.service.ts to use dependency injection"
mp send pedro/app:docs "Update README with the new login flow"

mp status
mp peek pedro/app:tests
```

## 2. Boss-coordinated feature

Use the Boss to plan and dispatch workers.

```bash
# Start the Boss (in another terminal) and open it in Brave.
mp spawn pedro/feature:Boss --cwd ./my-app --master

# Spawn workers that report to the Boss.
mp spawn pedro/feature:explore --cwd ./my-app --boss pedro/feature:Boss
mp spawn pedro/feature:coder --cwd ./my-app --boss pedro/feature:Boss

# The Boss can now dispatch work:
# mp send pedro/feature:explore "Explore how OAuth is currently handled"
# mp send pedro/feature:coder "Wait for the explore summary, then implement the OAuth route"
```

In the Boss chat:

> "Add OAuth login with Google. Explore first, then code."

The Boss will:
1. Write `plans/oauth/PLAN.md`.
2. Ask for your approval.
3. Send prompts to `pedro/feature:explore` and `pedro/feature:coder`.
4. Notify you when done.

## 3. Fire-and-forget background task

Send a long prompt and check the dashboard later.

```bash
mp spawn pedro/background:analyze --cwd ./my-app
mp send pedro/background:analyze "Read every file in src/ and summarize the architecture in /tmp/architecture.md"
# Go do something else; watch http://<wsl-ip>:9900/dashboard
mp peek pedro/background:analyze
mp kill pedro/background:analyze
```

## 4. Exploit / coder split

A classic split for uncertain work.

```bash
mp spawn pedro/task:explore --cwd ./my-app
mp send pedro/task:explore "Find where rate limiting is implemented and report back"
mp peek pedro/task:explore

mp spawn pedro/task:coder --cwd ./my-app
mp send pedro/task:coder "Based on the explore summary, add Redis rate limiting"
```

## 5. Reusable worker pool

Keep a pool of idle workers and reuse them.

```bash
for i in 1 2 3; do
  mp spawn pedro/pool:w$i --cwd ./my-app
done

mp send pedro/pool:w1 "Task A"
mp send pedro/pool:w2 "Task B"
mp send pedro/pool:w3 "Task C"

mp status
```

## 6. Boss loop example

A realistic Boss interaction:

```text
CEO: "We need to add a /health endpoint."
Boss: "I'll write a plan."
[Boss writes plans/health/PLAN.md]
Boss: "Approve with 'go' when ready."
CEO: "go"
Boss: [spawns coder] [sends prompt] [waits for Stop hook]
Boss: "Done. The endpoint is at src/routes/health.ts with a test."
```

## Patterns to avoid

- Do not spawn workers without a clear deliverable.
- Do not have two workers edit the same file at the same time.
- Do not bypass `mp` and poke at Kimi sessions directly.
