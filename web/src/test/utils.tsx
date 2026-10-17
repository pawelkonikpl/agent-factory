import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions, type RenderResult, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { expect, onTestFinished, vi } from "vitest";

/** No retries and no caching, so every test sees its own requests and fails fast. */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

interface RenderWithProvidersOptions {
  queryClient?: QueryClient;
}

export function renderWithProviders(
  ui: ReactElement,
  { queryClient = createTestQueryClient() }: RenderWithProvidersOptions = {},
): RenderResult & { queryClient: QueryClient } {
  const options: RenderOptions = {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  };
  return { ...render(ui, options), queryClient };
}

interface StubResponse {
  status?: number;
  body?: unknown;
}

type StubRoute = StubResponse | ((request: Request) => StubResponse | Promise<StubResponse>);

/**
 * Stubs fetch with routes keyed by "<METHOD> <path>", e.g. "GET /api/notes". The path is
 * the pathname, so the query string doesn't take part in matching.
 */
export function stubFetch(routes: Record<string, StubRoute>) {
  const unexpected: string[] = [];
  // TanStack Query turns a rejected fetch into an error state, so a rejection alone
  // wouldn't fail the test: this check does, even when the code under test caught it.
  onTestFinished(() => {
    if (unexpected.length > 0) {
      throw new Error(`stubFetch: unexpected requests: ${unexpected.join(", ")}`);
    }
  });
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const request = new Request(
        input instanceof Request ? input : new URL(input, window.location.href),
        init,
      );
      const route = `${request.method} ${new URL(request.url).pathname}`;
      const answer = routes[route];
      if (answer === undefined) {
        unexpected.push(route);
        throw new Error(`stubFetch: no route for ${route}`);
      }
      const { status = 200, body } = typeof answer === "function" ? await answer(request) : answer;
      return body === undefined ? new Response(null, { status }) : Response.json(body, { status });
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export async function waitForQueriesToSettle(queryClient: QueryClient): Promise<void> {
  await waitFor(() => {
    expect(queryClient.isFetching()).toBe(0);
    expect(queryClient.isMutating()).toBe(0);
  });
}
