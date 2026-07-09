import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { createSubject, deleteSubject, listSubjects, updateSubject } from '../api/subjects.js'
import { SUBJECT_LEVEL_GROUPS } from '../constants/subjectLevelGroups.js'
import { SCHOOL_GROUPS } from '../constants/schoolGroups.js'
import Spinner from '../components/Spinner.jsx'
import ErrorBanner from '../components/ErrorBanner.jsx'
import Empty from '../components/Empty.jsx'

function emptyQuickAdd() {
  return { nameFr: '', nameEn: '', section: 'FRENCH' }
}

function parseApplicableClasses(text) {
  return text
    .split(',')
    .map((name) => name.trim())
    .filter(Boolean)
}

function formatApplicableClasses(list) {
  return (list || []).join(', ')
}

export default function AdminSubjectsPage() {
  const { t } = useTranslation()
  const [subjects, setSubjects] = useState(null)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const [pending, setPending] = useState(false)

  const [quickAdd, setQuickAdd] = useState({})
  const [quickAddError, setQuickAddError] = useState({})
  const [addGroup, setAddGroup] = useState('NURSERY')
  const [showAddDialog, setShowAddDialog] = useState(false)
  const [search, setSearch] = useState('')

  const [editing, setEditing] = useState(null)
  const [editForm, setEditForm] = useState(null)
  const [editError, setEditError] = useState(null)

  async function refresh() {
    const data = await listSubjects()
    setSubjects(data)
    return data
  }

  useEffect(() => {
    let cancelled = false
    setError(null)
    setSubjects(null)
    listSubjects()
      .then((data) => {
        if (!cancelled) setSubjects(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const subjectsByLevelGroup = useMemo(() => {
    const map = {}
    for (const group of SUBJECT_LEVEL_GROUPS) map[group.value] = []
    const query = search.trim().toLowerCase()
    for (const subject of subjects || []) {
      if (query && !`${subject.name_fr} ${subject.name_en}`.toLowerCase().includes(query)) continue
      ;(map[subject.level_group] || (map[subject.level_group] = [])).push(subject)
    }
    return map
  }, [subjects, search])

  function quickAddFor(groupValue) {
    return quickAdd[groupValue] || emptyQuickAdd()
  }

  function setQuickAddField(groupValue, field, value) {
    setQuickAdd((q) => ({ ...q, [groupValue]: { ...quickAddFor(groupValue), [field]: value } }))
  }

  function openAddDialog() {
    setAddGroup(SUBJECT_LEVEL_GROUPS[0].value)
    setQuickAddError({})
    setShowAddDialog(true)
  }

  function nextSortOrder(groupValue, section) {
    const list = (subjectsByLevelGroup[groupValue] || []).filter((s) => s.section === section)
    return list.length ? Math.max(...list.map((s) => s.sort_order)) + 1 : 1
  }

  async function handleQuickAdd(event, groupValue) {
    event.preventDefault()
    setMessage(null)
    setQuickAddError((e) => ({ ...e, [groupValue]: null }))
    const form = quickAddFor(groupValue)
    if (!form.nameFr.trim() || !form.nameEn.trim()) {
      setQuickAddError((e) => ({ ...e, [groupValue]: t('subjects.errorBothRequired') }))
      return
    }
    setPending(true)
    try {
      await createSubject({
        nameFr: form.nameFr,
        nameEn: form.nameEn,
        section: form.section,
        levelGroup: groupValue,
        sortOrder: nextSortOrder(groupValue, form.section),
        applicableClasses: null,
      })
      await refresh()
      setQuickAdd((q) => ({ ...q, [groupValue]: emptyQuickAdd() }))
      setShowAddDialog(false)
      setMessage(t('subjects.added'))
    } catch (err) {
      setQuickAddError((e) => ({ ...e, [groupValue]: err.message }))
    } finally {
      setPending(false)
    }
  }

  function openEdit(subject) {
    setEditing(subject)
    setEditForm({
      nameFr: subject.name_fr,
      nameEn: subject.name_en,
      section: subject.section,
      levelGroup: subject.level_group,
      sortOrder: String(subject.sort_order),
      applicableClasses: formatApplicableClasses(subject.applicable_classes),
    })
    setEditError(null)
  }

  function updateEditField(field, value) {
    setEditForm((f) => ({ ...f, [field]: value }))
  }

  async function handleSaveEdit(event) {
    event.preventDefault()
    setEditError(null)
    if (!editForm.nameFr.trim() || !editForm.nameEn.trim()) {
      setEditError(t('subjects.errorBothRequired'))
      return
    }
    const sortOrder = Number(editForm.sortOrder)
    if (!Number.isInteger(sortOrder)) {
      setEditError(t('subjects.errorSortOrder'))
      return
    }
    setPending(true)
    try {
      await updateSubject(editing.id, {
        nameFr: editForm.nameFr,
        nameEn: editForm.nameEn,
        section: editForm.section,
        levelGroup: editForm.levelGroup,
        sortOrder,
        applicableClasses: parseApplicableClasses(editForm.applicableClasses),
      })
      await refresh()
      setEditing(null)
      setEditForm(null)
      setMessage(t('subjects.updated'))
    } catch (err) {
      setEditError(err.message)
    } finally {
      setPending(false)
    }
  }

  async function handleDelete(subject) {
    if (!window.confirm(t('subjects.confirmDelete', { name: subject.name_fr }))) return
    setMessage(null)
    setError(null)
    setPending(true)
    try {
      await deleteSubject(subject.id)
      await refresh()
      setMessage(t('subjects.deleted'))
    } catch (err) {
      if (err.status === 409 && err.detail && typeof err.detail === 'object') {
        setError(t('subjects.deleteBlocked', { name: subject.name_fr, count: err.detail.course_count }))
      } else {
        setError(err.message)
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="admin-page">
      <div className="report-header">
        <div>
          <h2 className="page-title">{t('nav.subjects')}</h2>
          <p className="muted">{t('subjects.subtitle')}</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={openAddDialog} disabled={pending}>
          {t('subjects.addSubject')}
        </button>
      </div>

      {message && <p className="grade-summary">{message}</p>}
      {error && <ErrorBanner message={error} />}
      {!error && subjects === null && <Spinner label={t('subjects.loading')} />}

      {subjects && (
        <div className="list-toolbar">
          <label className="toolbar-field">
            <span>{t('common.search')}</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t('subjects.searchPlaceholder')}
            />
          </label>
          <nav className="jump-nav" aria-label={t('nav.subjects')}>
            {SUBJECT_LEVEL_GROUPS.map((group) => (
              <a key={group.value} href={`#subjects-${group.value}`}>
                {t(`subjectLevelGroups.${group.value}`)}
              </a>
            ))}
          </nav>
        </div>
      )}

      {subjects &&
        SUBJECT_LEVEL_GROUPS.map((group) => {
          const list = subjectsByLevelGroup[group.value] || []
          return (
            <div key={group.value} id={`subjects-${group.value}`}>
              <div className="section-heading">
                <h3 className="section-title">{t(`subjectLevelGroups.${group.value}`)}</h3>
              </div>

              {list.length === 0 ? (
                <Empty message={t('subjects.emptyGroup', { group: t(`subjectLevelGroups.${group.value}`) })} />
              ) : (
                <div className="table-scroll">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{t('subjects.subjectCol')}</th>
                        <th>{t('subjects.section')}</th>
                        <th className="num">{t('subjects.orderCol')}</th>
                        <th>{t('nav.classes')}</th>
                        <th className="num">{t('subjects.coursesCol')}</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {list.map((subject) => (
                        <tr key={subject.id}>
                          <td>
                            <strong>{subject.name_fr}</strong>
                            <span className="muted"> · {subject.name_en}</span>
                          </td>
                          <td className="nowrap">
                            {subject.section === 'FRENCH' ? t('subjects.sectionFrench') : t('subjects.sectionEnglish')}
                          </td>
                          <td className="num">{subject.sort_order}</td>
                          <td className="nowrap">
                            {subject.applicable_classes
                              ? subject.applicable_classes.join(', ')
                              : t('subjects.allClasses')}
                          </td>
                          <td className="num">{subject.course_count}</td>
                          <td className="nowrap row-actions">
                            <button
                              type="button"
                              className="link-action"
                              onClick={() => openEdit(subject)}
                              disabled={pending}
                            >
                              {t('common.edit')}
                            </button>
                            <button
                              type="button"
                              className="link-action link-action-danger"
                              onClick={() => handleDelete(subject)}
                              disabled={pending}
                            >
                              {t('common.delete')}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )
        })}

      {showAddDialog && (
        <div className="modal-backdrop" onClick={() => !pending && setShowAddDialog(false)}>
          <div className="card modal-card" onClick={(e) => e.stopPropagation()}>
            <h3 className="section-title">{t('subjects.addSubject')}</h3>
            <form className="admin-form" onSubmit={(e) => handleQuickAdd(e, addGroup)}>
              <label className="field">
                <span>{t('subjects.levelGroup')}</span>
                <select
                  className="grade-input full-width-input"
                  value={addGroup}
                  onChange={(e) => setAddGroup(e.target.value)}
                  disabled={pending}
                >
                  {SUBJECT_LEVEL_GROUPS.map((group) => (
                    <option key={group.value} value={group.value}>
                      {t(`subjectLevelGroups.${group.value}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>{t('subjects.nameFr')}</span>
                <input
                  value={quickAddFor(addGroup).nameFr}
                  onChange={(e) => setQuickAddField(addGroup, 'nameFr', e.target.value)}
                  disabled={pending}
                  required
                />
              </label>
              <label className="field">
                <span>{t('subjects.nameEn')}</span>
                <input
                  value={quickAddFor(addGroup).nameEn}
                  onChange={(e) => setQuickAddField(addGroup, 'nameEn', e.target.value)}
                  disabled={pending}
                  required
                />
              </label>
              <label className="field">
                <span>{t('subjects.section')}</span>
                <select
                  className="grade-input full-width-input"
                  value={quickAddFor(addGroup).section}
                  onChange={(e) => setQuickAddField(addGroup, 'section', e.target.value)}
                  disabled={pending}
                >
                  {SCHOOL_GROUPS.map((section) => (
                    <option key={section.value} value={section.value}>
                      {t(section.labelKey)}
                    </option>
                  ))}
                </select>
              </label>
              <div className="grade-actions">
                <button type="submit" className="btn btn-primary" disabled={pending}>
                  {pending ? t('common.saving') : t('common.add')}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setShowAddDialog(false)}
                  disabled={pending}
                >
                  {t('common.cancel')}
                </button>
              </div>
              {quickAddError[addGroup] && <ErrorBanner message={quickAddError[addGroup]} />}
            </form>
          </div>
        </div>
      )}

      {editing && editForm && (
        <div className="modal-backdrop" onClick={() => setEditing(null)}>
          <div className="card modal-card" onClick={(e) => e.stopPropagation()}>
            <h3 className="section-title">{t('subjects.editTitle')}</h3>
            <form className="admin-form" onSubmit={handleSaveEdit}>
              <label className="field">
                <span>{t('subjects.nameFr')}</span>
                <input
                  value={editForm.nameFr}
                  onChange={(e) => updateEditField('nameFr', e.target.value)}
                  disabled={pending}
                  required
                />
              </label>
              <label className="field">
                <span>{t('subjects.nameEn')}</span>
                <input
                  value={editForm.nameEn}
                  onChange={(e) => updateEditField('nameEn', e.target.value)}
                  disabled={pending}
                  required
                />
              </label>
              <label className="field">
                <span>{t('subjects.section')}</span>
                <select
                  className="grade-input full-width-input"
                  value={editForm.section}
                  onChange={(e) => updateEditField('section', e.target.value)}
                  disabled={pending}
                >
                  {SCHOOL_GROUPS.map((section) => (
                    <option key={section.value} value={section.value}>
                      {t(section.labelKey)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>{t('subjects.levelGroup')}</span>
                <select
                  className="grade-input full-width-input"
                  value={editForm.levelGroup}
                  onChange={(e) => updateEditField('levelGroup', e.target.value)}
                  disabled={pending}
                >
                  {SUBJECT_LEVEL_GROUPS.map((group) => (
                    <option key={group.value} value={group.value}>
                      {t(`subjectLevelGroups.${group.value}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>{t('classes.sortOrder')}</span>
                <input
                  type="number"
                  value={editForm.sortOrder}
                  onChange={(e) => updateEditField('sortOrder', e.target.value)}
                  disabled={pending}
                />
              </label>
              <label className="field">
                <span>{t('subjects.classesLabel')}</span>
                <input
                  value={editForm.applicableClasses}
                  onChange={(e) => updateEditField('applicableClasses', e.target.value)}
                  disabled={pending}
                  placeholder="e.g. 4ème, 3ème"
                />
              </label>

              <div className="grade-actions">
                <button type="submit" className="btn btn-primary" disabled={pending}>
                  {pending ? t('common.saving') : t('common.saveChanges')}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setEditing(null)}
                  disabled={pending}
                >
                  {t('common.cancel')}
                </button>
              </div>
              {editError && <ErrorBanner message={editError} />}
            </form>
          </div>
        </div>
      )}
    </section>
  )
}
