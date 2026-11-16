"""Search tools: grep and glob.

Pure Python rather than shelling out to ripgrep or find. The dependency-free
version is fast enough at this scale, works identically on every platform, and
— the deciding reason — runs under the offline test suite without needing a
binary installed.

Both tools skip the directories in `tools.search.ignored_directories`. Walking
`.git` or `node_modules` finds nothing useful and costs seconds.
"""

import fnmatch
import os
import re
from pathlib import Path

from pydantic import BaseModel, Field

from pyharnx.tools.base import ToolContext, ToolResult, fail, ok, tool
from pyharnx.tools.fs import clip, resolve

#: What makes a glob segment a pattern rather than a name.
_WILDCARDS = frozenset("*?[")


def _looks_binary(path: Path, sniff: int) -> bool:
    """A NUL byte in the first `sniff` bytes is the usual heuristic, and good enough."""
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(sniff)
    except OSError:
        return True


# --- grep -----------------------------------------------------------------


class GrepParams(BaseModel):
    pattern: str = Field(description="Python regular expression to search for.")
    path: str = Field(default=".", description="File or directory to search.")
    glob: str | None = Field(
        default=None,
        description="Only search files whose name matches this glob, e.g. '*.py'.",
    )
    case_sensitive: bool = Field(default=True, description="Match case exactly.")
    offset: int = Field(
        default=0, ge=0, description="Matches to skip, to page past an earlier result."
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Maximum matches to return. Defaults to, and cannot exceed, the configured cap."
        ),
    )


@tool(
    name="grep",
    description=(
        "Search file contents with a regular expression. Returns matching lines "
        "as path:line:text, in a fixed order, so offset pages through a long "
        "result. Skips binary files and ignored directories. Prefer this to "
        "running grep through a shell."
    ),
)
async def grep(p: GrepParams, ctx: ToolContext) -> ToolResult:
    limits = ctx.config.tools.search
    root = resolve(p.path, ctx)

    flags = 0 if p.case_sensitive else re.IGNORECASE
    try:
        expression = re.compile(p.pattern, flags)
    except re.error as exc:
        # The model wrote the pattern; tell it precisely what was wrong.
        return fail(f"Invalid regular expression {p.pattern!r}: {exc}")

    if not root.exists():
        return fail(f"Path not found: {_rel(root, ctx)}")

    files = [root] if root.is_file() else _walk(root, limits.ignored_directories)
    base = root if root.is_dir() else root.parent

    limit = min(p.limit or limits.max_results, limits.max_results)
    page: list[str] = []
    seen = 0
    searched = 0
    more = False
    for candidate in files:
        if p.glob and not fnmatch.fnmatch(candidate.name, p.glob):
            continue
        if _looks_binary(candidate, limits.binary_sniff_bytes):
            continue
        searched += 1
        try:
            with candidate.open("r", encoding="utf-8", errors="replace") as handle:
                for number, line in enumerate(handle, start=1):
                    if not expression.search(line):
                        continue
                    seen += 1
                    if seen <= p.offset:
                        continue
                    # One match past the page is the proof that more remain;
                    # without it a page ending on the last match would say so.
                    if len(page) == limit:
                        more = True
                        break
                    body = clip(line.rstrip("\n"), limits.max_line_length)
                    page.append(f"{_rel(candidate, ctx, base)}:{number}:{body}")
        except OSError:
            # Unreadable file: skip it rather than failing the whole search.
            continue
        if more:
            break

    if not seen:
        return ok(
            f"No matches for {p.pattern!r} in {searched} file(s).",
            matches=0,
            files_searched=searched,
        )
    if not page:
        return fail(f"offset {p.offset} is past the last match ({seen} in all).")

    rendered = "\n".join(page)
    last = p.offset + len(page)
    if more:
        rendered += (
            f"\n[showing matches {p.offset + 1}-{last}; more remain, re-run with offset={last}]"
        )
    return ok(rendered, matches=len(page), offset=p.offset, files_searched=searched, truncated=more)


# --- glob -----------------------------------------------------------------


class GlobParams(BaseModel):
    pattern: str = Field(
        description="Glob pattern, e.g. '**/*.py' or 'src/*.ts'. Matched against "
        "paths relative to the search directory."
    )
    path: str = Field(default=".", description="Directory to search from.")
    offset: int = Field(
        default=0, ge=0, description="Paths to skip, to page past an earlier result."
    )


@tool(
    name="glob",
    description=(
        "Find files by path pattern. Returns paths sorted by modification time, "
        "newest first, so the files someone is working on surface first; offset "
        "pages through a long result. Prefer this to running find through a shell."
    ),
)
async def glob(p: GlobParams, ctx: ToolContext) -> ToolResult:
    limits = ctx.config.tools.search
    root = resolve(p.path, ctx)

    if not root.exists():
        return fail(f"Directory not found: {_rel(root, ctx)}")
    if not root.is_dir():
        return fail(f"{_rel(root, ctx)} is a file, not a directory.")

    segments = tuple(s for s in p.pattern.split("/") if s not in ("", "."))
    if Path(p.pattern).anchor or not segments:
        return fail(
            f"Could not expand pattern {p.pattern!r}: give it relative to the search "
            "directory, and set path to search somewhere else."
        )
    # Leading segments without a wildcard say where to start, not what to
    # match; the last one always matches, since it names the files.
    fixed = 0
    while fixed < len(segments) - 1 and not _WILDCARDS & set(segments[fixed]):
        fixed += 1
    start, rest = root.joinpath(*segments[:fixed]), segments[fixed:]
    # Without `**` a pattern says how deep its files are: `*.py` lists one
    # directory, and must not cost a walk of the whole tree.
    depth = None if "**" in rest else len(rest) - 1
    found = [
        candidate
        for candidate in _walk(start, limits.ignored_directories, depth)
        if candidate.is_file() and _matches(candidate.relative_to(start).parts, rest)
    ]

    if not found:
        return ok(f"No files match {p.pattern!r}.", files=0)

    # Newest first: in a repo someone is actively working in, recency is a
    # better relevance signal than alphabetical order. Ties go by path — a
    # checkout gives many files one mtime, and paging needs a fixed order.
    found.sort(key=lambda f: (-_mtime(f), str(f)))
    if p.offset >= len(found):
        return fail(f"offset {p.offset} is past the last path ({len(found)} in all).")

    shown = found[p.offset : p.offset + limits.max_files]
    rendered = "\n".join(_rel(f, ctx, root) for f in shown)
    last = p.offset + len(shown)
    if last < len(found):
        rendered += (
            f"\n[showing {p.offset + 1}-{last} of {len(found)} paths; "
            f"more remain, re-run with offset={last}]"
        )
    return ok(rendered, files=len(shown), offset=p.offset, total_files=len(found))


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


# --- shared ---------------------------------------------------------------


def _walk(root: Path, ignored: tuple[str, ...], depth: int | None = None) -> list[Path]:
    """Every file under `root`, skipping ignored directories entirely.

    Pruned during the walk rather than filtered after, so a large `node_modules`
    is never descended into at all. `depth` stops it that many directories
    down; None is no limit. Sorted, because `os.walk` yields whatever order the
    filesystem keeps, and an offset needs the same order each call.
    """
    out: list[Path] = []
    for directory, subdirectories, filenames in os.walk(root):
        if depth is not None and len(Path(directory).relative_to(root).parts) >= depth:
            subdirectories[:] = []
        else:
            subdirectories[:] = sorted(d for d in subdirectories if d not in ignored)
        for name in sorted(filenames):
            out.append(Path(directory) / name)
    return out


def _matches(parts: tuple[str, ...], segments: tuple[str, ...]) -> bool:
    """Whether a relative path matches a glob, segment by segment.

    pathlib's rules: `*`, `?` and `[...]` stay inside one segment — fnmatch
    sees one at a time, so none can cross a `/` — and a `**` segment spans any
    number of directories, none included. A trailing `**` matches everything
    below. fnmatch also brings the platform's case rule, as pathlib's did.
    """
    if not segments:
        return not parts
    head, rest = segments[0], segments[1:]
    if head == "**":
        if not rest:
            return bool(parts)
        return any(_matches(parts[i:], rest) for i in range(len(parts)))
    return bool(parts) and fnmatch.fnmatch(parts[0], head) and _matches(parts[1:], rest)


def _rel(path: Path, ctx: ToolContext, base: Path | None = None) -> str:
    """Render a path relative to the search base, falling back to cwd.

    Absolute paths leak machine layout into the transcript — see
    docs/contributing.md.
    """
    for anchor in (base, Path(ctx.cwd).expanduser()):
        if anchor is None:
            continue
        try:
            return str(path.relative_to(anchor))
        except ValueError:
            continue
    return str(path)


SEARCH_TOOLS = (grep, glob)
