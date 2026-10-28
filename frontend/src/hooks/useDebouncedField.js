import { useEffect, useState } from 'react'

/**
 * A text field whose value is committed (e.g. to the URL) only after the user pauses typing.
 * `external` is the committed value; if it changes from outside (like "Clear filters"), the field follows.
 */
export function useDebouncedField(external, commit, delay = 400) {
  const [value, setValue] = useState(external)

  useEffect(() => {
    setValue(external)
  }, [external])

  useEffect(() => {
    if (value === external) return undefined
    const timer = setTimeout(() => commit(value), delay)
    return () => clearTimeout(timer)
    // `commit` is recreated every render; only a change in what the user typed should restart the wait.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  return [value, setValue]
}
