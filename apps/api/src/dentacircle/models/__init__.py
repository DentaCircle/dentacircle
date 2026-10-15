"""ORM models. Importing this package registers every table on Base.metadata."""

from dentacircle.models.app_user import AppUser
from dentacircle.models.appointment import Appointment
from dentacircle.models.appointment_type import AppointmentType
from dentacircle.models.audit_event import AuditEvent
from dentacircle.models.auth_session import AuthSession
from dentacircle.models.care_item import CareItem
from dentacircle.models.care_plan import CarePlan
from dentacircle.models.clinic import Clinic
from dentacircle.models.patient import Patient
from dentacircle.models.patient_number_counter import PatientNumberCounter
from dentacircle.models.user_role import UserRole
from dentacircle.models.working_hours import ClinicWorkingHours

__all__ = [
    "AppUser",
    "Appointment",
    "AppointmentType",
    "AuditEvent",
    "AuthSession",
    "CareItem",
    "CarePlan",
    "Clinic",
    "ClinicWorkingHours",
    "Patient",
    "PatientNumberCounter",
    "UserRole",
]
