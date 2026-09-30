// @vitest-environment jsdom
import { QueryClient, QueryClientProvider, focusManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useServerToday } from './useServerToday';

let serverDay = '2026-09-30';

function wrapper({ children }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('useServerToday', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response(JSON.stringify({ date: serverDay }), { status: 200 }))),
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('gives the server’s day and its Monday, not the browser’s', async () => {
    const { result } = renderHook(() => useServerToday(), { wrapper });

    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.todayStr).toBe('2026-09-30');
    expect(result.current.today.getDate()).toBe(30); // a local-midnight Date for the week helpers
  });

  it('asks again when the window regains focus, so an open tab crosses the day boundary', async () => {
    const { result } = renderHook(() => useServerToday(), { wrapper });
    await waitFor(() => expect(result.current.loaded).toBe(true));
    serverDay = '2026-10-01';

    act(() => {
      focusManager.setFocused(false); // the tab went to the background overnight
      focusManager.setFocused(true); // and comes back in the morning
    });

    await waitFor(() => expect(result.current.todayStr).toBe('2026-10-01'));
  });
});
