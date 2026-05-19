# v6.3 OpenViking Backend

This system directory binds the real OpenViking runtime into `v6.3`.

- Runtime model: session commit -> memory extraction -> `viking://user/default/memories`
- Active support:
  - `mem_get`: supported
  - `mem_set/update/delete`: intentionally unsupported
- Worker:
  - `openviking_worker.py`
  - runs in `py312`
