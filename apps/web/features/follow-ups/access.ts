/** Roles that may use the coordinator queue. The API checks this again. */

const FOLLOW_UP_QUEUE_ROLES = ["clinician", "receptionist", "clinic_admin"] as const;

export function canUseFollowUpQueue(roles: readonly string[]): boolean {
  return roles.some((role) => FOLLOW_UP_QUEUE_ROLES.some((allowed) => allowed === role));
}
