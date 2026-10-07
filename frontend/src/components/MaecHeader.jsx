import { CircleUserRound, History, KeyRound, LogOut } from 'lucide-react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useState, useRef, useEffect } from 'react';
import { useAuth } from '../AuthContext';
import { useLeadsProjects } from '../hooks/useProjects';
import { canAccess } from '../utils/access';
import maecLogo from '../assets/maec-logo.png';
import { NotificationBell } from './NotificationBell';

const allTabs = [
  { label: 'Projects', path: '/created-projects', roles: ['bu_head'] },
  { label: 'Create Project', path: '/create-project', roles: ['bu_head'] },
  { label: 'Resource Booking', path: '/resource-booking', roles: ['lead', 'bu_head'] },
  { label: 'WBS Structure', path: '/wbs-structure', roles: ['lead', 'engineer', 'bu_head'] },
  { label: 'Timeline & Logs', path: '/timeline-logs', roles: ['lead', 'engineer', 'bu_head'] },
  { label: 'Executive Dashboard', path: '/executive-dashboard', roles: ['bu_head'] },
  { label: 'Work Summary', path: '/project-work-summary', roles: ['bu_head'] },
  { label: 'Audit Log', path: '/audit-log', roles: ['bu_head'] },
  // Leads (engineers who lead a project) and engineers: one dashboard, the project they lead included.
  { label: 'Performance Dashboard', path: '/engineer-performance-dashboard', roles: ['engineer'] },
  { label: 'SharePoint Mirror', path: '/sharepoint-mirror', roles: ['lead', 'engineer', 'bu_head'] },
];

const ROLE_LABELS = {
  bu_head: 'BU Head',
  engineer: 'Engineer',
};

/** The application's name, the same on every page. */
const APP_NAME = 'ProManage';

export function MaecHeader() {
  const [accountOpen, setAccountOpen] = useState(false);
  const { user, role, logout } = useAuth();
  const leadsProjects = useLeadsProjects();
  const menuRef = useRef(null);
  const navigate = useNavigate();

  const visibleTabs = allTabs.filter((tab) => canAccess(tab.roles, { role, leadsProjects }));

  const displayName = user?.full_name || user?.username || 'User';
  const roleLabel = role === 'engineer' && leadsProjects ? 'Lead / Engineer' : ROLE_LABELS[role] || '';
  // Governance alerts, booking and extension decisions go to the BU Head and project leads.
  const notified = role === 'bu_head' || leadsProjects;

  const initials = displayName
    .split(' ')
    .filter(Boolean)
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  useEffect(() => {
    if (!accountOpen) return;
    function handleClick(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setAccountOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [accountOpen]);

  function handleLogout() {
    setAccountOpen(false);
    logout();
  }

  return (
    // The logo bar and the tabs stay at the top of the window while the page scrolls.
    <div className="masthead">
      <header className="topbar">
        <NavLink to="/" className="brand" aria-label="MAEC home">
          <img src={maecLogo} alt="MAEC" className="logo" />
          <span className="brand-divider" aria-hidden="true" />
          <strong className="brand-title">{APP_NAME}</strong>
        </NavLink>
        <div className="user-menu">
          {notified && <NotificationBell />}
          <div className="account-control" ref={menuRef}>
            <button
              className="account-pill"
              type="button"
              aria-expanded={accountOpen}
              aria-haspopup="menu"
              onClick={() => setAccountOpen((open) => !open)}
            >
              <span className="avatar">{initials}</span>
              <span className="account-name">
                <span className="account-name-text">{displayName}</span>
                {roleLabel && <small className="account-role">{roleLabel}</small>}
              </span>
            </button>
            {accountOpen && (
              <div className="account-menu" role="menu">
                <button type="button" role="menuitem" disabled style={{ opacity: 0.5, cursor: 'default' }}>
                  {displayName}
                  {roleLabel && <small> — {roleLabel}</small>}
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setAccountOpen(false);
                    navigate('/change-password');
                  }}
                >
                  <KeyRound size={13} /> Change password
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setAccountOpen(false);
                    navigate('/my-activity');
                  }}
                >
                  <History size={13} /> My activity
                </button>
                <button className="account-logout" type="button" role="menuitem" onClick={handleLogout}>
                  <LogOut size={13} /> Logout
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      <nav className="tab-nav" aria-label="Project management sections">
        <div className="tab-inner">
          {visibleTabs.map((tab) => (
            <NavLink
              key={tab.path}
              to={tab.path}
              className={({ isActive }) => `tab-link${isActive ? ' active' : ''}`}
            >
              {tab.label}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}

export function PlaceholderPage({ title }) {
  return (
    <main className="placeholder-page">
      <CircleUserRound size={28} />
      <h1>{title}</h1>
      <p>This workspace is reserved for a future MAEC module.</p>
    </main>
  );
}