/** Create / Edit Project form: initial state, validation and request payloads (pure functions). */

import { isSupportedCurrency } from '../../constants/currencies';
import { SHAREPOINT_DISCIPLINES } from '../../constants/sharepoint';
import { parseAmount } from '../../utils/format';

export const INITIAL_FORM = {
  projectName: '',
  projectCode: '',
  clientCustomer: '',
  electricalLead: '',
  mechanicalLead: '',
  bimLead: '',
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
  ['electricalLead', 'Electrical project lead is required.'],
  ['targetStartDate', 'Target start date is required.'],
  ['mechanicalLead', 'Mechanical project lead is required.'],
  ['bimLead', 'BIM project lead is required.'],
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
    electricalLead: project.project_lead_electrical_user_id
      ? String(project.project_lead_electrical_user_id)
      : '',
    mechanicalLead: project.project_lead_mechanical_user_id
      ? String(project.project_lead_mechanical_user_id)
      : '',
    bimLead: project.project_lead_bim_user_id ? String(project.project_lead_bim_user_id) : '',
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

function leadRef(leadId, allLeads) {
  const match = allLeads.find((lead) => String(lead.id) === String(leadId));
  return { id: leadId ? Number(leadId) : null, name: match ? match.name : '' };
}

function projectFields(form, leads) {
  const allLeads = [...leads.electrical, ...leads.mechanical, ...leads.bim];
  const electrical = leadRef(form.electricalLead, allLeads);
  const mechanical = leadRef(form.mechanicalLead, allLeads);
  const bim = leadRef(form.bimLead, allLeads);
  return {
    project_name: form.projectName.trim(),
    project_code: form.projectCode.trim(),
    client_customer: form.clientCustomer.trim(),
    project_lead_electrical: electrical.name,
    project_lead_mechanical: mechanical.name,
    project_lead_bim: bim.name,
    project_lead_electrical_user_id: electrical.id,
    project_lead_mechanical_user_id: mechanical.id,
    project_lead_bim_user_id: bim.id,
    target_start_date: form.targetStartDate,
    total_contract_value: parseAmount(form.contractValue),
    contract_currency: form.contractCurrency,
    target_effort_hours: parseHours(form.effortHours),
    alert_override_threshold_pct: Number(form.threshold),
  };
}

/** Body for POST /api/projects. `leads` is { electrical: [...], mechanical: [...], bim: [...] }. */
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
