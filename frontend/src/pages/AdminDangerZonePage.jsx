import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  moveDangerZoneToTrash,
  previewDangerZoneDelete,
  searchDangerZoneTargets,
} from '../api/dangerZone.js'
import ErrorBanner from '../components/ErrorBanner.jsx'

const ENTITY_TYPES = ['student', 'parent', 'teacher', 'class', 'course', 'grade_item', 'report']

function dangerLabel(t, key) {
  return t(`dangerZone.labels.${key}`, { defaultValue: key })
}

function warningLabel(t, warning) {
  const key = {
    'Parent profiles are not moved when deleting a student.': 'studentKeepsParents',
    'Students are not moved when deleting a parent.': 'parentKeepsStudents',
    'Students are not moved when deleting a class.': 'classKeepsStudents',
  }[warning]
  return key ? t(`dangerZone.warnings.${key}`) : warning
}

function CountsTable({ counts, t }) {
  const rows = Object.entries(counts || {})
  if (rows.length === 0) return <p className="muted">{t('dangerZone.noDependents')}</p>
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>{t('dangerZone.tableCol')}</th>
            <th className="num">{t('dangerZone.recordsCol')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([table, count]) => (
            <tr key={table}>
              <td>{dangerLabel(t, table)}</td>
              <td className="num">{count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function AdminDangerZonePage() {
  const { t } = useTranslation()
  const [entityType, setEntityType] = useState('student')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [selected, setSelected] = useState(null)
  const [reason, setReason] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [loading, setLoading] = useState(false)
  const [searching, setSearching] = useState(false)

  const targetConfirmation = preview ? `MOVE ${preview.target_label} TO TRASH` : ''
  const canDelete =
    preview &&
    (confirmation.trim() === 'MOVE TO TRASH' || confirmation.trim() === targetConfirmation)

  useEffect(() => {
    setSelected(null)
    setPreview(null)
    setConfirmation('')
    setResults([])
  }, [entityType])

  useEffect(() => {
    let cancelled = false
    const trimmed = query.trim()
    setError(null)
    setPreview(null)
    setConfirmation('')
    if (!trimmed) {
      setResults([])
      setSearching(false)
      return () => {
        cancelled = true
      }
    }

    setSearching(true)
    const timer = window.setTimeout(() => {
      searchDangerZoneTargets(entityType, trimmed)
        .then((data) => {
          if (!cancelled) setResults(data)
        })
        .catch((err) => {
          if (!cancelled) setError(err.message)
        })
        .finally(() => {
          if (!cancelled) setSearching(false)
        })
    }, 250)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [entityType, query])

  function handleSelect(result) {
    setSelected(result)
    setPreview(null)
    setConfirmation('')
    setNotice(null)
  }

  async function handlePreview(event) {
    event.preventDefault()
    if (!selected) return
    setError(null)
    setNotice(null)
    setPreview(null)
    setConfirmation('')
    setLoading(true)
    try {
      const data = await previewDangerZoneDelete(entityType, selected.id)
      setPreview(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleMoveToTrash() {
    setError(null)
    setNotice(null)
    setLoading(true)
    try {
      const result = await moveDangerZoneToTrash({
        entity_type: entityType,
        entity_id: selected.id,
        confirmation,
        reason: reason.trim() || null,
      })
      setNotice(t('dangerZone.movedToTrash', { label: result.target_label, batchId: result.batch_id }))
      setPreview(null)
      setSelected(null)
      setQuery('')
      setResults([])
      setReason('')
      setConfirmation('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="admin-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('dangerZone.title')}</h2>
          <p className="muted">{t('dangerZone.subtitle')}</p>
        </div>
        <Link to="/admin/trash" className="btn btn-ghost">
          {t('nav.trash')}
        </Link>
      </div>

      {notice && <p className="grade-summary">{notice}</p>}
      {error && <ErrorBanner message={error} />}

      <form className="admin-form" onSubmit={handlePreview}>
        <label>
          {t('dangerZone.entityType')}
          <select
            value={entityType}
            onChange={(event) => {
              setEntityType(event.target.value)
              setQuery('')
            }}
          >
            {ENTITY_TYPES.map((type) => (
              <option key={type} value={type}>
                {dangerLabel(t, type)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('dangerZone.searchRecords')}
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value)
              setSelected(null)
            }}
            placeholder={t('dangerZone.searchPlaceholder')}
          />
        </label>
        {searching && <p className="muted">{t('dangerZone.searching')}</p>}
        {!searching && query.trim() && results.length === 0 && <p className="muted">{t('dangerZone.noMatches')}</p>}
        {results.length > 0 && (
          <div className="danger-search-results">
            {results.map((result) => (
              <button
                type="button"
                key={result.id}
                className={`danger-search-result${selected?.id === result.id ? ' danger-search-result-selected' : ''}`}
                onClick={() => handleSelect(result)}
              >
                <span>{result.label}</span>
                <small>{result.subtitle}</small>
              </button>
            ))}
          </div>
        )}
        {selected && (
          <div className="danger-selected">
            <span>{t('dangerZone.selected')}</span>
            <strong>{selected.label}</strong>
            <small>{selected.subtitle}</small>
          </div>
        )}
        <label>
          {t('dangerZone.note')}
          <input value={reason} onChange={(event) => setReason(event.target.value)} placeholder={t('dangerZone.notePlaceholder')} />
        </label>
        <button type="submit" className="btn btn-primary" disabled={loading || !selected}>
          {loading ? t('dangerZone.checking') : t('dangerZone.preview')}
        </button>
      </form>

      {preview && (
        <div className="admin-form">
          <h3>{t('dangerZone.preview')}</h3>
          <p>
            <strong>{preview.target_label}</strong>
          </p>
          <p className="muted">{t('dangerZone.previewDesc')}</p>
          <CountsTable counts={preview.counts} t={t} />
          {preview.warnings?.length > 0 && (
            <ul>
              {preview.warnings.map((warning) => (
                <li key={warning}>{warningLabel(t, warning)}</li>
              ))}
            </ul>
          )}
          <label>
            {t('dangerZone.confirmation')}
            <input
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              placeholder={targetConfirmation}
            />
          </label>
          <p className="muted">{t('dangerZone.confirmHint', { target: targetConfirmation })}</p>
          <button type="button" className="btn btn-danger" disabled={!canDelete || loading} onClick={handleMoveToTrash}>
            {t('dangerZone.moveToTrash')}
          </button>
        </div>
      )}
    </section>
  )
}
