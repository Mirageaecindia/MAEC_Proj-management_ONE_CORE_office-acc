import { describe, expect, it } from 'vitest';
import {
  INITIAL_FORM,
  creationNotice,
  formFromProject,
  toCreateProjectPayload,
  toUpdateProjectPayload,
  updateNotice,
  validateProjectForm,
} from './createProjectForm';

const LEADS = [
  { id: 1, name: 'Anita Kumar', title: 'Electrical Lead' },
  { id: 2, name: 'Priya Nair', title: 'Mechanical Lead' },
  { id: 3, name: 'Mohan Daniel', title: 'BIM Lead' },
];
const PERIOD = { Start: '2026-09-01', End: '2027-03-31', Pct: '20' };
const leadPeriods = (...slots) =>
  Object.fromEntries(slots.flatMap((slot) => Object.entries(PERIOD).map(([f, v]) => [`${slot}Lead${f}`, v])));

const VALID_FORM = {
  ...INITIAL_FORM,
  projectName: ' Hotel Tower ',
  projectCode: 'MAEC-001',
  clientCustomer: 'Acme',
  electricalLead: '1',
  mechanicalLead: '2',
  bimLead: '3',
  ...leadPeriods('electrical', 'mechanical', 'bim'),
  targetStartDate: '2026-09-01',
  contractValue: '480000.50',
  effortHours: '3,840',
  threshold: 75,
};

describe('validateProjectForm', () => {
  it('accepts a complete form', () => {
    expect(validateProjectForm(VALID_FORM)).toEqual({});
  });

  it('reports every missing required field', () => {
    const errors = validateProjectForm(INITIAL_FORM);
    expect(Object.keys(errors).sort()).toEqual(
      [
        'clientCustomer',
        'contractValue',
        'effortHours',
        'leads',
        'projectCode',
        'projectName',
        'targetStartDate',
      ].sort(),
    );
  });

  it('needs at least one lead, not all three', () => {
    expect(validateProjectForm({ ...VALID_FORM, electricalLead: '', bimLead: '' })).toEqual({});
    const payload = toCreateProjectPayload({ ...VALID_FORM, electricalLead: '', bimLead: '' }, LEADS);
    expect(payload).toMatchObject({
      project_lead_electrical: null,
      project_lead_electrical_user_id: null,
      project_lead_mechanical: 'Priya Nair',
      project_lead_mechanical_user_id: 2,
    });
  });

  it('a chosen lead needs a period and a whole percentage of their time', () => {
    const period = (changes) => validateProjectForm({ ...VALID_FORM, ...changes }).bimLeadPeriod;
    expect(period({ bimLeadStart: '' })).toBe('Give the lead a start and an end date.');
    expect(period({ bimLeadEnd: '2026-08-31' })).toBe('The end date is before the start date.');
    expect(period({ bimLeadPct: '0' })).toBeTruthy();
    expect(period({ bimLeadPct: '12.5' })).toBeTruthy();
    expect(period({ bimLeadPct: '100' })).toBeUndefined();
    expect(period({ bimLead: '', bimLeadStart: '' })).toBeUndefined(); // no lead: nothing to check
  });

  it('rejects no disciplines, unknown currency and out-of-range threshold', () => {
    const errors = validateProjectForm({
      ...VALID_FORM,
      selectedDisciplines: [],
      contractCurrency: 'XYZ',
      threshold: 120,
    });
    expect(errors.selectedDisciplines).toBeTruthy();
    expect(errors.contractCurrency).toBeTruthy();
    expect(errors.threshold).toBeTruthy();
  });
});

describe('toCreateProjectPayload', () => {
  it('maps the form to the API body with lead ids and names', () => {
    const payload = toCreateProjectPayload(VALID_FORM, LEADS);
    expect(payload).toMatchObject({
      project_name: 'Hotel Tower',
      project_code: 'MAEC-001',
      client_customer: 'Acme',
      project_lead_electrical: 'Anita Kumar',
      project_lead_electrical_user_id: 1,
      project_lead_electrical_start_date: '2026-09-01',
      project_lead_electrical_end_date: '2027-03-31',
      project_lead_electrical_utilization_pct: 20,
      project_lead_mechanical_user_id: 2,
      project_lead_bim_user_id: 3,
      total_contract_value: 480000.5,
      target_effort_hours: 3840,
      alert_override_threshold_pct: 75,
      contract_currency: 'USD',
    });
    expect(payload.sharepoint_disciplines).toHaveLength(5);
  });
});

describe('creationNotice', () => {
  it('reports SharePoint success with the folder link', () => {
    const notice = creationNotice({
      project_name: 'Hotel Tower',
      sharepoint_status: 'provisioned',
      sharepoint_site_url: 'https://sp/x',
    });
    expect(notice).toEqual({
      type: 'success',
      message: 'Project "Hotel Tower" created. SharePoint directory created successfully.',
      url: 'https://sp/x',
    });
  });

  it('reports SharePoint failure as an error', () => {
    const notice = creationNotice({
      project_name: 'X',
      sharepoint_status: 'failed',
      sharepoint_error: '403',
    });
    expect(notice.type).toBe('error');
    expect(notice.message).toContain('SharePoint provisioning failed: 403');
  });
});

describe('editing a project', () => {
  const PROJECT = {
    project_name: 'Hotel Tower',
    project_code: 'MAEC-001',
    client_organization: 'Acme',
    project_lead_electrical_user_id: 1,
    project_lead_electrical_start_date: '2026-09-01',
    project_lead_electrical_end_date: '2027-03-31',
    project_lead_electrical_utilization_pct: 20,
    project_lead_mechanical_user_id: 2,
    project_lead_mechanical_start_date: '2026-09-01',
    project_lead_mechanical_end_date: '2027-03-31',
    project_lead_mechanical_utilization_pct: 40,
    project_lead_bim_user_id: 3,
    project_lead_bim_start_date: '2026-09-01',
    project_lead_bim_end_date: '2027-03-31',
    project_lead_bim_utilization_pct: 10,
    start_date: '2026-09-01',
    contract_value: 480000.5,
    contract_currency: 'USD',
    target_effort_hours: 3840,
    governance_threshold_pct: 75,
  };

  it('round-trips a project through the form into the update payload', () => {
    const form = formFromProject(PROJECT);

    expect(validateProjectForm(form, { requireDisciplines: false })).toEqual({});
    const payload = toUpdateProjectPayload(form, LEADS);
    expect(payload).toMatchObject({
      project_name: 'Hotel Tower',
      project_lead_electrical_user_id: 1,
      project_lead_electrical: 'Anita Kumar',
      project_lead_mechanical_utilization_pct: 40,
      project_lead_bim_end_date: '2027-03-31',
      total_contract_value: 480000.5,
      target_effort_hours: 3840,
      alert_override_threshold_pct: 75,
      confirm_currency_change: false,
    });
    expect(payload).not.toHaveProperty('sharepoint_disciplines');
  });

  it('only sends the currency confirmation when asked', () => {
    const payload = toUpdateProjectPayload(formFromProject(PROJECT), LEADS, { confirmCurrencyChange: true });

    expect(payload.confirm_currency_change).toBe(true);
  });

  it('reports moved WBS nodes after an edit', () => {
    expect(updateNotice({ project_name: 'Hotel Tower', reassigned_nodes: 2 }).message).toBe(
      'Project "Hotel Tower" updated. 2 WBS node(s) moved to the new lead.',
    );
  });
});
