import { SCHOOL_LEVELS } from '../constants/schoolLevels.js'

// Label for a class option. Suffixes the school year only when the surrounding
// list spans more than one year (so a single-year list stays uncluttered).
export function classOptionLabel(cls, multiYear) {
  const base = cls.name_en ? `${cls.name_fr} (${cls.name_en})` : cls.name_fr
  return multiYear ? `${base} — ${cls.school_year}` : base
}

// Groups a flat class list into optgroup-ready sections by school level (in
// SCHOOL_LEVELS order), each sorted by sort_order. Empty groups are dropped.
export function buildClassOptionGroups(classes) {
  const multiYear = new Set(classes.map((c) => c.school_year)).size > 1
  return SCHOOL_LEVELS.map((level) => ({
    level: level.value,
    label: level.label,
    options: classes
      .filter((c) => c.school_level === level.value)
      .slice()
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((c) => ({ value: c.id, label: classOptionLabel(c, multiYear) })),
  })).filter((group) => group.options.length > 0)
}
