import { useEffect, useMemo, useState } from 'react'
import {
  bulkCreateClasses,
  bulkEnrollClassStudents,
  createClass,
  deleteClass,
  listClasses,
  previewClassEnrollments,
  updateClass,
} from '../api/classes.js'
import { SCHOOL_LEVELS } from '../constants/schoolLevels.js'
import { GGFK_CLASS_NAMES, normalizeClassName } from '../constants/ggfkClasses.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

const DEFAULT_SCHOOL_YEAR = '2026-2027'
const SCHOOL_YEAR_SUGGESTIONS = ['2026-2027', '2027-2028', '2028-2029']

const SECTION_TITLES = {
  maternelle: 'Nursery / Maternelle',
  primaire: 'Primary / Primaire',
  college: 'Collège',
}

function emptyQuickAdd() {
  return { nameFr: '', nameEn: '', stream: '' }
}

export default function AdminClassesPage() {
  const [classes, setClasses] = useState(null)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const [selectedYear, setSelectedYear] = useState('')
  const [pending, setPending] = useState(false)

  const [quickAdd, setQuickAdd] = useState({})
  const [quickAddError, setQuickAddError] = useState({})

  const [editing, setEditing] = useState(null)
  const [editForm, setEditForm] = useState(null)
  const [editError, setEditError] = useState(null)

  const [showBulkDialog, setShowBulkDialog] = useState(false)
  const [bulkYear, setBulkYear] = useState('')
  const [bulkError, setBulkError] = useState(null)
  const [bulkCreating, setBulkCreating] = useState(false)

  const [enrollDialog, setEnrollDialog] = useState(null) // { cls, preview }
  const [enrollLoading, setEnrollLoading] = useState(false)
  const [enrollError, setEnrollError] = useState(null)
  const [enrolling, setEnrolling] = useState(false)

  async function refresh() {
    const data = await listClasses()
    setClasses(data)
    return data
  }

  useEffect(() => {
    let cancelled = false
    setError(null)
    setClasses(null)
    listClasses()
      .then((data) => {
        if (cancelled) return
        setClasses(data)
        const years = Array.from(new Set(data.map((c) => c.school_year))).sort().reverse()
        setSelectedYear(years[0] || DEFAULT_SCHOOL_YEAR)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const years = useMemo(() => {
    const set = new Set((classes || []).map((c) => c.school_year))
    if (selectedYear) set.add(selectedYear)
    return Array.from(set).sort().reverse()
  }, [classes, selectedYear])

  const classesByLevel = useMemo(() => {
    const map = {}
    for (const level of SCHOOL_LEVELS) map[level.value] = []
    for (const cls of classes || []) {
      if (cls.school_year !== selectedYear) continue
      ;(map[cls.school_level] || (map[cls.school_level] = [])).push(cls)
    }
    for (const key of Object.keys(map)) map[key].sort((a, b) => a.sort_order - b.sort_order)
    return map
  }, [classes, selectedYear])

  function nextSortOrder(levelValue) {
    const list = classesByLevel[levelValue] || []
    return list.length ? Math.max(...list.map((c) => c.sort_order)) + 1 : 1
  }

  function quickAddFor(levelValue) {
    return quickAdd[levelValue] || emptyQuickAdd()
  }

  function setQuickAddField(levelValue, field, value) {
    setQuickAdd((q) => ({ ...q, [levelValue]: { ...quickAddFor(levelValue), [field]: value } }))
  }

  async function handleQuickAdd(event, levelValue) {
    event.preventDefault()
    setMessage(null)
    setQuickAddError((e) => ({ ...e, [levelValue]: null }))
    const form = quickAddFor(levelValue)
    if (!form.nameFr.trim()) {
      setQuickAddError((e) => ({ ...e, [levelValue]: 'French name is required.' }))
      return
    }
    setPending(true)
    try {
      await createClass({
        nameFr: form.nameFr,
        nameEn: form.nameEn,
        schoolLevel: levelValue,
        stream: form.stream,
        sortOrder: nextSortOrder(levelValue),
        schoolYear: selectedYear,
      })
      await refresh()
      setQuickAdd((q) => ({ ...q, [levelValue]: emptyQuickAdd() }))
      setMessage('Class added.')
    } catch (err) {
      setQuickAddError((e) => ({ ...e, [levelValue]: err.message }))
    } finally {
      setPending(false)
    }
  }

  function openEdit(cls) {
    setEditing(cls)
    setEditForm({
      nameFr: cls.name_fr,
      nameEn: cls.name_en || '',
      schoolLevel: cls.school_level,
      stream: cls.stream || '',
      sortOrder: String(cls.sort_order),
      schoolYear: cls.school_year,
    })
    setEditError(null)
  }

  function updateEditField(field, value) {
    setEditForm((f) => ({ ...f, [field]: value }))
  }

  async function handleSaveEdit(event) {
    event.preventDefault()
    setEditError(null)
    if (!editForm.nameFr.trim()) {
      setEditError('French name is required.')
      return
    }
    const sortOrder = Number(editForm.sortOrder)
    if (!Number.isInteger(sortOrder)) {
      setEditError('Sort order must be a whole number.')
      return
    }
    setPending(true)
    try {
      await updateClass(editing.id, {
        nameFr: editForm.nameFr,
        nameEn: editForm.nameEn,
        schoolLevel: editForm.schoolLevel,
        stream: editForm.stream,
        sortOrder,
        schoolYear: editForm.schoolYear,
      })
      await refresh()
      setEditing(null)
      setEditForm(null)
      setMessage('Class updated.')
    } catch (err) {
      setEditError(err.message)
    } finally {
      setPending(false)
    }
  }

  // Precheck for the dialog: how many taxonomy classes are missing for the
  // chosen year. Display-only — the server re-checks with the same
  // normalization on submit.
  const bulkMissingCount = useMemo(() => {
    const existingKeys = new Set(
      (classes || [])
        .filter((cls) => cls.school_year === bulkYear.trim())
        .map((cls) => normalizeClassName(cls.name_fr)),
    )
    return GGFK_CLASS_NAMES.filter((name) => !existingKeys.has(normalizeClassName(name))).length
  }, [classes, bulkYear])

  function openBulkDialog() {
    setBulkYear(selectedYear || DEFAULT_SCHOOL_YEAR)
    setBulkError(null)
    setShowBulkDialog(true)
  }

  async function handleBulkCreate(event) {
    event.preventDefault()
    setBulkError(null)
    if (!bulkYear.trim()) {
      setBulkError('School year is required.')
      return
    }
    setBulkCreating(true)
    try {
      const result = await bulkCreateClasses({ schoolYear: bulkYear })
      await refresh()
      setShowBulkDialog(false)
      setSelectedYear(bulkYear.trim())
      let text = `Created ${result.created.length} class(es) for ${bulkYear.trim()}.`
      if (result.skipped.length) {
        text += ` Skipped ${result.skipped.length} already existing.`
      }
      setMessage(text)
    } catch (err) {
      setBulkError(err.message)
    } finally {
      setBulkCreating(false)
    }
  }

  async function openEnrollDialog(cls) {
    setEnrollDialog({ cls, preview: null })
    setEnrollLoading(true)
    setEnrollError(null)
    try {
      const preview = await previewClassEnrollments(cls.id)
      setEnrollDialog({ cls, preview })
    } catch (err) {
      setEnrollError(err.message)
    } finally {
      setEnrollLoading(false)
    }
  }

  async function handleEnroll() {
    if (!enrollDialog) return
    const { cls } = enrollDialog
    setEnrollError(null)
    setMessage(null)
    setEnrolling(true)
    try {
      const result = await bulkEnrollClassStudents(cls.id)
      setEnrollDialog(null)
      if (result.status === 'empty') {
        const missing = []
        if (result.students_in_class === 0) missing.push('no students assigned to this class')
        if (result.courses_in_class === 0) missing.push(`no courses tagged with this class for ${result.school_year}`)
        setMessage(`Nothing to enroll for ${cls.name_fr}: ${missing.join(' and ')}.`)
      } else {
        setMessage(
          `Enrolled ${cls.name_fr}: ${result.enrollments_created} new enrollment(s), ` +
            `${result.enrollments_skipped} already existed.`,
        )
      }
      await refresh()
    } catch (err) {
      setEnrollError(err.message)
    } finally {
      setEnrolling(false)
    }
  }

  async function handleDelete(cls) {
    if (!window.confirm(`Delete class "${cls.name_fr}"?`)) return
    setMessage(null)
    setError(null)
    setPending(true)
    try {
      await deleteClass(cls.id)
      await refresh()
      setMessage('Class deleted.')
    } catch (err) {
      if (err.status === 409 && err.detail && typeof err.detail === 'object') {
        setError(
          `Cannot delete "${cls.name_fr}": ${err.detail.student_count} student(s) and ` +
            `${err.detail.course_count} course(s) are still assigned. Reassign them first.`,
        )
      } else {
        setError(err.message)
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="admin-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">Classes</h2>
          <p className="muted">Create and manage classes per school year and level.</p>
        </div>
        {classes && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
            <label className="field" style={{ marginBottom: 0 }}>
              <span>School year</span>
              <select
                className="grade-input"
                value={selectedYear}
                onChange={(e) => setSelectedYear(e.target.value)}
                style={{ width: 'auto', textAlign: 'left' }}
              >
                {years.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="btn btn-primary" onClick={openBulkDialog} disabled={pending}>
              Create GGFK classes
            </button>
          </div>
        )}
      </div>

      {message && <p className="grade-summary">{message}</p>}
      {error && <ErrorBanner message={error} />}
      {!error && classes === null && <Spinner label="Loading classes…" />}

      {classes &&
        SCHOOL_LEVELS.map((level) => {
          const list = classesByLevel[level.value] || []
          const qa = quickAddFor(level.value)
          return (
            <div key={level.value}>
              <h3 className="section-title">{SECTION_TITLES[level.value] || level.label}</h3>

              <form
                onSubmit={(e) => handleQuickAdd(e, level.value)}
                style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 12 }}
              >
                <label className="field" style={{ marginBottom: 0 }}>
                  <span>Name (FR)</span>
                  <input
                    value={qa.nameFr}
                    onChange={(e) => setQuickAddField(level.value, 'nameFr', e.target.value)}
                    disabled={pending}
                  />
                </label>
                <label className="field" style={{ marginBottom: 0 }}>
                  <span>Name (EN)</span>
                  <input
                    value={qa.nameEn}
                    onChange={(e) => setQuickAddField(level.value, 'nameEn', e.target.value)}
                    disabled={pending}
                  />
                </label>
                <label className="field" style={{ marginBottom: 0 }}>
                  <span>Stream</span>
                  <input
                    value={qa.stream}
                    onChange={(e) => setQuickAddField(level.value, 'stream', e.target.value)}
                    disabled={pending}
                    style={{ maxWidth: 90 }}
                  />
                </label>
                <button type="submit" className="btn btn-primary" disabled={pending}>
                  Add
                </button>
              </form>
              {quickAddError[level.value] && <ErrorBanner message={quickAddError[level.value]} />}

              {list.length === 0 ? (
                <Empty message={`No ${level.label} classes for ${selectedYear}.`} />
              ) : (
                <div className="table-scroll">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Class</th>
                        <th>Stream</th>
                        <th className="num">Students</th>
                        <th className="num">Courses</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {list.map((cls) => (
                        <tr key={cls.id}>
                          <td>
                            <strong>{cls.name_fr}</strong>
                            {cls.name_en && <span className="muted"> · {cls.name_en}</span>}
                          </td>
                          <td className="nowrap">{cls.stream || '—'}</td>
                          <td className="num">{cls.student_count}</td>
                          <td className="num">{cls.course_count}</td>
                          <td className="nowrap">
                            <button
                              type="button"
                              className="btn btn-ghost"
                              onClick={() => openEnrollDialog(cls)}
                              disabled={pending || cls.student_count === 0 || cls.course_count === 0}
                              title={
                                cls.student_count === 0
                                  ? 'No students assigned to this class'
                                  : cls.course_count === 0
                                    ? 'No courses assigned to this class'
                                    : 'Enroll every student in this class into every course in this class'
                              }
                            >
                              Enroll
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost"
                              onClick={() => openEdit(cls)}
                              disabled={pending}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost"
                              onClick={() => handleDelete(cls)}
                              disabled={pending}
                            >
                              Delete
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )
        })}

      {showBulkDialog && (
        <div
          onClick={() => setShowBulkDialog(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
            zIndex: 1000,
          }}
        >
          <div
            className="card"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: 480, width: '100%', maxHeight: '90vh', overflowY: 'auto' }}
          >
            <h3 className="section-title">Create GGFK classes</h3>
            <p className="muted">
              Creates the 18 taxonomy classes (Pré-maternelle through Terminale D) for a school
              year with canonical spellings. Classes that already exist for the year are skipped —
              safe to re-run.
            </p>
            <form className="admin-form" onSubmit={handleBulkCreate}>
              <label className="field">
                <span>School year</span>
                <input
                  value={bulkYear}
                  onChange={(e) => setBulkYear(e.target.value)}
                  disabled={bulkCreating}
                  list="bulk-school-year-options"
                  placeholder="e.g. 2027-2028"
                  required
                />
              </label>
              <datalist id="bulk-school-year-options">
                {SCHOOL_YEAR_SUGGESTIONS.map((year) => (
                  <option key={year} value={year} />
                ))}
              </datalist>

              {bulkYear.trim() && bulkMissingCount === 0 && (
                <p className="muted">All 18 GGFK classes already exist for {bulkYear.trim()}.</p>
              )}

              <div className="grade-actions">
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={bulkCreating || !bulkYear.trim() || bulkMissingCount === 0}
                >
                  {bulkCreating
                    ? 'Creating…'
                    : `Create ${bulkMissingCount} class${bulkMissingCount === 1 ? '' : 'es'} for ${bulkYear.trim() || '…'}`}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setShowBulkDialog(false)}
                  disabled={bulkCreating}
                >
                  Cancel
                </button>
              </div>
              {bulkError && <ErrorBanner message={bulkError} />}
            </form>
          </div>
        </div>
      )}

      {enrollDialog && (
        <div
          onClick={() => !enrolling && setEnrollDialog(null)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
            zIndex: 1000,
          }}
        >
          <div
            className="card"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: 520, width: '100%', maxHeight: '90vh', overflowY: 'auto' }}
          >
            <h3 className="section-title">Enroll {enrollDialog.cls.name_fr} students</h3>
            <p className="muted">
              Enrolls every student in this class into every course tagged with this class for{' '}
              {enrollDialog.cls.school_year}. Existing enrollments are kept, not duplicated.
            </p>

            {enrollLoading && <Spinner label="Counting enrollments…" />}

            {!enrollLoading && enrollDialog.preview && enrollDialog.preview.status === 'empty' && (
              <ErrorBanner
                message={
                  enrollDialog.preview.students_in_class === 0 &&
                  enrollDialog.preview.courses_in_class === 0
                    ? 'This class has no students and no courses assigned to it — nothing to enroll.'
                    : enrollDialog.preview.students_in_class === 0
                      ? 'No students are assigned to this class. Assign students first.'
                      : `No courses are tagged with this class for ${enrollDialog.preview.school_year}. Create or tag courses first.`
                }
              />
            )}

            {!enrollLoading && enrollDialog.preview && enrollDialog.preview.status === 'ok' && (
              <p>
                <strong>{enrollDialog.preview.students_in_class}</strong> student(s) ×{' '}
                <strong>{enrollDialog.preview.courses_in_class}</strong> course(s) ={' '}
                <strong>{enrollDialog.preview.enrollments_to_create}</strong> new enrollment(s)
                {enrollDialog.preview.enrollments_already_existing > 0 && (
                  <>
                    ; {enrollDialog.preview.enrollments_already_existing} already exist and will be
                    kept.
                  </>
                )}
              </p>
            )}

            <div className="grade-actions">
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleEnroll}
                disabled={
                  enrolling ||
                  enrollLoading ||
                  !enrollDialog.preview ||
                  enrollDialog.preview.status !== 'ok' ||
                  enrollDialog.preview.enrollments_to_create === 0
                }
              >
                {enrolling
                  ? 'Enrolling…'
                  : enrollDialog.preview?.enrollments_to_create
                    ? `Create ${enrollDialog.preview.enrollments_to_create} enrollment(s)`
                    : 'Create enrollments'}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setEnrollDialog(null)}
                disabled={enrolling}
              >
                {enrollDialog.preview?.status === 'ok' &&
                enrollDialog.preview.enrollments_to_create > 0
                  ? 'Cancel'
                  : 'Close'}
              </button>
            </div>
            {enrollError && <ErrorBanner message={enrollError} />}
          </div>
        </div>
      )}

      {editing && editForm && (
        <div
          onClick={() => setEditing(null)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
            zIndex: 1000,
          }}
        >
          <div
            className="card"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: 480, width: '100%', maxHeight: '90vh', overflowY: 'auto' }}
          >
            <h3 className="section-title">Edit class</h3>
            <form className="admin-form" onSubmit={handleSaveEdit}>
              <label className="field">
                <span>Name (FR)</span>
                <input
                  value={editForm.nameFr}
                  onChange={(e) => updateEditField('nameFr', e.target.value)}
                  disabled={pending}
                  required
                />
              </label>
              <label className="field">
                <span>Name (EN)</span>
                <input
                  value={editForm.nameEn}
                  onChange={(e) => updateEditField('nameEn', e.target.value)}
                  disabled={pending}
                />
              </label>
              <label className="field">
                <span>School level</span>
                <select
                  className="grade-input"
                  value={editForm.schoolLevel}
                  onChange={(e) => updateEditField('schoolLevel', e.target.value)}
                  disabled={pending}
                  style={{ width: '100%', textAlign: 'left' }}
                >
                  {SCHOOL_LEVELS.map((level) => (
                    <option key={level.value} value={level.value}>
                      {level.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Stream</span>
                <input
                  value={editForm.stream}
                  onChange={(e) => updateEditField('stream', e.target.value)}
                  disabled={pending}
                />
              </label>
              <label className="field">
                <span>Sort order</span>
                <input
                  type="number"
                  value={editForm.sortOrder}
                  onChange={(e) => updateEditField('sortOrder', e.target.value)}
                  disabled={pending}
                />
              </label>
              <label className="field">
                <span>School year</span>
                <input
                  value={editForm.schoolYear}
                  onChange={(e) => updateEditField('schoolYear', e.target.value)}
                  disabled={pending}
                  required
                />
              </label>

              <div className="grade-actions">
                <button type="submit" className="btn btn-primary" disabled={pending}>
                  {pending ? 'Saving…' : 'Save changes'}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setEditing(null)}
                  disabled={pending}
                >
                  Cancel
                </button>
              </div>
              {editError && <ErrorBanner message={editError} />}
            </form>
          </div>
        </div>
      )}
    </section>
  )
}
