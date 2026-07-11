import { Link, Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../auth/AuthContext.jsx'
import LanguageSwitcher from './LanguageSwitcher.jsx'

export default function Layout() {
  const { user, role, logout, homePath } = useAuth()
  const { t } = useTranslation()

  return (
    <div className="app">
      <header className="topbar">
        <Link to={homePath} className="brand">
          {t('common.schoolName')}
        </Link>
        <div className="topbar-right">
          {user && <span className="parent-name">{user.name}</span>}
          <Link to={role === 'teacher' ? '/teacher/settings' : '/settings'} className="btn btn-ghost">
            {t('common.settings')}
          </Link>
          <LanguageSwitcher />
          <button type="button" className="btn btn-ghost" onClick={logout}>
            {t('common.logout')}
          </button>
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
