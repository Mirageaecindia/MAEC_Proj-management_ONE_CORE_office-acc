import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';

const MIN_LENGTH = 8;

/**
 * Set a new password. `forced`: the account still has a temporary password (onboarding or a
 * reset by the BU Head), so this is the only screen until it is replaced. Otherwise it is the
 * "Change password" item of the account menu.
 */
export function ChangePasswordPage({ forced = false }) {
  const { user, changePassword, logout } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const mismatch = repeat.length > 0 && next !== repeat;
  const tooShort = next.length > 0 && next.length < MIN_LENGTH;
  const ready = current && next.length >= MIN_LENGTH && next === repeat && !submitting;

  async function handleSubmit(event) {
    event.preventDefault();
    if (!ready) return;
    setError(null);
    setSubmitting(true);
    try {
      await changePassword(current, next);
      if (forced) navigate('/', { replace: true });
      else setDone(true);
    } catch (err) {
      setError(err.message || 'Could not change the password.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={forced ? 'login-page' : 'change-password-shell'}>
      <div className="login-card">
        {forced && <div className="login-logo">MAEC</div>}
        <h1 className="login-title">{forced ? 'Set your own password' : 'Change password'}</h1>
        {forced && (
          <p className="change-password-intro">
            Welcome{user?.full_name ? `, ${user.full_name}` : ''}. You signed in with a temporary password.
            Choose your own to continue; nobody else will know it.
          </p>
        )}
        {done ? (
          <p className="change-password-done" role="status">
            Your password is changed. Other browsers where you were signed in have been signed out.
          </p>
        ) : (
          <form className="login-form" onSubmit={handleSubmit}>
            <label className="field">
              <span className="field-label">{forced ? 'Temporary password' : 'Current password'}</span>
              <input
                type="password"
                value={current}
                aria-label={forced ? 'Temporary password' : 'Current password'}
                onChange={(event) => setCurrent(event.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <label className="field">
              <span className="field-label">New password</span>
              <input
                type="password"
                value={next}
                aria-label="New password"
                onChange={(event) => setNext(event.target.value)}
                autoComplete="new-password"
                required
              />
              <small className={tooShort ? 'field-hint is-error' : 'field-hint'}>
                At least {MIN_LENGTH} characters.
              </small>
            </label>
            <label className="field">
              <span className="field-label">Repeat the new password</span>
              <input
                type="password"
                value={repeat}
                aria-label="Repeat the new password"
                onChange={(event) => setRepeat(event.target.value)}
                autoComplete="new-password"
                required
              />
              {mismatch && <small className="field-hint is-error">The two passwords are not the same.</small>}
            </label>
            {error && <div className="login-error">{error}</div>}
            <button className="button button-primary login-submit" type="submit" disabled={!ready}>
              {submitting ? 'Saving…' : 'Save password'}
            </button>
            {forced && (
              <button className="button button-secondary login-submit" type="button" onClick={logout}>
                Sign out
              </button>
            )}
          </form>
        )}
      </div>
    </div>
  );
}
