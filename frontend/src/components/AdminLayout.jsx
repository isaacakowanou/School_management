import { Link, NavLink, Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../auth/AuthContext.jsx'
import LanguageSwitcher from './LanguageSwitcher.jsx'

const NAV_ITEMS = [
  { to: '/admin', key: 'nav.dashboard', end: true },
  { to: '/admin/reports', key: 'nav.reports', end: false },
  { to: '/admin/students', key: 'nav.students', end: false },
  { to: '/admin/teachers', key: 'nav.teachers', end: false },
  { to: '/admin/parents', key: 'nav.parents', end: false },
  { to: '/admin/courses', key: 'nav.courses', end: false },
  { to: '/admin/classes', key: 'nav.classes', end: false },
  { to: '/admin/subjects', key: 'nav.subjects', end: false },
  { to: '/admin/trash', key: 'nav.trash', end: false },
  { to: '/admin/danger-zone', key: 'nav.dangerZone', end: false },
  { to: '/admin/audit-logs', key: 'nav.auditLogs', end: false },
]

export default function AdminLayout() {
  const { user, logout, homePath } = useAuth()
  const { t } = useTranslation()

  return (
    <div className="app">
      <header className="topbar">
        <Link to={homePath} className="brand">
          {t('common.schoolName')}
        </Link>
        <div className="topbar-right">
          {user && <span className="parent-name">{user.name}</span>}
          <LanguageSwitcher />
          <button type="button" className="btn btn-ghost" onClick={logout}>
            {t('common.logout')}
          </button>
        </div>
      </header>

      <div className="admin-shell">
        <nav className="admin-sidebar" aria-label="Admin navigation">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `admin-nav-link${isActive ? ' admin-nav-link-active' : ''}`
              }
            >
              {t(item.key)}
            </NavLink>
          ))}
        </nav>

        <main className="admin-main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
