import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';
import { ApiError } from './client';

const isClientError = (error) => error instanceof ApiError && error.status >= 400 && error.status < 500;

/**
 * App-wide TanStack Query client.
 *
 * - Data is considered fresh for 30 s and refetched when the window regains
 *   focus, replacing the old fixed-interval polling.
 * - 4xx responses are never retried; network/5xx errors retry once.
 * - A 401 anywhere means the session expired: `onUnauthorized` logs out.
 */
export function createQueryClient(onUnauthorized) {
  const handleError = (error) => {
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
  };
  return new QueryClient({
    queryCache: new QueryCache({ onError: handleError }),
    mutationCache: new MutationCache({ onError: handleError }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: true,
        retry: (failureCount, error) => !isClientError(error) && failureCount < 1,
      },
      mutations: { retry: false },
    },
  });
}
