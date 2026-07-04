import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

export default function AdminDashboardPage() {
  const { t } = useTranslation()

  return (
    <section className="admin-page">
      <h2 className="page-title">{t('adminDashboard.title')}</h2>
      <p className="muted">{t('adminDashboard.subtitle')}</p>

      <ul className="card-list">
        <li>
          <Link className="card student-card" to="/admin/reports">
            <div className="student-name">{t('nav.reports')}</div>
            <div className="muted">{t('adminDashboard.reportsDescription')}</div>
          </Link>
        </li>
        <li>
          <Link className="card student-card" to="/admin/audit-logs">
            <div className="student-name">{t('nav.auditLogs')}</div>
            <div className="muted">{t('adminDashboard.auditLogsDescription')}</div>
          </Link>
        </li>
      </ul>
    </section>
  )
}
