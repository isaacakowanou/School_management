import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  getStudent,
  getStudentParents,
  getStudentGrades,
  linkStudentParent,
  unlinkStudentParent,
  deleteStudent,
  updateStudent,
} from '../api/students.js'
import { listParents } from '../api/parents.js'
import { listClasses } from '../api/classes.js'
import { getCourse } from '../api/courses.js'
import { listStudentCourseResults } from '../api/courseResults.js'
import { generateReport, getStudentReports } from '../api/reports.js'
import { SCHOOL_LEVELS } from '../constants/schoolLevels.js'
import { TRIMESTER_TERMS } from '../constants/terms.js'
import { formatReportAverage } from '../utils/format.js'
import { createSingleFlight } from '../utils/singleFlight.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import ClassSelect from '../components/ClassSelect.jsx'

function studentToForm(student) {
  return {
    firstName: student?.first_name || '',
    lastName: student?.last_name || '',
    studentNumber: student?.student_number || '',
    schoolLevel: student?.school_level || '',
    classId: student?.class_id || '',
    educmasterNumber: student?.educmaster_number || '',
  }
}

function reportPeriodKey(period) {
  return `${period.term}__${period.schoolYear}`
}

function formatDate(value, language) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(language === 'fr' ? 'fr-FR' : 'en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(new Date(value))
}

function itemTypeLabel(grade, t) {
  if (grade.item_type) {
    return t(`courses.${grade.item_type.toLowerCase()}Label`, { defaultValue: grade.item_type })
  }
  return grade.category || t('courses.gradeItem')
}

function groupGradesByCourse(grades) {
  const groups = []
  const byCourse = new Map()
  for (const grade of grades) {
    if (!byCourse.has(grade.course_id)) {
      const group = { courseId: grade.course_id, courseName: grade.course_name, items: [] }
      byCourse.set(grade.course_id, group)
      groups.push(group)
    }
    byCourse.get(grade.course_id).items.push(grade)
  }
  return groups
}

export default function AdminStudentDetailPage() {
  const { studentId } = useParams()
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const [student, setStudent] = useState(null)
  const [parents, setParents] = useState([])
  const [allParents, setAllParents] = useState([])
  const [reports, setReports] = useState([])
  const [grades, setGrades] = useState(null)
  const [gradeTerm, setGradeTerm] = useState('')
  const [gradeError, setGradeError] = useState(null)
  const [reportPeriods, setReportPeriods] = useState([])
  const [selectedReportPeriod, setSelectedReportPeriod] = useState('')
  const [generatingReport, setGeneratingReport] = useState(false)
  const [reportError, setReportError] = useState(null)
  const [reportMessage, setReportMessage] = useState(null)
  const [error, setError] = useState(null)
  const [linkParentId, setLinkParentId] = useState('')
  const [relationship, setRelationship] = useState('')
  const [linking, setLinking] = useState(false)
  const [linkError, setLinkError] = useState(null)
  const [linkMessage, setLinkMessage] = useState(null)
  const [showLinkParentForm, setShowLinkParentForm] = useState(false)
  const [unlinkingParentId, setUnlinkingParentId] = useState(null)
  const [showEditForm, setShowEditForm] = useState(false)
  const [editForm, setEditForm] = useState(studentToForm(null))
  const [savingEdit, setSavingEdit] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [editError, setEditError] = useState(null)
  const [editMessage, setEditMessage] = useState(null)
  const [classes, setClasses] = useState([])
  const runLinkRequest = useRef(createSingleFlight())

  useEffect(() => {
    let cancelled = false
    listClasses()
      .then((data) => {
        if (!cancelled) setClasses(data)
      })
      .catch(() => {
        /* non-fatal: the class dropdown just stays empty */
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setError(null)
    setStudent(null)
    setParents([])
    setAllParents([])
    setReports([])
    setGrades(null)
    setGradeTerm('')
    setGradeError(null)
    setReportPeriods([])
    setSelectedReportPeriod('')
    setGeneratingReport(false)
    setReportError(null)
    setReportMessage(null)
    setLinkParentId('')
    setRelationship('')
    setLinkError(null)
    setLinkMessage(null)
    setShowLinkParentForm(false)
    setUnlinkingParentId(null)
    setShowEditForm(false)
    setEditForm(studentToForm(null))
    setSavingEdit(false)
    setDeleting(false)
    setEditError(null)
    setEditMessage(null)

    async function load() {
      try {
        const data = await getStudent(studentId)
        if (cancelled) return
        setStudent(data)
        setEditForm(studentToForm(data))
      } catch (err) {
        if (!cancelled) setError(err.message)
        return
      }
      const [linkedParents, studentReports, parentOptions, courseResults] = await Promise.allSettled([
        getStudentParents(studentId),
        getStudentReports(studentId),
        listParents(),
        listStudentCourseResults(studentId),
      ])
      if (cancelled) return
      if (linkedParents.status === 'fulfilled') setParents(linkedParents.value)
      if (studentReports.status === 'fulfilled') setReports(studentReports.value)
      if (parentOptions.status === 'fulfilled') setAllParents(parentOptions.value)
      if (courseResults.status !== 'fulfilled') return

      const uniqueCourseIds = Array.from(
        new Set(courseResults.value.map((result) => result.course_id)),
      )
      const courseDetails = await Promise.allSettled(uniqueCourseIds.map((courseId) => getCourse(courseId)))
      if (cancelled) return

      const courseById = new Map()
      courseDetails.forEach((result) => {
        if (result.status === 'fulfilled') {
          courseById.set(result.value.id, result.value)
        }
      })

      const periodsByKey = new Map()
      for (const result of courseResults.value) {
        const course = courseById.get(result.course_id)
        if (!course?.school_year) continue
        const period = {
          term: result.term,
          schoolYear: course.school_year,
        }
        periodsByKey.set(reportPeriodKey(period), period)
      }
      const periods = Array.from(periodsByKey.values()).sort((a, b) =>
        `${b.schoolYear} ${b.term}`.localeCompare(`${a.schoolYear} ${a.term}`),
      )
      setReportPeriods(periods)
      setSelectedReportPeriod(periods[0] ? reportPeriodKey(periods[0]) : '')
    }

    load()
    return () => {
      cancelled = true
    }
  }, [studentId])

  useEffect(() => {
    let cancelled = false
    setGrades(null)
    setGradeError(null)
    getStudentGrades(studentId, { term: gradeTerm })
      .then((data) => {
        if (!cancelled) setGrades(data)
      })
      .catch((err) => {
        if (!cancelled) setGradeError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [studentId, gradeTerm])

  const linkedParentIds = useMemo(() => new Set(parents.map((parent) => parent.id)), [parents])
  const availableParents = useMemo(
    () => allParents.filter((parent) => !linkedParentIds.has(parent.id)),
    [allParents, linkedParentIds],
  )

  useEffect(() => {
    if (availableParents.length === 0) {
      if (linkParentId) setLinkParentId('')
      return
    }
    if (!availableParents.some((parent) => parent.id === linkParentId)) {
      setLinkParentId(availableParents[0].id)
    }
  }, [availableParents, linkParentId])

  const selectedReportPeriodData = useMemo(
    () => reportPeriods.find((period) => reportPeriodKey(period) === selectedReportPeriod) || null,
    [reportPeriods, selectedReportPeriod],
  )
  const recentGrades = useMemo(() => (grades || []).slice(0, 5), [grades])
  const gradeCourseGroups = useMemo(() => groupGradesByCourse(grades || []), [grades])

  function updateEditField(field, value) {
    setEditForm((current) => ({ ...current, [field]: value }))
  }

  function cancelEdit() {
    setEditForm(studentToForm(student))
    setEditError(null)
    setShowEditForm(false)
  }

  async function handleEditStudent(event) {
    event.preventDefault()
    setEditError(null)
    setEditMessage(null)

    if (!editForm.firstName.trim() || !editForm.lastName.trim() || !editForm.studentNumber.trim()) {
      setEditError(t('students.errorAllRequired'))
      return
    }

    setSavingEdit(true)
    try {
      await updateStudent(studentId, editForm)
      const refreshed = await getStudent(studentId)
      setStudent(refreshed)
      setEditForm(studentToForm(refreshed))
      setEditMessage(t('students.updated'))
      setShowEditForm(false)
    } catch (err) {
      setEditError(err.message)
    } finally {
      setSavingEdit(false)
    }
  }

  async function handleLinkParent(event) {
    event.preventDefault()
    setLinkError(null)
    setLinkMessage(null)

    if (!linkParentId) {
      setLinkError(t('students.chooseParent'))
      return
    }

    setLinking(true)
    try {
      await runLinkRequest.current(async () => {
        await linkStudentParent(studentId, {
          parentId: linkParentId,
          relationship,
        })
        const linked = await getStudentParents(studentId)
        setParents(linked)
        setRelationship('')
        setLinkMessage(t('students.parentLinked'))
        setShowLinkParentForm(false)
      })
    } catch (err) {
      setLinkError(err.message)
    } finally {
      setLinking(false)
    }
  }

  async function handleUnlinkParent(parent) {
    const confirmed = window.confirm(
      t('students.confirmUnlink', { name: parent.name, contact: parent.email || parent.phone || '—' }),
    )
    if (!confirmed) return

    setLinkError(null)
    setLinkMessage(null)
    setUnlinkingParentId(parent.id)
    try {
      await unlinkStudentParent(studentId, parent.id)
      const linked = await getStudentParents(studentId)
      setParents(linked)
      setLinkMessage(t('students.parentUnlinked'))
    } catch (err) {
      setLinkError(err.message)
    } finally {
      setUnlinkingParentId(null)
    }
  }

  async function handleGenerateReport() {
    if (!selectedReportPeriodData) {
      setReportError(t('students.chooseTermError'))
      return
    }

    setGeneratingReport(true)
    setReportError(null)
    setReportMessage(null)
    try {
      await generateReport(studentId, selectedReportPeriodData)
      const refreshed = await getStudentReports(studentId)
      setReports(refreshed)
      setReportMessage(t('students.reportGenerated'))
    } catch (err) {
      if (err.detail?.code === 'partial_results') {
        const confirmed = window.confirm(
          t('students.confirmGeneratePartial', {
            results: err.detail.results_count,
            expected: err.detail.expected_results_count,
            courses: (err.detail.missing_course_names || []).join(', '),
          }),
        )
        if (confirmed) {
          try {
            await generateReport(studentId, { ...selectedReportPeriodData, generatePartial: true })
            const refreshed = await getStudentReports(studentId)
            setReports(refreshed)
            setReportMessage(t('students.reportGeneratedPartial'))
            return
          } catch (overrideErr) {
            setReportError(overrideErr.message)
            return
          }
        }
      }
      setReportError(err.message)
    } finally {
      setGeneratingReport(false)
    }
  }

  async function handleDeleteStudent() {
    const name = `${student.first_name} ${student.last_name}`
    if (!window.confirm(t('students.confirmDelete', { name }))) return
    setEditError(null)
    setEditMessage(null)
    setDeleting(true)
    try {
      await deleteStudent(studentId)
      navigate('/admin/students', { replace: true, state: { message: t('students.movedToTrash', { name }) } })
    } catch (err) {
      setEditError(err.message)
    } finally {
      setDeleting(false)
    }
  }

  if (error) {
    return (
      <section className="admin-page">
        <Link to="/admin/students" className="back-link">
          ← {t('students.title')}
        </Link>
        <ErrorBanner message={error} />
      </section>
    )
  }

  if (!student) {
    return (
      <section className="admin-page">
        <Spinner label={t('students.loadingOne')} />
      </section>
    )
  }

  return (
    <section className="admin-page">
      <Link to="/admin/students" className="back-link">
        ← {t('students.title')}
      </Link>
      <div className="detail-header">
        <div>
          <h2 className="page-title">
            {student.first_name} {student.last_name}
          </h2>
          <p className="muted">
            {student.class_name || '—'}
            {student.school_level ? ` · ${t(`schoolLevels.${student.school_level}`)}` : ''} · #
            {student.student_number}
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
                setEditForm(studentToForm(student))
                setShowEditForm(true)
              }}
            >
              {t('common.edit')}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-danger-subtle"
              onClick={handleDeleteStudent}
              disabled={deleting}
            >
              {deleting ? t('students.moving') : t('common.delete')}
            </button>
          </div>
        )}
      </div>
      {editError && !showEditForm && <ErrorBanner message={editError} />}
      {editMessage && <p className="grade-summary">{editMessage}</p>}
      {showEditForm && (
        <form className="card admin-form detail-form" onSubmit={handleEditStudent}>
          <div className="section-heading">
            <h3>{t('common.edit')}</h3>
          </div>
          <label className="field">
            <span>{t('students.firstName')}</span>
            <input
              value={editForm.firstName}
              onChange={(event) => updateEditField('firstName', event.target.value)}
              disabled={savingEdit}
              required
            />
          </label>

          <label className="field">
            <span>{t('students.lastName')}</span>
            <input
              value={editForm.lastName}
              onChange={(event) => updateEditField('lastName', event.target.value)}
              disabled={savingEdit}
              required
            />
          </label>

          <label className="field">
            <span>{t('students.studentNumber')}</span>
            <input
              value={editForm.studentNumber}
              onChange={(event) => updateEditField('studentNumber', event.target.value)}
              disabled={savingEdit}
              required
            />
          </label>

          <label className="field">
            <span>{t('students.schoolLevel')}</span>
            <select
              className="grade-input full-width-input"
              value={editForm.schoolLevel}
              onChange={(event) => updateEditField('schoolLevel', event.target.value)}
              disabled={savingEdit}
            >
              <option value="">{t('common.notSet')}</option>
              {SCHOOL_LEVELS.map((level) => (
                <option key={level.value} value={level.value}>
                  {t(`schoolLevels.${level.value}`)}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>{t('students.classLabel')}</span>
            <ClassSelect
              classes={classes}
              value={editForm.classId}
              onChange={(value) => updateEditField('classId', value)}
              disabled={savingEdit}
            />
          </label>

          <label className="field">
            <span>{t('students.educmaster')}</span>
            <input
              value={editForm.educmasterNumber}
              onChange={(event) => updateEditField('educmasterNumber', event.target.value)}
              disabled={savingEdit}
              placeholder={t('students.educmasterShort')}
            />
          </label>

          <div className="grade-actions">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={savingEdit}
            >
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
        <div>
          <h3 className="section-title">{t('parentGrades.title')}</h3>
          <p className="muted">{t('parentGrades.subtitle')}</p>
        </div>
        <label className="field compact-field">
          <span>{t('common.term')}</span>
          <select value={gradeTerm} onChange={(event) => setGradeTerm(event.target.value)}>
            <option value="">{t('parentGrades.currentTerm')}</option>
            {TRIMESTER_TERMS.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          <span className="muted">{t('parentGrades.averageAvailableWithReport')}</span>
        </label>
      </div>

      {gradeError && <ErrorBanner message={gradeError} />}
      {!gradeError && grades === null && <Spinner label={t('parentGrades.loading')} />}
      {!gradeError && grades && grades.length === 0 && (
        <Empty message={t('parentGrades.emptyTerm')} />
      )}
      {!gradeError && grades && grades.length > 0 && (
        <>
          <h3 className="section-title">{t('parentGrades.recent')}</h3>
          <div className="recent-grade-strip">
            {recentGrades.map((grade) => (
              <div className="recent-grade-card" key={`${grade.grade_item_id}-${grade.updated_at}`}>
                <div className="muted">{grade.course_name}</div>
                <strong>{grade.item_title}</strong>
                <div className="stat-value stat-value-compact">{grade.score} / {grade.max_score}</div>
                <div className="muted">{formatDate(grade.updated_at || grade.created_at, i18n.language)}</div>
              </div>
            ))}
          </div>

          <h3 className="section-title">{t('parentGrades.byCourse')}</h3>
          <div className="grade-course-list">
            {gradeCourseGroups.map((group) => (
              <section className="card" key={group.courseId}>
                <h4 className="card-title">{group.courseName}</h4>
                <div className="table-scroll">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{t('parentGrades.item')}</th>
                        <th>{t('parentGrades.type')}</th>
                        <th className="num">{t('parentGrades.score')}</th>
                        <th>{t('parentGrades.date')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.items.map((grade) => (
                        <tr key={grade.grade_item_id}>
                          <td>{grade.item_title}</td>
                          <td>{itemTypeLabel(grade, t)}</td>
                          <td className="num">{grade.score} / {grade.max_score}</td>
                          <td>{formatDate(grade.updated_at || grade.created_at, i18n.language)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            ))}
          </div>
        </>
      )}

      <div className="section-heading">
        <h3 className="section-title">{t('students.parentsSection')}</h3>
        {!showLinkParentForm && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setLinkError(null)
              setLinkMessage(null)
              setShowLinkParentForm(true)
            }}
          >
            {t('students.linkParent')}
          </button>
        )}
      </div>
      {linkMessage && <p className="grade-summary">{linkMessage}</p>}
      {linkError && !showLinkParentForm && <ErrorBanner message={linkError} />}
      {showLinkParentForm && (
        <form className="card admin-form" onSubmit={handleLinkParent}>
          <label className="field">
            <span>{t('nav.parents')}</span>
            <select
              className="grade-input"
              value={linkParentId}
              onChange={(event) => setLinkParentId(event.target.value)}
              disabled={linking || availableParents.length === 0}
              required
              style={{ width: '100%', textAlign: 'left' }}
            >
              {availableParents.length === 0 ? (
                <option value="">{t('students.noAvailableParents')}</option>
              ) : (
                availableParents.map((parent) => (
                  <option key={parent.id} value={parent.id}>
                    {parent.name} — {parent.email}
                  </option>
                ))
              )}
            </select>
          </label>

          <label className="field">
            <span>{t('common.relationship')}</span>
            <select
              className="grade-input"
              value={relationship}
              onChange={(event) => setRelationship(event.target.value)}
              disabled={linking}
              style={{ width: '100%', textAlign: 'left' }}
            >
              <option value="">{t('students.relationshipOptional')}</option>
              <option value="Mother">{t('students.relationshipMother')}</option>
              <option value="Father">{t('students.relationshipFather')}</option>
              <option value="Guardian">{t('students.relationshipGuardian')}</option>
              <option value="Other">{t('students.relationshipOther')}</option>
            </select>
          </label>

          <div className="grade-actions">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={linking || availableParents.length === 0}
            >
              {linking ? t('students.linking') : t('students.linkParent')}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={linking}
              onClick={() => {
                setShowLinkParentForm(false)
                setLinkError(null)
              }}
            >
              {t('common.cancel')}
            </button>
          </div>
          {linkError && <ErrorBanner message={linkError} />}
        </form>
      )}

      {parents.length === 0 ? (
        <Empty message={t('students.noParents')} />
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('common.name')}</th>
                <th>{t('common.email')}</th>
                <th>{t('common.phone')}</th>
                <th>{t('common.relationship')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {parents.map((parent) => (
                <tr key={parent.id}>
                  <td>{parent.name}</td>
                  <td className="nowrap">{parent.email}</td>
                  <td className="nowrap">{parent.phone || '—'}</td>
                  <td className="nowrap">{parent.relationship || '—'}</td>
                  <td className="nowrap">
                    <Link className="link-action" to={`/admin/parents/${parent.id}`}>
                      {t('common.open')}
                    </Link>
                    <button
                      type="button"
                      className="link-action link-action-danger"
                      disabled={unlinkingParentId === parent.id}
                      onClick={() => handleUnlinkParent(parent)}
                    >
                      {unlinkingParentId === parent.id ? t('students.unlinking') : t('students.unlink')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="section-heading">
        <h3 className="section-title">{t('nav.reports')}</h3>
      </div>
      {reportMessage && <p className="grade-summary">{reportMessage}</p>}
      {reportError && <ErrorBanner message={reportError} />}
      {reports.length === 0 ? (
        <>
          {reportPeriods.length > 0 && (
            <div className="grade-actions">
              {reportPeriods.length > 1 && (
                <label className="field" style={{ marginBottom: 0 }}>
                  <span>{t('students.reportPeriod')}</span>
                  <select
                    className="grade-input"
                    value={selectedReportPeriod}
                    onChange={(event) => setSelectedReportPeriod(event.target.value)}
                    disabled={generatingReport}
                    style={{ width: 'auto', textAlign: 'left' }}
                  >
                    {reportPeriods.map((period) => (
                      <option key={reportPeriodKey(period)} value={reportPeriodKey(period)}>
                        {period.term} · {period.schoolYear}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <button
                type="button"
                className="btn btn-primary"
                disabled={generatingReport || !selectedReportPeriodData}
                onClick={handleGenerateReport}
              >
                {generatingReport ? t('students.generating') : t('students.generateReport')}
              </button>
            </div>
          )}
          <Empty
            message={
              reportPeriods.length > 0
                ? t('students.noReports')
                : t('students.noReportsCourseResults')
            }
          />
        </>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('students.term')}</th>
                <th>{t('students.schoolYear')}</th>
                <th>{t('common.status')}</th>
                <th className="num">{t('students.average')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {reports.map((report) => (
                <tr key={report.id}>
                  <td className="nowrap">{report.term}</td>
                  <td className="nowrap">{report.school_year}</td>
                  <td>
                    <StatusBadge status={report.status} />
                  </td>
                  <td className="num">{formatReportAverage(report.bilingual_average ?? report.overall_average, report.scale)}</td>
                  <td className="nowrap">
                    <Link className="link-action" to={`/admin/reports/${report.id}`}>
                      {t('common.open')}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
