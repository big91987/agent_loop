# Memory Policy: v6.3 simplemem

You have passive memory support and active tools: `mem_get`, `mem_set`, `mem_update`, `mem_delete`.

Passive behavior:
- The runtime may retrieve memories before your answer.
- The runtime may also store durable memory candidates after the turn.
- Passive write should keep memories atomic: one memory record = one memory point.

Active behavior:
- Use `mem_get` when you need targeted recall or want to verify a specific detail.
- Use `mem_set` when a durable fact, preference, profile fact, episode, procedure, or todo is clearly worth remembering.
- Use `mem_update` when new information refines an existing memory.
- Use `mem_delete` when the user explicitly invalidates a memory.

Storage policy:
- Memory artifacts live inside the current workspace.
- Do not read/write memory artifact files through generic file tools.
- Always use memory tools for active memory operations.

Time policy:
- Resolve relative time expressions like "yesterday", "today", "tomorrow" using the current time and timezone from system prompt.
- Prefer absolute dates in `occurred_at`.

Atomic examples:
- Good: `episode = "User fell and injured knee."`
- Good: `todo = "User plans to visit hospital for knee check."`
- Bad: `episode = "User fell, knee hurt, and plans to visit hospital."`
