import { useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * The project the user is working on stays chosen across refreshes and tabs
 * (decided 2026-10-09): a page opens on the project in its link, else the one
 * last shown on any page, else the newest. The choice lives in this browser only.
 */
const KEY = 'promanage.projectId';

function remembered() {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null; // storage blocked: fall back to the newest project
  }
}

export function rememberProject(projectId) {
  if (projectId == null || projectId === '') return;
  try {
    localStorage.setItem(KEY, String(projectId));
  } catch {
    /* storage blocked: nothing to remember */
  }
}

/** The project to show: the one asked for, else the remembered one, else the newest (first). */
export function pickProject(projects, requestedId) {
  const list = Array.isArray(projects) ? projects : [];
  const find = (id) => (id == null || id === '' ? undefined : list.find((p) => String(p.id) === String(id)));
  return find(requestedId) ?? find(remembered()) ?? list[0] ?? null;
}

/**
 * For pages that hold the chosen project in their own state: remembers whatever the page
 * shows, and returns `choose(id)` for the switcher, which also puts `?projectId=` in the
 * address so a refresh reopens the same project.
 */
export function useProjectChoice(selectedId, setSelectedId) {
  const [, setSearchParams] = useSearchParams();
  useEffect(() => rememberProject(selectedId), [selectedId]);
  return useCallback(
    (projectId) => {
      if (!projectId) return; // "Select project" is not a project: keep the one shown
      setSelectedId(String(projectId));
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          next.set('projectId', String(projectId));
          return next;
        },
        { replace: true },
      );
    },
    [setSelectedId, setSearchParams],
  );
}
