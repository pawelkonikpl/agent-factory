import { MutationObserver } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { SESSION_QUERY_KEY } from "./hooks/use-session";
import { createQueryClient } from "./query-client";
import { createNote, fetchNotes } from "./services/notes-api";
import { createMockUser } from "./test/mocks";
import { stubFetch } from "./test/utils";

function createClientWithSession() {
  const queryClient = createQueryClient();
  queryClient.setQueryData(SESSION_QUERY_KEY, { authenticated: true, user: createMockUser() });
  return queryClient;
}

describe("createQueryClient", () => {
  it("doesn't retry a query that answers 401", async () => {
    const fetchMock = stubFetch({ "GET /api/notes": { status: 401 } });
    const queryClient = createQueryClient();

    await expect(
      queryClient.fetchQuery({ queryKey: ["notes"], queryFn: fetchNotes }),
    ).rejects.toMatchObject({ status: 401 });

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("invalidates the session query when a query answers 401", async () => {
    stubFetch({ "GET /api/notes": { status: 401 } });
    const queryClient = createClientWithSession();

    await expect(
      queryClient.fetchQuery({ queryKey: ["notes"], queryFn: fetchNotes }),
    ).rejects.toMatchObject({ status: 401 });

    expect(queryClient.getQueryState(SESSION_QUERY_KEY)?.isInvalidated).toBe(true);
  });

  it("invalidates the session query when a mutation answers 401", async () => {
    stubFetch({ "POST /api/notes": { status: 401 } });
    const queryClient = createClientWithSession();
    const mutation = new MutationObserver(queryClient, { mutationFn: createNote });

    await expect(mutation.mutate("Notatka")).rejects.toMatchObject({ status: 401 });

    expect(queryClient.getQueryState(SESSION_QUERY_KEY)?.isInvalidated).toBe(true);
  });
});
