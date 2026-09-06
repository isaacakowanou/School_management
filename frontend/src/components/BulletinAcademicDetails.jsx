import { useTranslation } from 'react-i18next'
import { formatReportAverage } from '../utils/format.js'
import { annualAverageLabel } from '../utils/bulletinDisplay.js'

const TRACKS = ['french', 'english', 'bilingual']
const TRIMESTERS = [1, 2, 3]

function value(value, scale) {
  return value == null ? '—' : formatReportAverage(value, scale)
}

function CourseTable({ title, courses, scale, detailed = false, t }) {
  if (!courses?.length) return null

  return (
    <section className="bulletin-course-section">
      <h4>{title}</h4>
      <div className="table-scroll bulletin-scroll">
        <table className="table bulletin-course-table">
          <thead>
            <tr>
              <th>{t('reports.course')}</th>
              {detailed && <th className="num">{t('reports.moyInt')}</th>}
              {detailed && <th className="num">{t('reports.devoir')}</th>}
              {detailed && <th className="num">{t('reports.mcc')}</th>}
              {detailed && <th className="num">{t('reports.composition')}</th>}
              {detailed && <th className="num">{t('reports.averageShort')}</th>}
              <th className="num">{t('reports.grade')}</th>
              {!detailed && <th>{t('reports.appreciation')}</th>}
            </tr>
          </thead>
          <tbody>
            {courses.map((course) => (
              <tr key={course.course_id}>
                <td>{course.course_name}</td>
                {detailed && <td className="num">{value(course.moy_int, scale)}</td>}
                {detailed && <td className="num">{value(course.devoir_score, scale)}</td>}
                {detailed && <td className="num">{value(course.mcc, scale)}</td>}
                {detailed && <td className="num">{value(course.composition_score, scale)}</td>}
                {detailed && <td className="num"><strong>{value(course.average, scale)}</strong></td>}
                <td className="num">{course.letter_grade || '—'}</td>
                {!detailed && <td>{course.appreciation || '—'}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function BehaviorTable({ title, items, t }) {
  return (
    <section>
      <h4>{title}</h4>
      <table className="table">
        <thead>
          <tr>
            <th>{t('reports.item')}</th>
            <th className="num">{t('reports.grade')}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.key}>
              <td>{item.en_label} <span className="muted">/ {item.fr_label}</span></td>
              <td className="num">{item.letter_grade || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

export default function BulletinAcademicDetails({ report, showBehavior = false }) {
  const { t } = useTranslation()
  const bulletin = report?.bulletin
  if (!bulletin) return null

  const groups = bulletin.courses_by_language
  const frenchIsDetailed = groups.french_courses.some((course) => course.moy_int != null)
  const annual = bulletin.annual_averages

  return (
    <div className="bulletin-web">
      <section className="bulletin-metadata" aria-label={t('reports.bulletinDetails')}>
        <span><strong>{t('reports.educmasterNumber')}:</strong> {bulletin.student.educmaster_number || '—'}</span>
        <span><strong>{t('reports.class')}:</strong> {bulletin.school_class?.name_fr || '—'}</span>
        <span><strong>{t('reports.classSize')}:</strong> {bulletin.class_effectif ?? '—'}</span>
        {bulletin.term_dates_fr && (
          <span><strong>{t('reports.termDates')}:</strong> {bulletin.term_dates_fr}</span>
        )}
      </section>

      <h3 className="section-title">{t('reports.academicResults')}</h3>
      <CourseTable
        title={t('reports.frenchTrack')}
        courses={groups.french_courses}
        scale={report.scale}
        detailed={frenchIsDetailed}
        t={t}
      />
      <CourseTable
        title={t('reports.englishTrack')}
        courses={groups.english_courses}
        scale={report.scale}
        t={t}
      />
      <CourseTable
        title={t('reports.otherCourses')}
        courses={groups.untagged_courses}
        scale={report.scale}
        t={t}
      />

      <h3 className="section-title">{t('reports.averagesSection')}</h3>
      <div className="table-scroll bulletin-scroll">
        <table className="table bulletin-averages-table">
          <thead>
            <tr>
              <th>{t('reports.averagesSection')}</th>
              {TRACKS.map((track) => (
                <th key={track} colSpan="3" className="num">{t(`reports.track.${track}`)}</th>
              ))}
            </tr>
            <tr>
              <th />
              {TRACKS.flatMap((track) => TRIMESTERS.map((trimester) => (
                <th key={`${track}-${trimester}`} className="num">{trimester}{trimester === 1 ? 'er' : 'e'}</th>
              )))}
            </tr>
          </thead>
          <tbody>
            {[
              ['student', t('reports.studentAverage')],
              ['class_highest', t('reports.classHighest')],
              ['class_lowest', t('reports.classLowest')],
            ].map(([field, label]) => (
              <tr key={field}>
                <th>{label}</th>
                {TRACKS.flatMap((track) => TRIMESTERS.map((trimester) => (
                  <td key={`${field}-${track}-${trimester}`} className="num">
                    {value(bulletin.averages_grid[String(trimester)]?.[track]?.[field], report.scale)}
                  </td>
                )))}
              </tr>
            ))}
            {bulletin.is_final_trimester && (
              <tr className={annual.is_partial ? 'annual-average-partial' : ''}>
                <th>{annualAverageLabel(annual, t)}</th>
                {TRACKS.map((track) => (
                  <td key={track} colSpan="3" className="num"><strong>{value(annual[track], report.scale)}</strong></td>
                ))}
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {showBehavior && (
        <>
          <div className="bulletin-behavior-grid">
            <BehaviorTable title={t('reports.conductSection')} items={bulletin.conduct_items} t={t} />
            <BehaviorTable title={t('reports.workHabitsSection')} items={bulletin.work_habit_items} t={t} />
          </div>
          <h3 className="section-title">{t('reports.commentsSection')}</h3>
          <div className="bulletin-comments">
            <p><strong>{t('reports.teacherComment')}:</strong> {bulletin.teacher_comment_fr || bulletin.teacher_comment_en || '—'}</p>
            <p><strong>{t('reports.principalComment')}:</strong> {bulletin.principal_comment_fr || bulletin.principal_comment_en || '—'}</p>
          </div>
        </>
      )}

      <p className="bulletin-grading-key">{bulletin.grading_key}</p>
    </div>
  )
}
