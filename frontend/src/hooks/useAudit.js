import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { auditApi } from '../api/audit';
import { queryKeys } from './queryKeys';

/**
 * A page of the audit log. `everyone`: all people (BU Head); otherwise your own activity.
 * The previous page stays on screen while the next one loads, so the table never blanks.
 */
export function useAuditLog(filters, { everyone = false } = {}) {
  return useQuery({
    queryKey: queryKeys.audit(everyone ? 'everyone' : 'mine', filters),
    queryFn: () => (everyone ? auditApi.everyone(filters) : auditApi.mine(filters)),
    placeholderData: keepPreviousData,
  });
}
