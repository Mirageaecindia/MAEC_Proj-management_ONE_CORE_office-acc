// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react';
import { useState } from 'react';
import { MemoryRouter, useSearchParams } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { pickProject, rememberProject, useProjectChoice } from './currentProject';

const PROJECTS = [
  { id: 9, name: 'Newest' },
  { id: 4, name: 'DCH - F14' },
  { id: 2, name: 'Test' },
];

describe('the project being worked on', () => {
  beforeEach(() => localStorage.clear());
  afterEach(cleanup);

  it('opens the project in the link, else the one last shown, else the newest', () => {
    expect(pickProject(PROJECTS).id).toBe(9);

    rememberProject(4);
    expect(pickProject(PROJECTS).id).toBe(4); // a refresh or another tab stays on it
    expect(pickProject(PROJECTS, '2').id).toBe(2); // a link names its own project
    expect(pickProject(PROJECTS, 77).id).toBe(4); // a project no longer listed falls back
    expect(pickProject([{ id: 9 }]).id).toBe(9); // the remembered one is gone: the newest
    expect(pickProject([])).toBeNull();
  });

  it('a switch on the page is remembered and put in the address', () => {
    const { result } = renderHook(
      () => {
        const [selectedId, setSelectedId] = useState('9');
        const choose = useProjectChoice(selectedId, setSelectedId);
        return { selectedId, choose, url: useSearchParams()[0].get('projectId') };
      },
      {
        wrapper: ({ children }) => (
          <MemoryRouter initialEntries={['/wbs-structure?projectId=9']}>{children}</MemoryRouter>
        ),
      },
    );
    expect(localStorage.getItem('promanage.projectId')).toBe('9'); // what the page shows is remembered

    act(() => result.current.choose(4));

    expect(result.current.selectedId).toBe('4');
    expect(result.current.url).toBe('4');
    expect(pickProject(PROJECTS).id).toBe(4);
  });
});
