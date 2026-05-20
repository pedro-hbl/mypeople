# Smoke test — 30s

Paste this whole block into the Boss's claude pane:

---

Spawn two engineers (`--boss yourself`, `--cwd /tmp`): eng-a, eng-b. Wait for each [AGENT NOTIFICATION] before sending the next message.

1. send eng-a: "reply with exactly: PING-A"
2. send eng-b: "reply with exactly: PING-B"
3. After both notifications arrive, report: "eng-a said: <reply>; eng-b said: <reply>". Verify both replies contain their expected marker.
4. kill eng-a and eng-b.

PASS if both markers came back correctly and engineers are killed cleanly.
