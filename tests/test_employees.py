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
    assert "hireDate" in properties
    assert "first_name" not in properties


def test_schema_file_defines_view():
    schema = SCHEMA_PATH.read_text()
    assert "CREATE VIEW" in schema
    assert "active_roster" in schema
    assert "CREATE TABLE" in schema
