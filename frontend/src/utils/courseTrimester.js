export function assessmentDataForTerm({ term, gradeItems = [], grades = [], results = [] }) {
  const items = gradeItems.filter((item) => item.term === term)
  const itemIds = new Set(items.map((item) => item.id))
  return {
    gradeItems: items,
    grades: grades.filter((grade) => itemIds.has(grade.grade_item_id)),
    results: results.filter((result) => result.term === term),
  }
}

export function lockByTerm(locks = []) {
  return new Map(locks.map((lock) => [lock.term, Boolean(lock.is_locked)]))
}

export function gradingSystemChangeNeedsConfirmation({ currentSystem, nextSystem, gradeItemCount }) {
  return Boolean(nextSystem && nextSystem !== currentSystem && gradeItemCount > 0)
}
