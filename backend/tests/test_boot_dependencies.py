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
    "psycopg", "numpy", "scipy", "multipart", "httpx", "pymupdf",
}


def _module_path(mod: str) -> Path:
    p = BACKEND / (mod.replace(".", "/") + ".py")
    return p if p.exists() else BACKEND / (mod.replace(".", "/") + "/__init__.py")


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

        # module scope only: an import inside a function does not run at boot
        for node in ast.walk(ast.parse(path.read_text())):
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
