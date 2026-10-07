import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { governanceApi } from '../api/governance';
import { queryKeys } from './queryKeys';

/** A project's health and governance figures (the BU Head, and the project's leads). */
export function useExecutiveDashboard(projectId, { enabled = true } = {}) {
  return useQuery({
    queryKey: queryKeys.executiveDashboard(projectId),
    queryFn: () => governanceApi.executiveDashboard(projectId),
    enabled: Boolean(projectId) && enabled,
  });
}

/** A lead's extension request: `{ requestedHours, justification }`. */
export function useRequestExtension(projectId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request) => governanceApi.requestExtension(projectId, request),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.executiveDashboard(projectId) }),
  });
}

export function useWorkSummary(projectId) {
  return useQuery({
    queryKey: queryKeys.workSummary(projectId),
    queryFn: () => governanceApi.workSummary(projectId),
    enabled: Boolean(projectId),
  });
}

function useDashboardMutation(projectId, mutationFn) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.executiveDashboard(projectId) });
      // Governance actions notify Leads and may clear the BU Head's pending alerts.
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications });
    },
  });
}

/** BU Head approves or rejects a Lead's extension request. */
export function useDecideExtension(projectId) {
  return useDashboardMutation(projectId, ({ requestId, decision, comments }) =>
    governanceApi.decideExtension(projectId, requestId, { decision, comments }),
  );
}

/** BU Head soft-locks the project's timesheets. */
export function useStopExecution(projectId) {
  return useDashboardMutation(projectId, ({ comments, discipline }) =>
    governanceApi.stopExecution(projectId, { comments, discipline }),
  );
}

/** BU Head lifts a soft lock (manual or automatic) without an extension. */
export function useResumeExecution(projectId) {
  return useDashboardMutation(projectId, ({ comments }) =>
    governanceApi.resumeExecution(projectId, { comments }),
  );
}
