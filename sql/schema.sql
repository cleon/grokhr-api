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
    manager_id TEXT
);

-- Active roster: employees an HR person treats as currently employed.
-- GET /employees?status=active reads this view.
CREATE VIEW IF NOT EXISTS active_roster AS
SELECT
    id,
    first_name,
    last_name,
    email,
    department,
    title,
    hire_date,
    status,
    manager_id
FROM employees
WHERE status = 'active';
