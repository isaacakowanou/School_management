import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { advanceTerm, cloneYearCourses, listCourses, previewAdvanceTerm } from '../api/courses.js'
import { listTeachers } from '../api/teachers.js'
import { schoolGroupLabel } from '../constants/schoolGroups.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'
import TermSelect from '../components/TermSelect.jsx'

// Machine-readable preview warning keys -> i18n labels.
const ADVANCE_WARNING_KEYS = {
  missing_interro: 'courses.advanceWarnMissingInterro',
  missing_devoir: 'courses.advanceWarnMissingDevoir',
  missing_composition: 'courses.advanceWarnMissingComposition',
  non_canonical_term: 'courses.advanceWarnNonCanonicalTerm',
}

const TARGET_YEAR_SUGGESTIONS = ['2027-2028', '2028-2029', '2029-2030']

export default function AdminCoursesPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [courses, setCourses] = useState(null)
  const [teachers, setTeachers] = useState([])
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(location.state?.message || null)

  const [showCloneDialog, setShowCloneDialog] = useState(false)
  const [cloneSourceYear, setCloneSourceYear] = useState('')
  const [cloneTargetYear, setCloneTargetYear] = useState('')
  const [cloneError, setCloneError] = useState(null)
  const [cloning, setCloning] = useState(false)

  const [showAdvanceDialog, setShowAdvanceDialog] = useState(false)
  const [advanceYear, setAdvanceYear] = useState('')
  const [advanceTargetTerm, setAdvanceTargetTerm] = useState('')
  const [advancePreview, setAdvancePreview] = useState(null)
  const [advancePreviewLoading, setAdvancePreviewLoading] = useState(false)
  const [advancing, setAdvancing] = useState(false)
  const [advanceError, setAdvanceError] = useState(null)

  useEffect(() => {
    if (location.state?.message) {
      navigate(location.pathname, { replace: true, state: {} })
    }
  }, [location.pathname, location.state, navigate])

  useEffect(() => {
    let cancelled = false
    setError(null)
    setCourses(null)
    setTeachers([])

    async function load() {
      // Courses are the primary content.
      try {
        const courseList = await listCourses()
        if (cancelled) return
        setCourses(courseList)
      } catch (err) {
        if (!cancelled) setError(err.message)
        return
      }
      // Teacher names are a best-effort join (CourseResponse only carries teacher_id);
      // if this fails we fall back to showing the id.
      try {
        const teacherList = await listTeachers()
        if (!cancelled) setTeachers(teacherList)
      } catch {
        /* non-fatal */
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  const teacherNameById = useMemo(() => {
    const map = new Map()
    for (const teacher of teachers) map.set(teacher.id, teacher.name)
    return map
  }, [teachers])

  const courseCountByYear = useMemo(() => {
    const map = new Map()
    for (const course of courses || []) {
      map.set(course.school_year, (map.get(course.school_year) || 0) + 1)
    }
    return map
  }, [courses])

  const schoolYears = useMemo(
    () => Array.from(courseCountByYear.keys()).sort().reverse(),
    [courseCountByYear],
  )

  const cloneSourceCount = courseCountByYear.get(cloneSourceYear) || 0
  const cloneTargetCount = courseCountByYear.get(cloneTargetYear.trim()) || 0

  function openCloneDialog() {
    setCloneSourceYear(schoolYears[0] || '')
    setCloneTargetYear('')
    setCloneError(null)
    setShowCloneDialog(true)
  }

  function openAdvanceDialog() {
    setAdvanceYear(schoolYears[0] || '')
    setAdvanceTargetTerm('')
    setAdvancePreview(null)
    setAdvanceError(null)
    setShowAdvanceDialog(true)
  }

  // Changing either input invalidates a previously loaded preview.
  function updateAdvanceYear(value) {
    setAdvanceYear(value)
    setAdvancePreview(null)
    setAdvanceError(null)
  }

  function updateAdvanceTargetTerm(value) {
    setAdvanceTargetTerm(value)
    setAdvancePreview(null)
    setAdvanceError(null)
  }

  async function handleLoadAdvancePreview() {
    setAdvanceError(null)
    setAdvancePreviewLoading(true)
    try {
      const preview = await previewAdvanceTerm({ schoolYear: advanceYear, targetTerm: advanceTargetTerm })
      setAdvancePreview(preview)
    } catch (err) {
      setAdvanceError(err.message)
    } finally {
      setAdvancePreviewLoading(false)
    }
  }

  async function handleAdvanceTerm(event) {
    event.preventDefault()
    setAdvanceError(null)
    setAdvancing(true)
    try {
      const result = await advanceTerm({ schoolYear: advanceYear, targetTerm: advanceTargetTerm })
      const refreshed = await listCourses()
      setCourses(refreshed)
      setShowAdvanceDialog(false)
      setNotice(
        t('courses.advanced', {
          count: result.updated_count,
          term: result.target_term,
          skipped: result.skipped_count,
        }),
      )
    } catch (err) {
      setAdvanceError(err.message)
    } finally {
      setAdvancing(false)
    }
  }

  async function handleClone(event) {
    event.preventDefault()
    setCloneError(null)
    if (!cloneSourceYear || !cloneTargetYear.trim()) {
      setCloneError(t('courses.cloneValidation'))
      return
    }
    setCloning(true)
    try {
      const result = await cloneYearCourses({
        sourceYear: cloneSourceYear,
        targetYear: cloneTargetYear,
      })
      const refreshed = await listCourses()
      setCourses(refreshed)
      setShowCloneDialog(false)
      let text = t('courses.cloned', { count: result.created_count, year: cloneTargetYear.trim() })
      if (result.unmatched_class_names.length) {
        text += ' ' + t('courses.clonedUnmatched', { year: cloneTargetYear.trim(), names: result.unmatched_class_names.join(', ') })
      }
      setNotice(text)
    } catch (err) {
      if (err.status === 409 && err.detail && typeof err.detail === 'object') {
        if (err.detail.course_count != null) {
          setCloneError(t('courses.cloneTargetNotEmpty', { year: cloneTargetYear.trim(), count: err.detail.course_count }))
        } else if (err.detail.codes) {
          setCloneError(t('courses.cloneCodesExist', { codes: err.detail.codes.join(', ') }))
        } else {
          setCloneError(err.message)
        }
      } else {
        setCloneError(err.message)
      }
    } finally {
      setCloning(false)
    }
  }

  return (
    <section className="admin-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('nav.courses')}</h2>
          <p className="muted">{t('courses.subtitle')}</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={openAdvanceDialog}
            disabled={!courses || courses.length === 0}
          >
            {t('courses.advanceTerm')}
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={openCloneDialog}
            disabled={!courses || courses.length === 0}
          >
            {t('courses.cloneYear')}
          </button>
          <Link to="/admin/courses/new" className="btn btn-primary">
            {t('courses.addCourse')}
          </Link>
        </div>
      </div>

      {notice && <p className="grade-summary">{notice}</p>}
      {error && <ErrorBanner message={error} />}
      {!error && courses === null && <Spinner label={t('courses.loading')} />}
      {!error && courses && courses.length === 0 && <Empty message={t('courses.empty')} />}
      {!error && courses && courses.length > 0 && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('common.name')}</th>
                <th>{t('courses.code')}</th>
                <th>{t('common.teacher')}</th>
                <th>{t('students.class')}</th>
                <th>{t('common.term')}</th>
                <th>{t('common.schoolYear')}</th>
                <th>{t('courses.group')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {courses.map((course) => (
                <tr key={course.id}>
                  <td>{course.name}</td>
                  <td className="nowrap">{course.code}</td>
                  <td>
                    {teacherNameById.get(course.teacher_id) || (
                      <span className="audit-id" title={course.teacher_id}>
                        {course.teacher_id}
                      </span>
                    )}
                  </td>
                  <td className="nowrap">{course.class_name || '—'}</td>
                  <td className="nowrap">{course.term}</td>
                  <td className="nowrap">{course.school_year}</td>
                  <td className="nowrap">{schoolGroupLabel(course.language_group) || '—'}</td>
                  <td className="nowrap">
                    <Link className="back-link" to={`/admin/courses/${course.id}`}>
                      {t('common.open')}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCloneDialog && (
        <div
          onClick={() => setShowCloneDialog(false)}
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
            <h3 className="section-title">{t('courses.cloneDialogTitle')}</h3>
            <p className="muted">{t('courses.cloneDialogDesc')}</p>
            <form className="admin-form" onSubmit={handleClone}>
              <label className="field">
                <span>{t('courses.fromYear')}</span>
                <select
                  className="grade-input"
                  value={cloneSourceYear}
                  onChange={(e) => setCloneSourceYear(e.target.value)}
                  disabled={cloning}
                  style={{ width: '100%', textAlign: 'left' }}
                >
                  {schoolYears.map((year) => (
                    <option key={year} value={year}>
                      {t('courses.yearOption', { year, count: courseCountByYear.get(year) })}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>{t('courses.toYear')}</span>
                <input
                  value={cloneTargetYear}
                  onChange={(e) => setCloneTargetYear(e.target.value)}
                  disabled={cloning}
                  list="clone-target-year-options"
                  placeholder="e.g. 2027-2028"
                  required
                />
              </label>
              <datalist id="clone-target-year-options">
                {TARGET_YEAR_SUGGESTIONS.filter((year) => year !== cloneSourceYear).map((year) => (
                  <option key={year} value={year} />
                ))}
              </datalist>

              {cloneTargetYear.trim() && cloneTargetCount > 0 && (
                <ErrorBanner
                  message={t('courses.cloneTargetNotEmpty', { year: cloneTargetYear.trim(), count: cloneTargetCount })}
                />
              )}

              <div className="grade-actions">
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={
                    cloning ||
                    !cloneSourceYear ||
                    !cloneTargetYear.trim() ||
                    cloneTargetYear.trim() === cloneSourceYear ||
                    cloneTargetCount > 0
                  }
                >
                  {cloning ? t('courses.cloning') : t('courses.cloneBtn', { count: cloneSourceCount })}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setShowCloneDialog(false)}
                  disabled={cloning}
                >
                  {t('common.cancel')}
                </button>
              </div>
              {cloneError && <ErrorBanner message={cloneError} />}
            </form>
          </div>
        </div>
      )}

      {showAdvanceDialog && (
        <div
          onClick={() => !advancing && setShowAdvanceDialog(false)}
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
            style={{ maxWidth: 720, width: '100%', maxHeight: '90vh', overflowY: 'auto' }}
          >
            <h3 className="section-title">{t('courses.advanceDialogTitle')}</h3>
            <p className="muted">{t('courses.advanceDialogDesc')}</p>
            <form className="admin-form" onSubmit={handleAdvanceTerm}>
              <label className="field">
                <span>{t('common.schoolYear')}</span>
                <select
                  className="grade-input"
                  value={advanceYear}
                  onChange={(e) => updateAdvanceYear(e.target.value)}
                  disabled={advancing || advancePreviewLoading}
                  style={{ width: '100%', textAlign: 'left' }}
                >
                  {schoolYears.map((year) => (
                    <option key={year} value={year}>
                      {t('courses.yearOption', { year, count: courseCountByYear.get(year) })}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>{t('courses.advanceTargetTerm')}</span>
                <TermSelect
                  value={advanceTargetTerm}
                  onChange={updateAdvanceTargetTerm}
                  disabled={advancing || advancePreviewLoading}
                />
              </label>

              {!advancePreview && (
                <div className="grade-actions">
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={handleLoadAdvancePreview}
                    disabled={advancePreviewLoading || !advanceYear || !advanceTargetTerm}
                  >
                    {advancePreviewLoading ? t('courses.advancePreviewLoading') : t('courses.advancePreviewBtn')}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => setShowAdvanceDialog(false)}
                    disabled={advancePreviewLoading}
                  >
                    {t('common.cancel')}
                  </button>
                </div>
              )}

              {advancePreview && advancePreview.courses.length === 0 && (
                <Empty message={t('courses.advanceNoCourses')} />
              )}

              {advancePreview && advancePreview.courses.length > 0 && (
                <>
                  <div className="table-scroll">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>{t('courses.code')}</th>
                          <th>{t('common.name')}</th>
                          <th>{t('common.term')}</th>
                          <th className="num">{t('courses.advanceEnrolled')}</th>
                          <th className="num">{t('courses.advanceResults')}</th>
                          <th>{t('courses.advanceWarnings')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {advancePreview.courses.map((row) => (
                          <tr key={row.course_id}>
                            <td className="nowrap">{row.code}</td>
                            <td>{row.name}</td>
                            <td className="nowrap">
                              {row.current_term}
                              {row.already_on_target && (
                                <span className="muted"> ({t('courses.advanceAlreadyOnTarget')})</span>
                              )}
                            </td>
                            <td className="num">{row.enrolled_count}</td>
                            <td className="num">{row.results_calculated_count}</td>
                            <td>
                              {row.warnings.length === 0 ? (
                                <span className="muted">—</span>
                              ) : (
                                <span style={{ color: 'var(--color-danger, #b91c1c)' }}>
                                  {row.warnings
                                    .map((key) => t(ADVANCE_WARNING_KEYS[key] || key))
                                    .join(' · ')}
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="grade-actions">
                    <button
                      type="submit"
                      className="btn btn-primary"
                      disabled={
                        advancing ||
                        advancePreview.total_count - advancePreview.already_on_target_count === 0
                      }
                    >
                      {advancing
                        ? t('courses.advancing')
                        : t('courses.advanceConfirmBtn', {
                            count: advancePreview.total_count - advancePreview.already_on_target_count,
                            term: advanceTargetTerm,
                          })}
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      onClick={() => setShowAdvanceDialog(false)}
                      disabled={advancing}
                    >
                      {t('common.cancel')}
                    </button>
                  </div>
                </>
              )}
              {advanceError && <ErrorBanner message={advanceError} />}
            </form>
          </div>
        </div>
      )}
    </section>
  )
}
