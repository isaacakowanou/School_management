import { buildSubjectOptionGroups } from '../utils/subjectOptions.js'
import { useTranslation } from 'react-i18next'

// Catalog-subject dropdown for the course forms (A1.9). optgroup by bulletin
// section. The explicit "Custom" first option is the free-text escape hatch:
// picking it unlocks the name / language-group fields for courses that don't
// exist in the catalog. `value` is a subject id ('' = custom / free text).
export default function SubjectSelect({ subjects, value, onChange, disabled }) {
  const { t } = useTranslation()
  const groups = buildSubjectOptionGroups(subjects || [], t)
  return (
    <select
      className="grade-input"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      disabled={disabled}
      style={{ width: '100%', textAlign: 'left' }}
    >
      <option value="">{t('courses.customSubject')}</option>
      {groups.map((group) => (
        <optgroup key={group.section} label={group.label}>
          {group.options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  )
}
