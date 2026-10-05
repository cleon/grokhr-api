-- Fictional people only. example.com addresses, not real PII.
INSERT INTO employees (first_name, last_name, email, department, title, hire_date, status)
VALUES
    ('Maya', 'Chen', 'maya.chen@example.com', 'People', 'People Partner', '2019-03-12', 'active'),
    ('Luis', 'Ortega', 'luis.ortega@example.com', 'Engineering', 'Software Engineer', '2021-06-01', 'active'),
    ('Priya', 'Nair', 'priya.nair@example.com', 'Engineering', 'Engineering Manager', '2018-11-20', 'active'),
    ('Jonah', 'Blake', 'jonah.blake@example.com', 'Finance', 'Payroll Specialist', '2022-02-14', 'active'),
    ('Samira', 'Haddad', 'samira.haddad@example.com', 'Design', 'Product Designer', '2020-09-08', 'active'),
    ('Owen', 'Park', 'owen.park@example.com', 'Engineering', 'Site Reliability Engineer', '2023-04-17', 'active'),
    ('Elena', 'Voss', 'elena.voss@example.com', 'People', 'HR Coordinator', '2024-01-09', 'inactive');

-- Reporting lines: engineering reports to Priya; Elena reports to Maya.
UPDATE employees
SET manager_id = (SELECT id FROM employees WHERE email = 'priya.nair@example.com')
WHERE email IN ('luis.ortega@example.com', 'owen.park@example.com');

UPDATE employees
SET manager_id = (SELECT id FROM employees WHERE email = 'maya.chen@example.com')
WHERE email = 'elena.voss@example.com';
