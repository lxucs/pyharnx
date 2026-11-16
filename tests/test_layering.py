"""Invariant 1: dependencies point downward, as docs/architecture.md draws them.

Read from the source rather than from the running interpreter, so a lazy import
inside a function counts as much as one at the top of a module.
"""

import ast
from pathlib import Path

import pytest

import pyharnx

PACKAGE = Path(pyharnx.__file__).parent

#: What each subpackage may import from the package, besides the leaf modules.
#: The diagram, as data: each box takes only from the boxes below it, and
#: `prompts/` — beside `agent/`, not under it — from none of them.
ALLOWED = {
    "llm": set(),
    "tools": {"llm"},
    "agent": {"tools", "llm"},
    "prompts": set(),
    "session": {"agent", "tools", "llm"},
    "cli": {"session", "agent", "prompts", "tools", "llm"},
}
#: Read by every layer, and importing nothing from the package but each other.
LEAVES = {"config": {"logs"}, "logs": {"config"}}


def _imported(paths: list[Path], own: str) -> set[str]:
    """The top-level parts of the package that `paths` import, other than `own`."""
    found: set[str] = set()
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            for name in names:
                parts = name.split(".")
                if parts[0] == "pyharnx" and len(parts) > 1:
                    found.add(parts[1])
    return found - {own}


@pytest.mark.parametrize("layer", sorted(ALLOWED))
def test_a_layer_imports_only_from_below_it(layer: str) -> None:
    imported = _imported(sorted((PACKAGE / layer).rglob("*.py")), layer)

    upward = imported - ALLOWED[layer] - set(LEAVES)
    assert not upward, f"{layer}/ imports {sorted(upward)}: see docs/architecture.md"


@pytest.mark.parametrize("leaf", sorted(LEAVES))
def test_the_leaf_modules_import_only_each_other(leaf: str) -> None:
    imported = _imported([PACKAGE / f"{leaf}.py"], leaf)

    assert imported <= LEAVES[leaf]


def test_every_subpackage_has_a_place_in_the_diagram() -> None:
    """A new subpackage must be drawn, and given its row here, before it lands."""
    packages = {p.name for p in PACKAGE.iterdir() if (p / "__init__.py").is_file()}

    assert packages == set(ALLOWED)
