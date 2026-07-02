// Canonical GGFK trimester terms (A1.7c). Mirrors the backend TrimesterTerm
// enum / TRIMESTER_TERMS constant; list position == trimester number. Terms
// are dropdown-only everywhere — free text is rejected by the backend.
export const TRIMESTER_TERMS = ['1er Trimestre', '2ème Trimestre', '3ème Trimestre']

export function isCanonicalTerm(value) {
  return TRIMESTER_TERMS.includes(value)
}
