import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { saveCourseGradesBatch } from '../api/grades.js'
import Empty from './Empty.jsx'

function cellKey(studentId, gradeItemId) {
  return `${studentId}__${gradeItemId}`
}

// Validate a single draft value against the grade item's max score.
// A blank value means "clear existing score" when a grade exists.
function validateCell(value, maxScore) {
  const trimmed = value.trim()
  if (trimmed === '') return { ok: true, value: null }
  const num = Number(trimmed)
  if (!Number.isFinite(num)) return { ok: false, messageKey: 'gradeEntry.errorNotNumber' }
  if (num < 0) return { ok: false, messageKey: 'gradeEntry.errorMin' }
  if (num > maxScore) return { ok: false, messageKey: 'gradeEntry.errorMax', messageOptions: { max: maxScore } }
  return { ok: true, value: num }
}

// A cell is unchanged when blank-with-no-grade or numerically equal to the stored score.
function isUnchanged(draftValue, existing) {
  const trimmed = draftValue.trim()
  if (!existing) return trimmed === ''
  if (trimmed === '') return false
  return Number(trimmed) === Number(existing.score)
}

const TYPE_ORDER = { INTERRO: 0, DEVOIR: 1, COMPOSITION: 2 }

export default function GradeEntryTable({ courseId, students, gradeItems, grades, onSaved, gradingMode = 'WEIGHTED', readOnly = false }) {
  const { t } = useTranslation()
  const isBeninese = gradingMode === 'BENINESE'
  const inputRefs = useRef(new Map())
  const [studentQuery, setStudentQuery] = useState('')

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

  const hasUnsavedChanges = useMemo(() => (
    Object.keys(initialDrafts).some((key) => (drafts[key] ?? '') !== (initialDrafts[key] ?? ''))
  ), [drafts, initialDrafts])

  useEffect(() => {
    if (!hasUnsavedChanges) return undefined

    function handleBeforeUnload(event) {
      event.preventDefault()
      event.returnValue = ''
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [hasUnsavedChanges])

  const filteredStudents = useMemo(() => {
    const query = studentQuery.trim().toLowerCase()
    if (!query) return students
    return students.filter((student) => (
      `${student.first_name} ${student.last_name} ${student.student_number || ''}`
        .toLowerCase()
        .includes(query)
    ))
  }, [studentQuery, students])

  function gradeItemKind(item) {
    if (isBeninese && item.item_type) {
      return t(`courses.${item.item_type.toLowerCase()}Label`, { defaultValue: item.item_type })
    }
    return item.category || t('courses.gradeItem')
  }

  if (orderedGradeItems.length === 0) {
    return <Empty message={t('gradeEntry.noGradeItems')} />
  }
  if (students.length === 0) {
    return <Empty message={t('gradeEntry.noStudents')} />
  }

  function setCell(key, value) {
    setDrafts((prev) => ({ ...prev, [key]: value }))
  }

  function setInputRef(key, node) {
    if (node) inputRefs.current.set(key, node)
    else inputRefs.current.delete(key)
  }

  function handleCellKeyDown(event, studentIndex, itemIndex) {
    if ((event.key !== 'Enter' && event.key !== 'Tab') || event.shiftKey) return
    event.preventDefault()

    let nextStudentIndex = studentIndex + 1
    let nextItemIndex = itemIndex
    if (nextStudentIndex >= filteredStudents.length) {
      nextStudentIndex = 0
      nextItemIndex = itemIndex + 1
    }
    if (nextItemIndex >= orderedGradeItems.length) return

    const nextStudent = filteredStudents[nextStudentIndex]
    const nextItem = orderedGradeItems[nextItemIndex]
    inputRefs.current.get(cellKey(nextStudent.id, nextItem.id))?.focus()
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
    const entries = []
    let saved = 0
    let failed = 0

    for (const student of students) {
      for (const item of orderedGradeItems) {
        const key = cellKey(student.id, item.id)
        const draftValue = drafts[key] ?? ''
        const existing = gradeByCell[key]
        if (isUnchanged(draftValue, existing)) continue

        const result = validateCell(draftValue, item.max_score)
        if (!result.ok) {
          nextErrors[key] = t(result.messageKey, result.messageOptions)
          failed += 1
          continue
        }

        entries.push({
          student_id: student.id,
          grade_item_id: item.id,
          score: result.value,
        })
        changedStudentIds.add(student.id)
      }
    }

    if (failed === 0 && entries.length > 0) {
      try {
        const result = await saveCourseGradesBatch(courseId, entries)
        saved = result.saved_count + result.deleted_count
      } catch (err) {
        failed += 1
        setCellErrors(nextErrors)
        setSummary({ saved, failed })
        setSaving(false)
        return
      }
    }

    setCellErrors(nextErrors)
    if (saved > 0 && onSaved) {
      try {
        await onSaved(Array.from(changedStudentIds))
        setSummary({ saved, failed, recalculated: true })
      } catch {
        setSummary({ saved, failed: failed + 1, recalculationFailed: true })
      }
    } else {
      setSummary({ saved, failed })
    }
    setSaving(false)
  }

  return (
    <div>
      <label className="field grade-search-field">
        <span>{t('gradeEntry.searchStudents')}</span>
        <input
          value={studentQuery}
          onChange={(event) => setStudentQuery(event.target.value)}
          placeholder={t('gradeEntry.searchPlaceholder')}
        />
      </label>

      {!readOnly && <div className="report-sticky-actions grade-save-bar">
        <button type="button" className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? t('gradeEntry.saving') : t('gradeEntry.saveGrades')}
        </button>
        {hasUnsavedChanges && !saving && <span className="grade-summary">{t('gradeEntry.unsaved')}</span>}
        {summary && (
          <span className={`grade-summary${summary.failed ? ' grade-summary-warn' : ''}`}>
            {summary.recalculationFailed
              ? t('gradeEntry.savedRecalcFailed')
              : summary.failed
                ? t('gradeEntry.saveFailed')
                : summary.recalculated
                  ? t('gradeEntry.savedAndRecalculated')
                  : t('gradeEntry.saved')}
          </span>
        )}
      </div>}

      {filteredStudents.length === 0 ? (
        <Empty message={t('gradeEntry.noMatchingStudents')} />
      ) : (
      <div className="table-scroll">
        <table className="table grade-matrix">
          <thead>
            <tr>
              <th>{t('gradeEntry.student')}</th>
              {orderedGradeItems.map((item) => (
                <th key={item.id} className="num">
                  <span title={`${gradeItemKind(item)} · / ${item.max_score}`}>{item.title}</span>
                  <span className="grade-max">{gradeItemKind(item)} · / {item.max_score}</span>
                </th>
              ))}
              {isBeninese && <th className="num">{t('gradeEntry.moyInt')}</th>}
              {isBeninese && <th className="num">{t('gradeEntry.mcc')}</th>}
              {isBeninese && <th className="num">{t('gradeEntry.moy')}</th>}
            </tr>
          </thead>
          <tbody>
            {filteredStudents.map((student, studentIndex) => {
              const ben = isBeninese ? computeBeninese(student.id) : null
              return (
                <tr key={student.id}>
                  <td className="nowrap">
                    {student.last_name}, {student.first_name}
                  </td>
                  {orderedGradeItems.map((item, itemIndex) => {
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
                          onKeyDown={(event) => handleCellKeyDown(event, studentIndex, itemIndex)}
                          ref={(node) => setInputRef(key, node)}
                          disabled={saving || readOnly}
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
      )}
    </div>
  )
}
