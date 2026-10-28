import { useSyncExternalStore } from 'react'
import { serverNow } from '../api/client'

// One shared timer for every countdown on screen. Without this, a page of 12 cards would run
// 12 separate intervals. The timer only runs while at least one component is listening.

let now = serverNow()
const listeners = new Set()
let timer = null

function tick() {
  now = serverNow()
  listeners.forEach((listener) => listener())
}

function subscribe(listener) {
  listeners.add(listener)
  if (listeners.size === 1) {
    now = serverNow()
    timer = setInterval(tick, 1000)
    // A sleeping tab's timers drift; recompute from the real clock the moment it wakes up.
    document.addEventListener('visibilitychange', tick)
  }
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0) {
      clearInterval(timer)
      timer = null
      document.removeEventListener('visibilitychange', tick)
    }
  }
}

/** The current SERVER time in ms, updating every second. Countdowns are computed from this, never
 *  by decrementing, so a slow or sleeping tab can't make them drift. */
export function useNow() {
  return useSyncExternalStore(subscribe, () => now)
}
