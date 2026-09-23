import { useQuery } from '@tanstack/react-query';
import { sharepointApi } from '../api/sharepoint';
import { queryKeys } from './queryKeys';

/**
 * Live SharePoint folder data. Each fetch makes several Microsoft Graph calls,
 * so it is not refetched on window focus; the page offers an explicit resync.
 */
export function useSharePointMirror(projectId) {
  return useQuery({
    queryKey: queryKeys.sharepointMirror(projectId),
    queryFn: () => sharepointApi.mirror(projectId),
    enabled: Boolean(projectId),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}
