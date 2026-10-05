import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import SCHEMA_PATH, connect
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
    assert len(listed.json()) == SEEDED

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
        "preferredName",
        "lastName",
        "email",
        "department",
        "title",
        "hireDate",
        "status",
    }
    assert body["status"] == "active"
    assert body["preferredName"] is None
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
    assert "preferredName" in properties
    assert "hireDate" in properties
    assert "first_name" not in properties
    assert "preferredName" not in spec["components"]["schemas"]["Employee"].get("required", [])


def test_schema_file_defines_view():
    schema = SCHEMA_PATH.read_text()
    assert "CREATE VIEW" in schema
    assert "active_roster" in schema
    assert "CREATE TABLE" in schema
    assert "preferred_name" in schema


def _employee_payload(email: str, **extra: object) -> dict:
    payload = {
        "firstName": "Ada",
        "lastName": "Example",
        "email": email,
        "department": "Engineering",
        "title": "Engineer",
        "hireDate": "2024-05-06",
    }
    payload.update(extra)
    return payload


def test_preferred_name_round_trip(client: TestClient):
    created = client.post(
        "/employees",
        json=_employee_payload(
            "addy.example@example.com",
            preferredName="  Addy ",
        ),
    )
    assert created.status_code == 201
    body = created.json()
    employee_id = body["id"]
    assert body["preferredName"] == "Addy"
    assert body["firstName"] == "Ada"

    fetched = client.get(f"/employees/{employee_id}")
    assert fetched.status_code == 200
    assert fetched.json()["preferredName"] == "Addy"

    listed = client.get("/employees")
    assert listed.status_code == 200
    listed_row = next(row for row in listed.json() if row["id"] == employee_id)
    assert listed_row["preferredName"] == "Addy"

    roster = client.get("/employees", params={"status": "active"})
    assert roster.status_code == 200
    roster_row = next(row for row in roster.json() if row["id"] == employee_id)
    assert roster_row["preferredName"] == "Addy"

    kept = client.patch(f"/employees/{employee_id}", json={"title": "Staff Engineer"})
    assert kept.status_code == 200
    assert kept.json()["preferredName"] == "Addy"
    assert kept.json()["title"] == "Staff Engineer"

    cleared = client.patch(f"/employees/{employee_id}", json={"preferredName": None})
    assert cleared.status_code == 200
    assert cleared.json()["preferredName"] is None
    assert client.get(f"/employees/{employee_id}").json()["preferredName"] is None

    restored = client.patch(f"/employees/{employee_id}", json={"preferredName": "Addy"})
    assert restored.status_code == 200
    assert restored.json()["preferredName"] == "Addy"
    blank = client.patch(f"/employees/{employee_id}", json={"preferredName": "   "})
    assert blank.status_code == 200
    assert blank.json()["preferredName"] is None


@pytest.mark.parametrize("preferred", [None, "", "   "])
def test_create_preferred_name_unset(client: TestClient, preferred: str | None):
    response = client.post(
        "/employees",
        json=_employee_payload(f"ada-{uuid.uuid4().hex}@example.com", preferredName=preferred),
    )
    assert response.status_code == 201
    assert response.json()["preferredName"] is None


def test_create_omits_preferred_name(client: TestClient):
    response = client.post(
        "/employees",
        json=_employee_payload(f"ada-{uuid.uuid4().hex}@example.com"),
    )
    assert response.status_code == 201
    assert response.json()["preferredName"] is None


def test_seeded_preferred_name(client: TestClient):
    listed = client.get("/employees")
    assert listed.status_code == 200
    by_email = {row["email"]: row for row in listed.json()}
    assert by_email["maya.chen@example.com"]["preferredName"] == "Mai"
    assert by_email["luis.ortega@example.com"]["preferredName"] is None

    roster = client.get("/employees", params={"status": "active"})
    assert roster.status_code == 200
    roster_by_email = {row["email"]: row for row in roster.json()}
    assert roster_by_email["maya.chen@example.com"]["preferredName"] == "Mai"
    assert "elena.voss@example.com" not in roster_by_email


def test_patch_null_still_rejected_for_other_fields(client: TestClient):
    employee_id = client.get("/employees").json()[0]["id"]
    assert client.patch(f"/employees/{employee_id}", json={"firstName": None}).status_code == 422
    assert client.patch(f"/employees/{employee_id}", json={"hireDate": None}).status_code == 422
    assert client.patch(f"/employees/{employee_id}", json={"status": None}).status_code == 422


def test_preferred_name_too_long(client: TestClient):
    response = client.post(
        "/employees",
        json=_employee_payload(
            f"ada-{uuid.uuid4().hex}@example.com",
            preferredName="n" * 81,
        ),
    )
    assert response.status_code == 422


def test_legacy_database_adds_preferred_name(tmp_path):
    database = str(tmp_path / "legacy.db")
    conn = connect(database)
    conn.executescript(
        """
        CREATE TABLE employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            department TEXT NOT NULL,
            title TEXT NOT NULL,
            hire_date TEXT NOT NULL,
            status TEXT NOT NULL
        );
        CREATE VIEW active_roster AS
        SELECT id, first_name, last_name, email, department, title, hire_date, status
        FROM employees
        WHERE status = 'active';
        INSERT INTO employees (
            first_name, last_name, email, department, title, hire_date, status
        ) VALUES
            ('Maya', 'Chen', 'maya.chen@example.com', 'People', 'People Partner', '2019-03-12', 'active'),
            ('Elena', 'Voss', 'elena.voss@example.com', 'People', 'HR Coordinator', '2024-01-09', 'inactive');
        """
    )
    conn.commit()
    conn.close()

    app = create_app(database=database)
    with TestClient(app) as legacy_client:
        listed = legacy_client.get("/employees")
        assert listed.status_code == 200
        by_email = {row["email"]: row for row in listed.json()}
        assert set(by_email) == {"maya.chen@example.com", "elena.voss@example.com"}
        assert by_email["maya.chen@example.com"]["preferredName"] is None
        assert by_email["maya.chen@example.com"]["hireDate"] == "2019-03-12"

        roster = legacy_client.get("/employees", params={"status": "active"})
        assert roster.status_code == 200
        roster_rows = roster.json()
        assert [row["email"] for row in roster_rows] == ["maya.chen@example.com"]
        assert roster_rows[0]["preferredName"] is None

        employee_id = by_email["maya.chen@example.com"]["id"]
        patched = legacy_client.patch(
            f"/employees/{employee_id}",
            json={"preferredName": "Mai"},
        )
        assert patched.status_code == 200
        assert patched.json()["preferredName"] == "Mai"
        assert patched.json()["hireDate"] == "2019-03-12"
        assert patched.json()["status"] == "active"
