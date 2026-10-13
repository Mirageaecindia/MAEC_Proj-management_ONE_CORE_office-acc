/**
 * What shows instead of the app while MAEC One's answer is pending, or when it (or this
 * app) refuses the person: no seat on Project Management, no profile here yet, signed out
 * twice in a row, or MAEC One unreachable. Signing in itself happens at MAEC One.
 */
const TITLES = {
  checking: 'Checking your MAEC One sign-in…',
  no_access: 'No access',
  org_suspended: 'No access',
  bad_origin: 'Request refused',
  bad_app: 'Not set up',
  PROFILE_NOT_SET_UP: 'Your profile is not set up yet',
  PROFILE_INACTIVE: 'Your profile is deactivated',
  'signed-out': 'You are signed out',
  unavailable: 'Project Management is unavailable',
};

export function SignInStatus({ kind, message, maecOneUrl }) {
  return (
    <div className="login-page">
      <div className="login-card" role={kind === 'checking' ? 'status' : 'alert'}>
        <div className="login-logo">MAEC</div>
        <h1 className="sign-in-status-title">{TITLES[kind] || 'No access'}</h1>
        {message && <p className="sign-in-status-message">{message}</p>}
        {kind === 'unavailable' && (
          <button type="button" className="btn-primary" onClick={() => window.location.reload()}>
            Try again
          </button>
        )}
        {maecOneUrl && kind !== 'checking' && (
          <a className="btn-secondary sign-in-status-link" href={maecOneUrl}>
            Open MAEC One
          </a>
        )}
      </div>
    </div>
  );
}
