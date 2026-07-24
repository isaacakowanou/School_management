import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  deleteCourse,
  enrollStudentInCourse,
  getCourse,
  listCourseStudents,
  unenrollStudentFromCourse,
  updateCourse,
} from '../api/courses.js'
import { listStudents } from '../api/students.js'
import { getTeacher, listTeachers } from '../api/teachers.js'
import { createGradeItem, deleteGradeItem, listGradeItems, updateGradeItem } from '../api/gradeItems.js'
import { calculateSelectedCourseResults, listCourseResults } from '../api/courseResults.js'
import { listCourseGrades } from '../api/grades.js'
import { listTrimesterLocks } from '../api/trimesterLocks.js'
import { listClasses } from '../api/classes.js'
import { listSubjects } from '../api/subjects.js'
import { SCHOOL_GROUPS } from '../constants/schoolGroups.js'
import { formatReportAverage } from '../utils/format.js'
import { derivedCourseName } from '../utils/subjectOptions.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'
import ClassSelect from '../components/ClassSelect.jsx'
import SubjectSelect from '../components/SubjectSelect.jsx'
import TermSelect from '../components/TermSelect.jsx'
import GradeEntryTable from '../components/GradeEntryTable.jsx'
import { TRIMESTER_TERMS } from '../constants/terms.js'
import {
  assessmentDataForTerm,
  gradingSystemChangeNeedsConfirmation,
  lockByTerm,
} from '../utils/courseTrimester.js'

const EMPTY_GRADE_ITEM_FORM = {
  title: '',
  category: '',
  maxScore: '20',
  weight: '',
  term: '',
  dueDate: '',
  itemType: '',
}

const EMPTY_COURSE_EDIT_FORM = {
  name: '',
  code: '',
  teacherId: '',
  term: '',
  schoolYear: '',
  languageGroup: '',
  classId: '',
  subjectId: '',
  coefficient: '1',
  gradingSystem: 'WEIGHTED',
}

const GRADE_ITEM_SUGGESTIONS = [
  'Homework',
  'Quiz',
  'Exam',
  'Midterm',
  'Final',
  'Project',
  'Participation',
]

const SCHOOL_YEAR_SUGGESTIONS = ['2026-2027', '2027-2028', '2028-2029']
const WEIGHT_TOLERANCE = 0.005

function formatWeight(value) {
  return value.toFixed(2)
}

function courseToForm(course) {
  return {
    name: course?.name || '',
    code: course?.code || '',
    teacherId: course?.teacher_id || '',
    term: course?.term || '',
    schoolYear: course?.school_year || '',
    languageGroup: course?.language_group || '',
    classId: course?.class_id || '',
    subjectId: course?.subject_id || '',
    coefficient: course?.coefficient != null ? String(course.coefficient) : '1',
    gradingSystem: course?.grading_system || (
      course?.language_group === 'FRENCH' && course?.class_school_level === 'college'
        ? 'BENINESE'
        : 'WEIGHTED'
    ),
  }
}

function gradeItemToForm(gradeItem) {
  return {
    title: gradeItem?.title || '',
    category: gradeItem?.category || '',
    maxScore: gradeItem?.max_score != null ? String(gradeItem.max_score) : '',
    weight: gradeItem?.weight != null ? String(gradeItem.weight) : '',
    term: gradeItem?.term || '',
    dueDate: gradeItem?.due_date || '',
    itemType: gradeItem?.item_type || '',
  }
}

export default function AdminCourseDetailPage() {
  const { courseId } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [course, setCourse] = useState(null)
  const [teacher, setTeacher] = useState(null)
  const [allTeachers, setAllTeachers] = useState([])
  const [students, setStudents] = useState([])
  const [allStudents, setAllStudents] = useState([])
  const [gradeItems, setGradeItems] = useState([])
  const [grades, setGrades] = useState([])
  const [results, setResults] = useState([])
  const [trimesterLocks, setTrimesterLocks] = useState([])
  const [selectedTerm, setSelectedTerm] = useState('')
  const [error, setError] = useState(null)
  const [enrollStudentId, setEnrollStudentId] = useState('')
  const [enrolling, setEnrolling] = useState(false)
  const [enrollError, setEnrollError] = useState(null)
  const [enrollMessage, setEnrollMessage] = useState(null)
  const [showEnrollForm, setShowEnrollForm] = useState(false)
  const [unenrollingStudentId, setUnenrollingStudentId] = useState(null)
  const [gradeItemForm, setGradeItemForm] = useState(EMPTY_GRADE_ITEM_FORM)
  const [addingGradeItem, setAddingGradeItem] = useState(false)
  const [gradeItemError, setGradeItemError] = useState(null)
  const [gradeItemMessage, setGradeItemMessage] = useState(null)
  const [showGradeItemForm, setShowGradeItemForm] = useState(false)
  const [showEditForm, setShowEditForm] = useState(false)
  const [editForm, setEditForm] = useState(EMPTY_COURSE_EDIT_FORM)
  const [savingEdit, setSavingEdit] = useState(false)
  const [editError, setEditError] = useState(null)
  const [editMessage, setEditMessage] = useState(null)
  const [deletingCourse, setDeletingCourse] = useState(false)
  const [courseDeleteError, setCourseDeleteError] = useState(null)
  const [editingGradeItemId, setEditingGradeItemId] = useState(null)
  const [editGradeItemForm, setEditGradeItemForm] = useState(gradeItemToForm(null))
  const [savingGradeItemEdit, setSavingGradeItemEdit] = useState(false)
  const [gradeItemEditError, setGradeItemEditError] = useState(null)
  const [deletingGradeItemId, setDeletingGradeItemId] = useState(null)

  const refreshCourseResults = useCallback(async () => {
    try {
      const refreshed = await listCourseResults(courseId)
      setResults(refreshed)
    } catch {
      /* non-fatal: keep the current course detail view visible */
    }
  }, [courseId])

  const handleAdminGradesSaved = useCallback(async (changedStudentIds = []) => {
    setGrades(await listCourseGrades(courseId))
    if (changedStudentIds.length > 0) {
      await calculateSelectedCourseResults(courseId, changedStudentIds, { term: selectedTerm })
      setResults(await listCourseResults(courseId))
    }
  }, [courseId, selectedTerm])

  const [classes, setClasses] = useState([])
  const [subjects, setSubjects] = useState([])

  useEffect(() => {
    let cancelled = false
    listClasses()
      .then((data) => {
        if (!cancelled) setClasses(data)
      })
      .catch(() => {
        /* non-fatal: the class dropdown just stays empty */
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Selecting a class in the edit form narrows the catalog to that class's
  // subjects; a subject that falls out of the narrowed list is deselected.
  useEffect(() => {
    let cancelled = false
    listSubjects(editForm.classId ? { classId: editForm.classId } : {})
      .then((data) => {
        if (cancelled) return
        setSubjects(data)
        setEditForm((current) =>
          current.subjectId && !data.some((s) => s.id === current.subjectId)
            ? { ...current, subjectId: '' }
            : current,
        )
      })
      .catch(() => {
        /* non-fatal: the subject dropdown just stays empty */
      })
    return () => {
      cancelled = true
    }
  }, [editForm.classId])

  useEffect(() => {
    let cancelled = false
    setError(null)
    setCourse(null)
    setTeacher(null)
    setAllTeachers([])
    setStudents([])
    setAllStudents([])
    setGradeItems([])
    setGrades([])
    setResults([])
    setTrimesterLocks([])
    setSelectedTerm('')
    setEnrollStudentId('')
    setEnrollError(null)
    setEnrollMessage(null)
    setShowEnrollForm(false)
    setUnenrollingStudentId(null)
    setGradeItemForm(EMPTY_GRADE_ITEM_FORM)
    setGradeItemError(null)
    setGradeItemMessage(null)
    setShowGradeItemForm(false)
    setShowEditForm(false)
    setEditForm(EMPTY_COURSE_EDIT_FORM)
    setSavingEdit(false)
    setEditError(null)
    setEditMessage(null)
    setDeletingCourse(false)
    setCourseDeleteError(null)
    setEditingGradeItemId(null)
    setEditGradeItemForm(gradeItemToForm(null))
    setSavingGradeItemEdit(false)
    setGradeItemEditError(null)
    setDeletingGradeItemId(null)

    async function load() {
      let courseData
      try {
        courseData = await getCourse(courseId)
        if (cancelled) return
        setCourse(courseData)
        setSelectedTerm(courseData.term)
        setEditForm(courseToForm(courseData))
        setGradeItemForm((current) => ({
          ...current,
          term: current.term || courseData.term || '',
        }))
      } catch (err) {
        if (!cancelled) setError(err.message)
        return
      }
      // Related data is best-effort; each section degrades independently.
      const [teacherRes, studentsRes, gradeItemsRes, resultsRes, gradesRes, allStudentsRes, allTeachersRes, locksRes] = await Promise.allSettled([
        getTeacher(courseData.teacher_id),
        listCourseStudents(courseId),
        listGradeItems(courseId),
        listCourseResults(courseId),
        listCourseGrades(courseId),
        listStudents(),
        listTeachers(),
        listTrimesterLocks(courseData.school_year),
      ])
      if (cancelled) return
      if (teacherRes.status === 'fulfilled') setTeacher(teacherRes.value)
      if (studentsRes.status === 'fulfilled') setStudents(studentsRes.value)
      if (gradeItemsRes.status === 'fulfilled') setGradeItems(gradeItemsRes.value)
      if (resultsRes.status === 'fulfilled') setResults(resultsRes.value)
      if (gradesRes.status === 'fulfilled') setGrades(gradesRes.value)
      if (allStudentsRes.status === 'fulfilled') setAllStudents(allStudentsRes.value)
      if (allTeachersRes.status === 'fulfilled') setAllTeachers(allTeachersRes.value)
      if (locksRes.status === 'fulfilled') setTrimesterLocks(locksRes.value)
    }

    load()
    return () => {
      cancelled = true
    }
  }, [courseId])

  useEffect(() => {
    function refreshWhenVisible() {
      if (document.visibilityState === 'visible') {
        refreshCourseResults()
      }
    }

    window.addEventListener('focus', refreshCourseResults)
    document.addEventListener('visibilitychange', refreshWhenVisible)
    return () => {
      window.removeEventListener('focus', refreshCourseResults)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [refreshCourseResults])

  const enrolledStudentIds = useMemo(() => new Set(students.map((student) => student.id)), [students])
  const availableStudents = useMemo(
    () => allStudents.filter((student) => !enrolledStudentIds.has(student.id)),
    [allStudents, enrolledStudentIds],
  )

  useEffect(() => {
    if (availableStudents.length === 0) {
      if (enrollStudentId) setEnrollStudentId('')
      return
    }
    if (!availableStudents.some((student) => student.id === enrollStudentId)) {
      setEnrollStudentId(availableStudents[0].id)
    }
  }, [availableStudents, enrollStudentId])

  function updateEditField(field, value) {
    setEditForm((current) => ({ ...current, [field]: value }))
  }

  function cancelEdit() {
    setEditForm(courseToForm(course))
    setEditError(null)
    setShowEditForm(false)
  }

  const editSelectedSubject = editForm.subjectId
    ? subjects.find((subject) => subject.id === editForm.subjectId) || null
    : null

  async function handleEditCourse(event) {
    event.preventDefault()
    setEditError(null)
    setEditMessage(null)

    if (
      (!editForm.subjectId && !editForm.name.trim()) ||
      !editForm.code.trim() ||
      !editForm.teacherId ||
      !editForm.term.trim() ||
      !editForm.schoolYear.trim()
    ) {
      setEditError(t('courses.errorRequired'))
      return
    }

    setSavingEdit(true)
    try {
      let confirmGradingSystemChange = false
      if (gradingSystemChangeNeedsConfirmation({
        currentSystem: course.grading_system || (
          course.language_group === 'FRENCH' && course.class_school_level === 'college'
            ? 'BENINESE'
            : 'WEIGHTED'
        ),
        nextSystem: editForm.gradingSystem,
        gradeItemCount: gradeItems.length,
      })) {
        confirmGradingSystemChange = window.confirm(
          t('courses.confirmGradingSystemChange', { count: gradeItems.length }),
        )
        if (!confirmGradingSystemChange) return
      }
      await updateCourse(courseId, { ...editForm, confirmGradingSystemChange })
      const refreshed = await getCourse(courseId)
      setCourse(refreshed)
      setEditForm(courseToForm(refreshed))
      setEditMessage(t('courses.updated'))
      setShowEditForm(false)
      try {
        const refreshedTeacher = await getTeacher(refreshed.teacher_id)
        setTeacher(refreshedTeacher)
      } catch {
        setTeacher(allTeachers.find((item) => item.id === refreshed.teacher_id) || null)
      }
    } catch (err) {
      setEditError(err.message)
    } finally {
      setSavingEdit(false)
    }
  }

  async function handleDeleteCourse() {
    if (!window.confirm(t('courses.confirmDelete', { name: course.name }))) return
    setCourseDeleteError(null)
    setEditMessage(null)
    setDeletingCourse(true)
    try {
      await deleteCourse(courseId)
      navigate('/admin/courses', { replace: true, state: { message: t('courses.deleted') } })
    } catch (err) {
      if (err.status === 409 && err.detail && typeof err.detail === 'object') {
        setCourseDeleteError(
          t('courses.deleteBlocked', {
            enrollments: err.detail.enrollment_count,
            gradeItems: err.detail.grade_item_count,
            grades: err.detail.grade_count,
            results: err.detail.course_result_count,
            snapshots: err.detail.report_snapshot_count,
          }),
        )
      } else {
        setCourseDeleteError(err.message)
      }
    } finally {
      setDeletingCourse(false)
    }
  }

  async function handleEnrollStudent(event) {
    event.preventDefault()
    setEnrollError(null)
    setEnrollMessage(null)

    if (!enrollStudentId) {
      setEnrollError(t('courses.chooseStudent'))
      return
    }

    setEnrolling(true)
    try {
      await enrollStudentInCourse(courseId, enrollStudentId)
      const refreshed = await listCourseStudents(courseId)
      setStudents(refreshed)
      setEnrollMessage(t('courses.studentEnrolled'))
      setShowEnrollForm(false)
    } catch (err) {
      setEnrollError(err.message)
    } finally {
      setEnrolling(false)
    }
  }

  async function handleUnenrollStudent(student) {
    const studentName = `${student.first_name} ${student.last_name}`
    const confirmed = window.confirm(t('courses.confirmUnenroll', { name: studentName, number: student.student_number, code: course.code }))
    if (!confirmed) return

    setEnrollError(null)
    setEnrollMessage(null)
    setUnenrollingStudentId(student.id)
    try {
      await unenrollStudentFromCourse(courseId, student.id)
      const refreshed = await listCourseStudents(courseId)
      setStudents(refreshed)
      setEnrollMessage(t('courses.studentUnenrolled'))
    } catch (err) {
      setEnrollError(err.message)
    } finally {
      setUnenrollingStudentId(null)
    }
  }

  function updateGradeItemField(field, value) {
    setGradeItemForm((current) => ({ ...current, [field]: value }))
  }

  function updateEditGradeItemField(field, value) {
    setEditGradeItemForm((current) => ({ ...current, [field]: value }))
  }

  async function handleAddGradeItem(event) {
    event.preventDefault()
    setGradeItemError(null)
    setGradeItemMessage(null)

    const maxScore = Number(gradeItemForm.maxScore)
    const weight = Number(gradeItemForm.weight)
    if (isBenineseMode) {
      if (!gradeItemForm.title.trim() || !gradeItemForm.itemType || !gradeItemForm.term.trim() || !Number.isFinite(maxScore)) {
        setGradeItemError(t('courses.benineseItemRequired'))
        return
      }
      if (maxScore <= 0) {
        setGradeItemError(t('courses.maxScorePositive'))
        return
      }
    } else {
      if (
        !gradeItemForm.title.trim() ||
        !gradeItemForm.category.trim() ||
        !gradeItemForm.term.trim() ||
        !Number.isFinite(maxScore) ||
        !Number.isFinite(weight)
      ) {
        setGradeItemError(t('courses.gradeItemRequired'))
        return
      }
      if (maxScore <= 0) {
        setGradeItemError(t('courses.maxScorePositive'))
        return
      }
      if (weight <= 0 || weight > 1) {
        setGradeItemError(t('courses.weightRange'))
        return
      }
    }

    setAddingGradeItem(true)
    try {
      await createGradeItem(courseId, gradeItemForm)
      const refreshed = await listGradeItems(courseId)
      setGradeItems(refreshed)
      setGradeItemForm({
        ...EMPTY_GRADE_ITEM_FORM,
        term: gradeItemForm.term.trim(),
      })
      setGradeItemMessage(t('courses.gradeItemAdded'))
      setShowGradeItemForm(false)
    } catch (err) {
      setGradeItemError(err.message)
    } finally {
      setAddingGradeItem(false)
    }
  }

  async function handleEditGradeItem(event, gradeItemId) {
    event.preventDefault()
    setGradeItemEditError(null)
    setGradeItemMessage(null)

    const maxScore = Number(editGradeItemForm.maxScore)
    const weight = Number(editGradeItemForm.weight)
    if (isBenineseMode) {
      if (!editGradeItemForm.title.trim() || !editGradeItemForm.term.trim() || !Number.isFinite(maxScore)) {
        setGradeItemEditError(t('courses.benineseItemRequired'))
        return
      }
      if (maxScore <= 0) {
        setGradeItemEditError(t('courses.maxScorePositive'))
        return
      }
    } else {
      if (
        !editGradeItemForm.title.trim() ||
        !editGradeItemForm.category.trim() ||
        !editGradeItemForm.term.trim() ||
        !Number.isFinite(maxScore) ||
        !Number.isFinite(weight)
      ) {
        setGradeItemEditError(t('courses.gradeItemRequired'))
        return
      }
      if (maxScore <= 0) {
        setGradeItemEditError(t('courses.maxScorePositive'))
        return
      }
      if (weight <= 0 || weight > 1) {
        setGradeItemEditError(t('courses.weightRange'))
        return
      }
    }

    setSavingGradeItemEdit(true)
    try {
      await updateGradeItem(gradeItemId, editGradeItemForm)
      const refreshed = await listGradeItems(courseId)
      setGradeItems(refreshed)
      setGradeItemMessage(t('courses.gradeItemUpdated'))
      setEditingGradeItemId(null)
      setEditGradeItemForm(gradeItemToForm(null))
    } catch (err) {
      setGradeItemEditError(err.message)
    } finally {
      setSavingGradeItemEdit(false)
    }
  }

  async function handleDeleteGradeItem(item) {
    if (!window.confirm(t('courses.confirmDeleteGradeItem', { title: item.title }))) return
    setGradeItemError(null)
    setGradeItemMessage(null)
    setGradeItemEditError(null)
    setDeletingGradeItemId(item.id)
    try {
      await deleteGradeItem(item.id)
      const refreshed = await listGradeItems(courseId)
      setGradeItems(refreshed)
      setEditingGradeItemId(null)
      setEditGradeItemForm(gradeItemToForm(null))
      setGradeItemMessage(t('courses.gradeItemDeleted'))
    } catch (err) {
      if (err.status === 409 && err.detail && typeof err.detail === 'object') {
        setGradeItemError(t('courses.gradeItemDeleteBlocked', { title: item.title, count: err.detail.grade_count }))
      } else {
        setGradeItemError(err.message)
      }
    } finally {
      setDeletingGradeItemId(null)
    }
  }

  if (error) {
    return (
      <section className="admin-page">
        <Link to="/admin/courses" className="back-link">
          ← {t('nav.courses')}
        </Link>
        <ErrorBanner message={error} />
      </section>
    )
  }

  if (!course) {
    return (
      <section className="admin-page">
        <Spinner label={t('courses.loadingOne')} />
      </section>
    )
  }

  // Grading mode mirrors TeacherCourseDetailPage: Beninese formula applies to
  // French-section collège courses; everything term-scoped to course.term.
  const isBenineseMode = course.grading_system
    ? course.grading_system === 'BENINESE'
    : !!(course.language_group === 'FRENCH' && course.class_school_level === 'college')
  const selectedData = assessmentDataForTerm({ term: selectedTerm, gradeItems, grades, results })
  const selectedTermItems = selectedData.gradeItems
  const selectedTermGrades = selectedData.grades
  const selectedTermResults = selectedData.results
  const selectedTermLocked = lockByTerm(trimesterLocks).get(selectedTerm) || false
  const selectedTermItemIds = new Set(selectedTermItems.map((item) => item.id))
  const enteredGradeCount = grades.filter(
    (grade) => selectedTermItemIds.has(grade.grade_item_id) && enrolledStudentIds.has(grade.student_id),
  ).length
  const expectedGradeCount = students.length * selectedTermItems.length
  const hasDevoir = selectedTermItems.some((item) => item.item_type === 'DEVOIR')
  const hasComposition = selectedTermItems.some((item) => item.item_type === 'COMPOSITION')

  const totalWeight = selectedTermItems.reduce((sum, item) => sum + Number(item.weight || 0), 0)
  const isWeightReady = Math.abs(totalWeight - 1) <= WEIGHT_TOLERANCE
  const weightSummary = isWeightReady
    ? t('courses.weightReady', { total: formatWeight(totalWeight) })
    : totalWeight < 1
      ? t('courses.weightMissing', { total: formatWeight(totalWeight), amount: formatWeight(1 - totalWeight) })
      : t('courses.weightOver', { total: formatWeight(totalWeight), amount: formatWeight(totalWeight - 1) })

  // Open the add form pre-loaded for a Beninese item type.
  function openBenineseForm(itemType) {
    const titleMap = { INTERRO: 'Interro', DEVOIR: 'Devoir', COMPOSITION: 'Composition' }
    setGradeItemForm({
      ...EMPTY_GRADE_ITEM_FORM,
      title: titleMap[itemType] || '',
      term: selectedTerm || course.term || '',
      itemType,
    })
    setGradeItemError(null)
    setGradeItemMessage(null)
    setEditingGradeItemId(null)
    setGradeItemEditError(null)
    setShowGradeItemForm(true)
  }

  return (
    <section className="admin-page">
      <Link to="/admin/courses" className="back-link">
        ← {t('nav.courses')}
      </Link>
      <div className="detail-header">
        <div>
          <h2 className="page-title">{course.name}</h2>
          <p className="muted">
            {course.code} · {course.class_name || '—'} · {course.term} · {course.school_year} · {t('courses.coefficient')}: {course.coefficient ?? 1}
            {isBenineseMode && <> · <em>{t('courses.benineseMode')}</em></>}
          </p>
          <p className="muted">
            {t('common.teacher')}:{' '}
            {teacher ? (
              <Link className="link-action" to={`/admin/teachers/${teacher.id}`}>
                {teacher.name}
              </Link>
            ) : (
              <span className="audit-id" title={course.teacher_id}>
                {course.teacher_id}
              </span>
            )}
          </p>
        </div>
        {!showEditForm && (
          <div className="detail-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                setEditError(null)
                setEditMessage(null)
                setEditForm(courseToForm(course))
                setShowEditForm(true)
              }}
            >
              {t('common.edit')}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-danger-subtle"
              onClick={handleDeleteCourse}
              disabled={deletingCourse}
            >
              {deletingCourse ? t('courses.deleting') : t('common.delete')}
            </button>
          </div>
        )}
      </div>
      {editMessage && <p className="grade-summary">{editMessage}</p>}
      {courseDeleteError && <ErrorBanner message={courseDeleteError} />}
      {showEditForm && (
        <form className="card admin-form" onSubmit={handleEditCourse}>
          <label className="field">
            <span>{t('courses.subject')}</span>
            <SubjectSelect
              subjects={subjects}
              value={editForm.subjectId}
              onChange={(value) => updateEditField('subjectId', value)}
              disabled={savingEdit}
            />
            <span className="muted">{t('courses.subjectHint')}</span>
          </label>

          <label className="field">
            <span>{t('courses.courseName')}</span>
            <input
              value={editSelectedSubject ? derivedCourseName(editSelectedSubject) : editForm.name}
              onChange={(event) => updateEditField('name', event.target.value)}
              disabled={savingEdit}
              readOnly={Boolean(editSelectedSubject)}
              required={!editSelectedSubject}
            />
            {editSelectedSubject && (
              <span className="muted">{t('courses.nameFromSubjectHint')}</span>
            )}
          </label>

          <label className="field">
            <span>{t('courses.courseCode')}</span>
            <input
              value={editForm.code}
              onChange={(event) => updateEditField('code', event.target.value)}
              disabled={savingEdit}
              required
            />
          </label>

          <label className="field">
            <span>{t('common.teacher')}</span>
            <select
              className="grade-input"
              value={editForm.teacherId}
              onChange={(event) => updateEditField('teacherId', event.target.value)}
              disabled={savingEdit}
              required
              style={{ width: '100%', textAlign: 'left' }}
            >
              {allTeachers.length === 0 ? (
                <option value={editForm.teacherId}>
                  {teacher ? `${teacher.name} — ${teacher.email}` : t('courses.currentTeacher')}
                </option>
              ) : (
                allTeachers.map((teacherOption) => (
                  <option key={teacherOption.id} value={teacherOption.id}>
                    {teacherOption.name} — {teacherOption.email} — #{teacherOption.employee_number}
                  </option>
                ))
              )}
            </select>
          </label>

          <label className="field">
            <span>{t('common.term')}</span>
            <TermSelect
              value={editForm.term}
              onChange={(value) => updateEditField('term', value)}
              disabled={savingEdit}
            />
          </label>

          <label className="field">
            <span>{t('common.schoolYear')}</span>
            <input
              value={editForm.schoolYear}
              onChange={(event) => updateEditField('schoolYear', event.target.value)}
              disabled={savingEdit}
              list="course-edit-school-year-options"
              required
            />
          </label>

          <label className="field">
            <span>{t('courses.languageGroup')}</span>
            <select
              className="grade-input"
              value={editSelectedSubject ? editSelectedSubject.section : editForm.languageGroup}
              onChange={(event) => updateEditField('languageGroup', event.target.value)}
              disabled={savingEdit || Boolean(editSelectedSubject)}
              style={{ width: '100%', textAlign: 'left' }}
            >
              <option value="">{t('common.notSet')}</option>
              {SCHOOL_GROUPS.map((group) => (
                <option key={group.value} value={group.value}>
                  {t(group.labelKey)}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>{t('courses.classOptional')}</span>
            <ClassSelect
              classes={classes}
              value={editForm.classId}
              onChange={(value) => updateEditField('classId', value)}
              disabled={savingEdit}
            />
          </label>

          <label className="field">
            <span>{t('courses.coefficient')}</span>
            <input
              type="number"
              min="1"
              step="1"
              value={editForm.coefficient}
              onChange={(event) => updateEditField('coefficient', event.target.value)}
              disabled={savingEdit}
              required
            />
            <span className="muted">{t('courses.coefficientHint')}</span>
          </label>

          <label className="field">
            <span>{t('courses.gradingSystem')}</span>
            <select
              className="grade-input"
              value={editForm.gradingSystem}
              onChange={(event) => updateEditField('gradingSystem', event.target.value)}
              disabled={savingEdit}
              style={{ width: '100%', textAlign: 'left' }}
            >
              <option value="BENINESE">{t('courses.gradingSystemBeninese')}</option>
              <option value="WEIGHTED">{t('courses.gradingSystemWeighted')}</option>
            </select>
          </label>

          <datalist id="course-edit-school-year-options">
            {SCHOOL_YEAR_SUGGESTIONS.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>

          <div className="grade-actions">
            <button type="submit" className="btn btn-primary" disabled={savingEdit}>
              {savingEdit ? t('common.saving') : t('common.saveChanges')}
            </button>
            <button type="button" className="btn btn-ghost" disabled={savingEdit} onClick={cancelEdit}>
              {t('common.cancel')}
            </button>
          </div>
          {editError && <ErrorBanner message={editError} />}
        </form>
      )}

      <div className="section-heading">
        <h3 className="section-title">{t('courses.enrolledStudents')}</h3>
        {!showEnrollForm && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setEnrollError(null)
              setEnrollMessage(null)
              setShowEnrollForm(true)
            }}
          >
            {t('courses.enrollStudent')}
          </button>
        )}
      </div>
      {enrollMessage && <p className="grade-summary">{enrollMessage}</p>}
      {enrollError && !showEnrollForm && <ErrorBanner message={enrollError} />}
      {showEnrollForm && (
        <form className="card admin-form" onSubmit={handleEnrollStudent}>
          <label className="field">
            <span>{t('students.title')}</span>
            <select
              className="grade-input"
              value={enrollStudentId}
              onChange={(event) => setEnrollStudentId(event.target.value)}
              disabled={enrolling || availableStudents.length === 0}
              required
              style={{ width: '100%', textAlign: 'left' }}
            >
              {availableStudents.length === 0 ? (
                <option value="">{t('courses.noAvailableStudents')}</option>
              ) : (
                availableStudents.map((student) => (
                  <option key={student.id} value={student.id}>
                    {student.first_name} {student.last_name} — #{student.student_number}
                  </option>
                ))
              )}
            </select>
          </label>

          <div className="grade-actions">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={enrolling || availableStudents.length === 0}
            >
              {enrolling ? t('courses.enrolling') : t('courses.enrollStudent')}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={enrolling}
              onClick={() => {
                setShowEnrollForm(false)
                setEnrollError(null)
              }}
            >
              {t('common.cancel')}
            </button>
          </div>
          {enrollError && <ErrorBanner message={enrollError} />}
        </form>
      )}

      {students.length === 0 ? (
        <Empty message={t('courses.noStudents')} />
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('common.name')}</th>
                <th>{t('students.studentNumber')}</th>
                <th>{t('students.class')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {students.map((student) => (
                <tr key={student.id}>
                  <td>
                    {student.first_name} {student.last_name}
                  </td>
                  <td className="nowrap">{student.student_number}</td>
                  <td className="nowrap">{student.class_name || '—'}</td>
                  <td className="nowrap row-actions">
                    <Link className="link-action" to={`/admin/students/${student.id}`}>
                      {t('common.open')}
                    </Link>
                    <button
                      type="button"
                      className="link-action link-action-danger"
                      disabled={unenrollingStudentId === student.id}
                      onClick={() => handleUnenrollStudent(student)}
                    >
                      {unenrollingStudentId === student.id ? t('courses.unenrolling') : t('courses.unenroll')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="trimester-tabs" role="tablist" aria-label={t('courses.trimesterSections')}>
        {TRIMESTER_TERMS.map((term) => {
          const locked = lockByTerm(trimesterLocks).get(term) || false
          return (
            <button
              key={term}
              type="button"
              role="tab"
              aria-selected={selectedTerm === term}
              className={`trimester-tab${selectedTerm === term ? ' is-active' : ''}`}
              onClick={() => {
                setSelectedTerm(term)
                setGradeItemForm((current) => ({ ...current, term }))
                setShowGradeItemForm(false)
                setEditingGradeItemId(null)
              }}
            >
              {term}{locked ? ` · ${t('courses.lockedShort')}` : ''}
            </button>
          )
        })}
      </div>
      {selectedTermLocked && (
        <div className="state trimester-lock-notice trimester-lock-notice-admin" role="status">
          <strong>{t('courses.trimesterLockedTitle')}</strong>
          <p>{t('courses.trimesterLockedAdmin')}</p>
        </div>
      )}

      <div className="section-heading">
        <h3 className="section-title">{t('courses.gradeItems')}</h3>
        {!showGradeItemForm && (
          <div className="grade-actions">
          {isBenineseMode ? (
            <>
              <button type="button" className="btn btn-primary" onClick={() => openBenineseForm('INTERRO')}>
                {t('courses.addInterro')}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => openBenineseForm('DEVOIR')}
                disabled={hasDevoir}
              >
                {t('courses.addDevoir')}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => openBenineseForm('COMPOSITION')}
                disabled={hasComposition}
              >
                {t('courses.addComposition')}
              </button>
            </>
          ) : (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                setGradeItemForm((current) => ({ ...current, term: selectedTerm }))
                setGradeItemError(null)
                setGradeItemMessage(null)
                setEditingGradeItemId(null)
                setGradeItemEditError(null)
                setShowGradeItemForm(true)
              }}
            >
              {t('courses.addGradeItem')}
            </button>
          )}
          </div>
        )}
      </div>
      {gradeItemMessage && <p className="grade-summary">{gradeItemMessage}</p>}
      {gradeItemError && !showGradeItemForm && <ErrorBanner message={gradeItemError} />}
      {isBenineseMode ? (
        <div className="state state-empty weight-summary">
          <strong>{t('courses.benineseMode')}</strong>
        </div>
      ) : (
        <div className="state state-empty weight-summary">
          <strong>{weightSummary}</strong>
          <p>{t('courses.weightHint')}</p>
        </div>
      )}
      {showGradeItemForm && (
        <div className="modal-backdrop" onClick={() => !addingGradeItem && setShowGradeItemForm(false)}>
          <form className="card admin-form modal-card" onClick={(event) => event.stopPropagation()} onSubmit={handleAddGradeItem}>
          <h3 className="section-title">{t('courses.addGradeItem')}</h3>
          <label className="field">
            <span>{t('courses.title')}</span>
            <input
              value={gradeItemForm.title}
              onChange={(event) => updateGradeItemField('title', event.target.value)}
              disabled={addingGradeItem}
              list="grade-item-title-options"
              required
            />
          </label>

          {!isBenineseMode && (
            <label className="field">
              <span>{t('courses.category')}</span>
              <input
                value={gradeItemForm.category}
                onChange={(event) => updateGradeItemField('category', event.target.value)}
                disabled={addingGradeItem}
                list="grade-item-category-options"
                required
              />
            </label>
          )}

          <label className="field">
            <span>{t('courses.maxScore')}</span>
            <input
              type="number"
              min="0"
              step="any"
              value={gradeItemForm.maxScore}
              onChange={(event) => updateGradeItemField('maxScore', event.target.value)}
              disabled={addingGradeItem}
              required
            />
          </label>

          {!isBenineseMode && (
            <label className="field">
              <span>{t('courses.weight')}</span>
              <input
                type="number"
                min="0.01"
                max="1"
                step="0.01"
                value={gradeItemForm.weight}
                onChange={(event) => updateGradeItemField('weight', event.target.value)}
                disabled={addingGradeItem}
                required
              />
              <p className="muted">{t('courses.weightExample')}</p>
            </label>
          )}

          <label className="field">
            <span>{t('common.term')}</span>
            <TermSelect
              value={gradeItemForm.term}
              onChange={(value) => updateGradeItemField('term', value)}
              disabled={addingGradeItem}
            />
          </label>

          <datalist id="grade-item-title-options">
            {GRADE_ITEM_SUGGESTIONS.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>
          <datalist id="grade-item-category-options">
            {GRADE_ITEM_SUGGESTIONS.map((value) => (
              <option key={value} value={value} />
            ))}
          </datalist>

          <div className="grade-actions">
            <button type="submit" className="btn btn-primary" disabled={addingGradeItem}>
              {addingGradeItem ? t('courses.adding') : t('courses.addGradeItem')}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={addingGradeItem}
              onClick={() => {
                setShowGradeItemForm(false)
                setGradeItemError(null)
              }}
            >
              {t('common.cancel')}
            </button>
          </div>
          {gradeItemError && <ErrorBanner message={gradeItemError} />}
        </form>
        </div>
      )}

      {selectedTermItems.length === 0 ? (
        <Empty message={t('courses.noGradeItems')} />
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('courses.title')}</th>
                {isBenineseMode ? <th>{t('courses.itemType')}</th> : <th>{t('courses.category')}</th>}
                <th className="num">{t('courses.maxScore')}</th>
                {!isBenineseMode && <th className="num">{t('courses.weight')}</th>}
                <th>{t('common.term')}</th>
                <th>{t('courses.dueDate')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {selectedTermItems.map((item) => (
                <Fragment key={item.id}>
                  <tr>
                    <td>{item.title}</td>
                    {isBenineseMode ? (
                      <td className="nowrap">{item.item_type}</td>
                    ) : (
                      <td className="nowrap">{item.category}</td>
                    )}
                    <td className="num">{item.max_score}</td>
                    {!isBenineseMode && <td className="num">{item.weight}</td>}
                    <td className="nowrap">{item.term}</td>
                    <td className="nowrap">{item.due_date || '—'}</td>
                    <td className="nowrap row-actions">
                      <button
                        type="button"
                        className="link-action"
                        disabled={savingGradeItemEdit || deletingGradeItemId === item.id}
                        onClick={() => {
                          setShowGradeItemForm(false)
                          setGradeItemError(null)
                          setGradeItemMessage(null)
                          setGradeItemEditError(null)
                          setEditGradeItemForm(gradeItemToForm(item))
                          setEditingGradeItemId(item.id)
                        }}
                      >
                        {t('common.edit')}
                      </button>
                      <button
                        type="button"
                        className="link-action link-action-danger"
                        disabled={savingGradeItemEdit || deletingGradeItemId === item.id}
                        onClick={() => handleDeleteGradeItem(item)}
                      >
                        {deletingGradeItemId === item.id ? t('courses.deleting') : t('common.delete')}
                      </button>
                    </td>
                  </tr>
                  {editingGradeItemId === item.id && (
                    <tr>
                      <td colSpan={isBenineseMode ? '6' : '7'}>
                        <form className="card admin-form" onSubmit={(event) => handleEditGradeItem(event, item.id)}>
                          <label className="field">
                            <span>{t('courses.title')}</span>
                            <input
                              value={editGradeItemForm.title}
                              onChange={(event) => updateEditGradeItemField('title', event.target.value)}
                              disabled={savingGradeItemEdit}
                              list="grade-item-edit-title-options"
                              required
                            />
                          </label>

                          {!isBenineseMode && (
                            <label className="field">
                              <span>{t('courses.category')}</span>
                              <input
                                value={editGradeItemForm.category}
                                onChange={(event) => updateEditGradeItemField('category', event.target.value)}
                                disabled={savingGradeItemEdit}
                                list="grade-item-edit-category-options"
                                required
                              />
                            </label>
                          )}

                          <label className="field">
                            <span>{t('courses.maxScore')}</span>
                            <input
                              type="number"
                              min="0.01"
                              step="any"
                              value={editGradeItemForm.maxScore}
                              onChange={(event) => updateEditGradeItemField('maxScore', event.target.value)}
                              disabled={savingGradeItemEdit}
                              required
                            />
                          </label>

                          {!isBenineseMode && (
                            <label className="field">
                              <span>{t('courses.weight')}</span>
                              <input
                                type="number"
                                min="0.01"
                                max="1"
                                step="0.01"
                                value={editGradeItemForm.weight}
                                onChange={(event) => updateEditGradeItemField('weight', event.target.value)}
                                disabled={savingGradeItemEdit}
                                required
                              />
                              <p className="muted">{t('courses.weightExample')}</p>
                            </label>
                          )}

                          <label className="field">
                            <span>{t('common.term')}</span>
                            <TermSelect
                              value={editGradeItemForm.term}
                              onChange={(value) => updateEditGradeItemField('term', value)}
                              disabled={savingGradeItemEdit}
                            />
                          </label>

                          <label className="field">
                            <span>{t('courses.dueDate')}</span>
                            <input
                              type="date"
                              value={editGradeItemForm.dueDate}
                              onChange={(event) => updateEditGradeItemField('dueDate', event.target.value)}
                              disabled={savingGradeItemEdit}
                            />
                          </label>

                          <datalist id="grade-item-edit-title-options">
                            {GRADE_ITEM_SUGGESTIONS.map((value) => (
                              <option key={value} value={value} />
                            ))}
                          </datalist>
                          <datalist id="grade-item-edit-category-options">
                            {GRADE_ITEM_SUGGESTIONS.map((value) => (
                              <option key={value} value={value} />
                            ))}
                          </datalist>

                          <div className="grade-actions">
                            <button type="submit" className="btn btn-primary" disabled={savingGradeItemEdit}>
                              {savingGradeItemEdit ? t('common.saving') : t('common.saveChanges')}
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost"
                              disabled={savingGradeItemEdit}
                              onClick={() => {
                                setEditingGradeItemId(null)
                                setEditGradeItemForm(gradeItemToForm(null))
                                setGradeItemEditError(null)
                              }}
                            >
                              {t('common.cancel')}
                            </button>
                          </div>
                          {gradeItemEditError && <ErrorBanner message={gradeItemEditError} />}
                        </form>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="section-heading">
        <h3>{t('courses.gradeEntry')}</h3>
      </div>
      <GradeEntryTable
        courseId={courseId}
        students={students}
        gradeItems={selectedTermItems}
        grades={selectedTermGrades}
        onSaved={handleAdminGradesSaved}
        gradingMode={isBenineseMode ? 'BENINESE' : 'WEIGHTED'}
      />

      <h3 className="section-title">{t('courses.results')}</h3>
      {selectedTermResults.length === 0 ? (
        <div className="state state-empty">
          {t('courses.quietIncompleteResults', { entered: enteredGradeCount, total: expectedGradeCount })}
        </div>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>{t('reports.student')}</th>
                <th>{t('common.term')}</th>
                <th className="num">{t('reports.average')}</th>
                <th className="num">{t('reports.grade')}</th>
              </tr>
            </thead>
            <tbody>
              {selectedTermResults.map((result) => (
                <tr key={result.id}>
                  <td>
                    {result.student_name || (
                      <span className="audit-id" title={result.student_id}>
                        {result.student_id}
                      </span>
                    )}
                  </td>
                  <td className="nowrap">{result.term}</td>
                  <td className="num">{formatReportAverage(result.average, result.scale)}</td>
                  <td className="num">{result.letter_grade}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
