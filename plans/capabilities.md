# mypeople — capabilities (testable spec, v2 Kimi)

Each capability defines Action, observable truth, and a deterministic test.

## Architectural constraint — global identity

Every agent id is `<host>/<session>:<tab>`. Short form `<session>:<tab>` is canonicalized with `hostname`.

## 1. spawn

| | |
|---|---|
| **Action** | `mp spawn <host>/<session>:<tab> --cwd <path>` |
| **Pane truth** | HTTP `/agents` lists the new agent with `state: idle` and a `session_id`. |
| **Test** | `mp spawn $(hostname)/test:w1 --cwd /tmp`<br>`curl -sf -H "X-Queue-Secret: $SECRET" http://127.0.0.1:9900/agents \| jq -e '.[] \| select(.agent_id=="'$(hostname)'/test:w1")'`<br>`curl -sf -H "X-Queue-Secret: $SECRET" http://127.0.0.1:9900/agents \| jq -e '.[] \| select(.agent_id=="'$(hostname)'/test:w1" and .state=="idle")'` |

## 2. send

| | |
|---|---|
| **Action** | `mp send <host>/<session>:<tab> "<prompt>"` |
| **Pane truth** | The agent's `last_activity` updates and `state` becomes `idle` after the turn ends. |
| **Test** | `mp send $(hostname)/test:w1 "Reply HELLO"`<br>`sleep 3`<br>`curl -sf -H "X-Queue-Secret: $SECRET" http://127.0.0.1:9900/agents \| jq -e '.[] \| select(.agent_id=="'$(hostname)'/test:w1" and .state=="idle")'` |

## 3. peek

| | |
|---|---|
| **Action** | `mp peek <host>/<session>:<tab>` |
| **Pane truth** | CLI output contains `state=` and the agent's summary/history. |
| **Test** | `mp peek $(hostname)/test:w1 \| grep -E 'state=(idle\|working\|blocked\|dead)'` |

## 4. kill

| | |
|---|---|
| **Action** | `mp kill <host>/<session>:<tab>` |
| **Pane truth** | `/agents` shows the agent with `state: dead`. |
| **Test** | `mp kill $(hostname)/test:w1`<br>`curl -sf -H "X-Queue-Secret: $SECRET" http://127.0.0.1:9900/agents \| jq -e '.[] \| select(.agent_id=="'$(hostname)'/test:w1" and .state=="dead")'` |

## 5. status

| | |
|---|---|
| **Action** | `mp status` |
| **Pane truth** | Output lists every alive agent with a state token. |
| **Test** | `mp status \| grep -E "'$(hostname)'/test:w.*\[(idle\|working\|blocked\|dead)\]"` |

## 6. boss-tab

| | |
|---|---|
| **Action** | `mp spawn $(hostname)/test:Boss --master` then `mp spawn $(hostname)/test:w1 --boss $(hostname)/test:Boss` |
| **Pane truth** | When w1 finishes a turn, the Boss agent receives a prompt notification from the queue server. The Boss's history reflects the notification. |
| **Test** | `mp send $(hostname)/test:w1 "Reply PONG"`<br>`sleep 5`<br>`mp peek $(hostname)/test:Boss \| grep -q "AGENT NOTIFICATION"` |

## 7. stop-hook

| | |
|---|---|
| **Action** | Implicit — Kimi hook fires on Stop. |
| **Pane truth** | `/agents` updates `state` to `idle` and refreshes `last_activity` after the turn. |
| **Test** | `mp send $(hostname)/test:w1 "Reply PONG"`<br>`sleep 3`<br>`curl -sf -H "X-Queue-Secret: $SECRET" http://127.0.0.1:9900/agents \| jq -r '.[] \| select(.agent_id=="'$(hostname)'/test:w1") \| .state' \| grep -q idle` |

## 8. status-files

| | |
|---|---|
| **Action** | Same as stop-hook. |
| **Pane truth** | `/agents` returns objects with `agent_id`, `session_id`, `state`, `summary`, `last_activity`. |
| **Test** | `curl -sf -H "X-Queue-Secret: $SECRET" http://127.0.0.1:9900/agents \| jq -e '.[0] \| .agent_id and .session_id and .state and .summary and .last_activity'` |

## 9. hud

| | |
|---|---|
| **Action** | Open `http://<wsl-ip>:9900/dashboard` in Brave. |
| **Pane truth** | HTTP 200 + HTML lists agents with state pills. |
| **Test** | `curl -sf http://127.0.0.1:9900/dashboard \| grep -q 'mypeople dashboard'` |

## 10. browser-open

| | |
|---|---|
| **Action** | Click "Open in Kimi Web" in the HUD. |
| **Pane truth** | Link targets `http://127.0.0.1:5494?token=<secret>` (or the configured Kimi web port). |
| **Test** | `curl -sf http://127.0.0.1:9900/dashboard \| grep -q 'href=\"http://127.0.0.1:5494'` |

## 11. backend-kimi

| | |
|---|---|
| **Action** | `mp spawn $(hostname)/test:w1 --cwd /tmp` |
| **Pane truth** | Queue server process spawned `kimi acp`; an ACP session id exists for the agent. |
| **Test** | `curl -sf -H "X-Queue-Secret: $SECRET" http://127.0.0.1:9900/agents \| jq -e '.[] \| select(.agent_id=="'$(hostname)'/test:w1" and .session_id != null)'` |

## 12. cross-host (Tailscale)

| | |
|---|---|
| **Action** | (not in v2) |
| **Pane truth** | — |
| **Test** | — |
