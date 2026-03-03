# simplemem_v1

Minimal memory-system package for `v6.2`.

Contents:
- `memory_policy.md`: model-side strategy for using memory tools.
- `tools_schema.json`: tool contract and object model for memory operations.

Runtime wiring:
- policy/schema are injected into system prompt by `V6_2`.
- persistent data store is configured via `memory_store_path`.
