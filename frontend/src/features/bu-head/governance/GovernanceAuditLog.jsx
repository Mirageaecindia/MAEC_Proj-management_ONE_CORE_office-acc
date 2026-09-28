import { formatDateTime, formatHours, formatPercent } from '../../../utils/format';

const ACTION_TEXT = {
  extension_request: (entry) => `Requested extension of ${formatHours(entry.requested_hours)}`,
  approve_extension: (entry) => `Approved extension of ${formatHours(entry.requested_hours)}`,
  reject_extension: (entry) => `Rejected extension of ${formatHours(entry.requested_hours)}`,
  stop_execution: () => 'Stopped execution',
  auto_lock: (entry) =>
    `Timesheets locked automatically at ${formatPercent(entry.consumption_pct)} of the baseline`,
  resume_execution: () => 'Resumed execution',
  hours_unapproved: () => 'Approved hours taken back',
  archive: () => 'Archived the project',
  unarchive: () => 'Reopened the project',
};

function describe(entry) {
  const action = ACTION_TEXT[entry.action]?.(entry) ?? entry.action;
  const comments = entry.comments ? ` — ${entry.comments}` : '';
  const author = entry.created_by ? ` by ${entry.created_by}` : '';
  return `${action}${comments}${author}`;
}

/** Recent governance actions, newest first. `actions` is undefined until a project loads. */
export function GovernanceAuditLog({ actions }) {
  return (
    <section className="allocation-card ed-audit-section">
      <div className="allocation-header">
        <div>
          <h2>Recent Governance Audit Log</h2>
          <p>Latest project governance actions and extension decisions.</p>
        </div>
      </div>
      {!actions && (
        <div className="timesheet-empty-cell">
          No project selected — governance audit logs are unavailable.
        </div>
      )}
      {actions?.length === 0 && (
        <div className="timesheet-empty-cell">No governance actions recorded yet.</div>
      )}
      {actions?.length > 0 && (
        <div className="ed-audit-list">
          {actions.map((entry) => (
            <div className="ed-audit-item" key={entry.id}>
              <span className="ed-audit-date">{formatDateTime(entry.created_at)}</span>
              <span className="ed-audit-separator">: </span>
              <span className="ed-audit-message">{describe(entry)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
