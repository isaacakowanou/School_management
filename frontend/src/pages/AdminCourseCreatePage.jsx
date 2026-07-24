import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAcademicContext } from '../academic/AcademicContext.jsx'
import { createCourse } from '../api/courses.js'
import { listTeachers } from '../api/teachers.js'
import { listClasses } from '../api/classes.js'
import { listSubjects } from '../api/subjects.js'
import { SCHOOL_GROUPS } from '../constants/schoolGroups.js'
import { derivedCourseName } from '../utils/subjectOptions.js'
import ClassSelect from '../components/ClassSelect.jsx'
import SubjectSelect from '../components/SubjectSelect.jsx'
import TermSelect from '../components/TermSelect.jsx'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

const EMPTY_FORM = {
  name: '',
  code: '',
  teacherId: '',
  term: '',
  schoolYear: '',
  languageGroup: '',
  classId: '',
  subjectId: '',
  coefficient: '1',
  gradingSystem: 'WEIGHTED',
}

const SCHOOL_YEAR_SUGGESTIONS = ['2026-2027', '2027-2028', '2028-2029']

export default function AdminCourseCreatePage() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { currentSchoolYear, currentTerm } = useAcademicContext()
  const [form, setForm] = useState(EMPTY_FORM)
  const [teachers, setTeachers] = useState(null)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [classes, setClasses] = useState([])
  const [subjects, setSubjects] = useState([])
  const [gradingSystemTouched, setGradingSystemTouched] = useState(false)

  // Selecting a class narrows the catalog to that class's subjects; a subject
  // that falls out of the narrowed list is deselected.
  useEffect(() => {
    let cancelled = false
    listSubjects(form.classId ? { classId: form.classId } : {})
      .then((data) => {
        if (cancelled) return
        setSubjects(data)
        setForm((current) =>
          current.subjectId && !data.some((s) => s.id === current.subjectId)
            ? { ...current, subjectId: '' }
            : current,
        )
      })
      .catch(() => {
        /* non-fatal: the subject dropdown just stays empty */
      })
    return () => {
      cancelled = true
    }
  }, [form.classId])

  useEffect(() => {
    setForm((current) => ({
      ...current,
      schoolYear: current.schoolYear || currentSchoolYear || '',
      term: current.term || currentTerm || '',
    }))
  }, [currentSchoolYear, currentTerm])

  useEffect(() => {
    if (!form.schoolYear) return undefined
    let cancelled = false
    listClasses({ schoolYear: form.schoolYear })
      .then((data) => {
        if (!cancelled) setClasses(data)
      })
      .catch(() => {
        /* non-fatal: the class dropdown just stays empty */
      })
    return () => {
      cancelled = true
    }
  }, [form.schoolYear])

  useEffect(() => {
    let cancelled = false
    setError(null)
    setTeachers(null)

    listTeachers()
      .then((data) => {
        if (cancelled) return
        setTeachers(data)
        setForm((current) => ({
          ...current,
          teacherId: current.teacherId || data[0]?.id || '',
        }))
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })

    return () => {
      cancelled = true
    }
  }, [])

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const selectedSubject = form.subjectId
    ? subjects.find((subject) => subject.id === form.subjectId) || null
    : null
  const selectedClass = classes.find((schoolClass) => schoolClass.id === form.classId) || null

  useEffect(() => {
    if (gradingSystemTouched) return
    const languageGroup = selectedSubject?.section || form.languageGroup
    const inferred = languageGroup === 'FRENCH' && selectedClass?.school_level === 'college'
      ? 'BENINESE'
      : 'WEIGHTED'
    setForm((current) => ({ ...current, gradingSystem: inferred }))
  }, [form.languageGroup, gradingSystemTouched, selectedClass?.school_level, selectedSubject?.section])

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)

    if (
      (!form.subjectId && !form.name.trim()) ||
      !form.code.trim() ||
      !form.teacherId ||
      !form.term.trim() ||
      !form.schoolYear.trim()
    ) {
      setError(t('courses.errorRequired'))
      return
    }

    setSaving(true)
    try {
      await createCourse(form)
      navigate('/admin/courses', {
        state: { message: t('courses.created') },
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="admin-page">
      <Link to="/admin/courses" className="back-link">
        ← {t('nav.courses')}
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">{t('courses.addCourse')}</h2>
          <p className="muted">{t('courses.createSubtitle')}</p>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}
      {!error && teachers === null && <Spinner label={t('courses.loadingTeachers')} />}
      {!error && teachers && teachers.length === 0 && (
        <Empty message={t('courses.needsTeacher')} />
      )}

      {teachers && teachers.length > 0 && (
        <form className="card admin-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>{t('courses.subject')}</span>
            <SubjectSelect
              subjects={subjects}
              value={form.subjectId}
              onChange={(value) => updateField('subjectId', value)}
              disabled={saving}
            />
            <span className="muted">{t('courses.subjectHint')}</span>
          </label>

          <label className="field">
            <span>{t('courses.courseName')}</span>
            <input
              value={selectedSubject ? derivedCourseName(selectedSubject) : form.name}
              onChange={(event) => updateField('name', event.target.value)}
              disabled={saving}
              readOnly={Boolean(selectedSubject)}
              required={!selectedSubject}
            />
            {selectedSubject && (
              <span className="muted">{t('courses.nameFromSubjectHint')}</span>
            )}
          </label>

          <label className="field">
            <span>{t('courses.courseCode')}</span>
            <input
              value={form.code}
              onChange={(event) => updateField('code', event.target.value)}
              disabled={saving}
              required
            />
          </label>

          <label className="field">
            <span>{t('common.teacher')}</span>
            <select
              className="grade-input"
              value={form.teacherId}
              onChange={(event) => updateField('teacherId', event.target.value)}
              disabled={saving}
              required
              style={{ width: '100%', textAlign: 'left' }}
            >
              {teachers.map((teacher) => (
                <option key={teacher.id} value={teacher.id}>
                  {teacher.name} — {teacher.email} — #{teacher.employee_number}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>{t('common.term')}</span>
            <TermSelect
              value={form.term}
              onChange={(value) => updateField('term', value)}
              disabled={saving}
            />
          </label>

          <label className="field">
            <span>{t('common.schoolYear')}</span>
            <input
              value={form.schoolYear}
              onChange={(event) => updateField('schoolYear', event.target.value)}
              disabled={saving}
              list="course-school-year-options"
              required
            />
          </label>

          <label className="field">
            <span>{t('courses.languageGroup')}</span>
            <select
              className="grade-input"
              value={selectedSubject ? selectedSubject.section : form.languageGroup}
              onChange={(event) => updateField('languageGroup', event.target.value)}
              disabled={saving || Boolean(selectedSubject)}
              style={{ width: '100%', textAlign: 'left' }}
            >
              <option value="">{t('common.notSet')}</option>
              {SCHOOL_GROUPS.map((group) => (
                <option key={group.value} value={group.value}>
                  {t(group.labelKey)}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>{t('courses.classOptional')}</span>
            <ClassSelect
              classes={classes}
              value={form.classId}
              onChange={(value) => updateField('classId', value)}
              disabled={saving}
            />
          </label>

          <label className="field">
            <span>{t('courses.coefficient')}</span>
            <input
              type="number"
              min="1"
              step="1"
              value={form.coefficient}
              onChange={(event) => updateField('coefficient', event.target.value)}
              disabled={saving}
              required
            />
            <span className="muted">{t('courses.coefficientHint')}</span>
          </label>

          <label className="field">
            <span>{t('courses.gradingSystem')}</span>
            <select
              className="grade-input"
              value={form.gradingSystem}
              onChange={(event) => {
                setGradingSystemTouched(true)
                updateField('gradingSystem', event.target.value)
              }}
              disabled={saving}
              style={{ width: '100%', textAlign: 'left' }}
            >
              <option value="BENINESE">{t('courses.gradingSystemBeninese')}</option>
              <option value="WEIGHTED">{t('courses.gradingSystemWeighted')}</option>
            </select>
          </label>

          <datalist id="course-school-year-options">
            {SCHOOL_YEAR_SUGGESTIONS.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>

          <div className="grade-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? t('courses.creating') : t('courses.create')}
            </button>
            <Link to="/admin/courses" className="btn btn-ghost">
              {t('common.cancel')}
            </Link>
          </div>
        </form>
      )}
    </section>
  )
}
