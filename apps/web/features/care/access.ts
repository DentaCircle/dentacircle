/** Roles that may read a care plan. The API checks this again. */

const CARE_READ_ROLES = ["clinician", "receptionist", "clinic_admin"] as const;
const CARE_WRITE_ROLES = ["clinician", "clinic_admin"] as const;

export function canReadCare(roles: readonly string[]): boolean {
  return roles.some((role) => CARE_READ_ROLES.some((allowed) => allowed === role));
}

export function canWriteCare(roles: readonly string[]): boolean {
  return roles.some((role) => CARE_WRITE_ROLES.some((allowed) => allowed === role));
}
