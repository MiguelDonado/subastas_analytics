-- =============================================================================
-- Database user of the Shiny app: reads gold, reads app.users, and reads and modifies app.lot_reviews
-- (PostgreSQL)
--
-- Principle of least privilege: the app gets only the permissions it needs to
-- work, and nothing more.
--
-- How to use it:
--   1. Run create_app.sql first.
--   2. Run this file once, connected as the pipeline's user.
--   3. Set the password in psql: \password subastas_app
-- The password isn't written here, so it doesn't end up in git.
-- =============================================================================

-- Create database user named "subastas_app"
-- LOGIN: allows this role to connect to the db as a user
-- No password is specified here. It will be configured manually later, so it is not stored in SQL file or git
CREATE ROLE subastas_app LOGIN;

-- No access to bronze or silver: nothing is granted on them, so the app can't read or change them

-- -----------------------------------------------------------------------------
-- gold: read only
-- -----------------------------------------------------------------------------

-- Allow access to the schema  (this permission alone does not allow it to read tables)
GRANT USAGE ON SCHEMA gold TO subastas_app;
-- Allow reading all existing tables (views included)
GRANT SELECT ON ALL TABLES IN SCHEMA gold TO subastas_app;

-- Automatically grant permissions on future tables
-- Example: Imagine next month your data pipeline creates a new view
-- Without additional permissions, "subastas_app" would not automatically be able to read this view
-- ALTER DEFAULT PRIVILEGES: Solves this problem
ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT SELECT ON TABLES TO subastas_app;

-- -----------------------------------------------------------------------------
-- app: read the users for the login, read and write the notes
-- -----------------------------------------------------------------------------
-- Allow access to the schema
GRANT USAGE ON SCHEMA app TO subastas_app;
-- Read user information
GRANT SELECT ON app.users TO subastas_app;  -- users are created by hand, never by the app
-- Read and modify reviews
GRANT SELECT, INSERT, UPDATE, DELETE ON app.lot_reviews TO subastas_app;