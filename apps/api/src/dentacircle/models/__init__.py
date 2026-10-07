"""ORM models. Importing this package registers every table on Base.metadata."""

from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.auth_session import AuthSession
from dentacircle.models.clinic import Clinic
from dentacircle.models.user_role import UserRole
from dentacircle.models.working_hours import ClinicWorkingHours

__all__ = [
    "AppUser",
    "AppointmentType",
    "AuthSession",
    "Clinic",
    "ClinicWorkingHours",
    "UserRole",
]
