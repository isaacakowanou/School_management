import { Link } from 'react-router-dom'

export default function AdminDashboardPage() {
  return (
    <section className="admin-page">
      <h2 className="page-title">Admin dashboard</h2>
      <p className="muted">
        Manage report cards and review activity across the school. Use the links below or the
        sidebar to get started.
      </p>

      <ul className="card-list">
        <li>
          <Link className="card student-card" to="/admin/reports">
            <div className="student-name">Reports</div>
            <div className="muted">
              Review, check, summarize, approve, and send student report cards.
            </div>
          </Link>
        </li>
        <li>
          <Link className="card student-card" to="/admin/audit-logs">
            <div className="student-name">Audit logs</div>
            <div className="muted">Trace grade changes, approvals, and report sending.</div>
          </Link>
        </li>
      </ul>
    </section>
  )
}
