import { useEffect } from 'react'
import { APP_NAME } from '../lib/brand'

/** Give the page a title that says where you are (screen readers and browser tabs rely on it). */
export function usePageTitle(title) {
  useEffect(() => {
    const before = document.title
    document.title = `${title} · ${APP_NAME}`
    return () => {
      document.title = before
    }
  }, [title])
}
