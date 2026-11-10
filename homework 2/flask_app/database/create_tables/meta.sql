-- meta.sql
-- This file contains the SQL statements to create the meta table.
CREATE TABLE IF NOT EXISTS meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
)
