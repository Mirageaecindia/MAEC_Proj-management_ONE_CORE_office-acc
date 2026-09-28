/**
 * Which pages an account may open. `roles` lists account roles, where 'lead' means
 * "an engineer who leads at least one project" (a role on a project, not an account).
 */
export function canAccess(roles, { role, leadsProjects = false }) {
  return roles.includes(role) || (role === 'engineer' && leadsProjects && roles.includes('lead'));
}
