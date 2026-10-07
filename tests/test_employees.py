import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import SCHEMA_PATH, connect, init_db
from app.main import create_app

SEEDED = 7
SEEDED_ACTIVE = 6


@pytest.fixture(params=["memory", "file"])
def client(request, tmp_path):
    if request.param == "memory":
        database = f"file:grokhr-{uuid.uuid4().hex}?mode=memory&cache=shared"
    else:
        database = str(tmp_path / "grokhr.db")
    app = create_app(database=database)
    with TestClient(app) as test_client:
        yield test_client


def test_crud_happy_path(client: TestClient):
    listed = client.get("/employees")
    assert listed.status_code == 200
    assert len(listed.json()) == SEEDED_ACTIVE

    created = client.post(
        "/employees",
        json={
            "firstName": "Ada",
            "lastName": "Example",
            "email": "ada.example@example.com",
            "department": "Engineering",
            "title": "Engineer",
            "hireDate": "2024-05-06",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert set(body) == {
        "id",
        "firstName",
        "lastName",
        "email",
        "department",
        "title",
        "hireDate",
        "status",
        "deactivatedAt",
    }
    assert body["status"] == "active"
    assert body["deactivatedAt"] is None
    employee_id = body["id"]

    fetched = client.get(f"/employees/{employee_id}")
    assert fetched.status_code == 200
    assert fetched.json()["email"] == "ada.example@example.com"

    patched = client.patch(
        f"/employees/{employee_id}",
        json={"title": "Staff Engineer", "department": "Platform"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Staff Engineer"
    assert patched.json()["lastName"] == "Example"

    deactivated = client.post(f"/employees/{employee_id}/deactivate")
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "inactive"
    stamp = deactivated.json()["deactivatedAt"]
    assert stamp
    deactivated_again = client.post(f"/employees/{employee_id}/deactivate")
    assert deactivated_again.status_code == 200
    assert deactivated_again.json()["status"] == "inactive"
    assert deactivated_again.json()["deactivatedAt"] == stamp

    roster = client.get("/employees", params={"status": "active"})
    assert roster.status_code == 200
    assert employee_id not in [row["id"] for row in roster.json()]

    reactivated = client.patch(f"/employees/{employee_id}", json={"status": "active"})
    assert reactivated.status_code == 200
    assert reactivated.json()["status"] == "active"
    assert reactivated.json()["deactivatedAt"] == stamp
    roster_again = client.get("/employees", params={"status": "active"})
    assert employee_id in [row["id"] for row in roster_again.json()]


def test_active_roster_matches_view(client: TestClient):
    conn = connect(client.app.state.database)
    try:
        kind = conn.execute(
            "SELECT type FROM sqlite_master WHERE name = 'active_roster'"
        ).fetchone()
        assert kind[0] == "view"
        view_ids = [row[0] for row in conn.execute("SELECT id FROM active_roster").fetchall()]
    finally:
        conn.close()

    response = client.get("/employees", params={"status": "active"})
    assert response.status_code == 200
    api_ids = [row["id"] for row in response.json()]
    assert sorted(api_ids) == sorted(view_ids)
    assert len(api_ids) == SEEDED_ACTIVE
    emails = {row["email"] for row in response.json()}
    assert "elena.voss@example.com" not in emails
    assert "maya.chen@example.com" in emails


def test_missing_employee(client: TestClient):
    assert client.get("/employees/9999").status_code == 404
    assert client.patch("/employees/9999", json={"title": "Nope"}).status_code == 404
    assert client.post("/employees/9999/deactivate").status_code == 404
    assert client.delete("/employees/9999").status_code == 404


def test_duplicate_email(client: TestClient):
    payload = {
        "firstName": "Maya",
        "lastName": "Chen",
        "email": "maya.chen@example.com",
        "department": "People",
        "title": "People Partner",
        "hireDate": "2019-03-12",
    }
    conflict = client.post("/employees", json=payload)
    assert conflict.status_code == 409


def test_create_rejects_incomplete_body(client: TestClient):
    response = client.post("/employees", json={"firstName": "Only"})
    assert response.status_code == 422


def test_openapi_documents_routes(client: TestClient):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["info"]["title"] == "GrokHR API"
    paths = spec["paths"]
    assert "get" in paths["/employees"]
    assert "post" in paths["/employees"]
    assert "get" in paths["/employees/{employee_id}"]
    assert "patch" in paths["/employees/{employee_id}"]
    assert "delete" in paths["/employees/{employee_id}"]
    assert "204" in paths["/employees/{employee_id}"]["delete"]["responses"]
    assert "post" in paths["/employees/{employee_id}/deactivate"]
    list_params = {param["name"] for param in paths["/employees"]["get"]["parameters"]}
    assert "includeInactive" in list_params
    assert "status" in list_params
    properties = spec["components"]["schemas"]["Employee"]["properties"]
    assert "firstName" in properties
    assert "hireDate" in properties
    assert "deactivatedAt" in properties
    assert "first_name" not in properties


def test_schema_file_defines_view():
    schema = SCHEMA_PATH.read_text()
    assert "CREATE VIEW" in schema
    assert "active_roster" in schema
    assert "CREATE TABLE" in schema
    assert "deactivated_at" in schema


def test_list_hides_inactive_unless_requested(client: TestClient):
    active = client.get("/employees")
    assert active.status_code == 200
    active_emails = {row["email"] for row in active.json()}
    assert "elena.voss@example.com" not in active_emails
    assert len(active.json()) == SEEDED_ACTIVE
    assert all(row["status"] == "active" for row in active.json())

    everyone = client.get("/employees", params={"includeInactive": "true"})
    assert everyone.status_code == 200
    assert len(everyone.json()) == SEEDED
    elena = next(row for row in everyone.json() if row["email"] == "elena.voss@example.com")
    assert elena["status"] == "inactive"
    assert elena["deactivatedAt"] == "2025-06-30T17:00:00Z"

    fetched = client.get(f"/employees/{elena['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "inactive"
    assert fetched.json()["deactivatedAt"] == "2025-06-30T17:00:00Z"

    explicit = client.get("/employees", params={"includeInactive": "false"})
    assert {row["id"] for row in explicit.json()} == {row["id"] for row in active.json()}

    inactive_only = client.get(
        "/employees", params={"status": "inactive", "includeInactive": "true"}
    )
    assert inactive_only.status_code == 200
    assert [row["email"] for row in inactive_only.json()] == ["elena.voss@example.com"]


def test_delete_soft_deletes_and_is_idempotent(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    listed = client.get("/employees")
    target = next(row for row in listed.json() if row["email"] == "maya.chen@example.com")
    employee_id = target["id"]

    monkeypatch.setattr("app.db._utc_now", lambda: "2026-04-01T12:00:00Z")
    deleted = client.delete(f"/employees/{employee_id}")
    assert deleted.status_code == 204
    assert deleted.content == b""

    fetched = client.get(f"/employees/{employee_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["status"] == "inactive"
    assert body["deactivatedAt"] == "2026-04-01T12:00:00Z"
    assert body["email"] == "maya.chen@example.com"

    active = client.get("/employees")
    assert employee_id not in {row["id"] for row in active.json()}
    everyone = client.get("/employees", params={"includeInactive": "true"})
    match = next(row for row in everyone.json() if row["id"] == employee_id)
    assert match["deactivatedAt"] == "2026-04-01T12:00:00Z"

    conn = connect(client.app.state.database)
    try:
        row = conn.execute(
            "SELECT status, deactivated_at FROM employees WHERE id = ?",
            (employee_id,),
        ).fetchone()
        assert row["status"] == "inactive"
        assert row["deactivated_at"] == "2026-04-01T12:00:00Z"
    finally:
        conn.close()

    monkeypatch.setattr("app.db._utc_now", lambda: "2026-05-01T12:00:00Z")
    again = client.delete(f"/employees/{employee_id}")
    assert again.status_code == 204
    assert client.get(f"/employees/{employee_id}").json()["deactivatedAt"] == "2026-04-01T12:00:00Z"

    rehired = client.patch(f"/employees/{employee_id}", json={"status": "active"})
    assert rehired.status_code == 200
    assert rehired.json()["status"] == "active"
    assert rehired.json()["deactivatedAt"] == "2026-04-01T12:00:00Z"
    assert employee_id in {row["id"] for row in client.get("/employees").json()}

    removed_again = client.delete(f"/employees/{employee_id}")
    assert removed_again.status_code == 204
    assert client.get(f"/employees/{employee_id}").json()["deactivatedAt"] == "2026-05-01T12:00:00Z"


def test_existing_database_gains_deactivated_at(tmp_path):
    database = str(tmp_path / "legacy.db")
    conn = connect(database)
    conn.executescript(
        """
        CREATE TABLE employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            department TEXT NOT NULL,
            title TEXT NOT NULL,
            hire_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'inactive'))
        );
        CREATE VIEW active_roster AS
        SELECT id, first_name, last_name, email, department, title, hire_date, status
        FROM employees
        WHERE status = 'active';
        INSERT INTO employees (
            first_name, last_name, email, department, title, hire_date, status
        ) VALUES (
            'Legacy', 'Person', 'legacy.person@example.com', 'People', 'Coordinator',
            '2020-01-01', 'inactive'
        );
        """
    )
    conn.commit()
    conn.close()

    conn = connect(database)
    try:
        init_db(conn)
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(employees)")]
        assert "deactivated_at" in columns
        view_columns = [row["name"] for row in conn.execute("PRAGMA table_info(active_roster)")]
        assert "deactivated_at" in view_columns
        row = conn.execute(
            "SELECT status, deactivated_at FROM employees WHERE email = 'legacy.person@example.com'"
        ).fetchone()
        assert row["status"] == "inactive"
        assert row["deactivated_at"] is None
        assert conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 1
    finally:
        conn.close()
