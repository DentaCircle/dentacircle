/** Roles that may read a patient timeline. The API checks this again. */

const TIMELINE_ROLES = ["clinician", "receptionist", "clinic_admin"] as const;

export function canReadTimeline(roles: readonly string[]): boolean {
  return roles.some((role) => TIMELINE_ROLES.some((allowed) => allowed === role));
}
