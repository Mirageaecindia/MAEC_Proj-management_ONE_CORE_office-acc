import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { projectsApi } from '../api/projects';
import { queryKeys } from './queryKeys';

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

/** Everyone who can lead a project (any account with an employee record), for the lead dropdowns. */
export function useProjectLeads() {
  const { data, error, isLoading } = useQuery({
    queryKey: queryKeys.projectLeads,
    queryFn: projectsApi.leads,
    staleTime: 5 * 60_000,
  });
  return { leads: data ?? [], error, isLoading };
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

/** Edits change governance figures too, so the project's dashboards are refreshed. */
export function useUpdateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, payload }) => projectsApi.update(projectId, payload),
    onSuccess: (_project, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects });
      queryClient.invalidateQueries({ queryKey: queryKeys.executiveDashboard(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.workSummary(projectId) });
    },
  });
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
