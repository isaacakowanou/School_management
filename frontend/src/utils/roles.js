// Maps a role to the landing path for that role's area of the app.
export function homePathForRole(role) {
  return role === 'admin' ? '/admin/audit-logs' : '/'
}

// True when `path` belongs to the given role's area. Admin owns /admin/*;
// everything else is the parent area. Used to restore deep links after login.
export function isPathForRole(path, role) {
  const isAdminPath = path.startsWith('/admin')
  return role === 'admin' ? isAdminPath : !isAdminPath
}
