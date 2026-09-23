import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { TOKEN_KEY } from './api/client';

const AuthContext = createContext(null);

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function fetchLogin(username, password) {
  const resp = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || 'Login failed.');
  return data;
}

async function fetchMe(token) {
  const resp = await fetch(`${API_BASE_URL}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) return null;
  return resp.json();
}

async function fetchLogout(token) {
  try {
    await fetch(`${API_BASE_URL}/api/auth/logout`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch { /* best effort */ }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch { return null; }
  });
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (token) {
        try {
          const me = await fetchMe(token);
          if (!cancelled) {
            if (me) {
              setUser(me);
            } else {
              try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
              setToken(null);
            }
          }
        } catch {
          if (!cancelled) {
            try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
            setToken(null);
          }
        }
      }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [token]);

  const login = useCallback(async (username, password) => {
    const data = await fetchLogin(username, password);
    try {
      localStorage.setItem(TOKEN_KEY, data.token);
    } catch { /* ignore */ }
    setToken(data.token);
    setUser({
      id: data.id ?? null,
      username: data.username,
      full_name: data.full_name || null,
      role: data.role,
      employee_id: data.engineer_id || null,
    });
    return data;
  }, []);

  const logout = useCallback(async () => {
    if (token) await fetchLogout(token);
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch { /* ignore */ }
    setToken(null);
    setUser(null);
    navigate('/login');
  }, [navigate, token]);

  const authHeaders = useCallback(() => {
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [token]);

  const role = user ? user.role : null;

  return (
    <AuthContext.Provider value={{
      user,
      role,
      token,
      loading,
      login,
      logout,
      authHeaders,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}