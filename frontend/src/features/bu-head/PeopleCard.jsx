import { Download, KeyRound, Upload } from 'lucide-react';
import { useState } from 'react';
import { ErrorBanner } from '../../components/Feedback';
import { useImportPeople, useResetPassword } from '../../hooks/usePeople';
import { credentialsCsv } from './peopleCsv';
import { PeopleList } from './PeopleList';

/** Hand the temporary passwords over as a CSV file, built in the browser: never sent anywhere else. */
function downloadCredentials(created) {
  const url = URL.createObjectURL(new Blob([credentialsCsv(created)], { type: 'text/csv' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'temporary-passwords.csv';
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Onboarding for the BU Head, until the company's global admin application takes it over:
 * import engineers from the HR export, see and correct everyone with an account, deactivate
 * a leaver, and reset a forgotten password.
 */
export function PeopleCard() {
  const importPeople = useImportPeople();
  const resetPassword = useResetPassword();
  const [file, setFile] = useState(null);
  const [username, setUsername] = useState('');
  const result = importPeople.data;
  const reset = resetPassword.data;

  return (
    <section className="people-card" aria-label="People">
      <h2>People</h2>
      <p className="people-hint">
        Import engineers from the HR export (CSV with Employee Id, Full Name, Work Email and Job Role). Each
        new person signs in with their work email and a temporary password, and must set their own at the
        first login. Remove anyone who shouldn&apos;t have an account from the file first.
      </p>

      <div className="people-row">
        <input
          type="file"
          accept=".csv,text/csv"
          aria-label="Employee CSV file"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <button
          type="button"
          className="button button-primary"
          disabled={!file || importPeople.isPending}
          onClick={() => importPeople.mutate(file)}
        >
          <Upload size={15} /> {importPeople.isPending ? 'Importing…' : 'Import'}
        </button>
      </div>
      <ErrorBanner error={importPeople.error} />

      {result && (
        <div className="people-result" role="status">
          <p>
            <strong>{result.created.length}</strong> account{result.created.length === 1 ? '' : 's'} created,{' '}
            <strong>{result.skipped.length}</strong> skipped.
          </p>
          {result.created.length > 0 && (
            <>
              <button
                type="button"
                className="button button-secondary"
                onClick={() => downloadCredentials(result.created)}
              >
                <Download size={15} /> Download the temporary passwords (CSV)
              </button>
              <p className="people-warning">
                Download it now: the passwords are shown only once and are not stored. Give each person their
                own.
              </p>
            </>
          )}
          {result.skipped.length > 0 && (
            <ul className="people-skipped">
              {result.skipped.map((row) => (
                <li key={row.row}>
                  Line {row.row}: {row.name || row.email || 'empty'} – {row.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <h3>Reset a forgotten password</h3>
      <form
        className="people-row"
        onSubmit={(event) => {
          event.preventDefault();
          if (username.trim()) resetPassword.mutate(username.trim());
        }}
      >
        <input
          type="text"
          aria-label="Username to reset"
          placeholder="Work email"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
        />
        <button
          type="submit"
          className="button button-secondary"
          disabled={!username.trim() || resetPassword.isPending}
        >
          <KeyRound size={15} /> Reset
        </button>
      </form>
      <ErrorBanner error={resetPassword.error} />
      {reset && (
        <p className="people-result" role="status">
          New temporary password for <strong>{reset.full_name || reset.username}</strong>:{' '}
          <code className="people-password">{reset.temporary_password}</code>. They must change it when they
          sign in.
        </p>
      )}

      <PeopleList />
    </section>
  );
}
