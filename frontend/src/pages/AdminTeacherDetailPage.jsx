import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAcademicQueryParams } from '../academic/AcademicContext.jsx'
import { deleteTeacher, getTeacher, getTeacherCourses, resetTeacherPassword, updateTeacher } from '../api/teachers.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

function teacherToForm(teacher) {
  return {
    name: teacher?.name || '',
    email: teacher?.email || '',
    phone: teacher?.phone || '',
    employeeNumber: teacher?.employee_number || '',
  }
}

export default function AdminTeacherDetailPage() {
  const { teacherId } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [teacher, setTeacher] = useState(null)
  const [courses, setCourses] = useState([])
  const [error, setError] = useState(null)
  const [showEditForm, setShowEditForm] = useState(false)
  const [editForm, setEditForm] = useState(teacherToForm(null))
  const [savingEdit, setSavingEdit] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [editError, setEditError] = useState(null)
  const [editMessage, setEditMessage] = useState(null)
  const [resetConfirm, setResetConfirm] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [resetResult, setResetResult] = useState(null)
  const {
    selectedSchoolYear,
    selectedTerm,
    setSelectedSchoolYear,
    setSelectedTerm,
    availableSchoolYears,
    terms,
  } = useAcademicQueryParams()

  useEffect(() => {
    if (!selectedSchoolYear || !selectedTerm) return undefined
    let cancelled = false
    setError(null)
    setTeacher(null)
    setCourses([])
    setShowEditForm(false)
    setEditForm(teacherToForm(null))
    setSavingEdit(false)
    setDeleting(false)
    setEditError(null)
    setEditMessage(null)

    async function load() {
      try {
        const data = await getTeacher(teacherId)
        if (cancelled) return
        setTeacher(data)
        setEditForm(teacherToForm(data))
      } catch (err) {
        if (!cancelled) setError(err.message)
        return
      }
      try {
        const list = await getTeacherCourses(teacherId, {
          schoolYear: selectedSchoolYear,
          term: selectedTerm,
        })
        if (!cancelled) setCourses(list)
      } catch {
        /* non-fatal */
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [teacherId, selectedSchoolYear, selectedTerm])

  function updateEditField(field, value) {
    setEditForm((current) => ({ ...current, [field]: value }))
  }

  function cancelEdit() {
    setEditForm(teacherToForm(teacher))
    setEditError(null)
    setShowEditForm(false)
  }

  async function handleEditTeacher(event) {
    event.preventDefault()
    setEditError(null)
    setEditMessage(null)

    if (!editForm.name.trim() || !editForm.employeeNumber.trim()) {
      setEditError(t('teachers.errorRequired'))
      return
    }

    setSavingEdit(true)
    try {
      await updateTeacher(teacherId, editForm)
      const refreshed = await getTeacher(teacherId)
      setTeacher(refreshed)
      setEditForm(teacherToForm(refreshed))
      setEditMessage(t('teachers.updated'))
      setShowEditForm(false)
    } catch (err) {
      setEditError(err.message)
    } finally {
      setSavingEdit(false)
    }
  }

  async function handleDeleteTeacher() {
    if (!window.confirm(t('teachers.confirmDelete', { name: teacher.name }))) return
    setEditError(null)
    setEditMessage(null)
    setDeleting(true)
    try {
      await deleteTeacher(teacherId)
      navigate('/admin/teachers', { replace: true, state: { message: t('teachers.deleted') } })
    } catch (err) {
      if (err.status === 409 && err.detail && typeof err.detail === 'object') {
        setEditError(t('teachers.deleteBlocked', { courses: err.detail.course_count, grades: err.detail.submitted_grade_count }))
      } else {
        setEditError(err.message)
      }
    } finally {
      setDeleting(false)
    }
  }

  async function handleResetPassword() {
    setResetting(true)
    setEditError(null)
    try {
      setResetResult(await resetTeacherPassword(teacherId))
      setResetConfirm(false)
    } catch (err) {
      setEditError(err.message)
    } finally {
      setResetting(false)
    }
  }

  if (error) {
    return (
      <section className="admin-page">
        <Link to="/admin/teachers" className="back-link">
          ← {t('nav.teachers')}
        </Link>
        <ErrorBanner message={error} />
      </section>
    )
  }

  if (!teacher) {
    return (
      <section className="admin-page">
        <Spinner label={t('teachers.loadingOne')} />
      </section>
    )
  }

  return (
    <section className="admin-page">
      <Link to="/admin/teachers" className="back-link">
        ← {t('nav.teachers')}
      </Link>
      <div className="detail-header">
        <div>
          <h2 className="page-title">{teacher.name}</h2>
          <p className="muted">
            {teacher.email || '—'} · {teacher.phone || '—'} · {t('common.employeeNumber')} #{teacher.employee_number}
          </p>
        </div>
        {!showEditForm && (
          <div className="detail-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                setEditError(null)
                setEditMessage(null)
                setEditForm(teacherToForm(teacher))
                setShowEditForm(true)
              }}
            >
              {t('common.edit')}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setResetConfirm(true)}
            >
              {t('authReset.action')}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-danger-subtle"
              onClick={handleDeleteTeacher}
              disabled={deleting}
            >
              {deleting ? t('common.deleting') : t('common.delete')}
            </button>
          </div>
        )}
      </div>
      {editMessage && <p className="grade-summary">{editMessage}</p>}
      {resetResult && (
        <div className="card admin-form">
          <h3>{t('authReset.done')}</h3>
          <code>{resetResult.temp_password}</code>
          <button type="button" className="btn btn-ghost" onClick={() => navigator.clipboard.writeText(resetResult.temp_password)}>{t('common.copy')}</button>
          <p className="muted">{t('authReset.tempHint')}</p>
          {resetResult.email_sent === true && <p className="grade-summary">{t('authReset.emailSent')}</p>}
          {resetResult.sms_sent === true && <p className="grade-summary">{t('authReset.smsSent')}</p>}
          {resetResult.email_sent === null && resetResult.sms_sent === null && <p className="muted">{t('authReset.manualDelivery')}</p>}
          {resetResult.email_sent === false && <ErrorBanner message={t('common.notifyEmailFailed')} />}
          {resetResult.sms_sent === false && <ErrorBanner message={t('common.notifySmsFailed')} />}
        </div>
      )}
      {editError && !showEditForm && <ErrorBanner message={editError} />}
      {showEditForm && (
        <form className="card admin-form detail-form" onSubmit={handleEditTeacher}>
          <div className="section-heading">
            <h3>{t('common.edit')}</h3>
          </div>
          <label className="field">
            <span>{t('common.name')}</span>
            <input
              value={editForm.name}
              onChange={(event) => updateEditField('name', event.target.value)}
              disabled={savingEdit}
              required
            />
          </label>

          <label className="field">
            <span>{t('teachers.emailOptional')}</span>
            <input
              type="text"
              value={editForm.email}
              onChange={(event) => updateEditField('email', event.target.value)}
              disabled={savingEdit}
            />
          </label>

          <label className="field">
            <span>{t('teachers.phoneOptional')}</span>
            <input
              type="text"
              value={editForm.phone}
              onChange={(event) => updateEditField('phone', event.target.value)}
              disabled={savingEdit}
              placeholder="+22961000000"
            />
          </label>

          <label className="field">
            <span>{t('teachers.employeeNumber')}</span>
            <input
              value={editForm.employeeNumber}
              onChange={(event) => updateEditField('employeeNumber', event.target.value)}
              disabled={savingEdit}
              required
            />
          </label>

          <div className="grade-actions">
            <button type="submit" className="btn btn-primary" disabled={savingEdit}>
              {savingEdit ? t('common.saving') : t('common.saveChanges')}
            </button>
            <button type="button" className="btn btn-ghost" disabled={savingEdit} onClick={cancelEdit}>
              {t('common.cancel')}
            </button>
          </div>
          {editError && <ErrorBanner message={editError} />}
        </form>
      )}

      <div className="section-heading">
        <h3 className="section-title">{t('teachers.assignedCourses')}</h3>
      </div>
      <div className="list-toolbar">
        <label className="toolbar-field">
          <span>{t('common.schoolYear')}</span>
          <select value={selectedSchoolYear} onChange={(event) => setSelectedSchoolYear(event.target.value)}>
            {availableSchoolYears.map((year) => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
        </label>
        <label className="toolbar-field">
          <span>{t('common.term')}</span>
          <select value={selectedTerm} onChange={(event) => setSelectedTerm(event.target.value)}>
            {terms.map((term) => (
              <option key={term} value={term}>{term}</option>
            ))}
          </select>
        </label>
      </div>
      {courses.length === 0 ? (
        <Empty message={t('teachers.noCourses')} />
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('common.name')}</th>
                <th>{t('courses.code')}</th>
                <th>{t('students.class')}</th>
                <th>{t('common.term')}</th>
                <th>{t('common.schoolYear')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {courses.map((course) => (
                <tr key={course.id}>
                  <td>{course.name}</td>
                  <td className="nowrap">{course.code}</td>
                  <td className="nowrap">{course.class_name || '—'}</td>
                  <td className="nowrap">{course.term}</td>
                  <td className="nowrap">{course.school_year}</td>
                  <td className="nowrap">
                    <Link className="link-action" to={`/admin/courses/${course.id}`}>
                      {t('common.open')}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {resetConfirm && (
        <div className="modal-backdrop" onClick={() => !resetting && setResetConfirm(false)}>
          <div className="card modal-card" onClick={(e) => e.stopPropagation()}>
            <h3>{t('authReset.title')}</h3>
            <p>{t('authReset.confirm', { name: teacher.name })}</p>
            <div className="form-actions"><button type="button" className="btn btn-ghost" onClick={() => setResetConfirm(false)} disabled={resetting}>{t('common.cancel')}</button><button type="button" className="btn btn-primary" onClick={handleResetPassword} disabled={resetting}>{resetting ? t('common.saving') : t('authReset.action')}</button></div>
          </div>
        </div>
      )}
    </section>
  )
}
