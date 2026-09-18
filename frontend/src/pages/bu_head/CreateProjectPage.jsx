import { AlertCircle, ArrowLeft, Check, ChevronDown, LoaderCircle, PlusCircle, Save, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../AuthContext';

const API_BASE_URL = 'http://localhost:8000';

const disciplines = [
  { value: 'HVAC Discipline', label: '01_HVAC Discipline' },
  { value: 'Electrical Discipline', label: '02_Electrical Discipline' },
  { value: 'Plumbing', label: '03_Plumbing' },
  { value: 'Firefighting', label: '04_Firefighting' },
  { value: 'BIM Models', label: '05_BIM_Models' },
];

const currencies = [
  { code: 'USD', symbol: '$' },
  { code: 'INR', symbol: '₹' },
  { code: 'EUR', symbol: '€' },
  { code: 'GBP', symbol: '£' },
  { code: 'AED', symbol: 'د.إ' },
  { code: 'AUD', symbol: 'A$' },
  { code: 'CAD', symbol: 'C$' },
  { code: 'SGD', symbol: 'S$' },
];

const initialForm = {
  projectName: '',
  projectCode: '',
  clientCustomer: '',
  electricalLead: '',
  targetStartDate: '',
  mechanicalLead: '',
  bimLead: '',
  contractCurrency: 'USD',
  contractValue: '',
  effortHours: '',
  threshold: 80,
  selectedDisciplines: disciplines.map((discipline) => discipline.value),
};

function currencySymbol(currency) {
  return currencies.find((item) => item.code === currency)?.symbol || '$';
}

/**
 * Format a raw numeric value/string (e.g. "480000" or "8") into a formatted
 * display string with thousands separators and 2 decimal places (e.g. "480,000.00").
 * Only used for DISPLAY when the input is NOT focused.
 */
function formatCurrencyNumber(rawValue) {
  if (rawValue === '' || rawValue === null || rawValue === undefined) return '';
  const num = Number(String(rawValue).replace(/[^0-9.]/g, ''));
  if (isNaN(num)) return '';
  return num.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Strip everything except digits and decimal point — used for validation/submit. */
function rawToNumber(rawValue) {
  return Number(String(rawValue).replace(/[^0-9.]/g, ''));
}

function SectionTitle({ number, children }) {
  return (
    <div className="section-heading">
      <h2><span>{number}.</span> {children}</h2>
    </div>
  );
}

function Field({ label, required = false, children, className = '' }) {
  return (
    <label className={`field ${className}`}>
      <span className="field-label">{label}{required && <b aria-hidden="true"> *</b>}</span>
      {children}
    </label>
  );
}

export function CreateProjectPage() {
  const navigate = useNavigate();
  const { authHeaders } = useAuth();
  const [form, setForm] = useState(initialForm);
  const [leads, setLeads] = useState({ electrical: [], mechanical: [], bim: [] });
  const [leadError, setLeadError] = useState('');
  const [errors, setErrors] = useState({});
  const [submitState, setSubmitState] = useState('idle');
  const [notice, setNotice] = useState(null);
  // Tracks whether the contract value input is focused (raw digits) or blurred (formatted display).
  const [contractValueFocused, setContractValueFocused] = useState(false);

  useEffect(() => {
    let isMounted = true;
    Promise.all(['electrical', 'mechanical', 'bim'].map(async (discipline) => {
      const response = await fetch(`${API_BASE_URL}/api/project-leads?discipline=${discipline}`, {
        headers: authHeaders(),
      });
      if (!response.ok) throw new Error(`Could not load ${discipline} leads.`);
      return [discipline, await response.json()];
    }))
      .then((results) => {
        if (isMounted) setLeads(Object.fromEntries(results));
      })
      .catch((error) => {
        if (isMounted) setLeadError(error.message);
      });
    return () => { isMounted = false; };
  }, []);

  const selectedCount = form.selectedDisciplines.length;
  const thresholdPosition = useMemo(() => `${form.threshold}%`, [form.threshold]);

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: '' }));
    setNotice(null);
  }

  function toggleDiscipline(value) {
    const selected = form.selectedDisciplines.includes(value)
      ? form.selectedDisciplines.filter((item) => item !== value)
      : [...form.selectedDisciplines, value];
    updateField('selectedDisciplines', selected);
  }

  function changeCurrency(currency) {
    setForm((current) => ({
      ...current,
      contractCurrency: currency,
      // contractValue stays as the raw numeric string — only the symbol/display changes
    }));
    setErrors((current) => ({ ...current, contractCurrency: '', contractValue: '' }));
    setNotice(null);
  }

  function validate() {
    const nextErrors = {};
    const requiredFields = [
      ['projectName', 'Project name is required.'],
      ['projectCode', 'Project code is required.'],
      ['clientCustomer', 'Client / Customer is required.'],
      ['electricalLead', 'Electrical project lead is required.'],
      ['targetStartDate', 'Target start date is required.'],
      ['mechanicalLead', 'Mechanical project lead is required.'],
      ['bimLead', 'BIM project lead is required.'],
    ];
    requiredFields.forEach(([field, message]) => {
      if (!String(form[field]).trim()) nextErrors[field] = message;
    });
    if (!Number.isFinite(rawToNumber(form.contractValue)) || rawToNumber(form.contractValue) <= 0) {
      nextErrors.contractValue = 'Enter a contract value greater than 0.';
    }
    if (!currencies.some((currency) => currency.code === form.contractCurrency)) {
      nextErrors.contractCurrency = 'Select a supported currency.';
    }
    if (!Number.isFinite(Number(form.effortHours.replace(/,/g, ''))) || Number(form.effortHours.replace(/,/g, '')) <= 0) {
      nextErrors.effortHours = 'Enter effort hours greater than 0.';
    }
    if (selectedCount === 0) nextErrors.selectedDisciplines = 'Select at least one discipline.';
    if (form.threshold < 0 || form.threshold > 100) nextErrors.threshold = 'Threshold must be between 0 and 100.';
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setNotice(null);
    if (!validate()) return;
    setSubmitState('submitting');
    const payload = {
      project_name: form.projectName.trim(),
      project_code: form.projectCode.trim(),
      client_customer: form.clientCustomer.trim(),
      project_lead_electrical: form.electricalLead,
      project_lead_mechanical: form.mechanicalLead.trim(),
      project_lead_bim: form.bimLead.trim(),
      target_start_date: form.targetStartDate,
      sharepoint_disciplines: form.selectedDisciplines,
      total_contract_value: rawToNumber(form.contractValue),
      contract_currency: form.contractCurrency,
      target_effort_hours: Number(form.effortHours.replace(/,/g, '')),
      alert_override_threshold_pct: Number(form.threshold),
    };
    try {
      const response = await fetch(`${API_BASE_URL}/api/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || 'Project could not be created.');

      let message = `Project created.`;
      let noticeType = 'success';
      if (body.sharepoint_status === 'provisioned') {
        message += ` SharePoint directory created successfully.`;
      } else if (body.sharepoint_status === 'failed') {
        message += ` SharePoint provisioning failed: ${body.sharepoint_error || 'Unknown error'}`;
        noticeType = 'error';
      } else if (body.sharepoint_status === 'error') {
        message += ` SharePoint error: ${body.sharepoint_error || 'Unexpected error'}`;
        noticeType = 'error';
      } else if (body.sharepoint_status === 'not_requested') {
        message += ` SharePoint directory not requested (no disciplines selected).`;
      } else {
        message += ` SharePoint status: ${body.sharepoint_status}.`;
      }

      setNotice({ type: noticeType, message, url: body.sharepoint_site_url });
      setForm(initialForm);
      setErrors({});
      if (body?.id) {
        navigate('/created-projects');
      }
    } catch (error) {
      setNotice({ type: 'error', message: error.message });
    } finally {
      setSubmitState('idle');
    }
  }

  function handleReset() {
    setForm(initialForm);
    setErrors({});
    setNotice(null);
    setSubmitState('idle');
  }

  return (
    <main className="page-shell">
      <div className="resource-heading-row">
        <div>
          <div className="breadcrumb"><span>Projects</span><i>/</i><span>Commercial Setup</span><i>/</i><strong>New Entry</strong></div>
          <h1>Create Project &amp; Commercial Baseline</h1>
          <p>Define project parameters, commercial limits, and trigger automated SharePoint folder provisioning.</p>
        </div>
        <button type="button" className="button button-secondary" onClick={() => navigate('/created-projects')}>
          <ArrowLeft size={16} /> Back to Created Projects
        </button>
      </div>

      {notice && (
        <div className={`notice ${notice.type}`} role="status">
          {notice.type === 'success' ? <Check size={18} /> : <AlertCircle size={18} />}
          <div><strong>{notice.message}</strong>{notice.url && <a href={notice.url} target="_blank" rel="noreferrer">{notice.url}</a>}</div>
          <button type="button" onClick={() => setNotice(null)} aria-label="Dismiss notification"><X size={17} /></button>
        </div>
      )}

      <form className="project-card" onSubmit={handleSubmit} noValidate>
        <div className="form-column left-column">
          <section>
            <SectionTitle number="1">Project &amp; Commercial Identification</SectionTitle>
            <div className="field-grid one-column">
              <Field label="Project Name" required>
                <input value={form.projectName} onChange={(event) => updateField('projectName', event.target.value)} placeholder="Enter project name" />
                {errors.projectName && <span className="field-error">{errors.projectName}</span>}
              </Field>
            </div>
            <div className="field-grid two-column">
              <Field label="Project Code" required>
                <input value={form.projectCode} onChange={(event) => updateField('projectCode', event.target.value)} placeholder="e.g. MAEC-2026-001" />
                {errors.projectCode && <span className="field-error">{errors.projectCode}</span>}
              </Field>
              <Field label="Client / Customer" required>
                <input value={form.clientCustomer} onChange={(event) => updateField('clientCustomer', event.target.value)} placeholder="Enter client or customer" />
                {errors.clientCustomer && <span className="field-error">{errors.clientCustomer}</span>}
              </Field>
            </div>
            <div className="field-grid two-column">
              <Field label="Assigned Project Lead | Electrical" required>
                <div className="select-wrap">
                  <select value={form.electricalLead} onChange={(event) => updateField('electricalLead', event.target.value)}>
                    <option value="">Select electrical lead</option>
                    {leads.electrical.map((lead) => <option key={lead.id} value={lead.name}>{lead.name}</option>)}
                  </select><ChevronDown size={16} />
                </div>
                {leadError && <span className="field-error">{leadError}</span>}
                {errors.electricalLead && <span className="field-error">{errors.electricalLead}</span>}
              </Field>
              <Field label="Target Start Date" required>
                <input type="date" value={form.targetStartDate} onChange={(event) => updateField('targetStartDate', event.target.value)} />
                {errors.targetStartDate && <span className="field-error">{errors.targetStartDate}</span>}
              </Field>
            </div>
            <div className="field-grid two-column">
              <Field label="Assigned Project Lead | Mechanical" required>
                <div className="select-wrap">
                  <select value={form.mechanicalLead} onChange={(event) => updateField('mechanicalLead', event.target.value)}>
                    <option value="">Select mechanical lead</option>
                    {leads.mechanical.map((lead) => <option key={lead.id} value={lead.name}>{lead.name}</option>)}
                  </select><ChevronDown size={16} />
                </div>
                {errors.mechanicalLead && <span className="field-error">{errors.mechanicalLead}</span>}
              </Field>
              <Field label="Assigned Project Lead | BIM" required>
                <div className="select-wrap">
                  <select value={form.bimLead} onChange={(event) => updateField('bimLead', event.target.value)}>
                    <option value="">Select BIM lead</option>
                    {leads.bim.map((lead) => <option key={lead.id} value={lead.name}>{lead.name}</option>)}
                  </select><ChevronDown size={16} />
                </div>
                {errors.bimLead && <span className="field-error">{errors.bimLead}</span>}
              </Field>
            </div>
          </section>

          <section className="discipline-section">
            <SectionTitle number="2">Automated SharePoint Directory Setup</SectionTitle>
            <p className="section-copy">Select MEP engineering disciplines to auto-create inside SharePoint site:</p>
            <div className="discipline-grid">
              {disciplines.map((discipline) => (
                <label className={`discipline-option ${form.selectedDisciplines.includes(discipline.value) ? 'checked' : ''}`} key={discipline.value}>
                  <input type="checkbox" checked={form.selectedDisciplines.includes(discipline.value)} onChange={() => toggleDiscipline(discipline.value)} />
                  <span className="checkmark"><Check size={13} /></span>
                  <span>{discipline.label}</span>
                </label>
              ))}
            </div>
            {errors.selectedDisciplines && <span className="field-error">{errors.selectedDisciplines}</span>}
          </section>
        </div>

        <div className="form-column right-column">
          <section>
            <SectionTitle number="3">Commercial Controls &amp; Budget Baselines</SectionTitle>
            <Field label="Total Commercial Contract Value" required>
              <div className="currency-input-row">
                <div className="select-wrap currency-select-wrap">
                  <select value={form.contractCurrency} onChange={(event) => changeCurrency(event.target.value)} aria-label="Contract currency">
                    {currencies.map((currency) => <option key={currency.code} value={currency.code}>{currency.code} ({currency.symbol})</option>)}
                  </select><ChevronDown size={16} />
                </div>
                <div className="currency-amount-wrap">
                  <span className="currency-prefix">{currencySymbol(form.contractCurrency)}</span>
                  <input
                    className="currency-amount"
                    inputMode="decimal"
                    value={contractValueFocused ? form.contractValue : formatCurrencyNumber(form.contractValue)}
                    onChange={(event) => {
                      // Strip everything except digits and a single decimal point
                      const raw = event.target.value.replace(/[^0-9.]/g, '');
                      // Prevent multiple decimal points
                      const parts = raw.split('.');
                      const sanitized = parts.length > 2 ? parts[0] + '.' + parts.slice(1).join('') : raw;
                      updateField('contractValue', sanitized);
                    }}
                    onFocus={() => setContractValueFocused(true)}
                    onBlur={() => setContractValueFocused(false)}
                    placeholder="480,000.00"
                  />
                </div>
              </div>
              {errors.contractCurrency && <span className="field-error">{errors.contractCurrency}</span>}
              {errors.contractValue && <span className="field-error">{errors.contractValue}</span>}
            </Field>
            <Field label="Target Effort Hours Baseline (Hrs)" required>
              <div className="input-with-suffix"><input inputMode="numeric" value={form.effortHours} onChange={(event) => updateField('effortHours', event.target.value.replace(/[^0-9,]/g, ''))} placeholder="3,840" /><span>Hours</span></div>
              {errors.effortHours && <span className="field-error">{errors.effortHours}</span>}
            </Field>

            <div className="governance-box">
              <h3>Governance Threshold &amp; Exception Trigger</h3>
              <p>When logged hours exceed this percentage threshold of baseline hours, timesheets block further logging until Business Unit Head approval.</p>
              <div className="threshold-label"><span>Alert &amp; Override Threshold Limit:</span><strong>{form.threshold} %</strong></div>
              <input className="range-input" type="range" min="0" max="100" value={form.threshold} style={{ '--range-position': thresholdPosition }} onChange={(event) => updateField('threshold', Number(event.target.value))} aria-label="Alert and override threshold limit" />
              <div className="range-labels"><span>0% (Start)</span><strong>80% (Warning)</strong><span>100% (Hard Stop)</span></div>
            </div>
          </section>

          <div className="action-row">
            <button type="button" className="button button-secondary" onClick={handleReset}><X size={16} /> Cancel</button>
            <button type="submit" className="button button-primary" disabled={submitState === 'submitting'}>
              {submitState === 'submitting' ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />}
              {submitState === 'submitting' ? 'Creating Project...' : 'Create Project & Build SharePoint Directory'}
            </button>
          </div>
        </div>
      </form>
    </main>
  );
}
