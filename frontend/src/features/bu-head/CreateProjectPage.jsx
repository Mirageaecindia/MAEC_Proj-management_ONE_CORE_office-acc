import { ArrowLeft, Check, ChevronDown, LoaderCircle, Save, X } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Notice } from '../../components/Feedback';
import { PageHeader } from '../../components/PageHeader';
import { CURRENCIES, currencySymbol } from '../../constants/currencies';
import { SHAREPOINT_DISCIPLINES } from '../../constants/sharepoint';
import { useCreateProject, useProjectLeads } from '../../hooks/useProjects';
import { formatAmount } from '../../utils/format';
import { creationNotice, toCreateProjectPayload } from './createProjectForm';
import { useCreateProjectForm } from './useCreateProjectForm';

function SectionTitle({ number, children }) {
  return (
    <div className="section-heading">
      <h2>
        <span>{number}.</span> {children}
      </h2>
    </div>
  );
}

function Field({ label, required = false, error, children }) {
  return (
    <label className="field">
      <span className="field-label">
        {label}
        {required && <b aria-hidden="true"> *</b>}
      </span>
      {children}
      {error && <span className="field-error">{error}</span>}
    </label>
  );
}

function LeadSelect({ label, placeholder, leads, value, error, extraError, onChange }) {
  return (
    <Field label={label} required error={error}>
      <div className="select-wrap">
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          <option value="">{placeholder}</option>
          {leads.map((lead) => (
            <option key={lead.id} value={lead.id}>
              {lead.name}
            </option>
          ))}
        </select>
        <ChevronDown size={16} />
      </div>
      {extraError && <span className="field-error">{extraError}</span>}
    </Field>
  );
}

/** Amount input: raw digits while editing, "480,000.00" when not focused. */
function AmountInput({ value, onChange }) {
  const [focused, setFocused] = useState(false);

  function handleChange(event) {
    const raw = event.target.value.replace(/[^0-9.]/g, '');
    const [whole, ...decimals] = raw.split('.');
    onChange(decimals.length > 1 ? `${whole}.${decimals.join('')}` : raw);
  }

  return (
    <input
      className="currency-amount"
      inputMode="decimal"
      value={focused ? value : formatAmount(value, { fallback: '' })}
      onChange={handleChange}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      placeholder="480,000.00"
    />
  );
}

export function CreateProjectPage() {
  const navigate = useNavigate();
  const { leads, error: leadsError } = useProjectLeads();
  const createProject = useCreateProject();
  const { form, errors, updateField, toggleDiscipline, changeCurrency, validate, reset } =
    useCreateProjectForm();

  function handleSubmit(event) {
    event.preventDefault();
    createProject.reset();
    if (!validate()) return;
    createProject.mutate(toCreateProjectPayload(form, leads), {
      // The outcome (including SharePoint) is shown on the project list.
      onSuccess: (project) => navigate('/created-projects', { state: { notice: creationNotice(project) } }),
    });
  }

  function handleCancel() {
    reset();
    createProject.reset();
  }

  const submitting = createProject.isPending;

  return (
    <main className="page-shell">
      <PageHeader
        breadcrumb={['Projects', 'Commercial Setup', 'New Entry']}
        title="Create Project & Commercial Baseline"
        description="Define project parameters, commercial limits, and trigger automated SharePoint folder provisioning."
      >
        <button
          type="button"
          className="button button-secondary"
          onClick={() => navigate('/created-projects')}
        >
          <ArrowLeft size={16} /> Back to Created Projects
        </button>
      </PageHeader>

      {createProject.error && (
        <Notice type="error" message={createProject.error.message} onDismiss={() => createProject.reset()} />
      )}

      <form className="project-card" onSubmit={handleSubmit} noValidate>
        <div className="form-column left-column">
          <section>
            <SectionTitle number="1">Project &amp; Commercial Identification</SectionTitle>
            <div className="field-grid one-column">
              <Field label="Project Name" required error={errors.projectName}>
                <input
                  value={form.projectName}
                  onChange={(event) => updateField('projectName', event.target.value)}
                  placeholder="Enter project name"
                />
              </Field>
            </div>
            <div className="field-grid two-column">
              <Field label="Project Code" required error={errors.projectCode}>
                <input
                  value={form.projectCode}
                  onChange={(event) => updateField('projectCode', event.target.value)}
                  placeholder="e.g. MAEC-2026-001"
                />
              </Field>
              <Field label="Client / Customer" required error={errors.clientCustomer}>
                <input
                  value={form.clientCustomer}
                  onChange={(event) => updateField('clientCustomer', event.target.value)}
                  placeholder="Enter client or customer"
                />
              </Field>
            </div>
            <div className="field-grid two-column">
              <LeadSelect
                label="Assigned Project Lead | Electrical"
                placeholder="Select electrical lead"
                leads={leads.electrical}
                value={form.electricalLead}
                error={errors.electricalLead}
                extraError={leadsError?.message}
                onChange={(value) => updateField('electricalLead', value)}
              />
              <Field label="Target Start Date" required error={errors.targetStartDate}>
                <input
                  type="date"
                  value={form.targetStartDate}
                  onChange={(event) => updateField('targetStartDate', event.target.value)}
                />
              </Field>
            </div>
            <div className="field-grid two-column">
              <LeadSelect
                label="Assigned Project Lead | Mechanical"
                placeholder="Select mechanical lead"
                leads={leads.mechanical}
                value={form.mechanicalLead}
                error={errors.mechanicalLead}
                onChange={(value) => updateField('mechanicalLead', value)}
              />
              <LeadSelect
                label="Assigned Project Lead | BIM"
                placeholder="Select BIM lead"
                leads={leads.bim}
                value={form.bimLead}
                error={errors.bimLead}
                onChange={(value) => updateField('bimLead', value)}
              />
            </div>
          </section>

          <section className="discipline-section">
            <SectionTitle number="2">Automated SharePoint Directory Setup</SectionTitle>
            <p className="section-copy">
              Select MEP engineering disciplines to auto-create inside SharePoint site:
            </p>
            <div className="discipline-grid">
              {SHAREPOINT_DISCIPLINES.map((discipline) => {
                const checked = form.selectedDisciplines.includes(discipline.value);
                return (
                  <label className={`discipline-option ${checked ? 'checked' : ''}`} key={discipline.value}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleDiscipline(discipline.value)}
                    />
                    <span className="checkmark">
                      <Check size={13} />
                    </span>
                    <span>{discipline.label}</span>
                  </label>
                );
              })}
            </div>
            {errors.selectedDisciplines && <span className="field-error">{errors.selectedDisciplines}</span>}
          </section>
        </div>

        <div className="form-column right-column">
          <section>
            <SectionTitle number="3">Commercial Controls &amp; Budget Baselines</SectionTitle>
            <Field
              label="Total Commercial Contract Value"
              required
              error={errors.contractCurrency || errors.contractValue}
            >
              <div className="currency-input-row">
                <div className="select-wrap currency-select-wrap">
                  <select
                    value={form.contractCurrency}
                    onChange={(event) => changeCurrency(event.target.value)}
                    aria-label="Contract currency"
                  >
                    {CURRENCIES.map((currency) => (
                      <option key={currency.code} value={currency.code}>
                        {currency.code} ({currency.symbol})
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={16} />
                </div>
                <div className="currency-amount-wrap">
                  <span className="currency-prefix">{currencySymbol(form.contractCurrency)}</span>
                  <AmountInput
                    value={form.contractValue}
                    onChange={(value) => updateField('contractValue', value)}
                  />
                </div>
              </div>
            </Field>
            <Field label="Target Effort Hours Baseline (Hrs)" required error={errors.effortHours}>
              <div className="input-with-suffix">
                <input
                  inputMode="numeric"
                  value={form.effortHours}
                  onChange={(event) => updateField('effortHours', event.target.value.replace(/[^0-9,]/g, ''))}
                  placeholder="3,840"
                />
                <span>Hours</span>
              </div>
            </Field>

            <div className="governance-box">
              <h3>Governance Threshold &amp; Exception Trigger</h3>
              <p>
                When logged hours exceed this percentage threshold of baseline hours, timesheets block further
                logging until Business Unit Head approval.
              </p>
              <div className="threshold-label">
                <span>Alert &amp; Override Threshold Limit:</span>
                <strong>{form.threshold} %</strong>
              </div>
              <input
                className="range-input"
                type="range"
                min="0"
                max="100"
                value={form.threshold}
                style={{ '--range-position': `${form.threshold}%` }}
                onChange={(event) => updateField('threshold', Number(event.target.value))}
                aria-label="Alert and override threshold limit"
              />
              <div className="range-labels">
                <span>0% (Start)</span>
                <strong>80% (Warning)</strong>
                <span>100% (Hard Stop)</span>
              </div>
              {errors.threshold && <span className="field-error">{errors.threshold}</span>}
            </div>
          </section>

          <div className="action-row">
            <button type="button" className="button button-secondary" onClick={handleCancel}>
              <X size={16} /> Cancel
            </button>
            <button type="submit" className="button button-primary" disabled={submitting}>
              {submitting ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />}
              {submitting ? 'Creating Project...' : 'Create Project & Build SharePoint Directory'}
            </button>
          </div>
        </div>
      </form>
    </main>
  );
}
