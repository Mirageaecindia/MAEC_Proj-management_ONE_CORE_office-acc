/** Create Project form: initial state, validation and request payload (pure functions). */

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

/** Field -> error message for every invalid field (empty object when valid). */
export function validateProjectForm(form) {
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
  if (form.selectedDisciplines.length === 0) {
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

/** Body for POST /api/projects. `leads` is { electrical: [...], mechanical: [...], bim: [...] }. */
export function toCreateProjectPayload(form, leads) {
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
    sharepoint_disciplines: form.selectedDisciplines,
    total_contract_value: parseAmount(form.contractValue),
    contract_currency: form.contractCurrency,
    target_effort_hours: parseHours(form.effortHours),
    alert_override_threshold_pct: Number(form.threshold),
  };
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
