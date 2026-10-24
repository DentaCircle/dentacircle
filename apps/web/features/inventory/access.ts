/** Who may see inventory, and who may change it. The API checks this again. */

const READ_ROLES = ["inventory_admin", "clinic_admin", "clinician"] as const;
const WRITE_ROLES = ["inventory_admin", "clinic_admin"] as const;

export function canReadInventory(roles: readonly string[]): boolean {
  return roles.some((role) => READ_ROLES.some((allowed) => allowed === role));
}

export function canWriteInventory(roles: readonly string[]): boolean {
  return roles.some((role) => WRITE_ROLES.some((allowed) => allowed === role));
}
