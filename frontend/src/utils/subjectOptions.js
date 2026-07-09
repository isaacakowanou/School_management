// Helpers for the catalog-subject dropdown on the course forms (A1.9).

// The course name the backend will derive for a subject: French-section
// subjects print under their French name on the bulletin, English-section
// under their English name. Mirrors derived_from_subject in the backend.
export function derivedCourseName(subject) {
  if (!subject) return ''
  return subject.section === 'FRENCH' ? subject.name_fr : subject.name_en
}

// Group subjects into <optgroup> data, French section first (bulletin order;
// the backend already sorts within each section by sort_order).
export function buildSubjectOptionGroups(subjects, t) {
  const groups = []
  for (const section of ['FRENCH', 'ENGLISH']) {
    const options = (subjects || [])
      .filter((subject) => subject.section === section)
      .map((subject) => ({ value: subject.id, label: derivedCourseName(subject) }))
    if (options.length) {
      groups.push({
        section,
        label: t ? t(`subjects.sectionGroup${section}`) : section,
        options,
      })
    }
  }
  return groups
}
