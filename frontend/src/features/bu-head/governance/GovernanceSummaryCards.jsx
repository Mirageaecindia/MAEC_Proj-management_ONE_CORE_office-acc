import { ShieldCheck } from 'lucide-react';
import { StatCard } from '../../../components/StatCard';
import { NOT_AVAILABLE, formatDecimal, formatHours, formatMoney, formatPercent } from '../../../utils/format';

const NO_PROJECT = 'No project selected';

const LEVEL_CARDS = {
  normal: { value: 'NORMAL', className: 'ed-card-ok' },
  warning: { value: 'ALERT', className: 'ed-card-warning' },
  hard_stop: { value: 'BASELINE REACHED', className: 'ed-card-danger' },
};

function GovernanceStatusCard({ governance }) {
  const label = 'Governance Threshold Status';
  if (!governance) {
    return <StatCard label={label} value={NOT_AVAILABLE} sub={NO_PROJECT} className="ed-card-ok" />;
  }
  if (!governance.configured) {
    return (
      <StatCard
        label={label}
        value="NOT CONFIGURED"
        sub="Set target effort hours to enable governance."
        className="ed-card-ok"
      />
    );
  }
  const { value, className } = LEVEL_CARDS[governance.level] ?? LEVEL_CARDS.normal;
  const threshold =
    governance.threshold_pct == null
      ? 'no alert threshold'
      : `alert at ${formatPercent(governance.threshold_pct)}`;
  const lockText =
    governance.lock_reason === 'auto' ? 'Timesheets Locked Automatically' : 'Timesheets Soft-Locked';
  return (
    <StatCard
      label={label}
      value={
        <>
          {value} ({formatPercent(governance.consumption_pct)})
          {governance.level === 'normal' && <ShieldCheck size={18} className="ed-card-inline-icon" />}
        </>
      }
      sub={`Of the baseline; ${threshold}, lock at 100%`}
      className={className}
    >
      {governance.soft_locked && <span className="ed-softlock">{lockText}</span>}
    </StatCard>
  );
}

/** The four headline KPIs of the Executive Dashboard. `data` is null until a project loads. */
export function GovernanceSummaryCards({ data }) {
  const currency = data?.project?.contract_currency || 'USD';
  const budget = data?.commercial_budget_burn;
  const hours = data?.hours_consumption;
  const spi = data?.spi;

  return (
    <section className="ed-summary-cards">
      <StatCard
        label="Commercial Budget Burn"
        value={budget ? formatMoney(budget.consumed, currency) : NOT_AVAILABLE}
        sub={budget ? `of ${formatMoney(budget.total, currency)} contract value` : NO_PROJECT}
        progress={{ tone: 'blue', percent: budget?.percent }}
        foot={budget ? formatPercent(budget.percent) : 'No project data'}
      />
      <StatCard
        label="Total Hours Consumption"
        value={hours ? formatHours(hours.hours) : NOT_AVAILABLE}
        sub={hours ? `(${formatPercent(hours.percent)})` : NO_PROJECT}
        progress={{ tone: 'orange', percent: hours?.percent }}
        foot={
          hours
            ? `${formatHours(hours.approved)} approved / ${formatHours(hours.pending)} pending of ${formatHours(hours.scheduled)} baseline (WBS ${formatHours(hours.wbs_planned)})`
            : 'No project data'
        }
      />
      <GovernanceStatusCard governance={data?.governance_status} />
      <StatCard
        label="Schedule Index (SPI)"
        value={spi ? formatDecimal(spi.value, 2) : NOT_AVAILABLE}
        valueClassName="ed-spi-value"
        sub={spi ? spi.note : NO_PROJECT}
        subClassName="ed-spi-note"
        progress={{ tone: 'green', percent: spi?.value != null ? spi.value * 100 : 0 }}
      />
    </section>
  );
}
