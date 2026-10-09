"""Request and response models owned by this service.

Phone is defined here. The vendored employee contract stays unchanged.
"""

import re

from pydantic import Field, field_validator

from grokhr_shared import Employee
from grokhr_shared import EmployeeCreate as SharedEmployeeCreate
from grokhr_shared import EmployeeUpdate as SharedEmployeeUpdate

# E.164: leading "+", first digit 1-9, 2 to 15 digits total.
_E164 = re.compile(r"\+[1-9]\d{1,14}")
_PHONE_MESSAGE = "phone must be E.164 (for example +15551234567)"


def _validate_phone(value: str | None) -> str | None:
    if value is None:
        return None
    if not _E164.fullmatch(value):
        raise ValueError(_PHONE_MESSAGE)
    return value


class EmployeeCreate(SharedEmployeeCreate):
    phone: str | None = Field(
        default=None,
        description="Optional E.164 phone number, for example +15551234567.",
    )

    @field_validator("phone")
    @classmethod
    def phone_is_e164(cls, value: str | None) -> str | None:
        return _validate_phone(value)


class EmployeeUpdate(SharedEmployeeUpdate):
    """Partial update. Omitted fields stay as they are.

    Null is rejected, except ``phone``: null clears the stored number.
    """

    phone: str | None = Field(
        default=None,
        description=(
            "E.164 phone number, for example +15551234567. "
            "Null clears the stored number."
        ),
    )

    @field_validator("phone")
    @classmethod
    def phone_is_e164(cls, value: str | None) -> str | None:
        return _validate_phone(value)


class EmployeeDetail(Employee):
    phone: str | None = Field(
        default=None,
        description="E.164 phone number, for example +15551234567, or null when unset.",
    )
