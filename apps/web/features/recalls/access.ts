/** Roles that may use the recall queue. The API checks this again. */

const RECALL_QUEUE_ROLES = ["clinician", "receptionist", "clinic_admin"] as const;

export function canUseRecallQueue(roles: readonly string[]): boolean {
  return roles.some((role) => RECALL_QUEUE_ROLES.some((allowed) => allowed === role));
}
