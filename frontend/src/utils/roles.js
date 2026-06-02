// Maps a role to the landing path for that role's area of the app.
export function homePathForRole(role) {
  if (role === 'admin') return '/admin'
  if (role === 'teacher') return '/teacher'
  return '/'
}

// True when `path` belongs to the given role's area. Admin owns /admin/*,
// teacher owns /teacher/*; everything else is the parent area. Used to restore
// deep links after login.
export function isPathForRole(path, role) {
  if (role === 'admin') return path.startsWith('/admin')
  if (role === 'teacher') return path.startsWith('/teacher')
  return !path.startsWith('/admin') && !path.startsWith('/teacher')
}
