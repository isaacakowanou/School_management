import { apiGet } from './client.js'

// GET /api/v1/audit-logs (admin only) with optional filters:
//   entity_type, entity_id, actor_user_id
// Empty/blank filters are omitted from the query string.
export function getAuditLogs(filters = {}) {
  const params = new URLSearchParams()
  if (filters.entity_type) params.set('entity_type', filters.entity_type)
  if (filters.entity_id) params.set('entity_id', filters.entity_id)
  if (filters.actor_user_id) params.set('actor_user_id', filters.actor_user_id)
  const qs = params.toString()
  return apiGet(`/audit-logs${qs ? `?${qs}` : ''}`)
}
