import { apiGet } from './client.js'

// GET /api/v1/admin/stats -> live dashboard counts for admins.
export function getAdminStats() {
  return apiGet('/admin/stats')
}
