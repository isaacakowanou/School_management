// Course language group (which language track a course belongs to). Internal
// values match the backend LanguageGroup enum; labels are display-only and
// never sent to the backend.
export const SCHOOL_GROUPS = [
  { value: 'FRENCH', label: 'French' },
  { value: 'ENGLISH', label: 'English' },
]

export function schoolGroupLabel(value) {
  return SCHOOL_GROUPS.find((group) => group.value === value)?.label || ''
}
