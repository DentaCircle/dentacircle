"""Lock a patient row without flushing a pending timeline insert."""

from uuid import UUID

from sqlalchemy.orm import Session

from dentacircle.models.patient import Patient
from dentacircle.repositories.patient_repository import PatientRepository


def lock_patient(session: Session, clinic_id: UUID, patient_id: UUID) -> Patient:
    """Take a row lock without flushing pending timeline rows that reference the patient."""
    with session.no_autoflush:
        patient = PatientRepository(session, clinic_id).get(patient_id, lock=True)
    if patient is None:
        raise RuntimeError("visit points at a missing patient")
    return patient
