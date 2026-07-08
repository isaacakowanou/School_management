import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { createGrade, updateGrade } from '../api/grades.js'
import Empty from './Empty.jsx'

function cellKey(studentId, gradeItemId) {
  return `${studentId}__${gradeItemId}`
}

// Validate a single draft value against the grade item's max score.
// A blank value means "no change / do not submit".
function validateCell(value, maxScore) {
  const trimmed = value.trim()
  if (trimmed === '') return { skip: true }
  const num = Number(trimmed)
  if (!Number.isFinite(num)) return { ok: false, message: 'Not a number' }
  if (num < 0) return { ok: false, message: 'Must be ≥ 0' }
  if (num > maxScore) return { ok: false, message: `Max ${maxScore}` }
  return { ok: true, value: num }
}

// A cell is unchanged when blank-with-no-grade, blank-with-existing-grade
// (blank = no change), or numerically equal to the stored score.
function isUnchanged(draftValue, existing) {
  const trimmed = draftValue.trim()
  if (!existing) return trimmed === ''
  if (trimmed === '') return true
  return Number(trimmed) === Number(existing.score)
}

const TYPE_ORDER = { INTERRO: 0, DEVOIR: 1, COMPOSITION: 2 }

export default function GradeEntryTable({ students, gradeItems, grades, onSaved, gradingMode = 'WEIGHTED' }) {
  const { t } = useTranslation()
  const isBeninese = gradingMode === 'BENINESE'

  // In Beninese mode: sort interros first, then devoir, then composition.
  const orderedGradeItems = useMemo(() => {
    if (!isBeninese) return gradeItems
    return [...gradeItems].sort((a, b) => (TYPE_ORDER[a.item_type] ?? 3) - (TYPE_ORDER[b.item_type] ?? 3))
  }, [gradeItems, isBeninese])

  const interros = useMemo(
    () => (isBeninese ? orderedGradeItems.filter((i) => i.item_type === 'INTERRO') : []),
    [orderedGradeItems, isBeninese],
  )
  const devoir = useMemo(
    () => (isBeninese ? (orderedGradeItems.find((i) => i.item_type === 'DEVOIR') ?? null) : null),
    [orderedGradeItems, isBeninese],
  )
  const composition = useMemo(
    () => (isBeninese ? (orderedGradeItems.find((i) => i.item_type === 'COMPOSITION') ?? null) : null),
    [orderedGradeItems, isBeninese],
  )

  const gradeByCell = useMemo(() => {
    const map = {}
    for (const grade of grades) {
      map[cellKey(grade.student_id, grade.grade_item_id)] = grade
    }
    return map
  }, [grades])

  const initialDrafts = useMemo(() => {
    const drafts = {}
    for (const student of students) {
      for (const item of orderedGradeItems) {
        const key = cellKey(student.id, item.id)
        const existing = gradeByCell[key]
        drafts[key] = existing ? String(existing.score) : ''
      }
    }
    return drafts
  }, [students, orderedGradeItems, gradeByCell])

  const [drafts, setDrafts] = useState(initialDrafts)
  const [cellErrors, setCellErrors] = useState({})
  const [saving, setSaving] = useState(false)
  const [summary, setSummary] = useState(null)

  // Re-sync drafts whenever the underlying data changes (e.g. after a save reload).
  useEffect(() => {
    setDrafts(initialDrafts)
    setCellErrors({})
  }, [initialDrafts])

  if (orderedGradeItems.length === 0) {
    return <Empty message={t('gradeEntry.noGradeItems')} />
  }
  if (students.length === 0) {
    return <Empty message={t('gradeEntry.noStudents')} />
  }

  function setCell(key, value) {
    setDrafts((prev) => ({ ...prev, [key]: value }))
  }

  // Compute Beninese intermediates for one student from current draft values.
  // Moy Int requires ALL interros to be filled; MCC requires Moy Int + Devoir;
  // Moy requires MCC + Composition. Returns formatted strings or '—'.
  function computeBeninese(studentId) {
    const norms = []
    let allFilled = interros.length > 0
    for (const item of interros) {
      const v = (drafts[cellKey(studentId, item.id)] ?? '').trim()
      if (v === '') { allFilled = false; break }
      const n = Number(v)
      if (!Number.isFinite(n) || n < 0 || n > item.max_score) { allFilled = false; break }
      norms.push((n / item.max_score) * 20)
    }
    const moyIntVal = allFilled ? norms.reduce((s, v) => s + v, 0) / norms.length : null

    function normItem(item) {
      if (!item) return null
      const v = (drafts[cellKey(studentId, item.id)] ?? '').trim()
      if (v === '') return null
      const n = Number(v)
      return Number.isFinite(n) && n >= 0 && n <= item.max_score ? (n / item.max_score) * 20 : null
    }

    const devoirNorm = normItem(devoir)
    const mccVal = moyIntVal !== null && devoirNorm !== null ? (moyIntVal + devoirNorm) / 2 : null
    const compNorm = normItem(composition)
    const moyVal = mccVal !== null && compNorm !== null ? (mccVal + compNorm) / 2 : null

    return {
      moy_int: moyIntVal != null ? moyIntVal.toFixed(2) : '—',
      mcc: mccVal != null ? mccVal.toFixed(2) : '—',
      moy: moyVal != null ? moyVal.toFixed(2) : '—',
    }
  }

  async function handleSave() {
    setSaving(true)
    setSummary(null)
    const nextErrors = {}
    const changedStudentIds = new Set()
    let saved = 0
    let failed = 0

    for (const student of students) {
      for (const item of orderedGradeItems) {
        const key = cellKey(student.id, item.id)
        const draftValue = drafts[key] ?? ''
        const existing = gradeByCell[key]
        if (isUnchanged(draftValue, existing)) continue

        const result = validateCell(draftValue, item.max_score)
        if (result.skip) continue
        if (!result.ok) {
          nextErrors[key] = result.message
          failed += 1
          continue
        }

        try {
          if (existing) {
            await updateGrade(existing.id, result.value)
          } else {
            await createGrade({ studentId: student.id, gradeItemId: item.id, score: result.value })
          }
          saved += 1
          changedStudentIds.add(student.id)
        } catch (err) {
          nextErrors[key] = err.message
          failed += 1
        }
      }
    }

    setCellErrors(nextErrors)
    setSaving(false)
    setSummary({ saved, failed })
    if (saved > 0 && onSaved) onSaved(Array.from(changedStudentIds))
  }

  return (
    <div>
      <div className="table-scroll">
        <table className="table grade-matrix">
          <thead>
            <tr>
              <th>{t('gradeEntry.student')}</th>
              {orderedGradeItems.map((item) => (
                <th key={item.id} className="num">
                  {item.title}
                  <span className="grade-max">/ {item.max_score}</span>
                </th>
              ))}
              {isBeninese && <th className="num">{t('gradeEntry.moyInt')}</th>}
              {isBeninese && <th className="num">{t('gradeEntry.mcc')}</th>}
              {isBeninese && <th className="num">{t('gradeEntry.moy')}</th>}
            </tr>
          </thead>
          <tbody>
            {students.map((student) => {
              const ben = isBeninese ? computeBeninese(student.id) : null
              return (
                <tr key={student.id}>
                  <td className="nowrap">
                    {student.last_name}, {student.first_name}
                  </td>
                  {orderedGradeItems.map((item) => {
                    const key = cellKey(student.id, item.id)
                    const error = cellErrors[key]
                    return (
                      <td key={item.id} className="num grade-cell">
                        <input
                          className={`grade-input${error ? ' grade-input-error' : ''}`}
                          type="number"
                          min="0"
                          max={item.max_score}
                          step="any"
                          value={drafts[key] ?? ''}
                          onChange={(e) => setCell(key, e.target.value)}
                          disabled={saving}
                          aria-label={`${student.last_name} ${student.first_name} — ${item.title}`}
                        />
                        {error && <div className="grade-cell-error">{error}</div>}
                      </td>
                    )
                  })}
                  {isBeninese && <td className="num">{ben.moy_int}</td>}
                  {isBeninese && <td className="num">{ben.mcc}</td>}
                  {isBeninese && <td className="num">{ben.moy}</td>}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="grade-actions">
        <button type="button" className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? t('gradeEntry.saving') : t('gradeEntry.saveGrades')}
        </button>
        {summary && (
          <span className={`grade-summary${summary.failed ? ' grade-summary-warn' : ''}`}>
            {summary.failed ? t('gradeEntry.saveFailed') : t('gradeEntry.saved')}
          </span>
        )}
      </div>
    </div>
  )
}
