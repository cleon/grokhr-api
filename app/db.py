"""SQLite access for the GrokHR demo.

Default database is in-memory and shared across connections in this process
(``file:grokhr?mode=memory&cache=shared``). A keeper connection stays open for
the app lifetime; SQLite drops a memory database when its last connection closes.
"""

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from grokhr_shared import Employee, EmployeeStatus

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "sql" / "schema.sql"
SEED_PATH = ROOT / "sql" / "seed.sql"

# Not user input. Used to build SELECT/UPDATE column lists.
EMPLOYEE_COLUMNS = (
    "id, first_name, last_name, email, department, title, hire_date, status, deactivated_at"
)
UPDATABLE_COLUMNS = frozenset(
    {"first_name", "last_name", "email", "department", "title", "hire_date", "status"}
)


def connect(database: str) -> sqlite3.Connection:
    if database.startswith("file:"):
        conn = sqlite3.connect(database, uri=True)
    else:
        conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_deactivated_at(conn: sqlite3.Connection) -> None:
    """Add deactivated_at to databases created before soft-delete.

    CREATE TABLE IF NOT EXISTS will not alter an existing table. The column
    has to land before schema.sql recreates active_roster, which selects it.
    """
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'employees'"
    ).fetchone()
    if table is None:
        return
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(employees)")}
    if "deactivated_at" not in columns:
        conn.execute("ALTER TABLE employees ADD COLUMN deactivated_at TEXT")


def init_db(conn: sqlite3.Connection) -> None:
    _ensure_deactivated_at(conn)
    conn.executescript(SCHEMA_PATH.read_text())
    count = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    if count == 0:
        conn.executescript(SEED_PATH.read_text())
    conn.commit()


def _employee(row: sqlite3.Row) -> Employee:
    return Employee(
        id=row["id"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        email=row["email"],
        department=row["department"],
        title=row["title"],
        hire_date=row["hire_date"],
        status=row["status"],
        deactivated_at=row["deactivated_at"],
    )


def _sql_value(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, EmployeeStatus):
        return value.value
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_employees(
    conn: sqlite3.Connection,
    status: EmployeeStatus | None = None,
    include_inactive: bool = False,
) -> list[Employee]:
    # No status filter means the active roster, unless the caller opted into history.
    # An explicit status is the whole filter; include_inactive does not widen it.
    if status is None and not include_inactive:
        status = EmployeeStatus.active
    # Active employees come from the view so the roster object stays on the read path.
    if status is EmployeeStatus.active:
        sql = f"SELECT {EMPLOYEE_COLUMNS} FROM active_roster ORDER BY last_name, first_name, id"
        rows = conn.execute(sql).fetchall()
    elif status is EmployeeStatus.inactive:
        sql = (
            f"SELECT {EMPLOYEE_COLUMNS} FROM employees "
            "WHERE status = 'inactive' ORDER BY last_name, first_name, id"
        )
        rows = conn.execute(sql).fetchall()
    else:
        sql = f"SELECT {EMPLOYEE_COLUMNS} FROM employees ORDER BY last_name, first_name, id"
        rows = conn.execute(sql).fetchall()
    return [_employee(row) for row in rows]


def fetch_employee(conn: sqlite3.Connection, employee_id: int) -> Employee | None:
    row = conn.execute(
        f"SELECT {EMPLOYEE_COLUMNS} FROM employees WHERE id = ?",
        (employee_id,),
    ).fetchone()
    if row is None:
        return None
    return _employee(row)


def insert_employee(conn: sqlite3.Connection, fields: dict) -> Employee:
    row = conn.execute(
        f"""
        INSERT INTO employees (first_name, last_name, email, department, title, hire_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        RETURNING {EMPLOYEE_COLUMNS}
        """,
        (
            fields["first_name"],
            fields["last_name"],
            fields["email"],
            fields["department"],
            fields["title"],
            _sql_value(fields["hire_date"]),
            _sql_value(fields["status"]),
        ),
    ).fetchone()
    return _employee(row)


def patch_employee(
    conn: sqlite3.Connection, employee_id: int, fields: dict
) -> Employee | None:
    if not fields:
        return fetch_employee(conn, employee_id)
    # Allowlist: SET identifiers must be column names, never request keys.
    unknown = set(fields) - UPDATABLE_COLUMNS
    if unknown:
        raise ValueError(f"unknown columns: {sorted(unknown)}")
    assignments = ", ".join(f"{column} = ?" for column in fields)
    values = [_sql_value(value) for value in fields.values()]
    values.append(employee_id)
    row = conn.execute(
        f"UPDATE employees SET {assignments} WHERE id = ? RETURNING {EMPLOYEE_COLUMNS}",
        values,
    ).fetchone()
    if row is None:
        return None
    return _employee(row)


def deactivate_employee(conn: sqlite3.Connection, employee_id: int) -> Employee | None:
    # CASE reads the pre-update status. Already-inactive rows keep their timestamp
    # so a second delete is a no-op; active rows, including rehires, record now.
    row = conn.execute(
        f"""
        UPDATE employees
        SET status = 'inactive',
            deactivated_at = CASE
                WHEN status = 'inactive' THEN deactivated_at
                ELSE ?
            END
        WHERE id = ?
        RETURNING {EMPLOYEE_COLUMNS}
        """,
        (_utc_now(), employee_id),
    ).fetchone()
    if row is None:
        return None
    return _employee(row)
