import pytest

from app.services.sql_guard import UnsafeSQL, validate_sql

T = {"sales", "customers"}
S = "org_1"


@pytest.mark.parametrize("sql", [
    "SELECT * FROM sales",
    "select region, sum(revenue) from sales group by 1 order by 2 desc;",
    "WITH m AS (SELECT region FROM sales) SELECT * FROM m",
    "SELECT * FROM org_1.sales",
    "SELECT s.region FROM sales s JOIN customers c ON c.id = s.customer_id",
    "SELECT region FROM sales UNION SELECT region FROM customers",
    "SELECT date_trunc('month', order_date)::date AS m, count(*) FROM sales GROUP BY 1",
    "SELECT * FROM sales WHERE region IN (SELECT region FROM customers)",
])
def test_allows_safe_selects(sql):
    assert validate_sql(sql, T, S)


@pytest.mark.parametrize("sql,msg", [
    ("DELETE FROM sales", "Only SELECT"),
    ("UPDATE sales SET revenue = 0", "Only SELECT"),
    ("DROP TABLE sales", "Only SELECT"),
    ("INSERT INTO sales VALUES (1)", "Only SELECT"),
    ("SELECT 1; DROP TABLE sales", "single statement"),
    ("SELECT * INTO copy FROM sales", "not allowed"),
    ("SELECT * FROM users", "Unknown table"),
    ("SELECT * FROM org_2.sales", "schema 'org_2'"),
    ("SELECT * FROM pg_catalog.pg_user", "schema 'pg_catalog'"),
    ("SELECT * FROM information_schema.tables", "schema 'information_schema'"),
    ("SELECT pg_sleep(10)", "pg_sleep"),
    ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
    ("SELECT current_setting('is_superuser')", "current_setting"),
    ("WITH x AS (DELETE FROM sales RETURNING *) SELECT * FROM x", "not allowed"),
    ("SELECT * FROM db.org_1.sales", "Database-qualified"),
    ("", "Empty"),
    ("SELEC * FRM", ""),
])
def test_blocks_unsafe(sql, msg):
    with pytest.raises(UnsafeSQL, match=msg):
        validate_sql(sql, T, S)
