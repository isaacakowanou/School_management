import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAcademicContext } from '../academic/AcademicContext.jsx'
import { createSchoolYear } from '../api/schoolYears.js'
import ErrorBanner from '../components/ErrorBanner.jsx'

function nextYearLabel(currentYear) {
  const match = /^(\d{4})-(\d{4})$/.exec(currentYear || '')
  if (!match) return ''
  return `${Number(match[1]) + 1}-${Number(match[2]) + 1}`
}

export default function AdminSchoolYearCreatePage() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { currentSchoolYear, availableSchoolYears, refreshAcademicContext } = useAcademicContext()
  const suggestedYear = useMemo(() => nextYearLabel(currentSchoolYear), [currentSchoolYear])
  const [schoolYear, setSchoolYear] = useState(suggestedYear)
  const [cloneCourses, setCloneCourses] = useState(true)
  const [sourceSchoolYear, setSourceSchoolYear] = useState(currentSchoolYear)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  useEffect(() => {
    setSchoolYear((current) => current || suggestedYear)
    setSourceSchoolYear((current) => current || currentSchoolYear)
  }, [currentSchoolYear, suggestedYear])

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setResult(null)
    if (!schoolYear.trim()) {
      setError(t('schoolYears.required'))
      return
    }
    setSaving(true)
    try {
      const created = await createSchoolYear({ schoolYear, cloneCourses, sourceSchoolYear })
      setResult(created)
      await refreshAcademicContext()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="admin-page">
      <Link to="/admin/classes" className="back-link">← {t('nav.classes')}</Link>
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('schoolYears.title')}</h2>
          <p className="muted">{t('schoolYears.subtitle')}</p>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}
      {result && (
        <p className="grade-summary">
          {t('schoolYears.created', {
            year: result.school_year,
            classes: result.created_classes.length,
            courses: result.cloned_course_count,
          })}
        </p>
      )}

      <form className="card admin-form" onSubmit={handleSubmit}>
        <label className="field">
          <span>{t('common.schoolYear')}</span>
          <input
            value={schoolYear}
            onChange={(event) => setSchoolYear(event.target.value)}
            placeholder="2027-2028"
            disabled={saving}
            required
          />
        </label>

        <label className="filter-check">
          <input
            type="checkbox"
            checked={cloneCourses}
            onChange={(event) => setCloneCourses(event.target.checked)}
            disabled={saving}
          />
          <span>{t('schoolYears.cloneCourses')}</span>
        </label>

        {cloneCourses && (
          <label className="field">
            <span>{t('schoolYears.sourceYear')}</span>
            <select
              value={sourceSchoolYear || ''}
              onChange={(event) => setSourceSchoolYear(event.target.value)}
              disabled={saving}
            >
              {availableSchoolYears.map((year) => (
                <option key={year} value={year}>{year}</option>
              ))}
            </select>
          </label>
        )}

        <div className="grade-actions">
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? t('common.saving') : t('schoolYears.create')}
          </button>
          {result && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => navigate(`/admin/classes?school_year=${encodeURIComponent(result.school_year)}`)}
            >
              {t('schoolYears.openYear')}
            </button>
          )}
        </div>
      </form>
    </section>
  )
}
