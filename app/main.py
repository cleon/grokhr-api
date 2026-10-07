"""GrokHR demo API. No auth. Fictional employees only."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response

from app.db import (
    connect,
    deactivate_employee,
    fetch_employee,
    fetch_employees,
    init_db,
    insert_employee,
    patch_employee,
)
from grokhr_shared import Employee, EmployeeCreate, EmployeeStatus, EmployeeUpdate

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
            "DELETE /employees/{id} keeps the row, sets status to inactive, and "
            "records deactivatedAt in UTC. Repeating it does not move that timestamp. "
            "GET /employees returns active employees unless includeInactive=true. "
            "GET /employees?status=active reads the active_roster SQL view."
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

    def require_employee(employee: Employee | None) -> Employee:
        if employee is None:
            raise HTTPException(status_code=404, detail="employee not found")
        return employee

    @app.get("/employees", response_model=list[Employee], tags=["employees"])
    def list_employees(
        status: EmployeeStatus | None = Query(
            default=None,
            description=(
                "Filter by status. `active` reads the active_roster SQL view. "
                "When set, this is the whole filter."
            ),
        ),
        include_inactive: bool = Query(
            default=False,
            alias="includeInactive",
            description=(
                "Include inactive employees. Used only when status is omitted; "
                "otherwise the status filter stands on its own."
            ),
        ),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> list[Employee]:
        """Active employees by default. Pass includeInactive=true for the full history."""
        return fetch_employees(conn, status, include_inactive)

    @app.post("/employees", response_model=Employee, status_code=201, tags=["employees"])
    def create_employee(
        body: EmployeeCreate,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Employee:
        try:
            return insert_employee(conn, body.model_dump())
        except sqlite3.IntegrityError as exc:
            if "employees.email" in str(exc):
                raise HTTPException(status_code=409, detail="email already exists") from exc
            raise HTTPException(status_code=400, detail="invalid employee") from exc

    @app.get("/employees/{employee_id}", response_model=Employee, tags=["employees"])
    def get_employee(
        employee_id: int,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Employee:
        return require_employee(fetch_employee(conn, employee_id))

    @app.patch("/employees/{employee_id}", response_model=Employee, tags=["employees"])
    def update_employee(
        employee_id: int,
        body: EmployeeUpdate,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Employee:
        fields = body.model_dump(exclude_unset=True)
        if any(value is None for value in fields.values()):
            raise HTTPException(status_code=422, detail="fields cannot be null")
        try:
            return require_employee(patch_employee(conn, employee_id, fields))
        except sqlite3.IntegrityError as exc:
            if "employees.email" in str(exc):
                raise HTTPException(status_code=409, detail="email already exists") from exc
            raise HTTPException(status_code=400, detail="invalid employee") from exc

    @app.delete("/employees/{employee_id}", status_code=204, tags=["employees"])
    def delete_employee(
        employee_id: int,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Response:
        """Soft-delete an employee.

        Sets status to inactive and records deactivatedAt in UTC. The row stays.
        An employee who is already inactive keeps the existing timestamp.
        Unknown ids return 404.
        """
        if deactivate_employee(conn, employee_id) is None:
            raise HTTPException(status_code=404, detail="employee not found")
        return Response(status_code=204)

    @app.post(
        "/employees/{employee_id}/deactivate",
        response_model=Employee,
        tags=["employees"],
    )
    def deactivate(
        employee_id: int,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Employee:
        """Soft-delete an employee and return the row. Same rules as DELETE."""
        return require_employee(deactivate_employee(conn, employee_id))

    return app


app = create_app()
