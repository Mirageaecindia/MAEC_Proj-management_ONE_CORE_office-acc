import { Link } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { useTrackingState } from '../hooks/useTracking';
import { parseApiTimestamp } from '../utils/displayTime';
import { formatDuration } from '../utils/hours';

const clock = (value) =>
  parseApiTimestamp(value)?.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

/**
 * Under the header on every page, for engineers: which subtask is being tracked and since
 * when, the "over 8 hours" rule once it applies, or that the system logged them out.
 * For engineers the line is always there, empty when there is nothing to say, so the page
 * never moves when they log in or out of a subtask.
 */
function TrackingMessage() {
  const { role } = useAuth();
  const { data } = useTrackingState({ enabled: role === 'engineer' });
  const session = data?.active_session;
  const logout = data?.system_logout;

  if (session) {
    return (
      <div className={`tracking-bar${data.over_mark ? ' is-over-mark' : ''}`} role="status">
        <span className="tracking-dot" aria-hidden="true" />
        <span>
          <strong>Tracking:</strong>{' '}
          <Link to={`/task-details?nodeId=${session.subtask_id}&projectId=${session.project_id}`}>
            {session.subtask_name || 'a subtask'}
          </Link>{' '}
          since {clock(session.login_at)}
          {data.over_mark && (
            <>
              . <strong>Over 8 hours today:</strong> every hour still counts, but visit this app at least
              every 30 minutes (a click here is enough) or you are logged out at your last visit
            </>
          )}
          .
        </span>
      </div>
    );
  }
  if (logout) {
    return (
      <div className="tracking-bar is-logout" role="status">
        <span>
          <strong>You were logged out at {clock(logout.at)}</strong>, your last visit, after 30 minutes away
          past the 8-hour mark. Today&apos;s time so far is {formatDuration(logout.day_hours)} and it is
          saved.{' '}
          <Link to={`/task-details?nodeId=${logout.subtask_id}&projectId=${logout.project_id}`}>
            Log in again
          </Link>{' '}
          if you are still working.
        </span>
      </div>
    );
  }
  return null;
}

export function TrackingBar() {
  const { role } = useAuth();
  if (role !== 'engineer') return null;
  return (
    <div className="tracking-slot">
      <TrackingMessage />
    </div>
  );
}
