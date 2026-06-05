import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getStudent, getStudentParents, linkStudentParent } from '../api/students.js'
import { listParents } from '../api/parents.js'
import { getStudentReports } from '../api/reports.js'
import { formatGpa, formatPercent } from '../utils/format.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'
import StatusBadge from '../components/StatusBadge.jsx'

export default function AdminStudentDetailPage() {
  const { studentId } = useParams()
  const [student, setStudent] = useState(null)
  const [parents, setParents] = useState([])
  const [allParents, setAllParents] = useState([])
  const [reports, setReports] = useState([])
  const [error, setError] = useState(null)
  const [linkParentId, setLinkParentId] = useState('')
  const [relationship, setRelationship] = useState('')
  const [linking, setLinking] = useState(false)
  const [linkError, setLinkError] = useState(null)
  const [linkMessage, setLinkMessage] = useState(null)
  const [showLinkParentForm, setShowLinkParentForm] = useState(false)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setStudent(null)
    setParents([])
    setAllParents([])
    setReports([])
    setLinkParentId('')
    setRelationship('')
    setLinkError(null)
    setLinkMessage(null)
    setShowLinkParentForm(false)

    async function load() {
      try {
        const data = await getStudent(studentId)
        if (cancelled) return
        setStudent(data)
      } catch (err) {
        if (!cancelled) setError(err.message)
        return
      }
      // Related sections are best-effort; one failing won't blank the page.
      const [linkedParents, studentReports, parentOptions] = await Promise.allSettled([
        getStudentParents(studentId),
        getStudentReports(studentId),
        listParents(),
      ])
      if (cancelled) return
      if (linkedParents.status === 'fulfilled') setParents(linkedParents.value)
      if (studentReports.status === 'fulfilled') setReports(studentReports.value)
      if (parentOptions.status === 'fulfilled') setAllParents(parentOptions.value)
    }

    load()
    return () => {
      cancelled = true
    }
  }, [studentId])

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

  async function handleLinkParent(event) {
    event.preventDefault()
    setLinkError(null)
    setLinkMessage(null)

    if (!linkParentId) {
      setLinkError('Choose a parent to link.')
      return
    }

    setLinking(true)
    try {
      await linkStudentParent(studentId, {
        parentId: linkParentId,
        relationship,
      })
      const linked = await getStudentParents(studentId)
      setParents(linked)
      setRelationship('')
      setLinkMessage('Parent linked.')
      setShowLinkParentForm(false)
    } catch (err) {
      setLinkError(err.message)
    } finally {
      setLinking(false)
    }
  }

  if (error) {
    return (
      <section className="admin-page">
        <Link to="/admin/students" className="back-link">
          ← Students
        </Link>
        <ErrorBanner message={error} />
      </section>
    )
  }

  if (!student) {
    return (
      <section className="admin-page">
        <Spinner label="Loading student…" />
      </section>
    )
  }

  return (
    <section className="admin-page">
      <Link to="/admin/students" className="back-link">
        ← Students
      </Link>
      <h2 className="page-title">
        {student.first_name} {student.last_name}
      </h2>
      <p className="muted">
        {student.grade_level} · #{student.student_number}
      </p>

      <h3 className="section-title">Parents</h3>
      {!showLinkParentForm && (
        <div className="grade-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setLinkError(null)
              setLinkMessage(null)
              setShowLinkParentForm(true)
            }}
          >
            Link parent
          </button>
        </div>
      )}
      {linkMessage && <p className="grade-summary">{linkMessage}</p>}
      {showLinkParentForm && (
        <form className="card admin-form" onSubmit={handleLinkParent}>
          <label className="field">
            <span>Parent</span>
            <select
              className="grade-input"
              value={linkParentId}
              onChange={(event) => setLinkParentId(event.target.value)}
              disabled={linking || availableParents.length === 0}
              required
              style={{ width: '100%', textAlign: 'left' }}
            >
              {availableParents.length === 0 ? (
                <option value="">No available parents</option>
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
            <span>Relationship</span>
            <select
              className="grade-input"
              value={relationship}
              onChange={(event) => setRelationship(event.target.value)}
              disabled={linking}
              style={{ width: '100%', textAlign: 'left' }}
            >
              <option value="">Optional</option>
              <option value="Mother">Mother</option>
              <option value="Father">Father</option>
              <option value="Guardian">Guardian</option>
              <option value="Other">Other</option>
            </select>
          </label>

          <div className="grade-actions">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={linking || availableParents.length === 0}
            >
              {linking ? 'Linking...' : 'Link parent'}
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
              Cancel
            </button>
          </div>
          {linkError && <ErrorBanner message={linkError} />}
        </form>
      )}

      {parents.length === 0 ? (
        <Empty message="No parents linked to this student." />
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Relationship</th>
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
                    <Link className="back-link" to={`/admin/parents/${parent.id}`}>
                      Open →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3 className="section-title">Reports</h3>
      {reports.length === 0 ? (
        <Empty message="No reports for this student." />
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Term</th>
                <th>School year</th>
                <th>Status</th>
                <th className="num">Average</th>
                <th className="num">GPA</th>
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
                  <td className="num">{formatPercent(report.overall_average)}</td>
                  <td className="num">{formatGpa(report.gpa)}</td>
                  <td className="nowrap">
                    <Link className="back-link" to={`/admin/reports/${report.id}`}>
                      Open →
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
