-- Runs once when the Postgres container is first created.
-- App role: owns the database, creates org_<id> schemas and tables.
-- Read-only role: used ONLY to run AI-generated / widget SQL. It can SELECT
-- from tenant schemas (grants are added per schema by the app) and nothing else.

CREATE ROLE insight LOGIN PASSWORD 'insight';
CREATE ROLE insight_readonly LOGIN PASSWORD 'insight_ro' NOSUPERUSER NOCREATEDB NOCREATEROLE;

CREATE DATABASE insight OWNER insight;
CREATE DATABASE insight_test OWNER insight;

\connect insight
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO insight;
-- The read-only role must NOT read the app's own tables (users, password hashes...).
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM insight_readonly;
ALTER ROLE insight_readonly SET default_transaction_read_only = on;
ALTER ROLE insight_readonly SET statement_timeout = '5s';

\connect insight_test
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO insight;
