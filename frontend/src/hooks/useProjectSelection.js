import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useProject, useProjects } from './useProjects';

/**
 * The project a page is showing, kept in the URL (`?projectId=`) so links,
 * refreshes and NEXT buttons land on the same project. Without a parameter
 * the most recent project is selected.
 *
 * The switcher lists active projects. A project that isn't in that list (an
 * archived one the BU Head opened from Created Projects) is fetched on its own
 * and shown at the top of the switcher.
 */
export function useProjectSelection() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: projects = [], isLoading, error } = useProjects();

  const requestedId = searchParams.get('projectId');
  const listed = requestedId ? projects.find((p) => String(p.id) === requestedId) : projects[0];
  const { data: unlisted = null } = useProject(requestedId, { enabled: !isLoading && !listed });
  const project = listed ?? unlisted ?? null;
  const options = !listed && unlisted ? [unlisted, ...projects] : projects;

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

  return { projects: options, project, projectId: project?.id ?? null, selectProject, isLoading, error };
}
