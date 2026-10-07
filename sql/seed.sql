-- Fictional people only. example.com addresses, not real PII.
INSERT INTO employees (
    first_name, last_name, email, department, title, hire_date, status, deactivated_at
)
VALUES
    ('Maya', 'Chen', 'maya.chen@example.com', 'People', 'People Partner', '2019-03-12', 'active', NULL),
    ('Luis', 'Ortega', 'luis.ortega@example.com', 'Engineering', 'Software Engineer', '2021-06-01', 'active', NULL),
    ('Priya', 'Nair', 'priya.nair@example.com', 'Engineering', 'Engineering Manager', '2018-11-20', 'active', NULL),
    ('Jonah', 'Blake', 'jonah.blake@example.com', 'Finance', 'Payroll Specialist', '2022-02-14', 'active', NULL),
    ('Samira', 'Haddad', 'samira.haddad@example.com', 'Design', 'Product Designer', '2020-09-08', 'active', NULL),
    ('Owen', 'Park', 'owen.park@example.com', 'Engineering', 'Site Reliability Engineer', '2023-04-17', 'active', NULL),
    ('Elena', 'Voss', 'elena.voss@example.com', 'People', 'HR Coordinator', '2024-01-09', 'inactive', '2025-06-30T17:00:00Z');
