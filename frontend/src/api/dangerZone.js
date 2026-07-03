import { apiGet, apiPost } from './client.js'

export function previewDangerZoneDelete(entityType, entityId) {
  const params = new URLSearchParams({ entity_type: entityType, entity_id: entityId })
  return apiGet(`/admin/danger-zone/preview?${params.toString()}`)
}

export function searchDangerZoneTargets(entityType, query) {
  const params = new URLSearchParams({ entity_type: entityType, q: query })
  return apiGet(`/admin/danger-zone/search?${params.toString()}`)
}

export function moveDangerZoneToTrash(payload) {
  return apiPost('/admin/danger-zone/delete', payload)
}

export function listDeletionBatches() {
  return apiGet('/admin/danger-zone/batches')
}

export function getDeletionBatch(batchId) {
  return apiGet(`/admin/danger-zone/batches/${batchId}`)
}

export function restoreDeletionBatch(batchId) {
  return apiPost(`/admin/danger-zone/batches/${batchId}/restore`)
}
