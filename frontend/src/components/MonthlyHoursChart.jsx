import { formatHours } from '../utils/format';

const SERIES = [
  {
    key: 'planned_baseline',
    className: 'ed-bar-vertical-planned',
    swatch: 'ed-swatch-planned',
    label: 'Planned Baseline',
  },
  {
    key: 'normal_consumption',
    className: 'ed-bar-vertical-normal',
    swatch: 'ed-swatch-normal',
    label: 'Normal Consumption',
  },
  {
    key: 'exceeded_threshold',
    className: 'ed-bar-vertical-exceeded',
    swatch: 'ed-swatch-exceeded',
    label: 'Exceeded Threshold',
  },
];
const Y_TICKS = 5;

/**
 * Grouped monthly bars: planned baseline vs normal vs over-threshold hours.
 * `months` is the `monthly_data` / `monthly_breakdown` array from the API.
 */
export function MonthlyHoursChart({ months = [], emptyMessage }) {
  const max = Math.max(
    1,
    ...months.flatMap((month) => SERIES.map((series) => Number(month[series.key]) || 0)),
  );

  return (
    <>
      {months.length > 0 ? (
        <div className="ed-chart ed-chart-vertical">
          <div className="ed-chart-vertical-wrapper">
            <div className="ed-chart-y-axis">
              {Array.from({ length: Y_TICKS }, (_, i) => (
                <span key={i} className="ed-chart-y-label">
                  {formatHours(Math.round(((max * (Y_TICKS - 1 - i)) / (Y_TICKS - 1)) * 10) / 10)}
                </span>
              ))}
            </div>
            <div className="ed-chart-plot-area">
              <div className="ed-chart-bars-grouped" role="img" aria-label="Monthly hours chart">
                {months.map((month, monthIndex) => (
                  <div
                    key={month.month}
                    className="ed-chart-month-group"
                    style={{ '--month-index': monthIndex }}
                  >
                    {SERIES.map((series) => (
                      <div key={series.key} className="ed-bar-vertical-wrapper">
                        <div
                          className={`ed-bar-vertical ${series.className}`}
                          style={{ height: `${((Number(month[series.key]) || 0) / max) * 100}%` }}
                          title={`${series.label}: ${formatHours(month[series.key])}`}
                        />
                      </div>
                    ))}
                    <div className="ed-chart-month-label">{month.month_label}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="timesheet-empty-cell ed-chart-empty">{emptyMessage}</div>
      )}
      <div className="ed-legend">
        {SERIES.map((series) => (
          <span key={series.key}>
            <i className={`ed-legend-swatch ${series.swatch}`} /> {series.label}
          </span>
        ))}
      </div>
    </>
  );
}
