import { Navigate, Route, Routes } from 'react-router-dom'
import RequireRole from './auth/RequireRole.jsx'
import Layout from './components/Layout.jsx'
import LoginPage from './pages/LoginPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import StudentReportsPage from './pages/StudentReportsPage.jsx'
import ReportDetailPage from './pages/ReportDetailPage.jsx'
import AuditLogsPage from './pages/AuditLogsPage.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* Parent area */}
      <Route
        element={
          <RequireRole role="parent">
            <Layout />
          </RequireRole>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/students/:studentId/reports" element={<StudentReportsPage />} />
        <Route path="/reports/:reportId" element={<ReportDetailPage />} />
      </Route>

      {/* Admin area */}
      <Route
        element={
          <RequireRole role="admin">
            <Layout />
          </RequireRole>
        }
      >
        <Route path="/admin/audit-logs" element={<AuditLogsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
