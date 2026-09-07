import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  REQUEST_FINISHED_EVENT,
  SLOW_REQUEST_EVENT,
  updateSlowRequestIds,
} from '../api/requestActivity.js'

export default function SlowServerBanner() {
  const { t } = useTranslation()
  const [slowRequestIds, setSlowRequestIds] = useState(() => new Set())

  useEffect(() => {
    const update = (event) => {
      setSlowRequestIds((current) => updateSlowRequestIds(current, event.type, event.detail.requestId))
    }
    window.addEventListener(SLOW_REQUEST_EVENT, update)
    window.addEventListener(REQUEST_FINISHED_EVENT, update)
    return () => {
      window.removeEventListener(SLOW_REQUEST_EVENT, update)
      window.removeEventListener(REQUEST_FINISHED_EVENT, update)
    }
  }, [])

  if (slowRequestIds.size === 0) return null

  return (
    <div className="state state-warning global-slow-server-banner" role="status" aria-live="polite">
      {t('serverStatus.slow')}
    </div>
  )
}
