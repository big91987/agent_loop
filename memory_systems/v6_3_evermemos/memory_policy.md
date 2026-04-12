# EverMemOS Policy

Use `mem_get` when the user is asking about prior facts, prior events, prior plans, or stable user information.
Use `mem_set` only for explicit reinforcement when the user clearly asks to remember something important.
Prefer letting the passive EverMemOS backend handle normal long-memory extraction.
Treat the workspace as the runtime home for this memory system; backend manifests and logs belong under the active workspace memory directory.
