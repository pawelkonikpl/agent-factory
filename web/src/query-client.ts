import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { SESSION_QUERY_KEY } from "./hooks/use-session";
import { isUnauthorized } from "./services/bff-client";

const MAX_RETRIES = 2;

/**
 * A 401 from the BFF means the session is gone (expired, or the refresh token was
 * revoked). Re-reading the session then switches the UI back to the login screen.
 */
export function createQueryClient(): QueryClient {
  const handleError = (error: unknown): void => {
    if (isUnauthorized(error)) {
      void queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY });
    }
  };
  const queryClient = new QueryClient({
    queryCache: new QueryCache({ onError: handleError }),
    mutationCache: new MutationCache({ onError: handleError }),
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => !isUnauthorized(error) && failureCount < MAX_RETRIES,
      },
    },
  });
  return queryClient;
}
