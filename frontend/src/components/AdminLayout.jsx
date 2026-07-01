import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'

// Layout for the admin area only. Adds a left sidebar for navigation between
// admin pages. Parent and teacher areas keep using the plain Layout (topbar only).
const NAV_ITEMS = [
  { to: '/admin', label: 'Dashboard', end: true },
  { to: '/admin/reports', label: 'Reports', end: false },
  { to: '/admin/students', label: 'Students', end: false },
  { to: '/admin/teachers', label: 'Teachers', end: false },
  { to: '/admin/parents', label: 'Parents', end: false },
  { to: '/admin/courses', label: 'Courses', end: false },
  { to: '/admin/classes', label: 'Classes', end: false },
  { to: '/admin/audit-logs', label: 'Audit logs', end: false },
]

export default function AdminLayout() {
  const { user, logout, homePath } = useAuth()

  return (
    <div className="app">
      <header className="topbar">
        <Link to={homePath} className="brand">
          School Reports
        </Link>
        <div className="topbar-right">
          {user && <span className="parent-name">{user.name}</span>}
          <button type="button" className="btn btn-ghost" onClick={logout}>
            Log out
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
              {item.label}
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
