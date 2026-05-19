# OpenViking Memory Policy

This backend is session-commit based.

Rules:
- Passive write is the primary path. At the end of each turn, the runtime will append the user/assistant messages into the OpenViking session and commit it.
- Passive retrieve is the primary read path. At the start of each turn, the runtime may search `viking://user/default/memories`.
- Do not rely on `mem_set` for this backend. OpenViking does not expose a stable direct CRUD memory API in this integration.
- If a memory result is returned, treat the memory file content as the authoritative long-term memory text.

What this backend tends to store:
- `profile`
- `preferences`
- `entities`
- `events`

Practical implication:
- This backend is better at passive memory formation and passive retrieval than explicit manual memory editing.
