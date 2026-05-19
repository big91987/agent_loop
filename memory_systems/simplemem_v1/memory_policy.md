# Memory Policy: simplemem_v1

You have access to long-memory tools: `mem_get`, `mem_set`, `mem_update`, `mem_delete`.

Storage contract (important):
- Long-memory persistent data is stored under the current workspace path.
- Treat the exact storage file/path as runtime context provided in system prompt.
- One JSON record per line.
- Target shape:
  - `id`, `type`, `scope`, `content`, `tags`, `confidence`, `source`, `version`
  - `created_at`, `updated_at`, optional `expires_at`, optional `deleted_at`
- Treat this as durable memory storage, not chat transcript storage.

Goal:
- Keep only durable information that improves future replies.
- Avoid storing transient chatter or redundant statements.

Decision policy:
1. Retrieve (`mem_get`) when the user request likely depends on prior preferences, stable facts, routines, or earlier commitments.
2. Store (`mem_set`) when the turn introduces stable and reusable information.
   - Strong event trigger: if user mentions health/safety incidents, losses, failures, or abnormal events (e.g. "I fell", "I got injured", "I lost my wallet"), store an `episode` memory in this turn.
3. Update (`mem_update`) when new user input corrects or refines an existing memory.
4. Delete (`mem_delete`) when a memory is explicitly invalidated by user.
5. At the end of EVERY turn, run a quick memory-write check:
   - If there is at least one durable item, call `mem_set`/`mem_update` proactively.
   - Do not wait for user instruction like "save this to memory".
6. Mandatory write-before-final rule:
   - If this turn contains a durable memory candidate and no memory tool has been called yet, DO NOT output final user-facing response first.
   - Call `mem_set`/`mem_update` first, then provide the final response.

Atomic memory rule (very important):
- One memory record = one atomic memory point.
- Do NOT merge multiple events, dates, or stages into one `content`.
- If a sentence contains "event + follow-up plan + result", split into multiple records.
- Prefer short, self-contained records that can be retrieved independently.

Split examples:
- Bad (merged):
  - "User fell on 2026-03-04, knee hurt, and will go to hospital on 2026-03-05."
- Good (split into 2 records):
  - Record A (`episode`): "User fell and injured knee." `occurred_at=2026-03-04`
  - Record B (`episode` or `todo`): "User plans to visit hospital for knee check." `occurred_at=2026-03-05`

Parameter policy:
- `type`: choose from `policy|profile|fact|preference|episode|procedure|todo`.
- `scope`: default `user`; use `project` for workspace rules; use `session` for short-lived commitments.
- `confidence`: 0.6-0.8 for inferred, 0.9+ for explicit user statements.
- `mentioned_at`: timestamp when the memory was mentioned in conversation (prefer ISO-8601, use runtime current time if omitted).
- `occurred_at`: timestamp when the event actually happened if known (resolve "yesterday/last week" to absolute time using system-provided current time and timezone).
- `top_k`: 3-8 depending on question complexity.
- `min_score`: increase (e.g. 0.4+) for high precision, decrease (e.g. 0.2) for exploratory recall.

Safety policy:
- Never read/write long-memory file directly via generic file tools (`read`, `write`, etc.).
- Always use `mem_get`/`mem_set`/`mem_update`/`mem_delete` for long-memory operations.
- Do not store secrets unless explicitly required by user.
- If retrieved memory conflicts with current explicit user statement, trust latest explicit statement.
- Keep memory concise and self-contained.

Durable memory examples (should store):
- Stable preferences ("I dislike cilantro", "I switched from americano to latte").
- Persistent profile facts (name, role, city, long-term constraints).
- Reusable procedures and commitments.

Do NOT store:
- Greetings, filler, or one-off emotional chatter with no future utility.
