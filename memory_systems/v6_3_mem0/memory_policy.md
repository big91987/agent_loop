# Memory Policy: v6.3 mem0

You have passive memory support and active tools: `mem_get`, `mem_set`, `mem_update`, `mem_delete`.

Passive behavior:
- The runtime may extract memory actions after a turn: add, update, or delete.
- Focus on durable facts, preferences, profile facts, episodes, and todos.
- Keep each record concise and self-contained.

Active behavior:
- Use `mem_get` for explicit recall.
- Use `mem_set` for new durable memories.
- Use `mem_update` when the user corrects or refines an existing memory.
- Use `mem_delete` when a memory becomes invalid.

Storage policy:
- Memory artifacts and action logs live inside the current workspace.
- Do not manipulate memory artifact files with generic file tools.
- Use memory tools instead.

Time policy:
- Use current time and timezone from system prompt to normalize relative dates.
- Prefer storing explicit `occurred_at` for episodes and todos when known.

Action examples:
- Add: `profile = "User is 80 years old."`
- Add: `episode = "User fell and injured knee."`
- Add: `todo = "User plans to visit hospital for knee check."`
- Update: replace stale preference with the latest explicit user statement.
