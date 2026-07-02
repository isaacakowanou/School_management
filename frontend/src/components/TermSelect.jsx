import { TRIMESTER_TERMS, isCanonicalTerm } from '../constants/terms.js'

// Canonical-term dropdown (A1.7c), shared by the course and grade-item forms.
// If an existing record still carries an unrecognized legacy term, it is shown
// as an extra "(legacy)" option so opening the form doesn't silently rewrite
// it — the API layer omits non-canonical terms on save, leaving them unchanged
// until an admin explicitly picks a trimester.
export default function TermSelect({ value, onChange, disabled, required = true }) {
  const legacyValue = value && !isCanonicalTerm(value) ? value : null
  return (
    <select
      className="grade-input"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      disabled={disabled}
      required={required}
      style={{ width: '100%', textAlign: 'left' }}
    >
      <option value="">Choose a term…</option>
      {legacyValue && <option value={legacyValue}>{legacyValue} (legacy)</option>}
      {TRIMESTER_TERMS.map((term) => (
        <option key={term} value={term}>
          {term}
        </option>
      ))}
    </select>
  )
}
