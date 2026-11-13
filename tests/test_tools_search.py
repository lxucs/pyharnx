"""grep and glob against tmp_path."""

import os
import time
from pathlib import Path

from lab_harness.config import Config, SearchConfig, ToolsConfig
from lab_harness.llm.types import TextBlock
from lab_harness.tools.base import ToolContext, ToolResult
from lab_harness.tools.search import glob, grep


def _ctx(tmp_path: Path, config: Config | None = None) -> ToolContext:
    return ToolContext(cwd=str(tmp_path), call_id="c1", config=config or Config())


def _text(result: ToolResult) -> str:
    return "".join(b.text for b in result.content if isinstance(b, TextBlock))


def _with_search(**kwargs: object) -> Config:
    return Config(tools=ToolsConfig(search=SearchConfig(**kwargs)))  # type: ignore[arg-type]


def _tree(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("import os\n\n\ndef run():\n    return os.getcwd()\n")
    (root / "src" / "util.py").write_text("def helper():\n    return 42\n")
    (root / "README.md").write_text("# Project\n\nRun with `run()`.\n")


# --- grep -----------------------------------------------------------------


async def test_grep_returns_path_line_and_text(tmp_path: Path) -> None:
    _tree(tmp_path)

    result = await grep.execute({"pattern": r"def run"}, _ctx(tmp_path))

    assert not result.is_error
    assert "src/app.py:4:def run():" in _text(result)


async def test_grep_filters_by_glob(tmp_path: Path) -> None:
    _tree(tmp_path)

    result = await grep.execute({"pattern": "run", "glob": "*.md"}, _ctx(tmp_path))

    body = _text(result)
    assert "README.md" in body
    assert "app.py" not in body


async def test_grep_case_insensitive_is_opt_in(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("Hello World\n")

    sensitive = await grep.execute({"pattern": "hello"}, _ctx(tmp_path))
    insensitive = await grep.execute({"pattern": "hello", "case_sensitive": False}, _ctx(tmp_path))

    assert "No matches" in _text(sensitive)
    assert "a.txt:1:Hello World" in _text(insensitive)


async def test_grep_reports_an_invalid_regex_actionably(tmp_path: Path) -> None:
    """The model wrote the pattern; it needs to know what was wrong."""
    result = await grep.execute({"pattern": "("}, _ctx(tmp_path))

    assert result.is_error
    assert "Invalid regular expression" in _text(result)


async def test_grep_skips_ignored_directories(tmp_path: Path) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("needle\n")
    (tmp_path / "mine.js").write_text("needle\n")

    result = await grep.execute({"pattern": "needle"}, _ctx(tmp_path))

    body = _text(result)
    assert "mine.js" in body
    assert "node_modules" not in body


async def test_grep_skips_binary_files(tmp_path: Path) -> None:
    (tmp_path / "data.bin").write_bytes(b"needle\x00\x01binary")
    (tmp_path / "text.txt").write_text("needle\n")

    result = await grep.execute({"pattern": "needle"}, _ctx(tmp_path))

    body = _text(result)
    assert "text.txt" in body
    assert "data.bin" not in body


async def test_grep_caps_results_and_says_how_to_page(tmp_path: Path) -> None:
    (tmp_path / "many.txt").write_text("hit\n" * 100)
    config = _with_search(max_results=5)

    result = await grep.execute({"pattern": "hit"}, _ctx(tmp_path, config))

    lines = _text(result).splitlines()
    assert lines[:5] == [f"many.txt:{n}:hit" for n in range(1, 6)]
    assert lines[5] == "[showing matches 1-5; more remain, re-run with offset=5]"
    assert result.details["truncated"] is True


async def test_grep_pages_with_offset_and_limit(tmp_path: Path) -> None:
    (tmp_path / "many.txt").write_text("".join(f"hit {n}\n" for n in range(1, 11)))

    result = await grep.execute({"pattern": "hit", "offset": 3, "limit": 2}, _ctx(tmp_path))

    assert _text(result).splitlines() == [
        "many.txt:4:hit 4",
        "many.txt:5:hit 5",
        "[showing matches 4-5; more remain, re-run with offset=5]",
    ]
    assert result.details["offset"] == 3


async def test_grep_last_page_has_no_paging_note(tmp_path: Path) -> None:
    """A page that ends exactly at the last match must not claim more remain."""
    (tmp_path / "many.txt").write_text("hit\n" * 5)
    config = _with_search(max_results=5)

    result = await grep.execute({"pattern": "hit"}, _ctx(tmp_path, config))

    assert "more remain" not in _text(result)
    assert result.details["truncated"] is False


async def test_grep_caps_a_requested_limit_at_the_configured_maximum(tmp_path: Path) -> None:
    (tmp_path / "many.txt").write_text("hit\n" * 100)
    config = _with_search(max_results=5)

    result = await grep.execute({"pattern": "hit", "limit": 50}, _ctx(tmp_path, config))

    assert result.details["matches"] == 5


async def test_grep_rejects_an_offset_past_the_last_match(tmp_path: Path) -> None:
    (tmp_path / "few.txt").write_text("hit\n" * 3)

    result = await grep.execute({"pattern": "hit", "offset": 3}, _ctx(tmp_path))

    assert result.is_error
    assert "past the last match (3 in all)" in _text(result)


async def test_grep_walks_files_in_sorted_order(tmp_path: Path) -> None:
    """Paging is only meaningful if every call sees the matches in the same order."""
    names = [f"{c}.txt" for c in "qwertyuiopasdfghjklzxcvbnm"]
    for name in names:
        (tmp_path / name).write_text("hit\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.txt").write_text("hit\n")

    result = await grep.execute({"pattern": "hit"}, _ctx(tmp_path))

    paths = [line.split(":")[0] for line in _text(result).splitlines()]
    assert paths == [*sorted(names), "sub/a.txt"]


async def test_grep_clips_very_long_matching_lines(tmp_path: Path) -> None:
    (tmp_path / "long.txt").write_text("needle" + "x" * 1000 + "\n")
    config = _with_search(max_line_length=20)

    result = await grep.execute({"pattern": "needle"}, _ctx(tmp_path, config))

    assert "[line truncated at 20 characters]" in _text(result)
    assert len(_text(result).splitlines()[0]) < 100


async def test_grep_reports_no_matches_without_erroring(tmp_path: Path) -> None:
    _tree(tmp_path)

    result = await grep.execute({"pattern": "zzz_absent"}, _ctx(tmp_path))

    assert not result.is_error
    assert "No matches" in _text(result)
    assert result.details["matches"] == 0


async def test_grep_can_search_a_single_file(tmp_path: Path) -> None:
    _tree(tmp_path)

    result = await grep.execute({"pattern": "def", "path": "src/util.py"}, _ctx(tmp_path))

    assert "util.py:1:def helper():" in _text(result)


async def test_grep_reports_a_missing_path(tmp_path: Path) -> None:
    result = await grep.execute({"pattern": "x", "path": "absent"}, _ctx(tmp_path))

    assert result.is_error
    assert "not found" in _text(result).lower()


# --- glob -----------------------------------------------------------------


async def test_glob_finds_files_by_pattern(tmp_path: Path) -> None:
    _tree(tmp_path)

    result = await glob.execute({"pattern": "**/*.py"}, _ctx(tmp_path))

    body = _text(result)
    assert "src/app.py" in body
    assert "src/util.py" in body
    assert "README.md" not in body


async def test_glob_sorts_newest_first(tmp_path: Path) -> None:
    """Recency beats alphabetical order in a repo someone is working in."""
    (tmp_path / "old.py").write_text("")
    (tmp_path / "new.py").write_text("")
    old = time.time() - 10_000
    os.utime(tmp_path / "old.py", (old, old))

    result = await glob.execute({"pattern": "*.py"}, _ctx(tmp_path))

    assert _text(result).splitlines() == ["new.py", "old.py"]


async def test_glob_skips_ignored_directories(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.py").write_text("")
    (tmp_path / "real.py").write_text("")

    result = await glob.execute({"pattern": "**/*.py"}, _ctx(tmp_path))

    body = _text(result)
    assert "real.py" in body
    assert ".git" not in body


def _same_age(root: Path, count: int) -> list[str]:
    """`count` files sharing one mtime, so glob's order among them is the tie-break."""
    names = [f"f{i:02}.py" for i in range(count)]
    stamp = time.time() - 10_000
    for name in names:
        (root / name).write_text("")
        os.utime(root / name, (stamp, stamp))
    return names


async def test_glob_caps_results_and_says_how_to_page(tmp_path: Path) -> None:
    _same_age(tmp_path, 20)
    config = _with_search(max_files=5)

    result = await glob.execute({"pattern": "*.py"}, _ctx(tmp_path, config))

    assert _text(result).splitlines()[-1] == (
        "[showing 1-5 of 20 paths; more remain, re-run with offset=5]"
    )
    assert result.details["total_files"] == 20


async def test_glob_pages_with_offset(tmp_path: Path) -> None:
    names = _same_age(tmp_path, 20)
    config = _with_search(max_files=5)

    result = await glob.execute({"pattern": "*.py", "offset": 5}, _ctx(tmp_path, config))

    assert _text(result).splitlines() == [
        *names[5:10],
        "[showing 6-10 of 20 paths; more remain, re-run with offset=10]",
    ]


async def test_glob_breaks_mtime_ties_by_path(tmp_path: Path) -> None:
    """A checkout gives many files one mtime; paging needs their order fixed."""
    names = _same_age(tmp_path, 12)

    result = await glob.execute({"pattern": "*.py"}, _ctx(tmp_path))

    assert _text(result).splitlines() == names


async def test_glob_rejects_an_offset_past_the_last_path(tmp_path: Path) -> None:
    _same_age(tmp_path, 3)

    result = await glob.execute({"pattern": "*.py", "offset": 3}, _ctx(tmp_path))

    assert result.is_error
    assert "past the last path (3 in all)" in _text(result)


async def test_glob_reports_no_matches_without_erroring(tmp_path: Path) -> None:
    result = await glob.execute({"pattern": "*.zzz"}, _ctx(tmp_path))

    assert not result.is_error
    assert "No files match" in _text(result)


async def test_glob_rejects_a_file_as_the_search_root(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("")

    result = await glob.execute({"pattern": "*", "path": "a.py"}, _ctx(tmp_path))

    assert result.is_error
    assert "not a directory" in _text(result)


async def test_glob_reports_a_missing_directory(tmp_path: Path) -> None:
    result = await glob.execute({"pattern": "*", "path": "absent"}, _ctx(tmp_path))

    assert result.is_error
    assert "not found" in _text(result).lower()


# --- shared ---------------------------------------------------------------


async def test_output_never_contains_absolute_paths(tmp_path: Path) -> None:
    """Transcripts get committed; machine layout should not ride along."""
    _tree(tmp_path)

    found = await glob.execute({"pattern": "**/*.py"}, _ctx(tmp_path))
    matched = await grep.execute({"pattern": "def"}, _ctx(tmp_path))

    assert str(tmp_path) not in _text(found)
    assert str(tmp_path) not in _text(matched)
