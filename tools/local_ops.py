from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Iterable

DEFAULT_MAX_LINES = 2000
DEFAULT_MAX_BYTES = 50 * 1024


def resolve_target(path: str, cwd: str | None = None) -> Path:
    base = Path(cwd or os.getcwd())
    target = Path(path)
    if not target.is_absolute():
        target = base / target
    return target.resolve()


def run_read(
    *,
    path: str,
    cwd: str | None = None,
    offset: int = 1,
    limit: int | None = None,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> str:
    target = resolve_target(path, cwd)
    lines = target.read_text(encoding="utf-8").splitlines()
    total = len(lines)

    if offset < 1:
        raise ValueError("offset must be >= 1")
    if offset > total and total > 0:
        raise ValueError(f"Offset {offset} is beyond end of file ({total} lines total)")
    if limit is not None and limit < 1:
        raise ValueError("limit must be >= 1")

    start = max(offset - 1, 0)
    remaining = lines[start:]
    if limit is not None:
        chunk = remaining[:limit]
        body = "\n".join(chunk)
        left = len(remaining) - len(chunk)
        if left > 0:
            next_offset = offset + len(chunk)
            return f"{body}\n[{left} more lines in file. Use offset={next_offset} to continue.]"
        return body

    chunk = remaining[:max_lines]
    text = "\n".join(chunk)
    if len(text.encode("utf-8")) > max_bytes:
        trimmed: list[str] = []
        used = 0
        for line in chunk:
            encoded = (line + "\n").encode("utf-8")
            if used + len(encoded) > max_bytes:
                break
            used += len(encoded)
            trimmed.append(line)
        chunk = trimmed
        last_line = offset + len(chunk) - 1
        next_offset = offset + len(chunk)
        body = "\n".join(chunk)
        return (
            f"{body}\n[Showing lines {offset}-{last_line} of {total} (byte limit). "
            f"Use offset={next_offset} to continue.]"
        )

    if len(remaining) > max_lines:
        last_line = offset + len(chunk) - 1
        next_offset = offset + len(chunk)
        body = "\n".join(chunk)
        return f"{body}\n[Showing lines {offset}-{last_line} of {total}. Use offset={next_offset} to continue.]"
    return text


def run_write(*, path: str, content: str, cwd: str | None = None) -> str:
    target = resolve_target(path, cwd)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    written = len(content.encode("utf-8"))
    return f"Successfully wrote {written} bytes to {target}"


def run_edit(*, path: str, old_text: str, new_text: str, cwd: str | None = None) -> str:
    target = resolve_target(path, cwd)
    content = target.read_text(encoding="utf-8")
    count = content.count(old_text)
    if count == 0:
        raise ValueError("Could not find the exact text in file")
    if count > 1:
        raise ValueError(f"Found {count} occurrences of old_text. Please make old_text more specific.")
    target.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
    return f"Successfully replaced text in {target}"


def _iter_files(root: Path) -> Iterable[Path]:
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            yield Path(dirpath) / filename


def run_grep(
    *,
    pattern: str,
    path: str,
    cwd: str | None = None,
    limit: int = 20,
    context: int = 0,
) -> str:
    target = resolve_target(path, cwd)
    regex = re.compile(pattern)
    files = [target] if target.is_file() else list(_iter_files(target))

    lines_out: list[str] = []
    match_count = 0
    for file in files:
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = file.name if target.is_file() else str(file.relative_to(target))
        file_lines = text.splitlines()
        for index, line in enumerate(file_lines, start=1):
            if not regex.search(line):
                continue
            match_count += 1
            if context > 0:
                start = max(1, index - context)
                end = min(len(file_lines), index + context)
                for i in range(start, end + 1):
                    if i == index:
                        lines_out.append(f"{rel}:{i}: {file_lines[i - 1]}")
                    else:
                        lines_out.append(f"{rel}-{i}- {file_lines[i - 1]}")
            else:
                lines_out.append(f"{rel}:{index}: {line}")
            if match_count >= limit:
                return (
                    "\n".join(lines_out)
                    + f"\n[{limit} matches limit reached. Use limit={limit + 1} for more, or refine pattern]"
                )
    return "\n".join(lines_out)


def run_find(*, pattern: str, path: str, cwd: str | None = None) -> str:
    root = resolve_target(path, cwd)
    files = sorted(root.glob(pattern))
    rel = [str(file.relative_to(root)) for file in files if file.is_file()]
    return "\n".join(rel) if rel else "No files found matching pattern"


def run_ls(*, path: str = ".", cwd: str | None = None) -> str:
    target = resolve_target(path, cwd)
    entries = sorted(target.iterdir(), key=lambda item: item.name.lower())
    rendered = [f"{entry.name}/" if entry.is_dir() else entry.name for entry in entries]
    return "\n".join(rendered) if rendered else "(empty directory)"


def run_bash(*, command: str, cwd: str | None = None, timeout: int = 30) -> str:
    command_cwd = str(resolve_target(cwd or ".", None))
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=command_cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired as err:
        raise RuntimeError(f"Command timed out after {timeout} seconds") from err

    stdout = result.stdout.rstrip("\n")
    stderr = result.stderr.rstrip("\n")
    parts = [part for part in [stdout, stderr] if part]
    output = "\n".join(parts) if parts else "(no output)"

    if result.returncode != 0:
        raise RuntimeError(f"{output}\n\nCommand exited with code {result.returncode}")
    return output
