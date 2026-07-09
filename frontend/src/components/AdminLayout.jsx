import { Link, NavLink, Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  BookOpen,
  FileText,
  GraduationCap,
  LayoutDashboard,
  Library,
  School,
  ScrollText,
  ShieldAlert,
  Trash2,
  UserRound,
  Users,
} from 'lucide-react'
import { useAuth } from '../auth/AuthContext.jsx'
import LanguageSwitcher from './LanguageSwitcher.jsx'

const NAV_GROUPS = [
  {
    items: [
      { to: '/admin', key: 'nav.dashboard', end: true, icon: LayoutDashboard },
    ],
  },
  {
    labelKey: 'navSections.management',
    items: [
      { to: '/admin/students', key: 'nav.students', end: false, icon: GraduationCap },
      { to: '/admin/teachers', key: 'nav.teachers', end: false, icon: Users },
      { to: '/admin/parents', key: 'nav.parents', end: false, icon: UserRound },
      { to: '/admin/classes', key: 'nav.classes', end: false, icon: School },
      { to: '/admin/courses', key: 'nav.courses', end: false, icon: BookOpen },
      { to: '/admin/subjects', key: 'nav.subjects', end: false, icon: Library },
    ],
  },
  {
    labelKey: 'navSections.reports',
    items: [
      { to: '/admin/reports', key: 'nav.reports', end: false, icon: FileText },
    ],
  },
  {
    labelKey: 'navSections.system',
    items: [
      { to: '/admin/audit-logs', key: 'nav.auditLogs', end: false, icon: ScrollText },
      { to: '/admin/trash', key: 'nav.trash', end: false, icon: Trash2 },
      { to: '/admin/danger-zone', key: 'nav.dangerZone', end: false, icon: ShieldAlert },
    ],
  },
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
          {NAV_GROUPS.map((group, groupIndex) => (
            <div className="admin-nav-group" key={group.labelKey || 'primary'}>
              {group.labelKey && <div className="admin-nav-section">{t(group.labelKey)}</div>}
              {group.items.map((item) => {
                const Icon = item.icon
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      `admin-nav-link${isActive ? ' admin-nav-link-active' : ''}`
                    }
                  >
                    <Icon className="admin-nav-icon" size={18} aria-hidden="true" />
                    <span>{t(item.key)}</span>
                  </NavLink>
                )
              })}
              {groupIndex < NAV_GROUPS.length - 1 && <div className="admin-nav-divider" aria-hidden="true" />}
            </div>
          ))}
        </nav>

        <main className="admin-main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
