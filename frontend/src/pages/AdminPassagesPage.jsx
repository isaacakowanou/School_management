import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { listClasses } from '../api/classes.js'
import { confirmPassage, previewClassPassage } from '../api/passages.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

function nextSchoolYear(year) {
  const match = /^(\d{4})-(\d{4})$/.exec(year || '')
  if (!match) return ''
  return `${Number(match[1]) + 1}-${Number(match[2]) + 1}`
}

function average(value) {
  return value == null ? '—' : Number(value).toFixed(2)
}

function decisionLabel(value, t) {
  if (value === 'pass') return t('passages.pass')
  if (value === 'repeat') return t('passages.repeat')
  if (value === 'graduate') return t('passages.graduate')
  return t('passages.deliberation')
}

export default function AdminPassagesPage() {
  const { t } = useTranslation()
  const [classes, setClasses] = useState(null)
  const [sourceYear, setSourceYear] = useState('')
  const [targetYear, setTargetYear] = useState('')
  const [classId, setClassId] = useState('')
  const [preview, setPreview] = useState(null)
  const [decisions, setDecisions] = useState({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)

  useEffect(() => {
    let cancelled = false
    listClasses()
      .then((data) => {
        if (cancelled) return
        setClasses(data)
        const latestYear = Array.from(new Set(data.map((row) => row.school_year))).sort().at(-1) || ''
        setSourceYear(latestYear)
        setTargetYear(nextSchoolYear(latestYear))
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const sourceClasses = useMemo(
    () => (classes || []).filter((row) => row.school_year === sourceYear),
    [classes, sourceYear],
  )

  useEffect(() => {
    if (!sourceClasses.some((row) => row.id === classId)) {
      setClassId(sourceClasses[0]?.id || '')
      setPreview(null)
    }
  }, [sourceClasses, classId])

  function hydrateDecisions(data) {
    const next = {}
    for (const row of data.students) {
      const finalDecision = row.final_decision || (row.suggested_decision === 'deliberation' ? '' : row.suggested_decision)
      next[row.student_id] = {
        studentId: row.student_id,
        finalDecision,
        targetClassName: row.target_class_name || '',
        note: row.note || '',
      }
    }
    setDecisions(next)
  }

  async function loadPreview() {
    if (!classId || !targetYear.trim()) return
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const data = await previewClassPassage(classId, { targetSchoolYear: targetYear })
      setPreview(data)
      hydrateDecisions(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function updateDecision(studentId, patch) {
    setDecisions((current) => ({
      ...current,
      [studentId]: { ...current[studentId], ...patch },
    }))
  }

  async function handleConfirm() {
    if (!preview) return
    const rows = preview.students.map((row) => decisions[row.student_id]).filter(Boolean)
    const unresolved = rows.filter((row) => !row.finalDecision)
    if (unresolved.length) {
      setError(t('passages.resolveAll'))
      return
    }
    if (!window.confirm(t('passages.confirmApply'))) return
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const result = await confirmPassage({
        schoolYear: preview.school_year,
        targetSchoolYear: targetYear,
        classId: preview.class_id,
        decisions: rows,
      })
      setMessage(t('passages.applied', { count: result.applied_count }))
      await loadPreview()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="admin-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('passages.title')}</h2>
          <p className="muted">{t('passages.subtitle')}</p>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}
      {message && <p className="grade-summary">{message}</p>}
      {classes === null && !error && <Spinner label={t('classes.loading')} />}

      {classes && (
        <div className="card admin-form">
          <div className="form-grid">
            <label className="field">
              <span>{t('passages.sourceYear')}</span>
              <select value={sourceYear} onChange={(event) => {
                setSourceYear(event.target.value)
                setTargetYear(nextSchoolYear(event.target.value))
                setPreview(null)
              }}>
                {Array.from(new Set(classes.map((row) => row.school_year))).sort().map((year) => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>{t('passages.targetYear')}</span>
              <input value={targetYear} onChange={(event) => setTargetYear(event.target.value)} />
            </label>
            <label className="field">
              <span>{t('students.class')}</span>
              <select value={classId} onChange={(event) => {
                setClassId(event.target.value)
                setPreview(null)
              }}>
                {sourceClasses.map((row) => (
                  <option key={row.id} value={row.id}>{row.name_fr}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="grade-actions">
            <button type="button" className="btn btn-primary" onClick={loadPreview} disabled={loading || !classId || !targetYear.trim()}>
              {loading ? t('common.loading') : t('passages.preview')}
            </button>
            <Link to="/admin/classes" className="btn btn-ghost">{t('passages.createTargetClasses')}</Link>
          </div>
        </div>
      )}

      {loading && <Spinner label={t('passages.loading')} />}
      {preview && preview.target_class_guidance && (
        <div className="warning-banner">
          {preview.target_class_guidance}
        </div>
      )}
      {preview && preview.students.length === 0 && <Empty message={t('passages.empty')} />}
      {preview && preview.students.length > 0 && (
        <div className="list-stack">
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('reports.student')}</th>
                  <th>{t('passages.annual')}</th>
                  <th>{t('passages.suggestion')}</th>
                  <th>{t('passages.decision')}</th>
                  <th>{t('passages.targetClass')}</th>
                  <th>{t('passages.note')}</th>
                </tr>
              </thead>
              <tbody>
                {preview.students.map((row) => {
                  const current = decisions[row.student_id] || {}
                  return (
                    <tr key={row.student_id}>
                      <td>
                        <strong>{row.student_name}</strong>
                        <div className="muted">{row.student_number}</div>
                      </td>
                      <td className="nowrap">
                        <div>FR {average(row.annual_french_average)}</div>
                        <div>EN {average(row.annual_english_average)}</div>
                        {row.incomplete_data && <div className="status-pill status-warning">{t('passages.incomplete')}</div>}
                      </td>
                      <td>
                        <span className={`status-pill ${row.suggested_decision === 'pass' ? 'status-success' : row.suggested_decision === 'repeat' ? 'status-warning' : 'status-neutral'}`}>
                          {decisionLabel(row.suggested_decision, t)}
                        </span>
                        <div className="muted">{row.suggested_reason}</div>
                      </td>
                      <td>
                        <select
                          value={current.finalDecision || ''}
                          onChange={(event) => updateDecision(row.student_id, { finalDecision: event.target.value })}
                        >
                          <option value="">{t('passages.choose')}</option>
                          <option value="pass">{t('passages.pass')}</option>
                          <option value="repeat">{t('passages.repeat')}</option>
                          {row.target_options.includes('Diplômé') && <option value="graduate">{t('passages.graduate')}</option>}
                        </select>
                      </td>
                      <td>
                        {current.finalDecision === 'pass' && row.target_options.filter((name) => name !== 'Diplômé').length > 1 ? (
                          <select
                            value={current.targetClassName || ''}
                            onChange={(event) => updateDecision(row.student_id, { targetClassName: event.target.value })}
                          >
                            <option value="">{t('passages.choose')}</option>
                            {row.target_options.filter((name) => name !== 'Diplômé').map((name) => (
                              <option key={name} value={name}>{name}</option>
                            ))}
                          </select>
                        ) : (
                          <span>{current.finalDecision === 'repeat' ? row.current_class_name : current.targetClassName || '—'}</span>
                        )}
                      </td>
                      <td>
                        <input
                          value={current.note || ''}
                          onChange={(event) => updateDecision(row.student_id, { note: event.target.value })}
                          placeholder={t('passages.notePlaceholder')}
                        />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="grade-actions">
            <button type="button" className="btn btn-primary" onClick={handleConfirm} disabled={saving || !preview.target_classes_ready}>
              {saving ? t('common.saving') : t('passages.apply')}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
