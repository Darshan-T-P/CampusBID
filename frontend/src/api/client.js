// The single place the frontend talks to the backend.

const TOKEN_KEY = 'campusbid.token'

// Browser storage can be unavailable (private windows, blocked cookies), so never let it crash the app.
export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable: the session just won't survive a reload */
  }
}

export class ApiError extends Error {
  /**
   * @param {number} status HTTP status (0 = could not reach the server)
   * @param {string} message readable text for the user
   * @param {string} [code] machine-readable code from the backend, e.g. "too_low", "email_not_verified"
   * @param {unknown} [detail] the raw `detail` from the response, for extras like `min_bid`
   */
  constructor(status, message, code, detail) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.detail = detail
  }
}

let unauthorizedHandler = null

/** Called when the server rejects our token, so the app can sign the user out. */
export function onUnauthorized(handler) {
  unauthorizedHandler = handler
}

// --- the server's clock -------------------------------------------------------------------
// Countdowns must follow the SERVER's time (a student's laptop clock can be minutes off).
// Many responses carry `server_time`; each one tells us how far our clock is from the server's.
let serverOffsetMs = 0

export function updateServerClock(serverTimeIso) {
  const server = Date.parse(serverTimeIso)
  if (!Number.isNaN(server)) serverOffsetMs = server - Date.now()
}

/** Current time according to the server, in milliseconds since the epoch. */
export function serverNow() {
  return Date.now() + serverOffsetMs
}

// FastAPI reports errors in a few shapes: a string, a {code, message} object (our bid and
// verification errors), or a list of validation problems. Turn each into one readable sentence.
export function describe(detail) {
  if (typeof detail === 'string') return { message: detail }
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => {
      const field = Array.isArray(d.loc) ? String(d.loc[d.loc.length - 1]) : ''
      return field && field !== 'body' ? `${field}: ${d.msg}` : String(d.msg)
    })
    return { message: parts.join('. ') }
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return { message: detail.message, code: detail.code }
  }
  return { message: 'Something went wrong. Please try again.' }
}

/**
 * Call the backend. `body` is sent as JSON, `form` as multipart (photo uploads).
 * Resolves with the parsed JSON (undefined for 204) or rejects with an ApiError.
 */
export async function api(path, { method = 'GET', body, form, signal } = {}) {
  const token = getToken()
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'Cannot reach the server. Check your connection and try again.')
  }

  if (response.status === 204) return undefined

  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const { message, code } = describe(data?.detail)
    // A rejected token (not a failed login attempt) means the session is over.
    if (response.status === 401 && token) unauthorizedHandler?.()
    throw new ApiError(response.status, message, code, data?.detail)
  }
  if (data && typeof data.server_time === 'string') updateServerClock(data.server_time)
  return data
}

/** Photo URLs come back from the API as "/media/..."; route them through the same /api proxy. */
export function mediaUrl(path) {
  return `/api${path}`
}
