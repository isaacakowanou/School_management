import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAcademicContext } from '../academic/AcademicContext.jsx'
import { listClasses } from '../api/classes.js'
import { createBulkCourseSetup, previewBulkCourseSetup } from '../api/courses.js'
import { listTeachers } from '../api/teachers.js'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Spinner from '../components/Spinner.jsx'
import TermSelect from '../components/TermSelect.jsx'


export default function AdminCourseSetupPage() {
  const { t } = useTranslation()
  const { currentSchoolYear, currentTerm, availableSchoolYears } = useAcademicContext()
  const [searchParams, setSearchParams] = useSearchParams()
  const [schoolYear, setSchoolYear] = useState(searchParams.get('year') || currentSchoolYear || '')
  const [term, setTerm] = useState(currentTerm || '')
  const [classes, setClasses] = useState(null)
  const [teachers, setTeachers] = useState([])
  const [selectedClassIds, setSelectedClassIds] = useState(() => {
    const classId = searchParams.get('class_id')
    return classId ? [classId] : []
  })
  const [rows, setRows] = useState(null)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [bulkTeacherId, setBulkTeacherId] = useState('')
  const [bulkCoefficient, setBulkCoefficient] = useState('1')

  useEffect(() => {
    if (!schoolYear && currentSchoolYear) setSchoolYear(currentSchoolYear)
    if (!term && currentTerm) setTerm(currentTerm)
  }, [currentSchoolYear, currentTerm, schoolYear, term])

  useEffect(() => {
    if (!schoolYear) return undefined
    let cancelled = false
    setClasses(null)
    setRows(null)
    listClasses({ schoolYear })
      .then((data) => {
        if (cancelled) return
        setClasses(data)
        setSelectedClassIds((current) => current.filter((id) => data.some((item) => item.id === id)))
      })
      .catch((err) => !cancelled && setError(err.message))
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('year', schoolYear)
      return next
    }, { replace: true })
    return () => { cancelled = true }
  }, [schoolYear, setSearchParams])

  useEffect(() => {
    listTeachers().then(setTeachers).catch(() => setTeachers([]))
  }, [])

  const groupedRows = useMemo(() => {
    const groups = new Map()
    for (const row of rows || []) {
      if (!groups.has(row.class_id)) groups.set(row.class_id, { name: row.class_name, rows: [] })
      groups.get(row.class_id).rows.push(row)
    }
    return [...groups.entries()]
  }, [rows])

  function toggleClass(classId) {
    setSelectedClassIds((current) => current.includes(classId)
      ? current.filter((id) => id !== classId)
      : [...current, classId])
    setRows(null)
  }

  function updateRow(index, field, value) {
    setRows((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row))
  }

  function applyToSelected(field, value) {
    setRows((current) => current.map((row) => row.selected && !row.already_exists ? { ...row, [field]: value } : row))
  }

  async function loadPreview() {
    setError(null)
    setNotice(null)
    if (!schoolYear || !term || selectedClassIds.length === 0) {
      setError(t('courses.bulkChooseClasses'))
      return
    }
    setLoadingPreview(true)
    try {
      const result = await previewBulkCourseSetup({ schoolYear, term, classIds: selectedClassIds })
      setRows(result.rows.map((row) => ({ ...row, selected: !row.already_exists, coefficient: String(row.coefficient) })))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingPreview(false)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const selected = (rows || []).filter((row) => row.selected && !row.already_exists)
    if (selected.length === 0) {
      setError(t('courses.bulkNothingSelected'))
      return
    }
    setSaving(true)
    setError(null)
    setNotice(null)
    try {
      const result = await createBulkCourseSetup({ schoolYear, term, items: selected })
      await loadPreview()
      setNotice(t('courses.bulkCreated', { created: result.created_count, skipped: result.skipped_existing_count }))
    } catch (err) {
      const failures = err.detail?.validation_failures
      setError(Array.isArray(failures) ? failures.map((item) => item.message).join(' · ') : err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="admin-page">
      <Link to="/admin/courses" className="back-link">← {t('nav.courses')}</Link>
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('courses.bulkSetup')}</h2>
          <p className="muted">{t('courses.bulkSetupDesc')}</p>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}
      {notice && <p className="grade-summary">{notice}</p>}

      <div className="card admin-form">
        <div className="filter-row">
          <label className="toolbar-field">
            <span>{t('common.schoolYear')}</span>
            <select value={schoolYear} onChange={(event) => setSchoolYear(event.target.value)} disabled={saving}>
              {availableSchoolYears.map((year) => <option key={year} value={year}>{year}</option>)}
            </select>
          </label>
          <label className="toolbar-field">
            <span>{t('common.term')}</span>
            <TermSelect value={term} onChange={setTerm} disabled={saving} />
          </label>
        </div>

        <fieldset className="field" disabled={saving || classes === null}>
          <legend>{t('courses.bulkClasses')}</legend>
          {classes === null ? <Spinner label={t('classes.loading')} /> : (
            <div className="checkbox-grid">
              {classes.map((schoolClass) => (
                <label key={schoolClass.id} className="checkbox-row">
                  <input type="checkbox" checked={selectedClassIds.includes(schoolClass.id)} onChange={() => toggleClass(schoolClass.id)} />
                  <span>{schoolClass.name_fr}{schoolClass.name_en ? ` · ${schoolClass.name_en}` : ''}</span>
                </label>
              ))}
            </div>
          )}
        </fieldset>

        <button type="button" className="btn btn-primary" onClick={loadPreview} disabled={loadingPreview || saving || selectedClassIds.length === 0}>
          {loadingPreview ? t('courses.bulkLoadingPreview') : t('courses.bulkPreview')}
        </button>
      </div>

      {rows && (
        <form onSubmit={handleSubmit}>
          <div className="card admin-form bulk-apply-bar">
            <strong>{t('courses.bulkApply')}</strong>
            <select value={bulkTeacherId} onChange={(event) => setBulkTeacherId(event.target.value)} disabled={saving}>
              <option value="">{t('common.unassigned')}</option>
              {teachers.map((teacher) => <option key={teacher.id} value={teacher.id}>{teacher.name}</option>)}
            </select>
            <button type="button" className="btn btn-ghost" onClick={() => applyToSelected('teacher_id', bulkTeacherId)}>{t('courses.bulkApplyTeacher')}</button>
            <input type="number" min="1" step="1" value={bulkCoefficient} onChange={(event) => setBulkCoefficient(event.target.value)} />
            <button type="button" className="btn btn-ghost" onClick={() => applyToSelected('coefficient', bulkCoefficient)}>{t('courses.bulkApplyCoefficient')}</button>
          </div>

          {groupedRows.map(([classId, group]) => (
            <div className="card bulk-course-group" key={classId}>
              <h3 className="section-title">{group.name}</h3>
              <div className="table-scroll">
                <table className="table">
                  <thead><tr><th></th><th>{t('courses.subject')}</th><th>{t('courses.courseCode')}</th><th>{t('courses.coefficient')}</th><th>{t('courses.gradingSystem')}</th><th>{t('common.teacher')}</th></tr></thead>
                  <tbody>
                    {group.rows.map((row) => {
                      const index = rows.indexOf(row)
                      const disabled = saving || row.already_exists
                      return (
                        <tr key={`${row.class_id}-${row.subject_id}`}>
                          <td><input type="checkbox" checked={row.selected} disabled={disabled} onChange={(event) => updateRow(index, 'selected', event.target.checked)} /></td>
                          <td><strong>{row.subject_name}</strong><div className="muted">{row.language_group === 'FRENCH' ? 'FR' : 'EN'}{row.already_exists ? ` · ${t('courses.bulkExisting')}` : ''}</div></td>
                          <td><input value={row.code} disabled={disabled} onChange={(event) => updateRow(index, 'code', event.target.value)} className={row.code_conflict ? 'grade-input-error' : ''} /></td>
                          <td><input type="number" min="1" step="1" value={row.coefficient} disabled={disabled} onChange={(event) => updateRow(index, 'coefficient', event.target.value)} /></td>
                          <td><select value={row.grading_system} disabled={disabled} onChange={(event) => updateRow(index, 'grading_system', event.target.value)}><option value="BENINESE">{t('courses.gradingSystemBeninese')}</option><option value="WEIGHTED">{t('courses.gradingSystemWeighted')}</option></select></td>
                          <td><select value={row.teacher_id || ''} disabled={disabled} onChange={(event) => updateRow(index, 'teacher_id', event.target.value || null)}><option value="">{t('common.unassigned')}</option>{teachers.map((teacher) => <option key={teacher.id} value={teacher.id}>{teacher.name}</option>)}</select></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
          <div className="grade-actions"><button type="submit" className="btn btn-primary" disabled={saving}>{saving ? t('courses.bulkCreating') : t('courses.bulkCreateSelected')}</button></div>
        </form>
      )}
    </section>
  )
}
