import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { projectsApi } from '../api/projects';
import { queryKeys } from './queryKeys';

export const LEAD_DISCIPLINES = ['electrical', 'mechanical', 'bim'];

/** Projects visible to the signed-in user; archived ones only for the BU Head, on request. */
export function useProjects({ includeArchived = false } = {}) {
  return useQuery({
    queryKey: queryKeys.projectList(includeArchived),
    queryFn: () => projectsApi.list({ includeArchived }),
  });
}

/** One project by id (the BU Head can read archived ones). */
export function useProject(projectId, { enabled = true } = {}) {
  return useQuery({
    queryKey: queryKeys.project(projectId),
    queryFn: () => projectsApi.get(projectId),
    enabled: Boolean(projectId) && enabled,
    retry: false,
  });
}

/** Lead accounts per discipline for the Create Project dropdowns: { electrical: [...], ... }. */
export function useProjectLeads() {
  return useQueries({
    queries: LEAD_DISCIPLINES.map((discipline) => ({
      queryKey: queryKeys.projectLeads(discipline),
      queryFn: () => projectsApi.leads(discipline),
      staleTime: 5 * 60_000,
    })),
    combine: (results) => ({
      leads: Object.fromEntries(LEAD_DISCIPLINES.map((discipline, i) => [discipline, results[i].data ?? []])),
      error: results.find((result) => result.error)?.error ?? null,
      isLoading: results.some((result) => result.isLoading),
    }),
  });
}

function useProjectMutation(mutationFn) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.projects }),
  });
}

export function useCreateProject() {
  return useProjectMutation(projectsApi.create);
}

/** Only succeeds for a project without history; the others are archived instead. */
export function useDeleteProject() {
  return useProjectMutation(projectsApi.remove);
}

export function useArchiveProject() {
  return useProjectMutation(({ projectId, comments }) => projectsApi.archive(projectId, comments));
}

export function useUnarchiveProject() {
  return useProjectMutation(({ projectId, comments }) => projectsApi.unarchive(projectId, comments));
}
