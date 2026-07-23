import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { getCourse, listCourseStudents } from '../api/courses.js'
import { createGradeItem, listGradeItems, updateGradeItem } from '../api/gradeItems.js'
import { listCourseGrades, notifyGradesChanged } from '../api/grades.js'
import {
  calculateCourseResults,
  calculateSelectedCourseResults,
  listCourseResults,
} from '../api/courseResults.js'
import { listTrimesterLocks } from '../api/trimesterLocks.js'
import { TRIMESTER_TERMS } from '../constants/terms.js'
import { assessmentDataForTerm, lockByTerm } from '../utils/courseTrimester.js'
import { formatReportAverage } from '../utils/format.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'
import GradeEntryTable from '../components/GradeEntryTable.jsx'
import TermSelect from '../components/TermSelect.jsx'

const EMPTY_GRADE_ITEM_FORM = {
  title: '',
  category: '',
  maxScore: '20',
  weight: '',
  term: '',
  dueDate: '',
  itemType: '',
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
const WEIGHT_TOLERANCE = 0.005

function formatWeight(value) {
  return value.toFixed(2)
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

function validateGradeItemForm(form, t, isBenineseMode = false) {
  const maxScore = Number(form.maxScore)
  if (isBenineseMode) {
    if (!form.title.trim() || !form.itemType || !form.term.trim() || !Number.isFinite(maxScore)) {
      return t('courses.benineseItemRequired')
    }
    if (maxScore <= 0) return t('courses.maxScorePositive')
    return null
  }
  const weight = Number(form.weight)
  if (
    !form.title.trim() ||
    !form.category.trim() ||
    !form.term.trim() ||
    !Number.isFinite(maxScore) ||
    !Number.isFinite(weight)
  ) {
    return t('courses.gradeItemRequired')
  }
  if (maxScore <= 0) return t('courses.maxScorePositive')
  if (weight <= 0 || weight > 1) return t('courses.weightRange')
  return null
}

export default function TeacherCourseDetailPage() {
  const { courseId } = useParams()
  const { t } = useTranslation()

  const [course, setCourse] = useState(null)
  const [students, setStudents] = useState(null)
  const [gradeItems, setGradeItems] = useState(null)
  const [grades, setGrades] = useState(null)
  const [results, setResults] = useState(null)
  const [trimesterLocks, setTrimesterLocks] = useState([])
  const [selectedTerm, setSelectedTerm] = useState('')
  const [error, setError] = useState(null)

  const [calculating, setCalculating] = useState(false)
  const [calcSummary, setCalcSummary] = useState(null)
  const [calcError, setCalcError] = useState(null)
  const [notificationNotice, setNotificationNotice] = useState(null)
  const [showGradeItemForm, setShowGradeItemForm] = useState(false)
  const [gradeItemForm, setGradeItemForm] = useState(EMPTY_GRADE_ITEM_FORM)
  const [addingGradeItem, setAddingGradeItem] = useState(false)
  const [gradeItemError, setGradeItemError] = useState(null)
  const [gradeItemMessage, setGradeItemMessage] = useState(null)
  const [editingGradeItemId, setEditingGradeItemId] = useState(null)
  const [editGradeItemForm, setEditGradeItemForm] = useState(gradeItemToForm(null))
  const [savingGradeItemEdit, setSavingGradeItemEdit] = useState(false)
  const [gradeItemEditError, setGradeItemEditError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setCourse(null)
    setStudents(null)
    setGradeItems(null)
    setGrades(null)
    setResults(null)
    setTrimesterLocks([])
    setSelectedTerm('')
    setCalcSummary(null)
    setCalcError(null)
    setNotificationNotice(null)
    setShowGradeItemForm(false)
    setGradeItemForm(EMPTY_GRADE_ITEM_FORM)
    setAddingGradeItem(false)
    setGradeItemError(null)
    setGradeItemMessage(null)
    setEditingGradeItemId(null)
    setEditGradeItemForm(gradeItemToForm(null))
    setSavingGradeItemEdit(false)
    setGradeItemEditError(null)

    async function load() {
      try {
        const [c, s, gi, g, r] = await Promise.all([
          getCourse(courseId),
          listCourseStudents(courseId),
          listGradeItems(courseId),
          listCourseGrades(courseId),
          listCourseResults(courseId),
        ])
        if (cancelled) return
        setCourse(c)
        setStudents(s)
        setGradeItems(gi)
        setGrades(g)
        setResults(r)
        const locks = await listTrimesterLocks(c.school_year)
        if (cancelled) return
        setTrimesterLocks(locks)
        setSelectedTerm(c.term)
        setGradeItemForm((current) => ({
          ...current,
          term: current.term || c.term || '',
        }))
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [courseId])

  const recalculateAllResults = useCallback(async () => {
    const res = await calculateCourseResults(courseId, { term: selectedTerm })
    setCalcSummary({
      calculated_count: res.calculated_count,
      skipped_students: res.skipped_students || [],
      no_changes: false,
    })
    const refreshed = await listCourseResults(courseId)
    setResults(refreshed)
    return res
  }, [courseId, selectedTerm])

  const handleGradesSaved = useCallback(async (changedStudentIds = []) => {
    if (changedStudentIds.length > 0) {
      setCalcSummary(null)
      setCalcError(null)
      setNotificationNotice(null)
    }

    try {
      const g = await listCourseGrades(courseId)
      setGrades(g)
    } catch {
      /* non-fatal: keep current matrix state */
    }

    if (changedStudentIds.length > 0) {
      try {
        const res = await calculateSelectedCourseResults(courseId, changedStudentIds, { term: selectedTerm })
        setCalcSummary({
          calculated_count: res.calculated_count,
          skipped_students: res.skipped_students || [],
          no_changes: false,
        })
        setResults(await listCourseResults(courseId))
      } catch (err) {
        setCalcError(err.message)
        throw err
      }

      try {
        const outcome = await notifyGradesChanged(courseId, changedStudentIds)
        if (outcome.recipients > 0) {
          const delivered = outcome.delivered.email + outcome.delivered.sms
          const failed = outcome.failed.email + outcome.failed.sms
          const skipped = outcome.skipped.email + outcome.skipped.sms
          setNotificationNotice(
            failed === 0 && skipped === 0
              ? t('courses.parentsNotified', { count: delivered })
              : t('courses.notificationOutcome', { delivered, failed, skipped }),
          )
        }
      } catch {
        setNotificationNotice(t('courses.notificationUnavailable'))
      }
    }
  }, [courseId, selectedTerm, t])

  function updateGradeItemField(field, value) {
    setGradeItemForm((current) => ({ ...current, [field]: value }))
  }

  function updateEditGradeItemField(field, value) {
    setEditGradeItemForm((current) => ({ ...current, [field]: value }))
  }

  async function refreshGradeItems() {
    const refreshed = await listGradeItems(courseId)
    setGradeItems(refreshed)
    return refreshed
  }

  function openAddGradeItemForm() {
    setGradeItemForm((current) => ({ ...current, term: selectedTerm }))
    setShowGradeItemForm(true)
    setGradeItemError(null)
    setGradeItemMessage(null)
    setEditingGradeItemId(null)
    setGradeItemEditError(null)
  }

  // Open the Beninese-specific form pre-loaded with the given item type.
  function openBenineseForm(itemType) {
    const titleMap = { INTERRO: 'Interro', DEVOIR: 'Devoir', COMPOSITION: 'Composition' }
    setGradeItemForm({
      ...EMPTY_GRADE_ITEM_FORM,
      title: titleMap[itemType] || '',
      term: selectedTerm || course?.term || '',
      itemType,
    })
    setShowGradeItemForm(true)
    setGradeItemError(null)
    setGradeItemMessage(null)
    setEditingGradeItemId(null)
    setGradeItemEditError(null)
  }

  function cancelAddGradeItem() {
    setShowGradeItemForm(false)
    setGradeItemError(null)
  }

  async function handleAddGradeItem(event) {
    event.preventDefault()
    setGradeItemError(null)
    setGradeItemMessage(null)

    const validationError = validateGradeItemForm(gradeItemForm, t, isBenineseMode)
    if (validationError) {
      setGradeItemError(validationError)
      return
    }

    setAddingGradeItem(true)
    try {
      await createGradeItem(courseId, gradeItemForm)
      await refreshGradeItems()
      setGradeItemForm({
        ...EMPTY_GRADE_ITEM_FORM,
        term: gradeItemForm.term.trim() || course?.term || '',
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

    const validationError = validateGradeItemForm(editGradeItemForm, t, isBenineseMode)
    if (validationError) {
      setGradeItemEditError(validationError)
      return
    }

    setSavingGradeItemEdit(true)
    try {
      await updateGradeItem(gradeItemId, editGradeItemForm)
      await refreshGradeItems()
      setGradeItemMessage(t('courses.gradeItemUpdated'))
      setEditingGradeItemId(null)
      setEditGradeItemForm(gradeItemToForm(null))
    } catch (err) {
      setGradeItemEditError(err.message)
    } finally {
      setSavingGradeItemEdit(false)
    }
  }

  async function handleRecalculate() {
    setCalculating(true)
    setCalcError(null)
    setCalcSummary(null)
    try {
      await recalculateAllResults()
    } catch (err) {
      setCalcError(err.message)
    } finally {
      setCalculating(false)
    }
  }

  const studentNameById = useMemo(() => {
    const map = {}
    for (const s of students || []) {
      map[s.id] = `${s.last_name}, ${s.first_name}`
    }
    return map
  }, [students])

  const gradeItemList = gradeItems || []

  // Grading mode: Beninese formula applies to French-section collège courses.
  const isBenineseMode = course?.grading_system
    ? course.grading_system === 'BENINESE'
    : !!(course?.language_group === 'FRENCH' && course?.class_school_level === 'college')

  const selectedData = assessmentDataForTerm({
    term: selectedTerm,
    gradeItems: gradeItemList,
    grades: grades || [],
    results: results || [],
  })
  const selectedTermItems = selectedData.gradeItems
  const selectedTermGrades = selectedData.grades
  const selectedTermResults = selectedData.results
  const locksByTerm = lockByTerm(trimesterLocks)
  const selectedTermLocked = locksByTerm.get(selectedTerm) || false

  const hasDevoir = selectedTermItems.some((i) => i.item_type === 'DEVOIR')
  const hasComposition = selectedTermItems.some((i) => i.item_type === 'COMPOSITION')

  const totalWeight = selectedTermItems.reduce((sum, item) => sum + Number(item.weight || 0), 0)
  const isWeightReady = Math.abs(totalWeight - 1) <= WEIGHT_TOLERANCE
  const weightSummary = isWeightReady
    ? t('courses.weightReady', { total: formatWeight(totalWeight) })
    : totalWeight < 1
      ? t('courses.weightMissing', { total: formatWeight(totalWeight), amount: formatWeight(1 - totalWeight) })
      : t('courses.weightOver', { total: formatWeight(totalWeight), amount: formatWeight(totalWeight - 1) })

  const loaded = course && students && gradeItems && grades && results

  return (
    <section className="teacher-page">
      <Link to="/teacher" className="back-link">
        ← {t('courses.myCourses')}
      </Link>

      {error && <ErrorBanner message={error} />}
      {!error && !loaded && <Spinner label={t('courses.loadingOne')} />}

      {!error && loaded && (
        <>
          <div className="detail-header">
            <div>
              <h2 className="page-title">{course.name}</h2>
              <p className="muted">
                {course.code} · {course.class_name || t('courses.withoutClass')} · {course.term} {course.school_year}
                {isBenineseMode && <> · <em>{t('courses.benineseMode')}</em></>}
              </p>
            </div>
          </div>

          <div className="section-heading">
            <h3>{t('courses.enrolledStudents')}</h3>
            <span className="muted">{t('courses.studentCount', { count: students.length })}</span>
          </div>
          {students.length === 0 ? (
            <Empty message={t('courses.noStudentsYet')} />
          ) : (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('reports.student')}</th>
                    <th>{t('students.class')}</th>
                    <th>{t('students.studentNumber')}</th>
                  </tr>
                </thead>
                <tbody>
                  {students.map((student) => (
                    <tr key={student.id}>
                      <td className="nowrap">
                        {student.last_name}, {student.first_name}
                      </td>
                      <td>{student.class_name || '—'}</td>
                      <td className="mono">{student.student_number}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="trimester-tabs" role="tablist" aria-label={t('courses.trimesterSections')}>
            {TRIMESTER_TERMS.map((term) => {
              const locked = locksByTerm.get(term) || false
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
                    setCalcSummary(null)
                    setCalcError(null)
                  }}
                >
                  {term}{locked ? ` · ${t('courses.lockedShort')}` : ''}
                </button>
              )
            })}
          </div>
          {selectedTermLocked && (
            <div className="state trimester-lock-notice" role="status">
              <strong>{t('courses.trimesterLockedTitle')}</strong>
              <p>{t('courses.trimesterLockedTeacher')}</p>
            </div>
          )}

          <div className="section-heading">
            <h3>{t('courses.gradeItems')}</h3>

            {!showGradeItemForm && !selectedTermLocked && (
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
                <button type="button" className="btn btn-primary" onClick={openAddGradeItemForm}>
                  {t('courses.addGradeItem')}
                </button>
              )}
              </div>
            )}
          </div>
          {gradeItemMessage && <p className="grade-summary">{gradeItemMessage}</p>}

          {/* Weight summary / mode label */}
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

          {/* Datalists for weighted mode suggestions */}
          {!isBenineseMode && (
            <>
              <datalist id="teacher-grade-item-title-options">
                {GRADE_ITEM_SUGGESTIONS.map((value) => (
                  <option key={value} value={value} />
                ))}
              </datalist>
              <datalist id="teacher-grade-item-category-options">
                {GRADE_ITEM_SUGGESTIONS.map((value) => (
                  <option key={value} value={value} />
                ))}
              </datalist>
            </>
          )}

          {/* Add grade item form */}
          {showGradeItemForm && (
            <div className="modal-backdrop" onClick={() => !addingGradeItem && cancelAddGradeItem()}>
              <form className="card admin-form modal-card" onClick={(event) => event.stopPropagation()} onSubmit={handleAddGradeItem}>
              <h3 className="section-title">{t('courses.addGradeItem')}</h3>
              <label className="field">
                <span>{t('courses.title')}</span>
                <input
                  value={gradeItemForm.title}
                  onChange={(event) => updateGradeItemField('title', event.target.value)}
                  disabled={addingGradeItem}
                  list={isBenineseMode ? undefined : 'teacher-grade-item-title-options'}
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
                    list="teacher-grade-item-category-options"
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

              <label className="field">
                <span>{t('courses.dueDate')}</span>
                <input
                  type="date"
                  value={gradeItemForm.dueDate}
                  onChange={(event) => updateGradeItemField('dueDate', event.target.value)}
                  disabled={addingGradeItem}
                />
              </label>

              <div className="grade-actions">
                <button type="submit" className="btn btn-primary" disabled={addingGradeItem}>
                  {addingGradeItem ? t('courses.adding') : t('courses.addGradeItem')}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={addingGradeItem}
                  onClick={cancelAddGradeItem}
                >
                  {t('common.cancel')}
                </button>
              </div>
              {gradeItemError && <ErrorBanner message={gradeItemError} />}
              </form>
            </div>
          )}

          {/* Grade items list */}
          {selectedTermItems.length === 0 ? (
            <Empty message={t('courses.noGradeItemsYet')} />
          ) : (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('courses.title')}</th>
                    {isBenineseMode
                      ? <th>{t('courses.itemType')}</th>
                      : <th>{t('courses.category')}</th>
                    }
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
                        {isBenineseMode
                          ? <td>{item.item_type}</td>
                          : <td>{item.category}</td>
                        }
                        <td className="num">{item.max_score}</td>
                        {!isBenineseMode && <td className="num">{item.weight}</td>}
                        <td>{item.term}</td>
                        <td className="nowrap">{item.due_date || '—'}</td>
                        <td className="nowrap">
                          <button
                            type="button"
                            className="btn btn-ghost"
                            disabled={savingGradeItemEdit || selectedTermLocked}
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
                                  list={isBenineseMode ? undefined : 'teacher-grade-item-title-options'}
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
                                    list="teacher-grade-item-category-options"
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
            onSaved={handleGradesSaved}
            gradingMode={isBenineseMode ? 'BENINESE' : 'WEIGHTED'}
            readOnly={selectedTermLocked}
          />

          <div className="section-heading">
            <div>
              <h3>{t('courses.results')}</h3>
              <p className="muted">{t('courses.autoRecalculateHint')}</p>
            </div>
            <div className="grade-actions">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={handleRecalculate}
                disabled={calculating}
              >
                {calculating ? t('courses.recalculating') : t('courses.recalculateManual')}
              </button>
              {calcSummary && (
                <span className="grade-summary">
                  {calcSummary.no_changes ? t('courses.noChanges') : t('courses.recalculated')}
                </span>
              )}
            </div>
          </div>

          {calcError && <ErrorBanner message={calcError} />}
          {notificationNotice && <p className="grade-summary">{notificationNotice}</p>}

          {calcSummary && calcSummary.skipped_students.length > 0 && (
            <div className="state state-empty skipped-note">
              <strong>{t('courses.skippedStudents')}</strong>
              <ul className="skipped-list">
                {calcSummary.skipped_students.map((skipped) => (
                  <li key={skipped.student_id}>
                    {t('courses.skippedLine', { name: skipped.student_name, items: skipped.missing_grade_items.join(', ') })}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {selectedTermResults.length === 0 ? (
            <Empty message={t('courses.noResultsYet')} />
          ) : (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('reports.student')}</th>
                    <th>{t('common.term')}</th>
                    <th className="num">{t('reports.average')}</th>
                    <th>{t('courses.letterGrade')}</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedTermResults.map((result) => (
                    <tr key={result.id}>
                      <td className="nowrap">
                        {studentNameById[result.student_id] || result.student_id}
                      </td>
                      <td>{result.term}</td>
                      <td className="num">{formatReportAverage(result.average, result.scale)}</td>
                      <td>{result.letter_grade}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  )
}
