import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './api.js';

export const CREDITS_KEY = ['billing', 'account'];

/**
 * The signed-in user's credit balance. Returns undefined data while loading
 * and when signed out (the endpoint is 401 for anonymous callers), so callers
 * should treat a missing balance as "don't show a number" rather than zero.
 */
export function useCredits(enabled = true) {
  return useQuery({
    queryKey: CREDITS_KEY,
    queryFn: () => api.get('/billing/account'),
    enabled,
    retry: false,        // 401 when signed out; don't hammer it
    staleTime: 30_000,
  });
}

/** Refetch the balance — call after anything that spends or buys credits. */
export function useRefreshCredits() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: CREDITS_KEY });
}
