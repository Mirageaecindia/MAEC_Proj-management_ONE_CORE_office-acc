import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useProjects } from './useProjects';

/**
 * The project a page is showing, kept in the URL (`?projectId=`) so links,
 * refreshes and NEXT buttons land on the same project. Without a parameter
 * the most recent project is selected.
 */
export function useProjectSelection() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: projects = [], isLoading, error } = useProjects();

  const requestedId = searchParams.get('projectId');
  const project = requestedId
    ? (projects.find((p) => String(p.id) === requestedId) ?? null)
    : (projects[0] ?? null);

  const selectProject = useCallback(
    (projectId) =>
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          next.set('projectId', String(projectId));
          return next;
        },
        { replace: true },
      ),
    [setSearchParams],
  );

  return { projects, project, projectId: project?.id ?? null, selectProject, isLoading, error };
}
