import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { correctionsApi } from '../api/corrections';
import { queryKeys } from './queryKeys';

/** A project's corrections: the pending ones first, then recent decisions. */
export function useCorrections(projectId) {
  return useQuery({
    queryKey: queryKeys.corrections(projectId),
    queryFn: () => correctionsApi.list(projectId),
    enabled: Boolean(projectId),
  });
}

function useCorrectionMutation(projectId, mutationFn) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.corrections(projectId) }),
  });
}

/** The engineer asks to move hours: `{ work_date, from_task_id, to_task_id, hours, note }`. */
export function useProposeCorrection(projectId) {
  return useCorrectionMutation(projectId, (body) => correctionsApi.propose(projectId, body));
}

/** Approve, reject or withdraw a correction: `{ id, action, reason }`. */
export function useDecideCorrection(projectId) {
  return useCorrectionMutation(projectId, ({ id, action, reason }) =>
    correctionsApi.decide(id, action, reason),
  );
}
