<!-- loopx:armed {"goal_id": "cc-ideaprojects", "agent_id": "cc"} -->
loopx tick — advance goal `cc-ideaprojects` (agent `cc`). Use the wired loopx MCP
tools; do NOT run `loopx --help` or guess ids.

1. Call `should_run()`. If should_run=false, say why in ONE line and STOP this
   iteration (do nothing else) — loopx has paused, gated, or converged.
2. If should_run=true: `claim_task` the next open todo, do ONE bounded segment,
   then VERIFY it with a real check (build/test) — never claim success from
   reasoning — and `complete_task(..., agent_id="cc", evidence="<ran + result>")`.
3. Stay within the goal's scope; do not start initiatives outside the todos.
   Irreversible actions (push/delete) only to finish work already authorized.
4. Re-check `should_run()`; stop when should_run=false or no open todos remain.
