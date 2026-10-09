import re
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import SCHEMA_PATH, connect, init_db
from app.main import create_app

E164 = re.compile(r"\+[1-9]\d{1,14}")

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
    assert len(listed.json()) == SEEDED
    assert all("phone" not in row for row in listed.json())

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
        "phone",
    }
    assert body["status"] == "active"
    assert body["phone"] is None
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
    deactivated_again = client.post(f"/employees/{employee_id}/deactivate")
    assert deactivated_again.status_code == 200
    assert deactivated_again.json()["status"] == "inactive"

    roster = client.get("/employees", params={"status": "active"})
    assert roster.status_code == 200
    assert employee_id not in [row["id"] for row in roster.json()]

    reactivated = client.patch(f"/employees/{employee_id}", json={"status": "active"})
    assert reactivated.status_code == 200
    assert reactivated.json()["status"] == "active"
    roster_again = client.get("/employees", params={"status": "active"})
    assert employee_id in [row["id"] for row in roster_again.json()]


def test_active_roster_matches_view(client: TestClient):
    conn = connect(client.app.state.database)
    try:
        kind = conn.execute(
            "SELECT type FROM sqlite_master WHERE name = 'active_roster'"
        ).fetchone()
        assert kind[0] == "view"
        view_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'active_roster'"
        ).fetchone()[0]
        assert "phone" not in view_sql
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
    assert all("phone" not in row for row in response.json())


def test_missing_employee(client: TestClient):
    assert client.get("/employees/9999").status_code == 404
    assert client.patch("/employees/9999", json={"title": "Nope"}).status_code == 404
    assert client.post("/employees/9999/deactivate").status_code == 404


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
    assert "post" in paths["/employees/{employee_id}/deactivate"]
    properties = spec["components"]["schemas"]["Employee"]["properties"]
    assert "firstName" in properties
    assert "hireDate" in properties
    assert "first_name" not in properties
    assert "phone" not in properties
    detail = spec["components"]["schemas"]["EmployeeDetail"]["properties"]
    assert "phone" in detail
    get_ref = paths["/employees/{employee_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    assert get_ref.endswith("/EmployeeDetail")
    list_ref = paths["/employees"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["items"]["$ref"]
    assert list_ref.endswith("/Employee")


def test_schema_file_defines_view():
    schema = SCHEMA_PATH.read_text()
    assert "CREATE VIEW" in schema
    assert "active_roster" in schema
    assert "CREATE TABLE" in schema
    assert re.search(r"phone\s+TEXT\b", schema)
    assert "phone TEXT NOT NULL" not in schema
    view = schema.split("CREATE VIEW", 1)[1]
    assert "phone" not in view


def _employee_payload(**overrides):
    payload = {
        "firstName": "Ada",
        "lastName": "Example",
        "email": "ada.phone@example.com",
        "department": "Engineering",
        "title": "Engineer",
        "hireDate": "2024-05-06",
    }
    payload.update(overrides)
    return payload


def test_phone_create_read_patch_and_validation(client: TestClient):
    created = client.post("/employees", json=_employee_payload(phone="+15551234567"))
    assert created.status_code == 201
    body = created.json()
    assert body["phone"] == "+15551234567"
    employee_id = body["id"]

    fetched = client.get(f"/employees/{employee_id}")
    assert fetched.status_code == 200
    assert fetched.json()["phone"] == "+15551234567"

    listed = client.get("/employees").json()
    match = next(row for row in listed if row["id"] == employee_id)
    assert "phone" not in match

    updated = client.patch(
        f"/employees/{employee_id}",
        json={"phone": "+442079460958"},
    )
    assert updated.status_code == 200
    assert updated.json()["phone"] == "+442079460958"
    assert client.get(f"/employees/{employee_id}").json()["phone"] == "+442079460958"

    cleared = client.patch(f"/employees/{employee_id}", json={"phone": None})
    assert cleared.status_code == 200
    assert cleared.json()["phone"] is None
    assert client.get(f"/employees/{employee_id}").json()["phone"] is None

    invalid_create = client.post(
        "/employees",
        json=_employee_payload(email="ada.badphone@example.com", phone="5551234567"),
    )
    assert invalid_create.status_code == 422
    assert "E.164" in invalid_create.text

    invalid_patch = client.patch(
        f"/employees/{employee_id}",
        json={"phone": "555-123-4567"},
    )
    assert invalid_patch.status_code == 422
    assert "phone must be E.164" in invalid_patch.text
    assert client.get(f"/employees/{employee_id}").json()["phone"] is None

    null_title = client.patch(f"/employees/{employee_id}", json={"title": None})
    assert null_title.status_code == 422


def test_seed_employees_have_e164_phones(client: TestClient):
    listed = client.get("/employees")
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == SEEDED
    phones = set()
    for row in rows:
        assert "phone" not in row
        detail = client.get(f"/employees/{row['id']}")
        assert detail.status_code == 200
        phone = detail.json()["phone"]
        assert E164.fullmatch(phone)
        phones.add(phone)
    assert len(phones) == SEEDED


def test_startup_adds_phone_column(tmp_path):
    database = tmp_path / "legacy.db"
    conn = sqlite3.connect(database)
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
            status TEXT NOT NULL
        );
        INSERT INTO employees (
            first_name, last_name, email, department, title, hire_date, status
        ) VALUES (
            'Ada', 'Legacy', 'ada.legacy@example.com', 'Engineering', 'Engineer',
            '2020-01-02', 'active'
        );
        """
    )
    conn.commit()
    conn.close()

    app = create_app(database=str(database))
    with TestClient(app) as client:
        listed = client.get("/employees")
        assert listed.status_code == 200
        assert len(listed.json()) == 1
        assert "phone" not in listed.json()[0]

        detail = client.get("/employees/1")
        assert detail.status_code == 200
        assert detail.json()["phone"] is None
        assert detail.json()["email"] == "ada.legacy@example.com"

        roster = client.get("/employees", params={"status": "active"})
        assert roster.status_code == 200
        assert [row["id"] for row in roster.json()] == [1]
        assert "phone" not in roster.json()[0]

    again = connect(str(database))
    try:
        init_db(again)
        names = [row[1] for row in again.execute("PRAGMA table_info(employees)")]
        assert names.count("phone") == 1
        stored = again.execute("SELECT phone FROM employees WHERE id = 1").fetchone()[0]
        assert stored is None
    finally:
        again.close()
