import { useTranslation } from 'react-i18next'

// Parents only ever receive approved/sent reports, but admins also see drafts.
const LABEL_KEYS = {
  draft: 'reports.statusDraft',
  approved: 'reports.statusApproved',
  sent: 'reports.statusSent',
}

export default function StatusBadge({ status }) {
  const { t } = useTranslation()
  const key = LABEL_KEYS[status]
  return <span className={`badge badge-${status}`}>{key ? t(key) : status}</span>
}
