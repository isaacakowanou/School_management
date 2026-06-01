// Parents only ever receive approved/sent reports, but we render defensively.
const LABELS = {
  approved: 'Approved',
  sent: 'Sent',
}

export default function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{LABELS[status] ?? status}</span>
}
