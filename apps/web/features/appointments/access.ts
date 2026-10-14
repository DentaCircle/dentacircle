/** Roles that may book. The API checks this again. */

const APPOINTMENT_ROLES = ["receptionist", "clinician", "clinic_admin"] as const;

export function canBookAppointments(roles: readonly string[]): boolean {
  return roles.some((role) => APPOINTMENT_ROLES.some((allowed) => allowed === role));
}
