import { apiGet } from './client.js'

export function getAcademicContext() {
  return apiGet('/academic-context')
}
