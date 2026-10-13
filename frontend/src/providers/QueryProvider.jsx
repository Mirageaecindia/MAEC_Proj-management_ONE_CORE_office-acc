import { QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { createQueryClient } from '../api/queryClient';
import { useAuth } from '../AuthContext';

/**
 * Provides the query cache. Must sit inside AuthProvider: the cache is cleared whenever
 * the signed-in person changes, so one person's data is never shown to the next.
 * MAEC One's refusals (sign in again, no access) are handled by api/client.js.
 */
export function QueryProvider({ children }) {
  const { user } = useAuth();
  const [queryClient] = useState(() => createQueryClient());
  const userId = user?.id ?? null;

  useEffect(() => {
    queryClient.clear();
  }, [userId, queryClient]);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
