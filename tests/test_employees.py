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
    assert len(listed.json()) == SEEDED_ACTIVE
    assert {row["status"] for row in listed.json()} == {"active"}

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
    }
    assert body["status"] == "active"
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

    directory = client.get("/employees")
    assert directory.status_code == 200
    assert employee_id not in [row["id"] for row in directory.json()]

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

    default = client.get("/employees")
    assert default.status_code == 200
    assert [row["id"] for row in default.json()] == api_ids


def test_directory_status_filter(client: TestClient):
    default = client.get("/employees")
    assert default.status_code == 200
    assert len(default.json()) == SEEDED_ACTIVE
    assert "elena.voss@example.com" not in {row["email"] for row in default.json()}

    inactive = client.get("/employees", params={"status": "inactive"})
    assert inactive.status_code == 200
    inactive_rows = inactive.json()
    assert len(inactive_rows) == SEEDED - SEEDED_ACTIVE
    assert {row["status"] for row in inactive_rows} == {"inactive"}
    assert "elena.voss@example.com" in {row["email"] for row in inactive_rows}
    fetched = client.get(f"/employees/{inactive_rows[0]['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "inactive"

    everyone = client.get("/employees", params={"status": "all"})
    assert everyone.status_code == 200
    everyone_rows = everyone.json()
    assert len(everyone_rows) == SEEDED
    assert {row["status"] for row in everyone_rows} == {"active", "inactive"}
    assert {row["id"] for row in everyone_rows} == {
        row["id"] for row in default.json()
    } | {row["id"] for row in inactive_rows}

    rejected = client.get("/employees", params={"status": "terminated"})
    assert rejected.status_code == 422


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
    employee_status = spec["components"]["schemas"]["EmployeeStatus"]
    assert employee_status["enum"] == ["active", "inactive"]

    operation = paths["/employees"]["get"]
    assert "terminated" in operation["description"].lower()
    status_param = next(param for param in operation["parameters"] if param["name"] == "status")
    assert status_param["in"] == "query"
    assert status_param["required"] is False
    description = status_param["description"].lower()
    assert "active" in description
    assert "all" in description
    schema = status_param["schema"]
    assert schema["default"] == "active"
    directory_status = spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
    assert directory_status["enum"] == ["active", "inactive", "all"]


def test_schema_file_defines_view():
    schema = SCHEMA_PATH.read_text()
    assert "CREATE VIEW" in schema
    assert "active_roster" in schema
    assert "CREATE TABLE" in schema
