import { Link, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import LanguageSwitcher from './LanguageSwitcher.jsx'

export default function Layout() {
  const { user, role, logout, homePath } = useAuth()

  return (
    <div className="app">
      <header className="topbar">
        <Link to={homePath} className="brand">
          School Reports
        </Link>
        <div className="topbar-right">
          {user && <span className="parent-name">{user.name}</span>}
          {role === 'parent' && (
            <Link to="/settings" className="btn btn-ghost">
              Settings
            </Link>
          )}
          <LanguageSwitcher />
          <button type="button" className="btn btn-ghost" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
