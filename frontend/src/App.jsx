import { Navigate, Route, Routes } from 'react-router-dom'
import RequireRole from './auth/RequireRole.jsx'
import Layout from './components/Layout.jsx'
import AdminLayout from './components/AdminLayout.jsx'
import LoginPage from './pages/LoginPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import StudentReportsPage from './pages/StudentReportsPage.jsx'
import ReportDetailPage from './pages/ReportDetailPage.jsx'
import AuditLogsPage from './pages/AuditLogsPage.jsx'
import TeacherCoursesPage from './pages/TeacherCoursesPage.jsx'
import TeacherCourseDetailPage from './pages/TeacherCourseDetailPage.jsx'
import AdminDashboardPage from './pages/AdminDashboardPage.jsx'
import AdminReportsPage from './pages/AdminReportsPage.jsx'
import AdminReportDetailPage from './pages/AdminReportDetailPage.jsx'
import AdminStudentsPage from './pages/AdminStudentsPage.jsx'
import AdminParentsPage from './pages/AdminParentsPage.jsx'
import AdminTeachersPage from './pages/AdminTeachersPage.jsx'
import AdminCoursesPage from './pages/AdminCoursesPage.jsx'
import AdminStudentCreatePage from './pages/AdminStudentCreatePage.jsx'
import AdminStudentDetailPage from './pages/AdminStudentDetailPage.jsx'
import AdminParentDetailPage from './pages/AdminParentDetailPage.jsx'
import AdminTeacherDetailPage from './pages/AdminTeacherDetailPage.jsx'
import AdminCourseDetailPage from './pages/AdminCourseDetailPage.jsx'

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

      {/* Teacher area */}
      <Route
        element={
          <RequireRole role="teacher">
            <Layout />
          </RequireRole>
        }
      >
        <Route path="/teacher" element={<TeacherCoursesPage />} />
        <Route path="/teacher/courses/:courseId" element={<TeacherCourseDetailPage />} />
      </Route>

      {/* Admin area */}
      <Route
        element={
          <RequireRole role="admin">
            <AdminLayout />
          </RequireRole>
        }
      >
        <Route path="/admin" element={<AdminDashboardPage />} />
        <Route path="/admin/reports" element={<AdminReportsPage />} />
        <Route path="/admin/reports/:reportId" element={<AdminReportDetailPage />} />
        <Route path="/admin/students" element={<AdminStudentsPage />} />
        <Route path="/admin/students/new" element={<AdminStudentCreatePage />} />
        <Route path="/admin/students/:studentId" element={<AdminStudentDetailPage />} />
        <Route path="/admin/teachers" element={<AdminTeachersPage />} />
        <Route path="/admin/teachers/:teacherId" element={<AdminTeacherDetailPage />} />
        <Route path="/admin/parents" element={<AdminParentsPage />} />
        <Route path="/admin/parents/:parentId" element={<AdminParentDetailPage />} />
        <Route path="/admin/courses" element={<AdminCoursesPage />} />
        <Route path="/admin/courses/:courseId" element={<AdminCourseDetailPage />} />
        <Route path="/admin/audit-logs" element={<AuditLogsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
