"""Vendored stand-in for the ``grokhr_shared`` employee contract.

NOTE: Production GrokHR API depends on cleon/grokhr-shared
(https://github.com/cleon/grokhr-shared). That repo does not publish an
employee model yet, so this module is a local compatible copy.
Sync field names, aliases, and EmployeeStatus from grokhr-shared when it lands.
"""

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator


class EmployeeStatus(str, Enum):
    active = "active"
    inactive = "inactive"


def _strip(value: str) -> str:
    return value.strip()


# Calendar date, the previous hireDate shape. Payroll exports need a timestamp.
_CALENDAR_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HIRE_DATE_ERROR = (
    "hireDate must be an ISO-8601 datetime with a timezone, for example 2024-03-15T00:00:00Z"
)


def _parse_hire_date(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if _CALENDAR_DATE.fullmatch(text):
            raise ValueError(_HIRE_DATE_ERROR)
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(_HIRE_DATE_ERROR) from exc
    else:
        raise ValueError(_HIRE_DATE_ERROR)
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    # Whole seconds keep the stored value and the wire value identical.
    return parsed.replace(microsecond=0)


def format_hire_date(value: datetime) -> str:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        value = value.replace(tzinfo=timezone.utc)
    utc = value.astimezone(timezone.utc).replace(microsecond=0)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


HireDate = Annotated[datetime, BeforeValidator(_parse_hire_date)]


class EmployeeBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    first_name: str = Field(alias="firstName", min_length=1, max_length=80)
    last_name: str = Field(alias="lastName", min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=80)
    hire_date: HireDate = Field(
        alias="hireDate",
        description="UTC hire timestamp, ISO-8601, for example 2024-03-15T00:00:00Z.",
        examples=["2024-03-15T00:00:00Z"],
    )
    status: EmployeeStatus = EmployeeStatus.active

    @field_validator("first_name", "last_name", "email", "department", "title")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    """Partial update. Omitted fields stay as they are. Null is rejected."""

    model_config = ConfigDict(populate_by_name=True)

    first_name: str | None = Field(default=None, alias="firstName", min_length=1, max_length=80)
    last_name: str | None = Field(default=None, alias="lastName", min_length=1, max_length=80)
    email: str | None = Field(
        default=None, min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )
    department: str | None = Field(default=None, min_length=1, max_length=80)
    title: str | None = Field(default=None, min_length=1, max_length=80)
    hire_date: HireDate | None = Field(
        default=None,
        alias="hireDate",
        description="UTC hire timestamp, ISO-8601, for example 2024-03-15T00:00:00Z.",
        examples=["2024-03-15T00:00:00Z"],
    )
    status: EmployeeStatus | None = None

    @field_validator("first_name", "last_name", "email", "department", "title")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _strip(value)


class Employee(EmployeeBase):
    id: int
