// Subject level groups (A1.9). Internal values match the backend
// SubjectLevelGroup enum; labels are display-only.
export const SUBJECT_LEVEL_GROUPS = [
  { value: 'NURSERY', label: 'Nursery / Maternelle' },
  { value: 'PRIMARY', label: 'Primary / Primaire' },
  { value: 'COLLEGE_FIRST_CYCLE', label: 'Collège — 1er cycle (6ème–3ème)' },
  { value: 'COLLEGE_SECOND_CYCLE', label: 'Collège — 2nd cycle (2nde–Terminale)' },
]

export function subjectLevelGroupLabel(value) {
  return SUBJECT_LEVEL_GROUPS.find((group) => group.value === value)?.label || value
}
