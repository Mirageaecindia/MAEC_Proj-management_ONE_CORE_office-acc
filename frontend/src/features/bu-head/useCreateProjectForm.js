import { useState } from 'react';
import { INITIAL_FORM, validateProjectForm } from './createProjectForm';

/** Form state for Create Project: values, per-field errors and edit helpers. */
export function useCreateProjectForm() {
  const [form, setForm] = useState(INITIAL_FORM);
  const [errors, setErrors] = useState({});

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: '' }));
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
    const nextErrors = validateProjectForm(form);
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }

  function reset() {
    setForm(INITIAL_FORM);
    setErrors({});
  }

  return { form, errors, updateField, toggleDiscipline, changeCurrency, validate, reset };
}
