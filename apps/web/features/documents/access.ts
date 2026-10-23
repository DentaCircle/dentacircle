/** Roles that may list, upload and download patient documents. The API checks this again. */

const DOCUMENT_ROLES = ["clinician", "receptionist", "clinic_admin"] as const;

export function canUseDocuments(roles: readonly string[]): boolean {
  return roles.some((role) => DOCUMENT_ROLES.some((allowed) => allowed === role));
}
