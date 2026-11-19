"""Validates SQL before it is allowed to run against tenant data.

Used for every LLM-generated query and every saved widget query. Rules:

1. Exactly one statement, and it must be a SELECT (or UNION of SELECTs, CTEs ok).
2. No write / DDL / admin nodes anywhere in the tree (INSERT, UPDATE, DROP, SELECT INTO ...).
3. Every table referenced must be one of *this org's* dataset tables. Schema
   qualifiers other than the org's own schema are rejected, which blocks
   cross-tenant reads and pg_catalog / information_schema probing.
4. Dangerous functions (pg_sleep, pg_read_file, dblink, lo_import, ...) are blocked.

The runner (query_runner.py) adds defence in depth: read-only transaction,
read-only DB role, search_path pinned to the tenant schema, statement timeout,
and a row limit.
"""
import sqlglot
from sqlglot import exp

FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
    exp.Into,
    exp.Merge,
    exp.TruncateTable,
    exp.Grant,
    exp.Copy,
    exp.Set,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
)

FORBIDDEN_FUNCTION_PREFIXES = ("pg_", "lo_", "dblink", "current_setting", "set_config", "query_to_xml", "version")


class UnsafeSQL(ValueError):
    pass


def validate_sql(sql: str, allowed_tables: set[str], tenant_schema: str) -> str:
    """Return a normalised copy of `sql` or raise UnsafeSQL."""
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        raise UnsafeSQL("Empty query")

    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise UnsafeSQL(f"Could not parse SQL: {e.errors[0]['description'] if e.errors else e}") from e

    if len(statements) != 1:
        raise UnsafeSQL("Only a single statement is allowed")
    tree = statements[0]

    if not isinstance(tree, (exp.Select, exp.Union, exp.Except, exp.Intersect, exp.Subquery)):
        raise UnsafeSQL("Only SELECT queries are allowed")

    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise UnsafeSQL(f"{type(node).__name__} is not allowed")
        if isinstance(node, exp.Func):
            fname = (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()
            if fname.startswith(FORBIDDEN_FUNCTION_PREFIXES):
                raise UnsafeSQL(f"Function {fname}() is not allowed")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    allowed = {t.lower() for t in allowed_tables}

    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        schema = (table.db or "").lower()
        if table.catalog:
            raise UnsafeSQL("Database-qualified names are not allowed")
        if schema and schema != tenant_schema.lower():
            raise UnsafeSQL(f"Access to schema '{schema}' is not allowed")
        if not schema and name in cte_names:
            continue
        if name not in allowed:
            raise UnsafeSQL(f"Unknown table '{name}'")

    return tree.sql(dialect="postgres")
