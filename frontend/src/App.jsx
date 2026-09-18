import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';
import { MaecHeader, PlaceholderPage } from './components/MaecHeader';
import { LoginPage } from './pages/LoginPage';
import { CreateProjectPage } from './pages/bu_head/CreateProjectPage';
import { CreatedProjectsPage } from './pages/bu_head/CreatedProjectsPage';
import { ExecutiveDashboardPage as BuHeadExecutiveDashboardPage } from './pages/bu_head/ExecutiveDashboardPage';
import { ExecutiveDashboardPage as LeadExecutiveDashboardPage } from './pages/lead/ExecutiveDashboardPage';
import { ProjectWorkSummaryPage } from './pages/bu_head/ProjectWorkSummaryPage';
import { EngineerPerformanceDashboardPage } from './pages/engineer/EngineerPerformanceDashboardPage';
import { ResourceBookingPage } from './pages/shared/ResourceBookingPage';
import { TimelineLogsPage } from './pages/shared/TimelineLogsPage';
import { WbsStructurePage } from './pages/shared/WbsStructurePage';
import { TaskDetailsPage } from './pages/shared/TaskDetailsPage';
import { SharePointMirrorPage } from './pages/shared/SharePointMirrorPage';

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
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route
        path="/login"
        element={<Navigate to="/" replace />}
      />
      <Route
        path="/created-projects"
        element={<WorkspaceRoute roles={['bu_head']} subtitle="Created Projects"><CreatedProjectsPage /></WorkspaceRoute>}
      />
      <Route
        path="/create-project"
        element={<WorkspaceRoute roles={['bu_head']}><CreateProjectPage /></WorkspaceRoute>}
      />
      <Route
        path="/resource-booking"
        element={<WorkspaceRoute roles={['lead', 'bu_head']}><ResourceBookingPage /></WorkspaceRoute>}
      />
      <Route
        path="/timeline-logs"
        element={<WorkspaceRoute roles={['lead', 'engineer', 'bu_head']} subtitle="Timeline & Logs"><TimelineLogsPage /></WorkspaceRoute>}
      />
      <Route
        path="/wbs-structure"
        element={<WorkspaceRoute roles={['lead', 'engineer', 'bu_head']} subtitle="MEP Enterprise Workspace"><WbsStructurePage /></WorkspaceRoute>}
      />
      <Route
        path="/task-details"
        element={<WorkspaceRoute roles={['lead', 'engineer', 'bu_head']} subtitle="WBS & Task Details"><TaskDetailsPage /></WorkspaceRoute>}
      />
      <Route
        path="/engineer-performance-dashboard"
        element={<WorkspaceRoute roles={['engineer']} subtitle="Engineer Performance Dashboard"><EngineerPerformanceDashboardPage /></WorkspaceRoute>}
      />
      <Route
        path="/executive-dashboard"
        element={<WorkspaceRoute roles={['lead', 'bu_head']} subtitle="Executive Dashboard"><ExecutiveDashboardRouter /></WorkspaceRoute>}
      />
      <Route
        path="/project-work-summary"
        element={<WorkspaceRoute roles={['bu_head']} subtitle="Project Work Summary"><ProjectWorkSummaryPage /></WorkspaceRoute>}
      />
      <Route
        path="/sharepoint-mirror"
        element={<WorkspaceRoute roles={['lead', 'engineer', 'bu_head']} subtitle="SharePoint Integration"><SharePointMirrorPage /></WorkspaceRoute>}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}