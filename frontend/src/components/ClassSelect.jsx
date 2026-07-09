import { buildClassOptionGroups } from '../utils/classOptions.js'
import { useTranslation } from 'react-i18next'

// Class / Classe dropdown shared by the student and course forms. optgroup by
// school level; blank option = unassigned. `value` is a class id ('' = none).
export default function ClassSelect({ classes, value, onChange, disabled }) {
  const { t } = useTranslation()
  const groups = buildClassOptionGroups(classes || [], t)
  return (
    <select
      className="grade-input"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      disabled={disabled}
      style={{ width: '100%', textAlign: 'left' }}
    >
      <option value="">{t('common.unassigned')}</option>
      {groups.map((group) => (
        <optgroup key={group.level} label={group.label}>
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
