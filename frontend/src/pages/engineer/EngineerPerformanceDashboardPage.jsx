import { ChevronDown, ChevronUp, ShieldCheck } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../AuthContext';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function formatHours(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '0.0 Hrs';
  return `${Number(value).toFixed(1)} Hrs`;
}

function formatPercent(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '0.0%';
  return `${Number(value).toFixed(1)}%`;
}

function formatValue(value, digits = 2) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'N/A';
  return Number(value).toFixed(digits);
}

export function EngineerPerformanceDashboardPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { authHeaders, user } = useAuth();
  const targetProjectId = searchParams.get('projectId') ? Number(searchParams.get('projectId')) : null;

  const [projects, setProjects] = useState([]);
  const [projectIndex, setProjectIndex] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  const safeProjectIndex = Math.min(projectIndex, Math.max(0, projects.length - 1));
  const project = projects[safeProjectIndex];
  const projectId = project?.id;

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/projects`, { headers: authHeaders() })
      .then((response) => {
        if (!response.ok) throw new Error(`Failed to load projects (${response.status})`);
        return response.json();
      })
      .then((list) => {
        setProjects(list);
        const index = targetProjectId ? list.findIndex((item) => item.id === targetProjectId) : -1;
        setProjectIndex(index >= 0 ? index : 0);
      })
      .catch((loadError) => setError(loadError.message));
  }, [authHeaders, targetProjectId]);

  const fetchDashboard = useCallback(async () => {
    if (!projectId) {
      setData(null);
      return;
    }
    setError('');
    setData(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/engineer-performance-dashboard`, {
        headers: authHeaders(),
      });
      if (!response.ok) throw new Error(`Failed to load dashboard (${response.status})`);
      setData(await response.json());
    } catch (loadError) {
      setError(loadError.message);
    }
  }, [projectId, authHeaders]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  const summary = data?.summary;
  const monthlyBreakdown = data?.monthly_breakdown || [];
  const hasData = Boolean(data);

  const maxChartValue = useMemo(() => {
    if (!monthlyBreakdown.length) return 1;
    return Math.max(
      1,
      ...monthlyBreakdown.map((month) =>
        Math.max(
          Number(month.planned_baseline) || 0,
          Number(month.normal_consumption) || 0,
          Number(month.exceeded_threshold) || 0
        )
      ),
    );
  }, [monthlyBreakdown]);

  const isExceeded = summary?.governance_exceeded;
  const threshold = summary?.governance_threshold_pct;

  return (
    <main className="timeline-page">
      <div className="resource-heading-row">
        <div>
          <div className="breadcrumb">
            <span>My Workspace</span>
            <i>/</i>
            <strong>Engineer Performance Dashboard</strong>
          </div>
          <h1>Engineer Performance Dashboard</h1>
          <p>
            Track your hours consumption, governance threshold status, schedule performance index, and monthly breakdown across assigned projects.
          </p>
        </div>

        {projects.length > 0 && (
          <div className="project-switcher">
            <span>Project Name</span>
            <div className="project-pill-box">
              <span className="project-pill-name" title={project?.project_name}>
                {project?.project_name || 'No projects available'}
              </span>
              <div className="project-stepper-arrows">
                <button
                  type="button"
                  aria-label="Previous project"
                  disabled={safeProjectIndex === 0}
                  onClick={() => setProjectIndex((index) => index - 1)}
                >
                  <ChevronUp size={12} />
                </button>
                <button
                  type="button"
                  aria-label="Next project"
                  disabled={safeProjectIndex >= projects.length - 1}
                  onClick={() => setProjectIndex((index) => index + 1)}
                >
                  <ChevronDown size={12} />
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {error && <div className="resource-error">{error}</div>}

      <section className="ed-summary-cards">
        <div className="ed-card">
          <span className="ed-card-label">Total Hours Consumption</span>
          <strong className="ed-card-value">{hasData ? formatHours(summary.total_hours_consumption) : 'Not available'}</strong>
          <span className="ed-card-sub">{hasData ? `(${formatPercent(summary.consumption_pct)})` : 'No project selected'}</span>
          <div className="ed-progress ed-progress-orange">
            <span style={{ width: hasData ? `${Math.min(100, summary.consumption_pct)}%` : '0%' }} />
          </div>
          <span className="ed-card-foot">
            {hasData
              ? `${formatHours(summary.total_hours_approved)} approved / ${formatHours(summary.total_hours_pending)} pending of ${formatHours(summary.total_hours_scheduled)}`
              : 'No project data'}
          </span>
        </div>

        <div className={`ed-card ${isExceeded ? 'ed-card-danger' : 'ed-card-ok'}`}>
          <span className="ed-card-label">Governance Threshold Status</span>
          {hasData && threshold === null ? (
            <>
              <strong className="ed-card-value">NOT CONFIGURED</strong>
              <span className="ed-card-sub">No governance threshold is configured for your assigned projects.</span>
            </>
          ) : hasData && isExceeded ? (
            <>
              <strong className="ed-card-value">EXCEEDED ({formatPercent(summary.consumption_pct)})</strong>
              <span className="ed-card-sub">Threshold: {formatPercent(threshold)}</span>
            </>
          ) : hasData ? (
            <>
              <strong className="ed-card-value">
                NORMAL <ShieldCheck size={18} className="ed-card-inline-icon" />
              </strong>
              <span className="ed-card-sub">
                Consumption {formatPercent(summary.consumption_pct)} at the {formatPercent(threshold)} threshold
              </span>
            </>
          ) : (
            <>
              <strong className="ed-card-value">Not available</strong>
              <span className="ed-card-sub">No project selected</span>
            </>
          )}
        </div>

        <div className="ed-card">
          <span className="ed-card-label">Schedule Index (SPI)</span>
          <strong className="ed-card-value ed-spi-value">{hasData ? formatValue(summary.spi_value, 2) : 'Not available'}</strong>
          <span className="ed-card-sub ed-spi-note">{hasData ? summary.spi_note : 'No project selected'}</span>
          <div className="ed-progress ed-progress-green">
            <span style={{ width: hasData && summary.spi_value !== null ? `${Math.min(100, summary.spi_value * 100)}%` : '0%' }} />
          </div>
        </div>
      </section>

      <section className="allocation-card ed-chart-panel">
        <div className="allocation-header">
          <div>
            <h2>Hours Burndown & Budget Consumption by Discipline</h2>
            <p>Planned baseline vs logged consumption per month from real approved time entries.</p>
          </div>
        </div>

        {hasData && monthlyBreakdown.length > 0 ? (
          <div className="ed-chart ed-chart-vertical">
            <div className="ed-chart-vertical-wrapper">
              <div className="ed-chart-y-axis">
                {Array.from({ length: 5 }, (_, i) => {
                  const value = Math.round((maxChartValue * (4 - i)) / 4 * 10) / 10;
                  return <span key={i} className="ed-chart-y-label">{formatHours(value)}</span>;
                })}
              </div>
              <div className="ed-chart-plot-area">
                <div className="ed-chart-bars-grouped" role="img" aria-label="Monthly hours burndown chart">
                  {monthlyBreakdown.map((month, monthIndex) => (
                    <div key={month.month} className="ed-chart-month-group" style={{ '--month-index': monthIndex }}>
                      <div className="ed-bar-vertical-wrapper">
                        <div
                          className="ed-bar-vertical ed-bar-vertical-planned"
                          style={{ height: maxChartValue > 0 ? `${(month.planned_baseline / maxChartValue) * 100}%` : '0%' }}
                          title={`Planned Baseline: ${formatHours(month.planned_baseline)}`}
                        />
                      </div>
                      <div className="ed-bar-vertical-wrapper">
                        <div
                          className="ed-bar-vertical ed-bar-vertical-normal"
                          style={{ height: maxChartValue > 0 ? `${(month.normal_consumption / maxChartValue) * 100}%` : '0%' }}
                          title={`Normal Consumption: ${formatHours(month.normal_consumption)}`}
                        />
                      </div>
                      <div className="ed-bar-vertical-wrapper">
                        <div
                          className="ed-bar-vertical ed-bar-vertical-exceeded"
                          style={{ height: maxChartValue > 0 ? `${(month.exceeded_threshold / maxChartValue) * 100}%` : '0%' }}
                          title={`Exceeded Threshold: ${formatHours(month.exceeded_threshold)}`}
                        />
                      </div>
                      <div className="ed-chart-month-label">{month.month_label}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="timesheet-empty-cell ed-chart-empty">
            {hasData ? 'No monthly activity on this project yet.' : 'No project selected — assign to projects and log hours to populate the burndown chart.'}
          </div>
        )}

        <div className="ed-legend">
          <span><i className="ed-legend-swatch ed-swatch-planned" /> Planned Baseline</span>
          <span><i className="ed-legend-swatch ed-swatch-normal" /> Normal Consumption</span>
          <span><i className="ed-legend-swatch ed-swatch-exceeded" /> Exceeded Threshold</span>
        </div>
      </section>

      <div className="ed-next-row">
        <button
          type="button"
          className="button button-primary button-next"
          onClick={() => navigate('/wbs-structure')}
        >
          BACK TO WBS STRUCTURE
        </button>
      </div>
    </main>
  );
}