import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { FileSpreadsheet, Link2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { commitParentLinkImport, previewParentLinkImport } from '../api/parents.js'
import ErrorBanner from '../components/ErrorBanner.jsx'

function issueText(t, issue) {
  return t(`parentLinkImport.issues.${issue.code}`, { defaultValue: issue.message })
}

export default function AdminParentLinkImportPage() {
  const { t } = useTranslation()
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [selectedRows, setSelectedRows] = useState(new Set())
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [previewing, setPreviewing] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const selectedList = useMemo(() => [...selectedRows].sort((a, b) => a - b), [selectedRows])

  function resetPreview() {
    setPreview(null)
    setSelectedRows(new Set())
    setResult(null)
    setError(null)
  }

  async function handlePreview(event) {
    event.preventDefault()
    if (!file) {
      setError(t('parentLinkImport.fileRequired'))
      return
    }
    setPreviewing(true)
    setError(null)
    setResult(null)
    try {
      const data = await previewParentLinkImport(file)
      setPreview(data)
      setSelectedRows(new Set(data.rows.filter((row) => row.is_valid).map((row) => row.row_number)))
    } catch (err) {
      setError(err.message)
      setPreview(null)
      setSelectedRows(new Set())
    } finally {
      setPreviewing(false)
    }
  }

  function toggleRow(rowNumber) {
    setSelectedRows((current) => {
      const next = new Set(current)
      if (next.has(rowNumber)) next.delete(rowNumber)
      else next.add(rowNumber)
      return next
    })
  }

  async function handleCommit() {
    setCommitting(true)
    setError(null)
    try {
      const data = await commitParentLinkImport({ file, selectedRows: selectedList })
      setResult(data)
      setPreview(null)
      setSelectedRows(new Set())
      setShowConfirm(false)
    } catch (err) {
      setError(err.message)
      setShowConfirm(false)
    } finally {
      setCommitting(false)
    }
  }

  return (
    <section className="admin-page">
      <Link to="/admin/parents" className="back-link">← {t('nav.parents')}</Link>
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('parentLinkImport.title')}</h2>
          <p className="muted">{t('parentLinkImport.subtitle')}</p>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}
      <form className="card admin-form" onSubmit={handlePreview}>
        <label className="field">
          <span>{t('parentLinkImport.fileLabel')}</span>
          <input
            className="import-file-input"
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={(event) => {
              setFile(event.target.files?.[0] || null)
              resetPreview()
            }}
            disabled={previewing || committing}
          />
        </label>
        <div className="import-column-help">
          <p><strong>{t('parentLinkImport.requiredColumns')}</strong></p>
          <p>{t('parentLinkImport.optionalColumns')}</p>
        </div>
        <button type="submit" className="btn btn-primary" disabled={!file || previewing || committing}>
          <FileSpreadsheet size={17} aria-hidden="true" />
          {previewing ? t('parentLinkImport.previewing') : t('parentLinkImport.preview')}
        </button>
      </form>

      {preview && (
        <div className="list-stack">
          <div className="import-summary">
            <span>{t('parentLinkImport.total')}: <strong>{preview.total_rows}</strong></span>
            <span>{t('parentLinkImport.valid')}: <strong>{preview.valid_rows}</strong></span>
            <span>{t('parentLinkImport.invalid')}: <strong>{preview.invalid_rows}</strong></span>
            <span>{t('parentLinkImport.selected')}: <strong>{selectedRows.size}</strong></span>
          </div>
          <div className="table-scroll">
            <table className="table import-preview-table">
              <thead><tr>
                <th>{t('parentLinkImport.include')}</th>
                <th>{t('parentLinkImport.row')}</th>
                <th>{t('parentLinkImport.student')}</th>
                <th>{t('parentLinkImport.parent')}</th>
                <th>{t('parentLinkImport.relationship')}</th>
                <th>{t('parentLinkImport.actions')}</th>
                <th>{t('parentLinkImport.validation')}</th>
              </tr></thead>
              <tbody>
                {preview.rows.map((row) => (
                  <tr key={row.row_number} className={row.is_valid ? '' : 'import-row-invalid'}>
                    <td><input
                      type="checkbox"
                      checked={selectedRows.has(row.row_number)}
                      onChange={() => toggleRow(row.row_number)}
                      disabled={!row.is_valid}
                      aria-label={t('parentLinkImport.selectRow', { row: row.row_number })}
                    /></td>
                    <td>{row.row_number}</td>
                    <td><strong>{row.student_name || row.student_number}</strong><div className="muted">{row.student_number}</div></td>
                    <td><strong>{row.parent_name}</strong><div className="muted">{row.parent_email}</div><div className="muted">{row.parent_phone || '—'}</div></td>
                    <td>{row.relationship || '—'}</td>
                    <td>{t(`parentLinkImport.parentActions.${row.parent_action}`)} · {t(`parentLinkImport.linkActions.${row.link_action}`)}</td>
                    <td>
                      {row.is_valid && row.warnings.length === 0 && <span className="import-ready">{t('parentLinkImport.ready')}</span>}
                      {row.errors.map((issue, index) => <div className="import-error" key={`${issue.code}-${index}`}>{issueText(t, issue)}</div>)}
                      {row.warnings.map((issue, index) => <div className="import-warning" key={`${issue.code}-${index}`}>{issueText(t, issue)}</div>)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="grade-actions">
            <button type="button" className="btn btn-primary" disabled={selectedRows.size === 0 || committing} onClick={() => setShowConfirm(true)}>
              <Link2 size={17} aria-hidden="true" /> {t('parentLinkImport.importSelected', { count: selectedRows.size })}
            </button>
          </div>
        </div>
      )}

      {result && (
        <div className="card import-result">
          <h3>{t('parentLinkImport.resultTitle')}</h3>
          <p>{t('parentLinkImport.resultSummary', result)}</p>
          {result.failures.length > 0 && <div><strong>{t('parentLinkImport.failedRows')}</strong>{result.failures.map((failure) => (
            <p key={failure.row_number}>{t('parentLinkImport.rowFailure', { row: failure.row_number })}: {failure.errors.map((issue) => issueText(t, issue)).join(' ')}</p>
          ))}</div>}
          {result.email_results.filter((item) => !item.success).map((item) => (
            <ErrorBanner key={item.parent_id} message={t('parentLinkImport.emailFailedPassword', { email: item.email, password: item.temp_password })} />
          ))}
          <Link to="/admin/parents" className="btn btn-primary">{t('parentLinkImport.backToParents')}</Link>
        </div>
      )}

      {showConfirm && (
        <div className="modal-backdrop" onClick={() => !committing && setShowConfirm(false)}>
          <div className="card modal-card" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <h3>{t('parentLinkImport.confirmTitle')}</h3>
            <p>{t('parentLinkImport.confirmBody', { count: selectedRows.size })}</p>
            <div className="grade-actions">
              <button type="button" className="btn btn-ghost" onClick={() => setShowConfirm(false)} disabled={committing}>{t('common.cancel')}</button>
              <button type="button" className="btn btn-primary" onClick={handleCommit} disabled={committing}>{committing ? t('parentLinkImport.importing') : t('parentLinkImport.confirm')}</button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
