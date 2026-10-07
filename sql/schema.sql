-- GrokHR demo schema. Fictional employees only.
-- Production employee fields are expected to match cleon/grokhr-shared.

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    department TEXT NOT NULL,
    title TEXT NOT NULL,
    hire_date TEXT NOT NULL CHECK (hire_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
    -- UTC timestamp of the latest soft-delete. Null until that happens.
    -- Kept after a later reactivation so the departure stays on the record.
    deactivated_at TEXT
);

-- Active roster: employees an HR person treats as currently employed.
-- GET /employees and GET /employees?status=active read this view.
-- Drop and recreate so an existing database picks up deactivated_at.
DROP VIEW IF EXISTS active_roster;
CREATE VIEW active_roster AS
SELECT
    id,
    first_name,
    last_name,
    email,
    department,
    title,
    hire_date,
    status,
    deactivated_at
FROM employees
WHERE status = 'active';
