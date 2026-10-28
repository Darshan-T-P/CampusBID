import { Link } from 'react-router-dom'

export function NotFound() {
  return (
    <section className="center">
      <h1>Page not found</h1>
      <p className="muted">
        <Link to="/">Back to browsing</Link>
      </p>
    </section>
  )
}
