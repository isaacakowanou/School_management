// Locked 18-class GGFK taxonomy (A1.10). Mirrors GGFK_CLASSES in the backend;
// used only for the bulk-create precheck ("Create N classes"). The server is
// authoritative — it re-checks with the same normalization on submit.
export const GGFK_CLASS_NAMES = [
  'Pré-maternelle',
  'Maternelle 1',
  'Maternelle 2',
  'CI',
  'CP',
  'CE1',
  'CE2',
  'CM1',
  'CM2',
  '6ème',
  '5ème',
  '4ème',
  '3ème',
  '2nde',
  '1ère C',
  '1ère D',
  'Terminale C',
  'Terminale D',
]

// Accent-, case-, and whitespace-insensitive key, mirroring the backend's
// normalize_class_name ("6ème" == "6eme" == "6EME ").
export function normalizeClassName(name) {
  return (name || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
    .replace(/\s+/g, ' ')
}
