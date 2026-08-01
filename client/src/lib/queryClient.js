import { QueryClient } from '@tanstack/react-query';

/** Shared server-state cache. Feeds, library, and story data read through this
 *  so counts/lists stay in sync and optimistic social updates land here later. */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 15_000,
    },
  },
});
