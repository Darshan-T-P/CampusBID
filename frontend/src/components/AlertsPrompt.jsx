import { useState } from 'react'
import { Icon } from './Icon'

const KEY = 'relay.alertsPrompt'
const supported = () => typeof Notification !== 'undefined'

function dismissedBefore() {
  try {
    return localStorage.getItem(KEY) === 'dismissed'
  } catch {
    return false // storage blocked: just show it
  }
}

/**
 * A one-time offer to turn on desktop alerts, so people don't have to find the button inside the bell menu.
 * Shown only while permission hasn't been decided, and never again once dismissed.
 */
export function AlertsPrompt() {
  const [visible, setVisible] = useState(() => supported() && Notification.permission === 'default' && !dismissedBefore())
  if (!visible) return null

  function dismiss() {
    try {
      localStorage.setItem(KEY, 'dismissed')
    } catch {
      /* storage blocked: it may show again next visit */
    }
    setVisible(false)
  }

  async function enable() {
    await Notification.requestPermission()
    dismiss()
  }

  return (
    <div className="alerts-prompt" role="region" aria-label="Desktop alerts">
      <div className="container alerts-prompt-inner">
        <Icon name="zap" size={16} />
        <span>Get a desktop alert when you're outbid or an auction you follow is about to close, even while this tab is in the background.</span>
        <button type="button" className="btn btn-primary btn-sm" onClick={enable}>
          Turn on alerts
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={dismiss}>
          Not now
        </button>
      </div>
    </div>
  )
}
