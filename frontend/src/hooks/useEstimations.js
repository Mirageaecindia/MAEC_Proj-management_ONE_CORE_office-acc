import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { estimationsApi } from '../api/estimations';
import { queryKeys } from './queryKeys';

/** The staff codes a row can take, each with its role (a fixed list: read once). */
export function useEstimationCodes() {
  const { data, error } = useQuery({
    queryKey: queryKeys.estimationCodes,
    queryFn: estimationsApi.codes,
    staleTime: Infinity,
  });
  return { codes: data ?? [], error };
}

/** The saved estimations, the most recently changed first. */
export function useEstimations() {
  return useQuery({ queryKey: queryKeys.estimationList, queryFn: estimationsApi.list });
}

export function useEstimation(estimationId) {
  return useQuery({
    queryKey: queryKeys.estimation(estimationId),
    queryFn: () => estimationsApi.get(estimationId),
    enabled: Boolean(estimationId),
    retry: false,
    refetchOnWindowFocus: false, // the page edits a copy of it: a refetch must not undo unsaved changes
  });
}

/** Saves a new estimation, or the whole grid of an existing one (`estimationId`). */
export function useSaveEstimation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ estimationId, payload }) =>
      estimationId ? estimationsApi.update(estimationId, payload) : estimationsApi.create(payload),
    onSuccess: (saved) => {
      queryClient.setQueryData(queryKeys.estimation(saved.id), saved);
      queryClient.invalidateQueries({ queryKey: queryKeys.estimationList });
    },
  });
}

export function useDeleteEstimation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: estimationsApi.remove,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.estimations }),
  });
}
