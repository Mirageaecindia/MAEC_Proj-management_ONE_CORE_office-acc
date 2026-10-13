import { createContext, useContext, useEffect, useState } from 'react';
import { GATE_BLOCKED, api, reauthorizationWorked } from './api/client';

/**
 * Who is using the app. Nobody signs in here: MAEC One does, and the backend asks it
 * about every request. This asks /api/auth/me once: the person's profile in this app
 * (role, leads_projects) and where MAEC One is (`core_url`, for Sign out and Change
 * password). A 401 sends the window to MAEC One's sign-in (api/client.js); a refusal
 * (no seat, no profile here) is kept in `blocked` and shown instead of the app.
 */
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [blocked, setBlocked] = useState(null); // { kind, message } once MAEC One or this app refuses
  const [error, setError] = useState('');

  useEffect(() => {
    const onBlocked = (event) => setBlocked(event.detail);
    window.addEventListener(GATE_BLOCKED, onBlocked);
    return () => window.removeEventListener(GATE_BLOCKED, onBlocked);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .get('/api/auth/me')
      .then((me) => {
        if (cancelled) return;
        reauthorizationWorked();
        setUser(me);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        // 401: the window is on its way to MAEC One's sign-in; keep showing "loading".
        if (err?.status === 401) return;
        setError(err?.message || 'Could not reach Project Management.');
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const role = user ? user.role : null;
  // Leading is a role on a project; an engineer who leads any project also gets the lead pages.
  const leadsProjects = Boolean(user?.leads_projects);
  const coreUrl = (user?.core_url || '').replace(/\/+$/, '');

  return (
    <AuthContext.Provider
      value={{
        user,
        role,
        leadsProjects,
        loading,
        blocked,
        error,
        // Signing out at MAEC One signs out everywhere; its launcher has the button.
        signOutUrl: coreUrl ? `${coreUrl}/` : '',
        changePasswordUrl: coreUrl ? `${coreUrl}/change-password` : '',
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// The hook and its provider belong together; only Fast Refresh (dev HMR) minds a hook next to a component.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}