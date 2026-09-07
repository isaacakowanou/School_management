import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  BookOpen,
  FileText,
  GraduationCap,
  School,
  ScrollText,
  UserPlus,
  UserRound,
  Users,
} from 'lucide-react'
import { getAdminStats } from '../api/adminStats.js'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Spinner from '../components/Spinner.jsx'

function StatCard({ icon: Icon, label, value }) {
  return (
    <div className="admin-stat-card">
      <div className="admin-stat-icon" aria-hidden="true">
        <Icon size={20} />
      </div>
      <div>
        <div className="admin-stat-value">{value}</div>
        <div className="admin-stat-label">{label}</div>
      </div>
    </div>
  )
}

function BulletinCount({ label, value, max }) {
  const width = value > 0 && max > 0 ? Math.max(8, Math.round((value / max) * 100)) : 0
  return (
    <div className="bulletin-count-row">
      <div className="bulletin-count-text">
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <div className="bulletin-count-track" aria-hidden="true">
        <span style={{ width: `${width}%` }} />
      </div>
    </div>
  )
}

export default function AdminDashboardPage() {
  const { t } = useTranslation()
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const loadStats = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setStats(await getAdminStats())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    loadStats()
  }, [loadStats])

  const statCards = useMemo(() => {
    if (!stats) return []
    return [
      { key: 'students', label: t('adminDashboard.stats.students'), value: stats.students, icon: GraduationCap },
      { key: 'teachers', label: t('adminDashboard.stats.teachers'), value: stats.teachers, icon: Users },
      { key: 'parents', label: t('adminDashboard.stats.parents'), value: stats.parents, icon: UserRound },
      { key: 'classes', label: t('adminDashboard.stats.classes'), value: stats.classes, icon: School },
    ]
  }, [stats, t])

  const generated = stats?.bulletins?.generated ?? 0
  const maxBulletins = Math.max(generated, stats?.bulletins?.approved ?? 0, stats?.bulletins?.sent ?? 0)

  return (
    <section className="admin-page admin-dashboard">
      <div className="page-heading">
        <div>
          <h2 className="page-title">{t('adminDashboard.title')}</h2>
          <p className="muted">{t('adminDashboard.subtitle')}</p>
        </div>
      </div>

      {error && (
        <div className="dashboard-error">
          <ErrorBanner message={error} />
          <button type="button" className="btn btn-ghost" onClick={loadStats}>
            {t('adminDashboard.retry')}
          </button>
        </div>
      )}

      {!error && loading && <Spinner label={t('adminDashboard.loading')} />}

      {!error && !loading && stats && (
        <>
          <div className="admin-stats-grid">
            {statCards.map((card) => (
              <StatCard key={card.key} icon={card.icon} label={card.label} value={card.value} />
            ))}
          </div>

          <div className="dashboard-main-grid">
            <Link to="/admin/reports" className="dashboard-bulletins-card">
              <div className="dashboard-card-header">
                <div>
                  <div className="section-title">{t('adminDashboard.bulletins.title')}</div>
                  <p className="muted">
                    {stats.current_term
                      ? t('adminDashboard.bulletins.currentTerm', { term: stats.current_term.name })
                      : t('adminDashboard.bulletins.noCurrentTerm')}
                  </p>
                </div>
                <FileText size={22} aria-hidden="true" />
              </div>
              <div className="bulletin-summary">
                <BulletinCount
                  label={t('adminDashboard.bulletins.generated')}
                  value={stats.bulletins.generated}
                  max={maxBulletins}
                />
                <BulletinCount
                  label={t('adminDashboard.bulletins.approved')}
                  value={stats.bulletins.approved}
                  max={maxBulletins}
                />
                <BulletinCount
                  label={t('adminDashboard.bulletins.sent')}
                  value={stats.bulletins.sent}
                  max={maxBulletins}
                />
              </div>
            </Link>

            <div className="dashboard-actions-card">
              <div className="section-title">{t('adminDashboard.quickActions.title')}</div>
              <div className="quick-actions-row">
                <Link to="/admin/courses" className="btn btn-primary">
                  <BookOpen size={18} aria-hidden="true" />
                  {t('adminDashboard.quickActions.enterGrades')}
                </Link>
                <Link to="/admin/reports/class" className="btn btn-primary">
                  <FileText size={18} aria-hidden="true" />
                  {t('adminDashboard.quickActions.generateReports')}
                </Link>
                <Link to="/admin/students/new" className="btn btn-primary">
                  <UserPlus size={18} aria-hidden="true" />
                  {t('adminDashboard.quickActions.addStudent')}
                </Link>
              </div>
              <Link to="/admin/audit-logs" className="dashboard-secondary-link">
                <ScrollText size={18} aria-hidden="true" />
                <span>{t('adminDashboard.auditLogsLink')}</span>
              </Link>
            </div>
          </div>
        </>
      )}
    </section>
  )
}
