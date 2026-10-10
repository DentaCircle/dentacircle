/** Roles that may register and list patients. The API checks this again. */

const PATIENT_ROLES = ["receptionist", "clinician", "clinic_admin"] as const;

export function canRegisterPatients(roles: readonly string[]): boolean {
  return roles.some((role) => PATIENT_ROLES.some((allowed) => allowed === role));
}
