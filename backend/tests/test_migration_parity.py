"""The migrations and the models must describe the same database.

They had drifted, and nothing compared them. A migration declared a column
(``concept_family_proposal.updated_at NOT NULL``) that no model carries, so SQLAlchemy
never sent it and every insert failed against Postgres with a NotNullViolation -- in
production, after the model calls had been paid for.

Nothing caught it because the two schemas are built from different sources: the tests call
``Base.metadata.create_all()`` from the models, production runs these migrations. A test
suite that only ever sees the models can never see a migration that disagrees with them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from app.models import Base

BACKEND = Path(__file__).resolve().parents[1]


def _migrated(url: str) -> None:
    """Run the migrations against ``url``.

    migrations/env.py takes the URL from the application settings and overwrites whatever
    the Config carries, so pointing this at a scratch database means pointing the settings
    at it -- setting sqlalchemy.url alone silently migrated the session database instead
    and left the scratch file empty.
    """
    from alembic import command
    from alembic.config import Config

    from app.config import get_settings

    # The cached Settings instance is mutated rather than the cache cleared: env.py calls
    # get_settings() itself, and clearing the cache would hand it a fresh object rebuilt
    # from the environment -- which is exactly the database this override exists to avoid.
    settings = get_settings()
    before = (settings.database_url, settings.migration_database_url)
    settings.database_url, settings.migration_database_url = url, None
    try:
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "migrations"))
        command.upgrade(cfg, "head")
    finally:
        settings.database_url, settings.migration_database_url = before


@pytest.fixture(scope="module")
def schemas(tmp_path_factory):
    """Two databases: one built by the migrations, one by the models."""
    d = tmp_path_factory.mktemp("parity")
    from_migrations = create_engine(f"sqlite+pysqlite:///{d}/migrated.db")
    _migrated(f"sqlite+pysqlite:///{d}/migrated.db")

    from_models = create_engine(f"sqlite+pysqlite:///{d}/models.db")
    Base.metadata.create_all(from_models)
    return inspect(from_migrations), inspect(from_models)


def test_every_model_table_is_created_by_the_migrations(schemas):
    migrated, models = schemas
    missing = set(models.get_table_names()) - set(migrated.get_table_names())
    assert not missing, (
        f"tables the models define but no migration creates: {sorted(missing)}. "
        f"Production would 500 on the first query against them."
    )


def test_no_migration_invents_a_table_no_model_has(schemas):
    migrated, models = schemas
    extra = set(migrated.get_table_names()) - set(models.get_table_names()) - {"alembic_version"}
    assert not extra, f"tables created by migrations that no model maps: {sorted(extra)}"


def test_the_columns_match_table_by_table(schemas):
    migrated, models = schemas
    problems: list[str] = []
    for table in sorted(set(models.get_table_names()) & set(migrated.get_table_names())):
        in_db = {c["name"] for c in migrated.get_columns(table)}
        in_model = {c["name"] for c in models.get_columns(table)}
        for name in sorted(in_model - in_db):
            problems.append(f"{table}.{name}: in the model, no migration adds it")
        for name in sorted(in_db - in_model):
            # The exact shape of the bug that reached production: an insert never sends
            # this column, so a NOT NULL on it fails every write.
            problems.append(f"{table}.{name}: created by a migration, no model has it")
    assert not problems, "migrations and models disagree:\n  " + "\n  ".join(problems)


def test_a_column_required_by_the_database_is_one_the_model_will_supply(schemas):
    """NOT NULL is only safe where the model has a default or the caller always sets it.

    Narrower than the column check above and worth stating separately: this is the
    property whose violation produced the NotNullViolation.
    """
    migrated, models = schemas
    model_columns = {
        table: {c["name"]: c for c in models.get_columns(table)}
        for table in models.get_table_names()
    }
    problems = []
    for table in sorted(set(model_columns) & set(migrated.get_table_names())):
        for column in migrated.get_columns(table):
            if column["nullable"] or column.get("default") is not None:
                continue
            if column["name"] not in model_columns[table]:
                problems.append(f"{table}.{column['name']} is NOT NULL and unmapped")
    assert not problems, "\n  ".join(problems)
