import { useState } from 'react'
import { Icon } from './Icon'

/** A password input with a show/hide eye button. `children` render under the box (strength, match note...). */
export function PasswordField({ id, label, value, onChange, onBlur, autoComplete, error, hint, children }) {
  const [shown, setShown] = useState(false)
  return (
    <div className="form-field">
      <label htmlFor={id}>{label}</label>
      <div className="input-with-action">
        <input
          id={id}
          type={shown ? 'text' : 'password'}
          autoComplete={autoComplete}
          value={value}
          onChange={onChange}
          onBlur={onBlur}
          maxLength={128}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={`${id}-note`}
        />
        <button
          type="button"
          className="input-action"
          onClick={() => setShown((s) => !s)}
          aria-label={shown ? 'Hide password' : 'Show password'}
          aria-pressed={shown}
          title={shown ? 'Hide password' : 'Show password'}
        >
          <Icon name={shown ? 'eyeOff' : 'eye'} size={18} />
        </button>
      </div>
      <div id={`${id}-note`} className="field-notes">
        {hint && !error && <small className="muted">{hint}</small>}
        {error && <small className="field-error" role="alert">{error}</small>}
        {children}
      </div>
    </div>
  )
}
