import { useState } from 'react'
import { mediaUrl } from '../api/client'

/** A large photo with clickable thumbnails. `images` are URLs as returned by the API ("/media/..."). */
export function ImageGallery({ images, title }) {
  const [selected, setSelected] = useState(0)
  if (images.length === 0) {
    return <div className="gallery-main gallery-empty">No photos</div>
  }
  const index = Math.min(selected, images.length - 1) // a photo may be removed while we're looking
  return (
    <div className="gallery">
      <div className="gallery-main">
        <img src={mediaUrl(images[index])} alt={`${title}, photo ${index + 1} of ${images.length}`} />
      </div>
      {images.length > 1 && (
        <div className="gallery-thumbs" role="group" aria-label="Photos">
          {images.map((src, i) => (
            <button
              key={src}
              type="button"
              className={`thumb-btn ${i === index ? 'thumb-btn-active' : ''}`}
              onClick={() => setSelected(i)}
              aria-label={`Show photo ${i + 1}`}
              aria-pressed={i === index}
            >
              <img src={mediaUrl(src)} alt="" loading="lazy" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
