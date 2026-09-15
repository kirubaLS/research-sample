"""Every module imported at boot must be a base dependency.

Twice now a deploy has built green and then failed on startup with ModuleNotFoundError,
because a library sat in an optional extra while something in the import chain from
app.main needed it. The build says nothing; the crash arrives at boot.

This walks the real import graph rather than trusting the dependency list, and it walks
`from app.api import books` into app.api.books -- missing that hop is what made an earlier
version of this check report "clean" while production was crashing.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

#: [project.dependencies] in pyproject.toml, by import name
BASE = {
    "fastapi", "uvicorn", "sqlalchemy", "alembic", "pydantic", "pydantic_settings",
    "psycopg", "numpy", "scipy", "multipart", "httpx", "pymupdf", "anthropic", "sarvamai",
}


def _module_path(mod: str) -> Path:
    p = BACKEND / (mod.replace(".", "/") + ".py")
    return p if p.exists() else BACKEND / (mod.replace(".", "/") + "/__init__.py")


def _module_level(tree: ast.Module):
    """Statements that run when the module is imported.

    Descends into `if`, `try` and `with` at module scope -- a conditional import still runs
    at boot -- but not into a function or class body, which does not.
    """
    out = []
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        out.append(node)
        if isinstance(node, (ast.If, ast.Try, ast.With)):
            stack.extend(node.body)
            stack.extend(getattr(node, "orelse", []))
            stack.extend(getattr(node, "finalbody", []))
            for handler in getattr(node, "handlers", []):
                stack.extend(handler.body)
    return out


def boot_imports() -> dict[str, str]:
    """Third-party top-level modules imported when `app.main` is imported."""
    seen: set[str] = set()
    stack = ["app.main"]
    found: dict[str, str] = {}

    while stack:
        mod = stack.pop()
        if mod in seen:
            continue
        seen.add(mod)
        path = _module_path(mod)
        if not path.exists():
            continue

        # Module scope only. An import inside a function body does not run at boot, and
        # treating one as though it did reported a deliberately lazy import as a fault --
        # ast.walk descends into function bodies, so the tree has to be walked by hand.
        tree = ast.parse(path.read_text())
        for node in _module_level(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("app"):
                        stack.append(alias.name)
                    else:
                        found.setdefault(alias.name.split(".")[0], mod)
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("app"):
                    stack.append(node.module)
                    # `from app.api import books` also imports app.api.books
                    stack.extend(f"{node.module}.{a.name}" for a in node.names)
                else:
                    found.setdefault(node.module.split(".")[0], mod)

    return found


def test_no_boot_import_lives_in_an_optional_extra():
    offenders = {
        name: by
        for name, by in boot_imports().items()
        if name not in BASE and name not in sys.stdlib_module_names
    }
    assert not offenders, (
        "these are imported at boot but are not base dependencies, so the API will build "
        "green and then fail to start: "
        + ", ".join(f"{n} (via {by})" for n, by in sorted(offenders.items()))
    )


def test_the_walker_follows_from_package_import_module():
    """The hop that an earlier version of this check missed, reporting clean while
    production was crashing on a missing pymupdf."""
    assert "pymupdf" in boot_imports(), "app.api.books -> app.ingest.book -> pymupdf"


def test_an_import_inside_a_function_is_not_a_boot_import():
    """The opposite mistake, and the one this check made next: `anthropic` is imported
    inside AnthropicJudge.__init__ precisely so a missing install fails one call rather
    than the whole service. Reporting that as a boot import is a false alarm that would
    train someone to ignore this test."""
    import ast

    tree = ast.parse(
        "import fastapi\n"
        "def f():\n"
        "    import anthropic\n"
        "class C:\n"
        "    import scipy\n"
    )
    names = {
        alias.name
        for node in _module_level(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert names == {"fastapi"}


def test_a_conditional_import_at_module_scope_still_counts():
    """`if TYPE_CHECKING` aside, an import inside a module-level try/except runs at boot."""
    import ast

    tree = ast.parse("try:\n    import scipy\nexcept ImportError:\n    scipy = None\n")
    names = {
        alias.name
        for node in _module_level(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert names == {"scipy"}
