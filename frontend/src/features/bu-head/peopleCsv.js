const quote = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;

/** The temporary passwords as CSV for the BU Head to hand out: one line per new account. */
export function credentialsCsv(created) {
  const header = ['Username', 'Full Name', 'Employee Id', 'Temporary Password'];
  const lines = created.map((row) =>
    [row.username, row.full_name, row.employee_code, row.temporary_password].map(quote).join(','),
  );
  return [header.map(quote).join(','), ...lines].join('\r\n') + '\r\n';
}
