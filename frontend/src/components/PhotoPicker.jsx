import { useEffect, useMemo, useRef } from 'react'
import { MAX_PHOTOS, PHOTO_TYPES } from '../lib/listingForm'

/**
 * Choose up to MAX_PHOTOS photos, with previews. The first photo is the "cover" shown on browse cards.
 *   files     the chosen File objects
 *   onChange  a React state setter: it is called with an updater function, so every change is
 *             applied to the LATEST list even if two taps land before the next render
 */
export function PhotoPicker({ files, onChange, error }) {
  const input = useRef(null)

  // Preview URLs for the chosen files. Created once per change, and released so they don't leak memory.
  const previews = useMemo(() => files.map((file) => URL.createObjectURL(file)), [files])
  useEffect(() => () => previews.forEach((url) => URL.revokeObjectURL(url)), [previews])

  function addFiles(event) {
    const picked = Array.from(event.target.files ?? [])
    event.target.value = '' // so choosing the same file again still fires a change
    if (picked.length) onChange((current) => [...current, ...picked])
  }

  return (
    <div className="photo-picker">
      <div className="photo-grid">
        {files.map((file, i) => (
          <figure key={`${file.name}-${i}`} className="photo-tile">
            <img src={previews[i]} alt={`Selected photo ${i + 1}: ${file.name}`} />
            {i === 0 && <figcaption className="photo-cover">Cover</figcaption>}
            <button
              type="button"
              className="photo-remove"
              onClick={() => onChange((current) => current.filter((_, j) => j !== i))}
              aria-label={`Remove photo ${i + 1}`}
            >
              ×
            </button>
          </figure>
        ))}
        {files.length < MAX_PHOTOS && (
          <button type="button" className="photo-add" onClick={() => input.current.click()}>
            + Add photo
          </button>
        )}
      </div>
      <input
        ref={input}
        type="file"
        accept={PHOTO_TYPES.join(',')}
        multiple
        hidden
        onChange={addFiles}
        aria-label="Add photos"
      />
      <small className="muted">
        {files.length} of {MAX_PHOTOS} · JPEG, PNG or WebP, up to 5 MB each. The first photo is the cover.
      </small>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
