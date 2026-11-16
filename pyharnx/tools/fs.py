"""Filesystem tools: read, write, edit, ls.

Every path is resolved against `ctx.cwd`, never the process working directory —
that is what lets the suite run them against `tmp_path` and what keeps two
agents with different roots from interfering.

Errors are returned, not raised. The messages are written for the model: they
say what went wrong and what to do instead, because the model's next action is
chosen from that text.
"""

import difflib
from pathlib import Path

from pydantic import BaseModel, Field

from pyharnx.config import ReadConfig
from pyharnx.tools.base import ToolContext, ToolResult, fail, ok, tool

_TRUNCATION_NOTE = "\n\n[truncated at {shown} of {total} lines; re-read with offset={next_offset}]"
_LINE_CUT = "… [line truncated at {limit} characters]"


def resolve(path: str, ctx: ToolContext) -> Path:
    """Resolve a tool-supplied path against the call's working directory.

    Absolute paths are honored as given. `expanduser` runs first so `~/x` means
    what the user expects rather than a literal directory named `~`.
    """
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path(ctx.cwd).expanduser() / candidate
    return candidate


def display(path: Path, ctx: ToolContext) -> str:
    """Render a path for output and `details`: relative to cwd when inside it.

    Absolute paths leak the machine's layout into the transcript, which is both
    noisy and the kind of thing that ends up committed — and `details` reach the
    event stream, so every `--json` log, as well.
    """
    try:
        return str(path.relative_to(Path(ctx.cwd).expanduser().resolve()))
    except ValueError:
        return str(path)


# --- read -----------------------------------------------------------------


class ReadParams(BaseModel):
    path: str = Field(description="Path to the file, absolute or relative to the working directory")
    offset: int | None = Field(
        default=None, ge=1, description="1-indexed line to start from. Omit to start at the top."
    )
    limit: int | None = Field(default=None, ge=1, description="Maximum number of lines to return.")


@tool(name="read", description="Read a text file. Returns 1-indexed numbered lines.")
async def read(p: ReadParams, ctx: ToolContext) -> ToolResult:
    path = resolve(p.path, ctx)
    limits = ctx.config.tools.read

    if not path.exists():
        return fail(f"File not found: {display(path, ctx)}")
    if path.is_dir():
        return fail(f"{display(path, ctx)} is a directory. Use `ls` to list it.")

    start = (p.offset or 1) - 1
    try:
        window, total = _window(path, start, p.limit or limits.default_limit, limits)
    except UnicodeDecodeError:
        return fail(f"{display(path, ctx)} is not UTF-8 text. It may be a binary file.")
    except OSError as exc:
        return fail(f"Could not read {display(path, ctx)}: {exc}")

    if not total:
        return ok("[file is empty]", path=display(path, ctx), lines=0, total_lines=0)
    if start >= total:
        return fail(f"offset {p.offset} is past the end of the file ({total} lines).")

    rendered = "\n".join(window)
    shown = start + len(window)
    if shown < total:
        rendered += _TRUNCATION_NOTE.format(shown=shown, total=total, next_offset=shown + 1)
    return ok(rendered, path=display(path, ctx), lines=len(window), total_lines=total)


def _window(path: Path, start: int, count: int, limits: ReadConfig) -> tuple[list[str], int]:
    """The numbered lines from `start` that fit both limits, and the file's line count.

    Streamed: only the window is held, so a range of a file far larger than
    `max_bytes` costs no more than the range. The first line is always taken,
    however wide, or the offset to resume from would be the one just tried.
    """
    window: list[str] = []
    budget = limits.max_bytes
    full = False
    total = 0
    with path.open("r", encoding="utf-8") as handle:
        for total, line in enumerate(handle, start=1):
            if full or total <= start:
                continue
            numbered = f"{total}\t{clip(line.rstrip('\n'), limits.max_line_length)}"
            cost = len(numbered.encode()) + 1
            if window and cost > budget:
                full = True
                continue
            window.append(numbered)
            budget -= cost
            full = len(window) == count
    return window, total


def clip(line: str, limit: int) -> str:
    """Cut `line` at `limit` characters, saying so. Shared with grep."""
    return line if len(line) <= limit else line[:limit] + _LINE_CUT.format(limit=limit)


# --- write ----------------------------------------------------------------


class WriteParams(BaseModel):
    path: str = Field(description="Path to write, absolute or relative to the working directory")
    content: str = Field(description="Full file contents. Overwrites any existing file.")


@tool(
    name="write",
    description="Write a file, creating parent directories as needed. Overwrites existing files.",
    # Sequential: concurrent writes to one path are a race nobody wants to debug.
    execution_mode="sequential",
)
async def write(p: WriteParams, ctx: ToolContext) -> ToolResult:
    path = resolve(p.path, ctx)
    if path.is_dir():
        return fail(f"{display(path, ctx)} is a directory.")

    existed = path.exists()
    shown = display(path, ctx)
    before = _previous_text(path) if existed else ""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(p.content, encoding="utf-8")
    except OSError as exc:
        return fail(f"Could not write {shown}: {exc}")

    verb = "Updated" if existed else "Created"
    line_count = len(p.content.splitlines())
    # A file that was not text has no diff worth showing; the write still happens.
    change = (
        {} if before is None else {"diff": _diff(before, p.content, shown, ctx, new=not existed)}
    )
    return ok(
        f"{verb} {shown} ({line_count} lines)",
        path=shown,
        created=not existed,
        lines=line_count,
        **change,
    )


# --- edit -----------------------------------------------------------------


class EditParams(BaseModel):
    path: str = Field(description="Path to edit, absolute or relative to the working directory")
    old: str = Field(
        description="Exact text to replace, including indentation. Must appear exactly once "
        "unless replace_all is set."
    )
    new: str = Field(description="Replacement text.")
    replace_all: bool = Field(default=False, description="Replace every occurrence of `old`.")


@tool(
    name="edit",
    description="Replace exact text in a file. Fails if the text is absent or ambiguous.",
    execution_mode="sequential",
)
async def edit(p: EditParams, ctx: ToolContext) -> ToolResult:
    path = resolve(p.path, ctx)
    if not path.exists():
        return fail(f"File not found: {display(path, ctx)}")
    if path.is_dir():
        return fail(f"{display(path, ctx)} is a directory.")
    if p.old == p.new:
        return fail("`old` and `new` are identical; nothing to do.")

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return fail(f"{display(path, ctx)} is not UTF-8 text.")
    except OSError as exc:
        return fail(f"Could not read {display(path, ctx)}: {exc}")

    occurrences = content.count(p.old)
    if occurrences == 0:
        return fail(
            f"`old` text not found in {display(path, ctx)}. Read the file and copy the "
            f"text exactly, including whitespace."
        )
    # Ambiguity is refused rather than guessed: replacing the first of several
    # matches edits a line the caller never looked at.
    if occurrences > 1 and not p.replace_all:
        return fail(
            f"`old` text appears {occurrences} times in {display(path, ctx)}. Add "
            f"surrounding context to make it unique, or set replace_all."
        )

    updated = content.replace(p.old, p.new) if p.replace_all else content.replace(p.old, p.new, 1)
    try:
        path.write_text(updated, encoding="utf-8")
    except OSError as exc:
        return fail(f"Could not write {display(path, ctx)}: {exc}")

    replaced = occurrences if p.replace_all else 1
    shown = display(path, ctx)
    return ok(
        f"Replaced {replaced} occurrence(s) in {shown}",
        path=shown,
        replacements=replaced,
        diff=_diff(content, updated, shown, ctx),
    )


def _previous_text(path: Path) -> str | None:
    """What a write is about to replace, or None if it was not readable text."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _diff(before: str, after: str, shown: str, ctx: ToolContext, *, new: bool = False) -> str:
    """A unified diff of a change, for `details` — never for the model.

    The standard format rather than an invented one, so a consumer of the event
    stream in any language can parse it with whatever it already has. Named by
    the displayed path, for the same reason output is.
    """
    lines = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile="/dev/null" if new else f"a/{shown}",
        tofile=f"b/{shown}",
        n=ctx.config.tools.diff.context_lines,
        lineterm="",
    )
    return "\n".join(lines)


# --- ls -------------------------------------------------------------------


class ListParams(BaseModel):
    path: str = Field(default=".", description="Directory to list. Defaults to the working dir.")
    all: bool = Field(default=False, description="Include entries beginning with a dot.")
    offset: int = Field(
        default=0, ge=0, description="Entries to skip, to page past an earlier result."
    )


@tool(
    name="ls",
    description=(
        "List the entries of a directory, directories first. Directories are "
        "marked with /; offset pages through a long listing."
    ),
)
async def ls(p: ListParams, ctx: ToolContext) -> ToolResult:
    path = resolve(p.path, ctx)
    if not path.exists():
        return fail(f"Directory not found: {display(path, ctx)}")
    if not path.is_dir():
        return fail(f"{display(path, ctx)} is a file. Use `read` to read it.")

    try:
        entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name))
    except OSError as exc:
        return fail(f"Could not list {display(path, ctx)}: {exc}")

    if not p.all:
        entries = [e for e in entries if not e.name.startswith(".")]

    if p.offset and p.offset >= len(entries):
        return fail(f"offset {p.offset} is past the last entry ({len(entries)} in all).")

    shown = entries[p.offset : p.offset + ctx.config.tools.list.max_entries]
    names = [f"{e.name}/" if e.is_dir() else e.name for e in shown]
    rendered = "\n".join(names) if names else "[empty]"
    last = p.offset + len(shown)
    if last < len(entries):
        rendered += (
            f"\n[showing {p.offset + 1}-{last} of {len(entries)} entries; "
            f"more remain, re-run with offset={last}]"
        )

    return ok(
        rendered,
        path=display(path, ctx),
        entries=len(shown),
        offset=p.offset,
        total_entries=len(entries),
    )


FILESYSTEM_TOOLS = (read, write, edit, ls)
