import { QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { createQueryClient } from '../api/queryClient';
import { useAuth } from '../AuthContext';

/**
 * Provides the query cache. Must sit inside AuthProvider:
 * - an expired session (401) logs the user out;
 * - the cache is cleared whenever the signed-in user changes, so one user's
 *   data is never shown to the next.
 */
export function QueryProvider({ children }) {
  const { user, logout } = useAuth();
  const logoutRef = useRef(logout);
  const [queryClient] = useState(() => createQueryClient(() => logoutRef.current()));
  const userId = user?.id ?? null;

  useEffect(() => {
    logoutRef.current = logout;
  }, [logout]);

  useEffect(() => {
    queryClient.clear();
  }, [userId, queryClient]);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
