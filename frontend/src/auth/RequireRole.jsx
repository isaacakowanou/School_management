import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext.jsx'
import Spinner from '../components/Spinner.jsx'
import { homePathForRole } from '../utils/roles.js'

// Guards a route subtree. Requires authentication and, when `role` is given,
// that the signed-in user has exactly that role. Wrong-role users are sent to
// their own area's home (so a parent can't reach admin pages and vice versa).
export default function RequireRole({ role, children }) {
  const { isAuthenticated, bootstrapping, role: currentRole } = useAuth()
  const location = useLocation()

  if (bootstrapping) {
    return (
      <div className="content">
        <Spinner label="Loading…" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  if (role && currentRole !== role) {
    return <Navigate to={homePathForRole(currentRole)} replace />
  }

  return children
}
