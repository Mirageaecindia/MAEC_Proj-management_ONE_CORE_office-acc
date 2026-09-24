import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';
import { MaecHeader } from './components/MaecHeader';
import { LoginPage } from './pages/LoginPage';
import { QueryProvider } from './providers/QueryProvider';

// Pages are code-split: each role only downloads the screens it opens.
const lazyPage = (load, name) => lazy(() => load().then((module) => ({ default: module[name] })));
const CreateProjectPage = lazyPage(() => import('./features/bu-head/CreateProjectPage'), 'CreateProjectPage');
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
const LeadExecutiveDashboardPage = lazyPage(
  () => import('./pages/lead/ExecutiveDashboardPage'),
  'ExecutiveDashboardPage',
);
const EngineerPerformanceDashboardPage = lazyPage(
  () => import('./pages/engineer/EngineerPerformanceDashboardPage'),
  'EngineerPerformanceDashboardPage',
);
const ResourceBookingPage = lazyPage(
  () => import('./pages/shared/ResourceBookingPage'),
  'ResourceBookingPage',
);
const TimelineLogsPage = lazyPage(() => import('./pages/shared/TimelineLogsPage'), 'TimelineLogsPage');
const WbsStructurePage = lazyPage(() => import('./pages/shared/WbsStructurePage'), 'WbsStructurePage');
const EngineerWeeklyLogsPage = lazyPage(() => import('./pages/shared/EngineerWeeklyLogsPage'), 'EngineerWeeklyLogsPage');
const TaskDetailsPage = lazyPage(() => import('./pages/shared/TaskDetailsPage'), 'TaskDetailsPage');

function ExecutiveDashboardRouter() {
  const { role } = useAuth();
  if (role === 'lead') return <LeadExecutiveDashboardPage />;
  return <BuHeadExecutiveDashboardPage />;
}

function HomeRedirect() {
  const { role } = useAuth();
  if (role === 'engineer') return <Navigate to="/wbs-structure" replace />;
  if (role === 'lead') return <Navigate to="/resource-booking" replace />;
  return <Navigate to="/created-projects" replace />;
}

function ProtectedRoute({ children, roles }) {
  const { role } = useAuth();
  if (!role || !roles.includes(role)) return <Navigate to="/" replace />;
  return children;
}

function WorkspaceRoute({ children, roles, subtitle }) {
  return (
    <ProtectedRoute roles={roles}>
      <MaecHeader subtitle={subtitle} />
      {children}
    </ProtectedRoute>
  );
}

function AppRoutes() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="login-page">
        <div className="login-card">
          <div className="login-logo">MAEC</div>
          <div className="login-loading">Restoring session…</div>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Suspense fallback={<div className="empty-state">Loading…</div>}>
      <Routes>
        <Route path="/" element={<HomeRedirect />} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route
          path="/created-projects"
          element={
            <WorkspaceRoute roles={['bu_head']} subtitle="Created Projects">
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
            <WorkspaceRoute roles={['lead', 'engineer', 'bu_head']} subtitle="Timeline & Logs">
              <TimelineLogsPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/weekly-logs"
          element={
            <WorkspaceRoute roles={['lead', 'engineer', 'bu_head']} subtitle="Engineer Weekly Logs">
              <EngineerWeeklyLogsPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/wbs-structure"
          element={
            <WorkspaceRoute roles={['lead', 'engineer', 'bu_head']} subtitle="MEP Enterprise Workspace">
              <WbsStructurePage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/task-details"
          element={
            <WorkspaceRoute roles={['lead', 'engineer', 'bu_head']} subtitle="WBS & Task Details">
              <TaskDetailsPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/engineer-performance-dashboard"
          element={
            <WorkspaceRoute roles={['engineer']} subtitle="Engineer Performance Dashboard">
              <EngineerPerformanceDashboardPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/executive-dashboard"
          element={
            <WorkspaceRoute roles={['lead', 'bu_head']} subtitle="Executive Dashboard">
              <ExecutiveDashboardRouter />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/project-work-summary"
          element={
            <WorkspaceRoute roles={['bu_head']} subtitle="Project Work Summary">
              <ProjectWorkSummaryPage />
            </WorkspaceRoute>
          }
        />
        <Route
          path="/sharepoint-mirror"
          element={
            <WorkspaceRoute roles={['lead', 'engineer', 'bu_head']} subtitle="SharePoint Integration">
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
