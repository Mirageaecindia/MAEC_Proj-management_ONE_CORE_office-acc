import { useQuery } from '@tanstack/react-query';
import { serverDateApi } from '../api/serverDate';
import { queryKeys } from './queryKeys';

const REFRESH_MS = 5 * 60_000;

/** The browser's UTC date, until the server has answered. */
const browserUtcDate = () => new Date().toISOString().slice(0, 10);

/**
 * "Today" as the server sees it: the UTC date every row, week and deadline in the app is
 * built on. The browser's local date differs from it between midnight and 05:30 India time,
 * so no page decides a day or a week from the browser clock.
 *
 * Returns `todayStr` ('YYYY-MM-DD'), `today` (that calendar day as a local-midnight Date, for
 * the week helpers) and `loaded` (the server has answered).
 */
export function useServerToday() {
  const { data } = useQuery({
    queryKey: queryKeys.serverDate,
    queryFn: serverDateApi.get,
    staleTime: 60_000,
    refetchInterval: REFRESH_MS,
  });
  const todayStr = data?.date ?? browserUtcDate();
  return { todayStr, today: new Date(`${todayStr}T00:00:00`), loaded: Boolean(data) };
}
