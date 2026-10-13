import { QueryClient } from '@tanstack/react-query';
import { ApiError } from './client';

const isClientError = (error) => error instanceof ApiError && error.status >= 400 && error.status < 500;

/**
 * App-wide TanStack Query client.
 *
 * - Data is considered fresh for 30 s and refetched when the window regains
 *   focus, replacing the old fixed-interval polling.
 * - 4xx responses are never retried; network/5xx errors retry once.
 * - A refusal by MAEC One (401: sign in; 403: no access) is handled for every request
 *   by the client itself (api/client.js `handleGateRefusal`), not here.
 */
export function createQueryClient() {
  return new QueryClient({
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
