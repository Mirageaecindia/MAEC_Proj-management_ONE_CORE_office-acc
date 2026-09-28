/** Create / Edit Project form: initial state, validation and request payloads (pure functions). */

import { isSupportedCurrency } from '../../constants/currencies';
import { SHAREPOINT_DISCIPLINES } from '../../constants/sharepoint';
import { parseAmount } from '../../utils/format';

/** The three lead slots. Each has a select (`<slot>Lead`) and, once a lead is chosen, the
 *  period and the share of their time the project takes (`<slot>LeadStart/End/Pct`). */
export const LEAD_SLOTS = ['electrical', 'mechanical', 'bim'];
const LEAD_FIELDS = LEAD_SLOTS.map((slot) => `${slot}Lead`);

export const INITIAL_FORM = {
  projectName: '',
  projectCode: '',
  clientCustomer: '',
  ...Object.fromEntries(
    LEAD_SLOTS.flatMap((slot) => ['', 'Start', 'End', 'Pct'].map((f) => [`${slot}Lead${f}`, ''])),
  ),
  targetStartDate: '',
  contractCurrency: 'USD',
  contractValue: '',
  effortHours: '',
  threshold: 80,
  selectedDisciplines: SHAREPOINT_DISCIPLINES.map((discipline) => discipline.value),
};

const REQUIRED_FIELDS = [
  ['projectName', 'Project name is required.'],
  ['projectCode', 'Project code is required.'],
  ['clientCustomer', 'Client / Customer is required.'],
  ['targetStartDate', 'Target start date is required.'],
];

/** "3,840" -> 3840 */
export function parseHours(raw) {
  return Number(String(raw ?? '').replace(/,/g, ''));
}

/** Form values for editing an existing project (GET /api/projects/{id}). */
export function formFromProject(project) {
  return {
    ...INITIAL_FORM,
    projectName: project.project_name ?? '',
    projectCode: project.project_code ?? '',
    clientCustomer: project.client_organization ?? '',
    ...Object.fromEntries(
      LEAD_SLOTS.flatMap((slot) => {
        const id = project[`project_lead_${slot}_user_id`];
        const pct = project[`project_lead_${slot}_utilization_pct`];
        return [
          [`${slot}Lead`, id ? String(id) : ''],
          [`${slot}LeadStart`, project[`project_lead_${slot}_start_date`] ?? ''],
          [`${slot}LeadEnd`, project[`project_lead_${slot}_end_date`] ?? ''],
          [`${slot}LeadPct`, pct != null ? String(pct) : ''],
        ];
      }),
    ),
    targetStartDate: project.start_date ?? '',
    contractCurrency: project.contract_currency || 'USD',
    contractValue: project.contract_value != null ? String(project.contract_value) : '',
    effortHours: project.target_effort_hours != null ? String(project.target_effort_hours) : '',
    threshold: project.governance_threshold_pct ?? 80,
    selectedDisciplines: [],
  };
}

/** Field -> error message for every invalid field (empty object when valid).
 *  SharePoint disciplines are chosen only when creating. */
export function validateProjectForm(form, { requireDisciplines = true } = {}) {
  const errors = {};
  for (const [field, message] of REQUIRED_FIELDS) {
    if (!String(form[field] ?? '').trim()) errors[field] = message;
  }
  if (!LEAD_FIELDS.some((field) => String(form[field] ?? '').trim())) {
    errors.leads = 'Choose at least one project lead.';
  }
  for (const slot of LEAD_SLOTS) {
    if (!String(form[`${slot}Lead`] ?? '').trim()) continue;
    const start = form[`${slot}LeadStart`];
    const end = form[`${slot}LeadEnd`];
    const pct = Number(form[`${slot}LeadPct`]);
    if (!start || !end) errors[`${slot}LeadPeriod`] = 'Give the lead a start and an end date.';
    else if (end < start) errors[`${slot}LeadPeriod`] = 'The end date is before the start date.';
    else if (!Number.isInteger(pct) || pct < 1 || pct > 100) {
      errors[`${slot}LeadPeriod`] = 'Utilization must be a whole number from 1 to 100.';
    }
  }
  const contractValue = parseAmount(form.contractValue);
  if (!Number.isFinite(contractValue) || contractValue <= 0) {
    errors.contractValue = 'Enter a contract value greater than 0.';
  }
  if (!isSupportedCurrency(form.contractCurrency)) {
    errors.contractCurrency = 'Select a supported currency.';
  }
  const effortHours = parseHours(form.effortHours);
  if (!Number.isFinite(effortHours) || effortHours <= 0) {
    errors.effortHours = 'Enter effort hours greater than 0.';
  }
  if (requireDisciplines && form.selectedDisciplines.length === 0) {
    errors.selectedDisciplines = 'Select at least one discipline.';
  }
  if (form.threshold < 0 || form.threshold > 100) {
    errors.threshold = 'Threshold must be between 0 and 100.';
  }
  return errors;
}

/** The API fields of one lead slot: who (id and name), and their period and % when someone is chosen. */
function leadFields(form, leads, slot) {
  const chosen = String(form[`${slot}Lead`] ?? '').trim();
  const match = leads.find((lead) => String(lead.id) === chosen);
  const id = chosen ? Number(chosen) : null;
  return {
    [`project_lead_${slot}`]: match ? match.name : null,
    [`project_lead_${slot}_user_id`]: id,
    [`project_lead_${slot}_start_date`]: id ? form[`${slot}LeadStart`] || null : null,
    [`project_lead_${slot}_end_date`]: id ? form[`${slot}LeadEnd`] || null : null,
    [`project_lead_${slot}_utilization_pct`]: id ? Number(form[`${slot}LeadPct`]) : null,
  };
}

function projectFields(form, leads) {
  return {
    project_name: form.projectName.trim(),
    project_code: form.projectCode.trim(),
    client_customer: form.clientCustomer.trim(),
    ...Object.assign({}, ...LEAD_SLOTS.map((slot) => leadFields(form, leads, slot))),
    target_start_date: form.targetStartDate,
    total_contract_value: parseAmount(form.contractValue),
    contract_currency: form.contractCurrency,
    target_effort_hours: parseHours(form.effortHours),
    alert_override_threshold_pct: Number(form.threshold),
  };
}

/** Body for POST /api/projects. `leads` is the list from GET /api/project-leads. */
export function toCreateProjectPayload(form, leads) {
  return { ...projectFields(form, leads), sharepoint_disciplines: form.selectedDisciplines };
}

/** Body for PUT /api/projects/{id}. A currency change must be confirmed explicitly. */
export function toUpdateProjectPayload(form, leads, { confirmCurrencyChange = false } = {}) {
  return { ...projectFields(form, leads), confirm_currency_change: confirmCurrencyChange };
}

/** Notice shown on the project list after an edit. */
export function updateNotice(project) {
  const moved = project.reassigned_nodes
    ? ` ${project.reassigned_nodes} WBS node(s) moved to the new lead.`
    : '';
  return { type: 'success', message: `Project "${project.project_name}" updated.${moved}` };
}

/** Notice describing the create outcome, including the SharePoint provisioning result. */
export function creationNotice(project) {
  const outcomes = {
    provisioned: { type: 'success', text: 'SharePoint directory created successfully.' },
    failed: {
      type: 'error',
      text: `SharePoint provisioning failed: ${project.sharepoint_error || 'Unknown error'}`,
    },
    error: { type: 'error', text: `SharePoint error: ${project.sharepoint_error || 'Unexpected error'}` },
    not_requested: { type: 'success', text: 'SharePoint directory not requested (no disciplines selected).' },
  };
  const outcome = outcomes[project.sharepoint_status] ?? {
    type: 'success',
    text: `SharePoint status: ${project.sharepoint_status}.`,
  };
  return {
    type: outcome.type,
    message: `Project "${project.project_name}" created. ${outcome.text}`,
    url: project.sharepoint_site_url || null,
  };
}
