import { useEffect, useMemo, useState } from 'react'
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

export default function GradeEntryTable({ students, gradeItems, grades, onSaved }) {
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
      for (const item of gradeItems) {
        const key = cellKey(student.id, item.id)
        const existing = gradeByCell[key]
        drafts[key] = existing ? String(existing.score) : ''
      }
    }
    return drafts
  }, [students, gradeItems, gradeByCell])

  const [drafts, setDrafts] = useState(initialDrafts)
  const [cellErrors, setCellErrors] = useState({})
  const [saving, setSaving] = useState(false)
  const [summary, setSummary] = useState(null)

  // Re-sync drafts whenever the underlying data changes (e.g. after a save reload).
  useEffect(() => {
    setDrafts(initialDrafts)
    setCellErrors({})
  }, [initialDrafts])

  if (gradeItems.length === 0) {
    return <Empty message="This course has no grade items yet." />
  }
  if (students.length === 0) {
    return <Empty message="No students are enrolled in this course yet." />
  }

  function setCell(key, value) {
    setDrafts((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSave() {
    setSaving(true)
    setSummary(null)
    const nextErrors = {}
    let saved = 0
    let failed = 0

    for (const student of students) {
      for (const item of gradeItems) {
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
        } catch (err) {
          nextErrors[key] = err.message
          failed += 1
        }
      }
    }

    setCellErrors(nextErrors)
    setSaving(false)
    setSummary({ saved, failed })
    if (saved > 0 && onSaved) onSaved()
  }

  return (
    <div>
      <div className="table-scroll">
        <table className="table grade-matrix">
          <thead>
            <tr>
              <th>Student</th>
              {gradeItems.map((item) => (
                <th key={item.id} className="num">
                  {item.title}
                  <span className="grade-max">/ {item.max_score}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {students.map((student) => (
              <tr key={student.id}>
                <td className="nowrap">
                  {student.last_name}, {student.first_name}
                </td>
                {gradeItems.map((item) => {
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
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grade-actions">
        <button type="button" className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save grades'}
        </button>
        {summary && (
          <span className={`grade-summary${summary.failed ? ' grade-summary-warn' : ''}`}>
            {summary.failed ? 'Some grades could not be saved.' : 'Grades saved.'}
          </span>
        )}
      </div>
    </div>
  )
}
