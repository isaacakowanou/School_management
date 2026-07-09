// Course language group (which language track a course belongs to). Internal
// values match the backend LanguageGroup enum; labels are display-only and
// never sent to the backend.
export const SCHOOL_GROUPS = [
  { value: 'FRENCH', labelKey: 'subjects.sectionFrench' },
  { value: 'ENGLISH', labelKey: 'subjects.sectionEnglish' },
]

export function schoolGroupLabel(value, t) {
  const group = SCHOOL_GROUPS.find((item) => item.value === value)
  if (!group) return ''
  return t ? t(group.labelKey) : group.value
}
