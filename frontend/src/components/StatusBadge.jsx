import { useTranslation } from 'react-i18next'

// Parents only ever receive approved/sent reports, but admins also see drafts.
const LABEL_KEYS = {
  draft: 'reports.statusDraft',
  approved: 'reports.statusApproved',
  sent: 'reports.statusSent',
  needs_review: 'reports.needsReview',
}

export default function StatusBadge({ status }) {
  const { t } = useTranslation()
  const key = LABEL_KEYS[status]
  const className = status === 'needs_review' ? 'badge badge-review' : `badge badge-${status}`
  return <span className={className}>{key ? t(key) : status}</span>
}
