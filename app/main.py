"""GrokHR demo API. No auth. Fictional employees only."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import TypeVar

from fastapi import Depends, FastAPI, HTTPException, Query, Request

from app.db import (
    connect,
    deactivate_employee,
    fetch_employee,
    fetch_employees,
    init_db,
    insert_employee,
    patch_employee,
)
from app.models import EmployeeCreate, EmployeeDetail, EmployeeUpdate
from grokhr_shared import Employee, EmployeeStatus

EmployeeT = TypeVar("EmployeeT", bound=Employee)

# Shared-cache memory DB. Override with a filesystem path to persist across restarts.
DEFAULT_DATABASE = "file:grokhr?mode=memory&cache=shared"


def create_app(database: str | None = None) -> FastAPI:
    db_path = database or os.environ.get("GROKHR_DATABASE", DEFAULT_DATABASE)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Hold one connection so the in-memory database survives between requests.
        keeper = connect(db_path)
        init_db(keeper)
        app.state.keeper = keeper
        try:
            yield
        finally:
            keeper.close()

    app = FastAPI(
        title="GrokHR API",
        version="0.1.0",
        summary="Manage fictional employees for the GrokHR demo.",
        description=(
            "HR person lists, creates, updates, and deactivates employees. "
            "Fictional data only. No authentication. No real PII. "
            "Production would depend on cleon/grokhr-shared; this demo vendors "
            "a compatible model in grokhr_shared.py. "
            "GET /employees?status=active reads the active_roster SQL view. "
            "Optional phone is E.164, accepted on create and PATCH, returned by "
            "GET /employees/{id}, and omitted from GET /employees."
        ),
        lifespan=lifespan,
    )
    app.state.database = db_path

    def get_db(request: Request) -> Iterator[sqlite3.Connection]:
        conn = connect(request.app.state.database)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def require_employee(employee: EmployeeT | None) -> EmployeeT:
        if employee is None:
            raise HTTPException(status_code=404, detail="employee not found")
        return employee

    @app.get("/employees", response_model=list[Employee], tags=["employees"])
    def list_employees(
        status: EmployeeStatus | None = Query(
            default=None,
            description="Filter by status. `active` reads the active_roster SQL view.",
        ),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> list[Employee]:
        return fetch_employees(conn, status)

    @app.post(
        "/employees",
        response_model=EmployeeDetail,
        status_code=201,
        tags=["employees"],
    )
    def create_employee(
        body: EmployeeCreate,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> EmployeeDetail:
        """Create an employee. Optional phone must be E.164."""
        try:
            return insert_employee(conn, body.model_dump())
        except sqlite3.IntegrityError as exc:
            if "employees.email" in str(exc):
                raise HTTPException(status_code=409, detail="email already exists") from exc
            raise HTTPException(status_code=400, detail="invalid employee") from exc

    @app.get(
        "/employees/{employee_id}",
        response_model=EmployeeDetail,
        tags=["employees"],
    )
    def get_employee(
        employee_id: int,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> EmployeeDetail:
        """Fetch one employee, including phone when set."""
        return require_employee(fetch_employee(conn, employee_id))

    @app.patch(
        "/employees/{employee_id}",
        response_model=EmployeeDetail,
        tags=["employees"],
    )
    def update_employee(
        employee_id: int,
        body: EmployeeUpdate,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> EmployeeDetail:
        """Partial update. Null phone clears the stored number."""
        fields = body.model_dump(exclude_unset=True)
        # phone is the only field that accepts null; null clears the stored number.
        if any(value is None for key, value in fields.items() if key != "phone"):
            raise HTTPException(status_code=422, detail="fields cannot be null")
        try:
            return require_employee(patch_employee(conn, employee_id, fields))
        except sqlite3.IntegrityError as exc:
            if "employees.email" in str(exc):
                raise HTTPException(status_code=409, detail="email already exists") from exc
            raise HTTPException(status_code=400, detail="invalid employee") from exc

    @app.post(
        "/employees/{employee_id}/deactivate",
        response_model=Employee,
        tags=["employees"],
    )
    def deactivate(
        employee_id: int,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Employee:
        # Idempotent: deactivating an already inactive employee returns that row.
        return require_employee(deactivate_employee(conn, employee_id))

    return app


app = create_app()
