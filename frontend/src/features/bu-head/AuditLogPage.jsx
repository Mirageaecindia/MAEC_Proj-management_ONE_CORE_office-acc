import { useSearchParams } from 'react-router-dom';
import { AuditLogView } from '../../components/AuditLogView';
import { PageHeader } from '../../components/PageHeader';
import { usePeople } from '../../hooks/usePeople';
import { useProjects } from '../../hooks/useProjects';

/** Everyone's activity for the BU Head: engineers, leads and BU Heads; `?userId=` opens one person's. */
export function AuditLogPage() {
  const [searchParams] = useSearchParams();
  const { data: people = [] } = usePeople();
  const { data: projects = [] } = useProjects({ includeArchived: true });
  return (
    <main className="timeline-page">
      <PageHeader
        breadcrumb={['Administration', 'Audit Log']}
        title="Audit Log"
        description="Every action anyone took in ProManage, newest first: sign-ins, WBS changes, Login/Logout, hour reviews, bookings, governance and people. Entries are kept for 30 days."
      />
      <AuditLogView
        everyone
        people={people}
        projects={projects}
        initialUserId={searchParams.get('userId') || ''}
      />
    </main>
  );
}
