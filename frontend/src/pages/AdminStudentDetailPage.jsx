import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getStudent, getStudentParents } from '../api/students.js'
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
  const [reports, setReports] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setStudent(null)
    setParents([])
    setReports([])

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
      const [linkedParents, studentReports] = await Promise.allSettled([
        getStudentParents(studentId),
        getStudentReports(studentId),
      ])
      if (cancelled) return
      if (linkedParents.status === 'fulfilled') setParents(linkedParents.value)
      if (studentReports.status === 'fulfilled') setReports(studentReports.value)
    }

    load()
    return () => {
      cancelled = true
    }
  }, [studentId])

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

      <h3 className="section-title">Linked parents</h3>
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
