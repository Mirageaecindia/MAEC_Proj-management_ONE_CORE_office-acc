import { Upload, UserPlus } from 'lucide-react';
import { useState } from 'react';
import { useAuth } from '../../AuthContext';
import { ErrorBanner } from '../../components/Feedback';
import { useAddPerson, useImportPeople } from '../../hooks/usePeople';
import { PeopleList } from './PeopleList';

const NO_ONE = { employee_code: '', full_name: '', email: '', job_role: '' };
const SEAT_REMINDER = 'Each person still needs a seat on Project Management in MAEC One to sign in.';

/**
 * People, for the BU Head: profiles in Project Management (employee record and role here),
 * from the HR export or one at a time, then seen and corrected in the list below.
 * Signing in, access and passwords are managed in MAEC One.
 */
export function PeopleCard() {
  const { signOutUrl: maecOneUrl } = useAuth();
  const importPeople = useImportPeople();
  const addPerson = useAddPerson();
  const [file, setFile] = useState(null);
  const [person, setPerson] = useState(NO_ONE);
  const result = importPeople.data;
  const added = addPerson.data;
  const field = (name) => ({
    value: person[name],
    onChange: (event) => setPerson((current) => ({ ...current, [name]: event.target.value })),
  });

  return (
    <section className="people-card" aria-label="People">
      <h2>People</h2>
      <p className="people-hint">
        Sign-in, access and passwords are managed in MAEC One
        {maecOneUrl && (
          <>
            {' '}
            (<a href={maecOneUrl}>open MAEC One</a>)
          </>
        )}
        .
      </p>
      <p className="people-hint">
        Import engineers&apos; profiles from the HR export (CSV with Employee Id, Full Name, Work Email and
        Job Role). Remove anyone who shouldn&apos;t have a profile from the file first. {SEAT_REMINDER}
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
            <strong>{result.created.length}</strong> profile{result.created.length === 1 ? '' : 's'} created,{' '}
            <strong>{result.skipped.length}</strong> skipped.
            {result.created.length > 0 && ` ${SEAT_REMINDER}`}
          </p>
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

      <h3>Add one person</h3>
      <p className="people-hint">
        For someone with a seat in MAEC One whose profile here isn&apos;t set up yet.
      </p>
      <form
        className="people-row"
        onSubmit={(event) => {
          event.preventDefault();
          addPerson.mutate(person, { onSuccess: () => setPerson(NO_ONE) });
        }}
      >
        <input type="text" aria-label="Employee Id" placeholder="Employee Id" {...field('employee_code')} />
        <input type="text" aria-label="Full name" placeholder="Full name" {...field('full_name')} />
        <input type="email" aria-label="Work email" placeholder="Work email" {...field('email')} />
        <input type="text" aria-label="Job role" placeholder="Job role" {...field('job_role')} />
        <button
          type="submit"
          className="button button-secondary"
          disabled={Object.values(person).some((value) => !value.trim()) || addPerson.isPending}
        >
          <UserPlus size={15} /> Add
        </button>
      </form>
      <ErrorBanner error={addPerson.error} />
      {added && (
        <p className="people-result" role="status">
          Profile created for <strong>{added.full_name}</strong> ({added.username}). {SEAT_REMINDER}
        </p>
      )}

      <PeopleList />
    </section>
  );
}
