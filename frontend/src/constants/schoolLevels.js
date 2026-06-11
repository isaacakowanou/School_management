// School level (broad academic category). Internal values match the backend
// SchoolLevel enum; labels are display-only and never sent to the backend.
export const SCHOOL_LEVELS = [
  { value: 'maternelle', label: 'Maternelle' },
  { value: 'primaire', label: 'Primaire' },
  { value: 'college', label: 'Collège' },
]

export function schoolLevelLabel(value) {
  return SCHOOL_LEVELS.find((level) => level.value === value)?.label || ''
}
