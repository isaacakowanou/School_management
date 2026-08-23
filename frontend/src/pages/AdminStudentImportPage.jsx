import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { FileSpreadsheet, Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAcademicQueryParams } from '../academic/AcademicContext.jsx'
import { commitStudentImport, previewStudentImport } from '../api/students.js'
import ErrorBanner from '../components/ErrorBanner.jsx'

function issueText(t, issue) {
  return t(`studentImport.issues.${issue.code}`, { defaultValue: issue.message })
}

export default function AdminStudentImportPage() {
  const { t } = useTranslation()
  const { selectedSchoolYear, setSelectedSchoolYear, availableSchoolYears } = useAcademicQueryParams({ includeTerm: false })
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [selectedRows, setSelectedRows] = useState(new Set())
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [previewing, setPreviewing] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)

  const selectedCount = selectedRows.size
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
      setError(t('studentImport.fileRequired'))
      return
    }
    setPreviewing(true)
    setError(null)
    setResult(null)
    try {
      const data = await previewStudentImport({ file, schoolYear: selectedSchoolYear })
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
      const data = await commitStudentImport({
        file,
        schoolYear: selectedSchoolYear,
        selectedRows: selectedList,
      })
      setResult(data)
      setShowConfirm(false)
      setPreview(null)
      setSelectedRows(new Set())
    } catch (err) {
      setError(err.message)
      setShowConfirm(false)
    } finally {
      setCommitting(false)
    }
  }

  return (
    <section className="admin-page">
      <Link to="/admin/students" className="back-link">
        ← {t('students.title')}
      </Link>

      <div className="report-header">
        <div>
          <h2 className="page-title">{t('studentImport.title')}</h2>
          <p className="muted">{t('studentImport.subtitle')}</p>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      <form className="card admin-form" onSubmit={handlePreview}>
        <label className="field">
          <span>{t('common.schoolYear')}</span>
          <select
            value={selectedSchoolYear}
            onChange={(event) => {
              setSelectedSchoolYear(event.target.value)
              resetPreview()
            }}
            disabled={previewing || committing}
          >
            {availableSchoolYears.map((year) => <option key={year} value={year}>{year}</option>)}
          </select>
        </label>

        <label className="field">
          <span>{t('studentImport.fileLabel')}</span>
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

        <p className="muted import-columns-copy">
          {t('studentImport.requiredColumns')}
          <br />
          {t('studentImport.optionalColumns')}
        </p>

        <div className="grade-actions">
          <button type="submit" className="btn btn-primary" disabled={!file || previewing || committing}>
            <Upload size={16} aria-hidden="true" />
            {previewing ? t('studentImport.previewing') : t('studentImport.preview')}
          </button>
        </div>
      </form>

      {preview && (
        <div className="list-stack">
          <div className="import-summary-grid">
            <div className="card"><strong>{preview.total_rows}</strong><span>{t('studentImport.total')}</span></div>
            <div className="card"><strong>{preview.valid_rows}</strong><span>{t('studentImport.valid')}</span></div>
            <div className="card"><strong>{preview.invalid_rows}</strong><span>{t('studentImport.invalid')}</span></div>
            <div className="card"><strong>{selectedCount}</strong><span>{t('studentImport.selected')}</span></div>
          </div>

          <div className="table-scroll">
            <table className="table import-preview-table">
              <thead>
                <tr>
                  <th>{t('studentImport.include')}</th>
                  <th>{t('studentImport.row')}</th>
                  <th>{t('studentImport.student')}</th>
                  <th>{t('students.class')}</th>
                  <th>{t('students.studentNumber')}</th>
                  <th>{t('studentImport.parent')}</th>
                  <th>{t('studentImport.parentAction')}</th>
                  <th>{t('studentImport.validation')}</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row) => (
                  <tr key={row.row_number} className={row.is_valid ? '' : 'import-row-invalid'}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedRows.has(row.row_number)}
                        onChange={() => toggleRow(row.row_number)}
                        disabled={!row.is_valid}
                        aria-label={t('studentImport.selectRow', { row: row.row_number })}
                      />
                    </td>
                    <td>{row.row_number}</td>
                    <td>
                      <strong>{row.student_first_name} {row.student_last_name}</strong>
                      {row.educmaster_number && <small className="muted">EducMaster: {row.educmaster_number}</small>}
                    </td>
                    <td>{row.class_name || '—'}</td>
                    <td>{row.student_number || t('studentImport.autoGenerated')}</td>
                    <td>
                      <strong>{row.parent_name}</strong>
                      <small className="muted">{row.parent_email}</small>
                    </td>
                    <td>
                      <span className={`badge ${row.parent_action === 'reuse' ? 'badge-approved' : 'badge-draft'}`}>
                        {t(`studentImport.parentActions.${row.parent_action}`)}
                      </span>
                    </td>
                    <td>
                      {row.is_valid && row.warnings.length === 0 && <span className="text-success">{t('studentImport.ready')}</span>}
                      {row.errors.map((issue, index) => (
                        <small className="import-issue import-issue-error" key={`${issue.code}-${index}`}>
                          {issueText(t, issue)}
                        </small>
                      ))}
                      {row.warnings.map((issue, index) => (
                        <small className="import-issue import-issue-warning" key={`${issue.code}-${index}`}>
                          {issueText(t, issue)}
                        </small>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grade-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={selectedCount === 0 || committing}
              onClick={() => setShowConfirm(true)}
            >
              <FileSpreadsheet size={16} aria-hidden="true" />
              {t('studentImport.importSelected', { count: selectedCount })}
            </button>
          </div>
        </div>
      )}

      {result && (
        <div className="card import-result-card">
          <h3>{t('studentImport.resultTitle')}</h3>
          <p>{t('studentImport.resultSummary', result)}</p>
          {result.failures.length > 0 && (
            <div>
              <h4>{t('studentImport.failedRows')}</h4>
              {result.failures.map((failure) => (
                <p key={failure.row_number} className="import-issue-error">
                  {t('studentImport.rowFailure', { row: failure.row_number })}: {failure.errors.map((issue) => issueText(t, issue)).join(' · ')}
                </p>
              ))}
            </div>
          )}
          {result.email_results.filter((item) => !item.success).map((item) => (
            <p key={item.parent_id} className="import-issue-warning">
              {t('studentImport.emailFailedPassword', { email: item.email, password: item.temp_password })}
            </p>
          ))}
          <Link to="/admin/students" className="btn btn-primary">{t('studentImport.backToStudents')}</Link>
        </div>
      )}

      {showConfirm && (
        <div className="modal-backdrop" onClick={() => !committing && setShowConfirm(false)}>
          <div className="card modal-card" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <h3>{t('studentImport.confirmTitle')}</h3>
            <p>{t('studentImport.confirmBody', { count: selectedCount, year: selectedSchoolYear })}</p>
            <div className="grade-actions">
              <button type="button" className="btn btn-ghost" onClick={() => setShowConfirm(false)} disabled={committing}>
                {t('common.cancel')}
              </button>
              <button type="button" className="btn btn-primary" onClick={handleCommit} disabled={committing}>
                {committing ? t('studentImport.importing') : t('studentImport.confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
