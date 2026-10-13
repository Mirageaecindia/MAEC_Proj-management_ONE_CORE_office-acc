import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';
import { MaecHeader } from './components/MaecHeader';
import { SignInStatus } from './components/SignInStatus';
import { TrackingBar } from './components/TrackingBar';
import { useLeadsProjects } from './hooks/useProjects';
import { useTrackingState } from './hooks/useTracking';
import { canAccess } from './utils/access';
import { QueryProvider } from './providers/QueryProvider';

// Pages are code-split: each role only downloads the screens it opens.
const lazyPage = (load, name) => lazy(() => load().then((module) => ({ default: module[name] })));
const CreateProjectPage = lazyPage(() => import('./features/bu-head/CreateProjectPage'), 'CreateProjectPage');
const EditProjectPage = lazyPage(() => import('./features/bu-head/CreateProjectPage'), 'EditProjectPage');
const CreatedProjectsPage = lazyPage(
  () => import('./features/bu-head/CreatedProjectsPage'),
  'CreatedProjectsPage',
);
const BuHeadExecutiveDashboardPage = lazyPage(
  () => import('./features/bu-head/ExecutiveDashboardPage'),
  'ExecutiveDashboardPage',
);
const ProjectWorkSummaryPage = lazyPage(
  () => import('./features/bu-head/ProjectWorkSummaryPage'),
  'ProjectWorkSummaryPage',
);
const SharePointMirrorPage = lazyPage(
  () => import('./features/sharepoint/SharePointMirrorPage'),
  'SharePointMirrorPage',
);
const PerformanceDashboardPage = lazyPage(
  () => import('./pages/shared/PerformanceDashboardPage'),
  'PerformanceDashboardPage',
);
const ResourceBookingPage = lazyPage(
  () => import('./pages/shared/ResourceBookingPage'),
  'ResourceBookingPage',
);
const TimelineLogsPage = lazyPage(() => import('./pages/shared/TimelineLogsPage'), 'TimelineLogsPage');
const WbsStructurePage = lazyPage(() => import('./pages/shared/WbsStructurePage'), 'WbsStructurePage');
const EngineerWeeklyLogsPage = lazyPage(
  () => import('./pages/shared/EngineerWeeklyLogsPage'),
  'EngineerWeeklyLogsPage',
);
const TaskDetailsPage = lazyPage(() => import('./pages/shared/TaskDetailsPage'), 'TaskDetailsPage');
const MyActivityPage = lazyPage(() => import('./pages/shared/MyActivityPage'), 'MyActivityPage');
const AuditLogPage = lazyPage(() => import('./features/bu-head/AuditLogPage'), 'AuditLogPage');

/** Leads have one dashboard (Performance Dashboard); old links to the Executive Dashboard land there. */
function ExecutiveDashboardRouter() {
  const { role } = useAuth();
  const { search } = useLocation();
  if (role === 'engineer') return <Navigate to={`/engineer-performance-dashboard${search}`} replace />;
  return <BuHeadExecutiveDashboardPage />;
}

/** Everyone but the BU Head starts on their own work (WBS), leads included. */
function HomeRedirect() {
  const { role } = useAuth();
  return <Navigate to={role === 'engineer' ? '/wbs-structure' : '/created-projects'} replace />;
}

/** `roles`: account roles; 'lead' means an engineer who leads at least one project. */
function ProtectedRoute({ children, roles }) {
  const { role } = useAuth();
  const leadsProjects = useLeadsProjects();
  if (!role || !canAccess(roles, { role, leadsProjects })) return <Navigate to="/" replace />;
  return children;
}

function WorkspaceRoute({ children, roles }) {
  return (
    <ProtectedRoute roles={roles}>
      <MaecHeader />
      <TrackingBar />
      {children}
    </ProtectedRoute>
  );
}

function AppRoutes() {
  const { user, role, loading, blocked, error, signOutUrl } = useAuth();
  // An engineer's Login/Logout heartbeat runs on every page, not just Task Details.
  useTrackingState({ enabled: role === 'engineer' && !blocked });

  // Nobody signs in here: MAEC One does (api/client.js sends the window there on a 401).
  if (blocked)
    return (
      <SignInStatus
        kind={blocked.kind}
        message={blocked.message}
        maecOneUrl={blocked.maecOneUrl || signOutUrl}
      />
    );
  if (loading) return <SignInStatus kind="checking" />;
  if (!user) return <SignInStatus kind="unavailable" message={error} />;

  return (
    <Suspense fallback={<div className="empty-state">Loading…</div>}>
      <Routes>
        <Route path="/" element={<HomeRedirect />} />
        <Route
          path="/my-activity"
          element={
            <WorkspaceRoute roles={['bu_head', 'engineer']}>
              <MyActivityPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/audit-log"
          element={
            <WorkspaceRoute roles={['bu_head']}>
              <AuditLogPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/created-projects"
          element={
            <WorkspaceRoute roles={['bu_head']}>
              <CreatedProjectsPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/create-project"
          element={
            <WorkspaceRoute roles={['bu_head']}>
              <CreateProjectPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/edit-project"
          element={
            <WorkspaceRoute roles={['bu_head']}>
              <EditProjectPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/resource-booking"
          element={
            <WorkspaceRoute roles={['lead', 'bu_head']}>
              <ResourceBookingPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/timeline-logs"
          element={
            <WorkspaceRoute roles={['lead', 'engineer', 'bu_head']}>
              <TimelineLogsPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/weekly-logs"
          element={
            <WorkspaceRoute roles={['lead', 'engineer', 'bu_head']}>
              <EngineerWeeklyLogsPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/wbs-structure"
          element={
            <WorkspaceRoute roles={['lead', 'engineer', 'bu_head']}>
              <WbsStructurePage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/task-details"
          element={
            <WorkspaceRoute roles={['lead', 'engineer', 'bu_head']}>
              <TaskDetailsPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/engineer-performance-dashboard"
          element={
            <WorkspaceRoute roles={['engineer']}>
              <PerformanceDashboardPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/executive-dashboard"
          element={
            <WorkspaceRoute roles={['lead', 'bu_head']}>
              <ExecutiveDashboardRouter />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/project-work-summary"
          element={
            <WorkspaceRoute roles={['bu_head']}>
              <ProjectWorkSummaryPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/sharepoint-mirror"
          element={
            <WorkspaceRoute roles={['lead', 'engineer', 'bu_head']}>
              <SharePointMirrorPage />
            </WorkspaceRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <QueryProvider>
          <AppRoutes />
        </QueryProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
