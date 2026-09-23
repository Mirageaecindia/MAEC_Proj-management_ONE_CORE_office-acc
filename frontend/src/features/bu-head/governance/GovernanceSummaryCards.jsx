import { ShieldCheck } from 'lucide-react';
import { StatCard } from '../../../components/StatCard';
import { NOT_AVAILABLE, formatDecimal, formatHours, formatMoney, formatPercent } from '../../../utils/format';

const NO_PROJECT = 'No project selected';

function GovernanceStatusCard({ governance }) {
  if (!governance) {
    return (
      <StatCard
        label="Governance Threshold Status"
        value={NOT_AVAILABLE}
        sub={NO_PROJECT}
        className="ed-card-ok"
      />
    );
  }
  const { status, threshold_pct: threshold, soft_locked: softLocked } = governance;
  const exceeded = status === 'exceeded';
  const softLock = softLocked && <span className="ed-softlock">Timesheets Soft-Locked for Approval</span>;

  if (threshold === null || threshold === undefined) {
    return (
      <StatCard
        label="Governance Threshold Status"
        value="NOT CONFIGURED"
        sub="No governance threshold is configured for this project."
        className="ed-card-ok"
      />
    );
  }
  if (exceeded) {
    const spike = governance.max_discipline_pct ?? governance.consumption_pct ?? 0;
    return (
      <StatCard
        label="Governance Threshold Status"
        value={`EXCEEDED (${formatPercent(spike)})`}
        sub={`Threshold: ${formatPercent(threshold)}`}
        className="ed-card-danger"
      >
        {softLock}
      </StatCard>
    );
  }
  return (
    <StatCard
      label="Governance Threshold Status"
      value={
        <>
          NORMAL <ShieldCheck size={18} className="ed-card-inline-icon" />
        </>
      }
      sub={`Consumption ${formatPercent(governance.consumption_pct)} at the ${formatPercent(threshold)} threshold`}
      className="ed-card-ok"
    >
      {softLock}
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
            ? `${formatHours(hours.approved)} approved / ${formatHours(hours.pending)} pending of ${formatHours(hours.scheduled)}`
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
