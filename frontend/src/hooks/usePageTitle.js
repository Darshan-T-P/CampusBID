import { useEffect } from 'react'

/** Give the page a title that says where you are (screen readers and browser tabs rely on it). */
export function usePageTitle(title) {
  useEffect(() => {
    const before = document.title
    document.title = `${title} · CampusBid`
    return () => {
      document.title = before
    }
  }, [title])
}
