import { Navigate, Route, Routes } from 'react-router-dom'
import RequireRole from './auth/RequireRole.jsx'
import Layout from './components/Layout.jsx'
import AdminLayout from './components/AdminLayout.jsx'
import LoginPage from './pages/LoginPage.jsx'
import ForgotPasswordPage from './pages/ForgotPasswordPage.jsx'
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
import AdminStudentTrashPage from './pages/AdminStudentTrashPage.jsx'
import AdminParentsPage from './pages/AdminParentsPage.jsx'
import AdminTeachersPage from './pages/AdminTeachersPage.jsx'
import AdminCoursesPage from './pages/AdminCoursesPage.jsx'
import AdminStudentCreatePage from './pages/AdminStudentCreatePage.jsx'
import AdminStudentDetailPage from './pages/AdminStudentDetailPage.jsx'
import AdminParentCreatePage from './pages/AdminParentCreatePage.jsx'
import AdminParentDetailPage from './pages/AdminParentDetailPage.jsx'
import AdminTeacherCreatePage from './pages/AdminTeacherCreatePage.jsx'
import AdminTeacherDetailPage from './pages/AdminTeacherDetailPage.jsx'
import AdminCourseCreatePage from './pages/AdminCourseCreatePage.jsx'
import AdminCourseDetailPage from './pages/AdminCourseDetailPage.jsx'
import AdminClassesPage from './pages/AdminClassesPage.jsx'
import AdminSubjectsPage from './pages/AdminSubjectsPage.jsx'
import AdminDangerZonePage from './pages/AdminDangerZonePage.jsx'
import AdminTrashPage from './pages/AdminTrashPage.jsx'
import ChangePasswordPage from './pages/ChangePasswordPage.jsx'
import ParentSettingsPage from './pages/ParentSettingsPage.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />

      {/* Change password — any authenticated role; bypasses must_change_password guard */}
      <Route
        path="/change-password"
        element={
          <RequireRole>
            <ChangePasswordPage />
          </RequireRole>
        }
      />

      {/* Parent area */}
      <Route
        element={
          <RequireRole role="parent">
            <Layout />
          </RequireRole>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/settings" element={<ParentSettingsPage />} />
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
        <Route path="/admin/students/trash" element={<AdminStudentTrashPage />} />
        <Route path="/admin/students/:studentId" element={<AdminStudentDetailPage />} />
        <Route path="/admin/teachers" element={<AdminTeachersPage />} />
        <Route path="/admin/teachers/new" element={<AdminTeacherCreatePage />} />
        <Route path="/admin/teachers/:teacherId" element={<AdminTeacherDetailPage />} />
        <Route path="/admin/parents" element={<AdminParentsPage />} />
        <Route path="/admin/parents/new" element={<AdminParentCreatePage />} />
        <Route path="/admin/parents/:parentId" element={<AdminParentDetailPage />} />
        <Route path="/admin/courses" element={<AdminCoursesPage />} />
        <Route path="/admin/courses/new" element={<AdminCourseCreatePage />} />
        <Route path="/admin/courses/:courseId" element={<AdminCourseDetailPage />} />
        <Route path="/admin/classes" element={<AdminClassesPage />} />
        <Route path="/admin/subjects" element={<AdminSubjectsPage />} />
        <Route path="/admin/danger-zone" element={<AdminDangerZonePage />} />
        <Route path="/admin/trash" element={<AdminTrashPage />} />
        <Route path="/admin/audit-logs" element={<AuditLogsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
