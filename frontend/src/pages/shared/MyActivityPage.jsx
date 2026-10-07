import { AuditLogView } from '../../components/AuditLogView';
import { PageHeader } from '../../components/PageHeader';
import { useProjects } from '../../hooks/useProjects';

/** Your own audit log: what you did in the app, newest first. Nobody but the BU Head sees it too. */
export function MyActivityPage() {
  const { data: projects = [] } = useProjects();
  return (
    <main className="timeline-page">
      <PageHeader
        breadcrumb={['My Account', 'My Activity']}
        title="My Activity"
        description="What you did in ProManage, newest first. Only you and the BU Head can see it; entries are kept for 30 days."
      />
      <AuditLogView projects={projects} />
    </main>
  );
}
