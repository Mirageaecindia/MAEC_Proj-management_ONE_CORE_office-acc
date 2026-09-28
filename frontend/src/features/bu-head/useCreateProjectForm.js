import { useState } from 'react';
import { INITIAL_FORM, validateProjectForm } from './createProjectForm';

/** Form state for Create / Edit Project: values, per-field errors and edit helpers. */
export function useCreateProjectForm(initialForm = INITIAL_FORM, { requireDisciplines = true } = {}) {
  const [form, setForm] = useState(initialForm);
  const [errors, setErrors] = useState({});

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
    // A lead's period and % share one error (`<slot>LeadPeriod`); editing any of them clears it.
    const periodError = field.replace(/Lead(Start|End|Pct)$/, 'LeadPeriod');
    setErrors((current) => ({ ...current, [field]: '', [periodError]: '' }));
  }

  function toggleDiscipline(value) {
    const selected = form.selectedDisciplines.includes(value)
      ? form.selectedDisciplines.filter((item) => item !== value)
      : [...form.selectedDisciplines, value];
    updateField('selectedDisciplines', selected);
  }

  function changeCurrency(currency) {
    // Only the symbol changes; the raw amount stays as typed.
    setForm((current) => ({ ...current, contractCurrency: currency }));
    setErrors((current) => ({ ...current, contractCurrency: '', contractValue: '' }));
  }

  /** Validates all fields, shows their errors, and returns whether the form is valid. */
  function validate() {
    const nextErrors = validateProjectForm(form, { requireDisciplines });
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }

  function reset() {
    setForm(initialForm);
    setErrors({});
  }

  return { form, errors, updateField, toggleDiscipline, changeCurrency, validate, reset };
}
