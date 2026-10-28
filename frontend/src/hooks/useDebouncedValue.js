import { useEffect, useState } from 'react'

/** `value`, but only after it has stopped changing for `ms` (so typing a title doesn't ask the server on every key). */
export function useDebouncedValue(value, ms = 600) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return debounced
}
