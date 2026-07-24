import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
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
import { useAcademicContext } from '../academic/AcademicContext.jsx'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'
import { canOpenClassEnrollmentDialog } from '../utils/classEnrollment.js'

const DEFAULT_SCHOOL_YEAR = '2026-2027'
const SCHOOL_YEAR_SUGGESTIONS = ['2026-2027', '2027-2028', '2028-2029']

function emptyQuickAdd() {
  return { nameFr: '', nameEn: '', stream: '' }
}

export default function AdminClassesPage() {
  const { t } = useTranslation()
  const { currentSchoolYear, availableSchoolYears, refreshAcademicContext } = useAcademicContext()
  const [classes, setClasses] = useState(null)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const [selectedYear, setSelectedYear] = useState('')
  const [pending, setPending] = useState(false)

  const [quickAdd, setQuickAdd] = useState({})
  const [quickAddError, setQuickAddError] = useState({})
  const [addLevel, setAddLevel] = useState('maternelle')
  const [showAddDialog, setShowAddDialog] = useState(false)

  const [editing, setEditing] = useState(null)
  const [editForm, setEditForm] = useState(null)
  const [editError, setEditError] = useState(null)

  const [showBulkDialog, setShowBulkDialog] = useState(false)
  const [bulkYear, setBulkYear] = useState('')
  const [bulkError, setBulkError] = useState(null)
  const [bulkCreating, setBulkCreating] = useState(false)

  const [enrollDialog, setEnrollDialog] = useState(null)
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
        setSelectedYear(currentSchoolYear || availableSchoolYears[0] || DEFAULT_SCHOOL_YEAR)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [availableSchoolYears, currentSchoolYear])

  const years = useMemo(() => {
    const set = new Set(availableSchoolYears)
    if (selectedYear) set.add(selectedYear)
    return Array.from(set).sort().reverse()
  }, [availableSchoolYears, selectedYear])

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

  function openAddDialog() {
    setAddLevel(SCHOOL_LEVELS[0].value)
    setQuickAddError({})
    setShowAddDialog(true)
  }

  async function handleQuickAdd(event, levelValue) {
    event.preventDefault()
    setMessage(null)
    setQuickAddError((e) => ({ ...e, [levelValue]: null }))
    const form = quickAddFor(levelValue)
    if (!form.nameFr.trim()) {
      setQuickAddError((e) => ({ ...e, [levelValue]: t('classes.errorFrRequired') }))
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
      setShowAddDialog(false)
      setMessage(t('classes.added'))
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
      setEditError(t('classes.errorFrRequired'))
      return
    }
    const sortOrder = Number(editForm.sortOrder)
    if (!Number.isInteger(sortOrder)) {
      setEditError(t('classes.errorSortOrder'))
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
      setMessage(t('classes.updated'))
    } catch (err) {
      setEditError(err.message)
    } finally {
      setPending(false)
    }
  }

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
      setBulkError(t('classes.errorYearRequired'))
      return
    }
    setBulkCreating(true)
    try {
      const result = await bulkCreateClasses({ schoolYear: bulkYear })
      await refresh()
      await refreshAcademicContext()
      setShowBulkDialog(false)
      setSelectedYear(bulkYear.trim())
      let text = t('classes.bulkCreated', { count: result.created.length, year: bulkYear.trim() })
      if (result.skipped.length) {
        text += ' ' + t('classes.bulkSkipped', { count: result.skipped.length })
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
        if (result.students_in_class === 0) missing.push(t('classes.missingStudents'))
        if (result.courses_in_class === 0) missing.push(t('classes.missingCourses', { year: result.school_year }))
        setMessage(t('classes.enrollNothingResult', { name: cls.name_fr, missing: missing.join(t('common.and')) }))
      } else {
        setMessage(t('classes.enrolledResult', { name: cls.name_fr, created: result.enrollments_created, skipped: result.enrollments_skipped }))
      }
      await refresh()
    } catch (err) {
      setEnrollError(err.message)
    } finally {
      setEnrolling(false)
    }
  }

  async function handleDelete(cls) {
    if (!window.confirm(t('classes.confirmDelete', { name: cls.name_fr }))) return
    setMessage(null)
    setError(null)
    setPending(true)
    try {
      await deleteClass(cls.id)
      await refresh()
      setMessage(t('classes.deleted'))
    } catch (err) {
      if (err.status === 409 && err.detail && typeof err.detail === 'object') {
        setError(t('classes.deleteBlocked', { name: cls.name_fr, students: err.detail.student_count, courses: err.detail.course_count }))
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
          <h2 className="page-title">{t('nav.classes')}</h2>
          <p className="muted">{t('classes.subtitle')}</p>
        </div>
        {classes && (
          <div className="detail-actions">
            <label className="toolbar-field">
              <span>{t('common.schoolYear')}</span>
              <select
                value={selectedYear}
                onChange={(e) => setSelectedYear(e.target.value)}
              >
                {years.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="btn btn-primary" onClick={openAddDialog} disabled={pending}>
              {t('classes.addClass')}
            </button>
            <Link className="btn btn-primary" to="/admin/school-years/new">
              {t('schoolYears.title')}
            </Link>
            <button type="button" className="btn btn-primary" onClick={openBulkDialog} disabled={pending}>
              {t('classes.createGGFK')}
            </button>
          </div>
        )}
      </div>

      {message && <p className="grade-summary">{message}</p>}
      {error && <ErrorBanner message={error} />}
      {!error && classes === null && <Spinner label={t('classes.loading')} />}

      {classes &&
        SCHOOL_LEVELS.map((level) => {
          const list = classesByLevel[level.value] || []
          return (
            <div key={level.value}>
              <div className="section-heading">
                <h3 className="section-title">{t('classes.level_' + level.value)}</h3>
              </div>

              {list.length === 0 ? (
                <Empty message={t('classes.emptyLevel', { level: t('classes.level_' + level.value), year: selectedYear })} />
              ) : (
                <div className="table-scroll">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{t('students.class')}</th>
                        <th>{t('classes.stream')}</th>
                        <th className="num">{t('classes.studentsCol')}</th>
                        <th className="num">{t('classes.coursesCol')}</th>
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
                          <td className="nowrap row-actions">
                            <button
                              type="button"
                              className="link-action"
                              onClick={() => openEnrollDialog(cls)}
                              disabled={!canOpenClassEnrollmentDialog({
                                pending,
                                studentCount: cls.student_count,
                                courseCount: cls.course_count,
                              })}
                              title={
                                cls.student_count === 0
                                  ? t('classes.enrollNoStudents')
                                  : cls.course_count === 0
                                    ? t('classes.enrollNoCourses')
                                    : t('classes.enrollAll')
                              }
                            >
                              {t('classes.enroll')}
                            </button>
                            <button
                              type="button"
                              className="link-action"
                              onClick={() => openEdit(cls)}
                              disabled={pending}
                            >
                              {t('common.edit')}
                            </button>
                            <button
                              type="button"
                              className="link-action link-action-danger"
                              onClick={() => handleDelete(cls)}
                              disabled={pending}
                            >
                              {t('common.delete')}
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

      {showAddDialog && (
        <div className="modal-backdrop" onClick={() => !pending && setShowAddDialog(false)}>
          <div className="card modal-card" onClick={(e) => e.stopPropagation()}>
            <h3 className="section-title">{t('classes.addClass')}</h3>
            <form className="admin-form" onSubmit={(e) => handleQuickAdd(e, addLevel)}>
              <label className="field">
                <span>{t('classes.schoolLevel')}</span>
                <select
                  className="grade-input full-width-input"
                  value={addLevel}
                  onChange={(e) => setAddLevel(e.target.value)}
                  disabled={pending}
                >
                  {SCHOOL_LEVELS.map((level) => (
                    <option key={level.value} value={level.value}>
                      {t('classes.level_' + level.value)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>{t('classes.nameFr')}</span>
                <input
                  value={quickAddFor(addLevel).nameFr}
                  onChange={(e) => setQuickAddField(addLevel, 'nameFr', e.target.value)}
                  disabled={pending}
                />
              </label>
              <label className="field">
                <span>{t('classes.nameEn')}</span>
                <input
                  value={quickAddFor(addLevel).nameEn}
                  onChange={(e) => setQuickAddField(addLevel, 'nameEn', e.target.value)}
                  disabled={pending}
                />
              </label>
              <label className="field">
                <span>{t('classes.stream')}</span>
                <input
                  value={quickAddFor(addLevel).stream}
                  onChange={(e) => setQuickAddField(addLevel, 'stream', e.target.value)}
                  disabled={pending}
                />
              </label>
              <div className="grade-actions">
                <button type="submit" className="btn btn-primary" disabled={pending}>
                  {pending ? t('common.saving') : t('common.add')}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setShowAddDialog(false)}
                  disabled={pending}
                >
                  {t('common.cancel')}
                </button>
              </div>
              {quickAddError[addLevel] && <ErrorBanner message={quickAddError[addLevel]} />}
            </form>
          </div>
        </div>
      )}

      {showBulkDialog && (
        <div className="modal-backdrop" onClick={() => setShowBulkDialog(false)}>
          <div className="card modal-card" onClick={(e) => e.stopPropagation()}>
            <h3 className="section-title">{t('classes.createGGFK')}</h3>
            <p className="muted">{t('classes.bulkDialogDesc')}</p>
            <form className="admin-form" onSubmit={handleBulkCreate}>
              <label className="field">
                <span>{t('common.schoolYear')}</span>
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
                {Array.from(new Set([...availableSchoolYears, ...SCHOOL_YEAR_SUGGESTIONS])).map((year) => (
                  <option key={year} value={year} />
                ))}
              </datalist>

              {bulkYear.trim() && bulkMissingCount === 0 && (
                <p className="muted">{t('classes.allExist', { year: bulkYear.trim() })}</p>
              )}

              <div className="grade-actions">
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={bulkCreating || !bulkYear.trim() || bulkMissingCount === 0}
                >
                  {bulkCreating
                    ? t('classes.bulkCreating')
                    : t('classes.bulkCreateBtn', { count: bulkMissingCount, year: bulkYear.trim() || '…' })}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setShowBulkDialog(false)}
                  disabled={bulkCreating}
                >
                  {t('common.cancel')}
                </button>
              </div>
              {bulkError && <ErrorBanner message={bulkError} />}
            </form>
          </div>
        </div>
      )}

      {enrollDialog && (
        <div className="modal-backdrop" onClick={() => !enrolling && setEnrollDialog(null)}>
          <div className="card modal-card" onClick={(e) => e.stopPropagation()}>
            <h3 className="section-title">{t('classes.enrollDialogTitle', { name: enrollDialog.cls.name_fr })}</h3>
            <p className="muted">{t('classes.enrollDialogDesc', { year: enrollDialog.cls.school_year })}</p>

            {enrollLoading && <Spinner label={t('classes.countingEnrollments')} />}

            {!enrollLoading && enrollDialog.preview && enrollDialog.preview.status === 'empty' && (
              <ErrorBanner
                message={
                  enrollDialog.preview.students_in_class === 0 &&
                  enrollDialog.preview.courses_in_class === 0
                    ? t('classes.enrollPreviewEmptyBoth')
                    : enrollDialog.preview.students_in_class === 0
                      ? t('classes.enrollPreviewEmptyStudents')
                      : t('classes.enrollPreviewEmptyCourses', { year: enrollDialog.preview.school_year })
                }
              />
            )}

            {!enrollLoading && enrollDialog.preview && enrollDialog.preview.status === 'ok' && (
              <p>
                <strong>{enrollDialog.preview.students_in_class}</strong> {t('classes.enrollStudentsX')}{' '}
                <strong>{enrollDialog.preview.courses_in_class}</strong> {t('classes.enrollCoursesEq')}{' '}
                <strong>{enrollDialog.preview.enrollments_to_create}</strong> {t('classes.enrollNewEnrollments')}
                {enrollDialog.preview.enrollments_already_existing > 0 && (
                  <>
                    {'; '}{t('classes.enrollExisting', { count: enrollDialog.preview.enrollments_already_existing })}
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
                  ? t('classes.enrollingProgress')
                  : enrollDialog.preview?.enrollments_to_create
                    ? t('classes.enrollBtn', { count: enrollDialog.preview.enrollments_to_create })
                    : t('classes.enrollBtnGeneric')}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setEnrollDialog(null)}
                disabled={enrolling}
              >
                {enrollDialog.preview?.status === 'ok' && enrollDialog.preview.enrollments_to_create > 0
                  ? t('common.cancel')
                  : t('common.close')}
              </button>
            </div>
            {enrollError && <ErrorBanner message={enrollError} />}
          </div>
        </div>
      )}

      {editing && editForm && (
        <div className="modal-backdrop" onClick={() => setEditing(null)}>
          <div className="card modal-card" onClick={(e) => e.stopPropagation()}>
            <h3 className="section-title">{t('classes.editTitle')}</h3>
            <form className="admin-form" onSubmit={handleSaveEdit}>
              <label className="field">
                <span>{t('classes.nameFr')}</span>
                <input
                  value={editForm.nameFr}
                  onChange={(e) => updateEditField('nameFr', e.target.value)}
                  disabled={pending}
                  required
                />
              </label>
              <label className="field">
                <span>{t('classes.nameEn')}</span>
                <input
                  value={editForm.nameEn}
                  onChange={(e) => updateEditField('nameEn', e.target.value)}
                  disabled={pending}
                />
              </label>
              <label className="field">
                <span>{t('classes.schoolLevel')}</span>
                <select
                  className="grade-input full-width-input"
                  value={editForm.schoolLevel}
                  onChange={(e) => updateEditField('schoolLevel', e.target.value)}
                  disabled={pending}
                >
                  {SCHOOL_LEVELS.map((level) => (
                    <option key={level.value} value={level.value}>
                      {t('classes.level_' + level.value)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>{t('classes.stream')}</span>
                <input
                  value={editForm.stream}
                  onChange={(e) => updateEditField('stream', e.target.value)}
                  disabled={pending}
                />
              </label>
              <label className="field">
                <span>{t('classes.sortOrder')}</span>
                <input
                  type="number"
                  value={editForm.sortOrder}
                  onChange={(e) => updateEditField('sortOrder', e.target.value)}
                  disabled={pending}
                />
              </label>
              <label className="field">
                <span>{t('common.schoolYear')}</span>
                <input
                  value={editForm.schoolYear}
                  onChange={(e) => updateEditField('schoolYear', e.target.value)}
                  disabled={pending}
                  required
                />
              </label>

              <div className="grade-actions">
                <button type="submit" className="btn btn-primary" disabled={pending}>
                  {pending ? t('common.saving') : t('common.saveChanges')}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setEditing(null)}
                  disabled={pending}
                >
                  {t('common.cancel')}
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
