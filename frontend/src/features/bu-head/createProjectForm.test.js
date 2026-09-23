import { describe, expect, it } from 'vitest';
import {
  INITIAL_FORM,
  creationNotice,
  toCreateProjectPayload,
  validateProjectForm,
} from './createProjectForm';

const LEADS = {
  electrical: [{ id: 1, name: 'Anita Kumar' }],
  mechanical: [{ id: 2, name: 'Priya Nair' }],
  bim: [{ id: 3, name: 'Mohan Daniel' }],
};

const VALID_FORM = {
  ...INITIAL_FORM,
  projectName: ' Hotel Tower ',
  projectCode: 'MAEC-001',
  clientCustomer: 'Acme',
  electricalLead: '1',
  mechanicalLead: '2',
  bimLead: '3',
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
        'bimLead',
        'clientCustomer',
        'contractValue',
        'effortHours',
        'electricalLead',
        'mechanicalLead',
        'projectCode',
        'projectName',
        'targetStartDate',
      ].sort(),
    );
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
