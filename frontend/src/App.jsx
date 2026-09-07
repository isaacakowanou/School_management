import { Navigate, Route, Routes } from 'react-router-dom'
import RequireRole from './auth/RequireRole.jsx'
import Layout from './components/Layout.jsx'
import AdminLayout from './components/AdminLayout.jsx'
import LoginPage from './pages/LoginPage.jsx'
import ForgotPasswordPage from './pages/ForgotPasswordPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import ParentStudentPage from './pages/ParentStudentPage.jsx'
import StudentReportsPage from './pages/StudentReportsPage.jsx'
import ReportDetailPage from './pages/ReportDetailPage.jsx'
import AuditLogsPage from './pages/AuditLogsPage.jsx'
import TeacherCoursesPage from './pages/TeacherCoursesPage.jsx'
import TeacherCourseDetailPage from './pages/TeacherCourseDetailPage.jsx'
import AdminDashboardPage from './pages/AdminDashboardPage.jsx'
import AdminReportsPage from './pages/AdminReportsPage.jsx'
import AdminClassReportsPage from './pages/AdminClassReportsPage.jsx'
import AdminReportDetailPage from './pages/AdminReportDetailPage.jsx'
import AdminStudentsPage from './pages/AdminStudentsPage.jsx'
import AdminStudentTrashPage from './pages/AdminStudentTrashPage.jsx'
import AdminParentsPage from './pages/AdminParentsPage.jsx'
import AdminTeachersPage from './pages/AdminTeachersPage.jsx'
import AdminCoursesPage from './pages/AdminCoursesPage.jsx'
import AdminStudentCreatePage from './pages/AdminStudentCreatePage.jsx'
import AdminStudentImportPage from './pages/AdminStudentImportPage.jsx'
import AdminStudentDetailPage from './pages/AdminStudentDetailPage.jsx'
import AdminParentCreatePage from './pages/AdminParentCreatePage.jsx'
import AdminParentLinkImportPage from './pages/AdminParentLinkImportPage.jsx'
import AdminParentDetailPage from './pages/AdminParentDetailPage.jsx'
import AdminTeacherCreatePage from './pages/AdminTeacherCreatePage.jsx'
import AdminTeacherImportPage from './pages/AdminTeacherImportPage.jsx'
import AdminTeacherDetailPage from './pages/AdminTeacherDetailPage.jsx'
import AdminCourseCreatePage from './pages/AdminCourseCreatePage.jsx'
import AdminCourseDetailPage from './pages/AdminCourseDetailPage.jsx'
import AdminCourseSetupPage from './pages/AdminCourseSetupPage.jsx'
import AdminClassesPage from './pages/AdminClassesPage.jsx'
import AdminArchivesPage from './pages/AdminArchivesPage.jsx'
import AdminPassagesPage from './pages/AdminPassagesPage.jsx'
import AdminSchoolYearCreatePage from './pages/AdminSchoolYearCreatePage.jsx'
import AdminSubjectsPage from './pages/AdminSubjectsPage.jsx'
import AdminDangerZonePage from './pages/AdminDangerZonePage.jsx'
import AdminTrashPage from './pages/AdminTrashPage.jsx'
import ChangePasswordPage from './pages/ChangePasswordPage.jsx'
import AccountSettingsPage from './pages/AccountSettingsPage.jsx'
import EmailResetPasswordPage from './pages/EmailResetPasswordPage.jsx'
import SlowServerBanner from './components/SlowServerBanner.jsx'

export default function App() {
  return (
    <>
      <SlowServerBanner />
      <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<EmailResetPasswordPage />} />

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
        <Route path="/settings" element={<AccountSettingsPage />} />
        <Route path="/students/:studentId" element={<ParentStudentPage />} />
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
        <Route path="/teacher/settings" element={<AccountSettingsPage />} />
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
        <Route path="/admin/settings" element={<AccountSettingsPage />} />
        <Route path="/admin/reports" element={<AdminReportsPage />} />
        <Route path="/admin/reports/class" element={<AdminClassReportsPage />} />
        <Route path="/admin/reports/:reportId" element={<AdminReportDetailPage />} />
        <Route path="/admin/archives" element={<AdminArchivesPage />} />
        <Route path="/admin/school-years/new" element={<AdminSchoolYearCreatePage />} />
        <Route path="/admin/students" element={<AdminStudentsPage />} />
        <Route path="/admin/students/new" element={<AdminStudentCreatePage />} />
        <Route path="/admin/students/import" element={<AdminStudentImportPage />} />
        <Route path="/admin/students/trash" element={<AdminStudentTrashPage />} />
        <Route path="/admin/students/:studentId" element={<AdminStudentDetailPage />} />
        <Route path="/admin/teachers" element={<AdminTeachersPage />} />
        <Route path="/admin/teachers/new" element={<AdminTeacherCreatePage />} />
        <Route path="/admin/teachers/import" element={<AdminTeacherImportPage />} />
        <Route path="/admin/teachers/:teacherId" element={<AdminTeacherDetailPage />} />
        <Route path="/admin/parents" element={<AdminParentsPage />} />
        <Route path="/admin/parents/new" element={<AdminParentCreatePage />} />
        <Route path="/admin/parents/link-import" element={<AdminParentLinkImportPage />} />
        <Route path="/admin/parents/:parentId" element={<AdminParentDetailPage />} />
        <Route path="/admin/courses" element={<AdminCoursesPage />} />
        <Route path="/admin/courses/new" element={<AdminCourseCreatePage />} />
        <Route path="/admin/courses/setup" element={<AdminCourseSetupPage />} />
        <Route path="/admin/courses/:courseId" element={<AdminCourseDetailPage />} />
        <Route path="/admin/classes" element={<AdminClassesPage />} />
        <Route path="/admin/passages" element={<AdminPassagesPage />} />
        <Route path="/admin/subjects" element={<AdminSubjectsPage />} />
        <Route path="/admin/danger-zone" element={<AdminDangerZonePage />} />
        <Route path="/admin/trash" element={<AdminTrashPage />} />
        <Route path="/admin/audit-logs" element={<AuditLogsPage />} />
      </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}
