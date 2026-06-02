// Parents only ever receive approved/sent reports, but admins also see drafts.
const LABELS = {
  draft: 'Draft',
  approved: 'Approved',
  sent: 'Sent',
}

export default function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{LABELS[status] ?? status}</span>
}
