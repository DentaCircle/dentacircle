/** Roles that may record and list lab work. The API checks this again. */

const LAB_ROLES = ["clinician", "receptionist", "clinic_admin"] as const;

export function canUseLab(roles: readonly string[]): boolean {
  return roles.some((role) => LAB_ROLES.some((allowed) => allowed === role));
}
