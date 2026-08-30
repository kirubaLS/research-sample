# These files are immutable once deployed

A migration that has run against any real database is a fact that database remembers, in
`alembic_version`. Deleting or regenerating the file orphans that row, and the next deploy
fails with:

    Can't locate revision identified by '<old id>'

...on a database that is otherwise healthy. Recovering means either dropping the schema or
hand-writing a bridge migration.

This happened once, in development, because regenerating was convenient while the local
database was being recreated on every run anyway.

**So: never `alembic revision --autogenerate` over an existing file, and never delete one.**
A schema change gets a NEW revision stacked on top, even if the previous one is a day old
and the change is small.

The only safe time to regenerate is before the migration has ever been applied anywhere but
a throwaway local database -- and by then it is rarely worth the risk of being wrong about
where it has run.
