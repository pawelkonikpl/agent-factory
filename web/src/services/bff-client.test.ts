import { describe, expect, it, vi } from "vitest";

import { createMockNote } from "../test/mocks";
import { stubFetch } from "../test/utils";
import { ApiError, bffRequest } from "./bff-client";

const passThrough = { parse: (data: unknown) => data };

describe("bffRequest", () => {
  it("sends X-CSRF and same-origin credentials", async () => {
    const fetchMock = stubFetch({ "GET /api/notes": { body: [] } });

    await bffRequest("/api/notes", passThrough);

    const init = fetchMock.mock.calls[0]?.[1];
    expect(new Headers(init?.headers).get("X-CSRF")).toBe("1");
    expect(init?.credentials).toBe("same-origin");
  });

  it("returns the parser's result for a 2xx JSON response", async () => {
    const note = createMockNote();
    stubFetch({ "GET /api/notes": { body: [note] } });
    const parser = { parse: vi.fn(() => "parsed") };

    await expect(bffRequest("/api/notes", parser)).resolves.toBe("parsed");
    expect(parser.parse).toHaveBeenCalledWith([note]);
  });

  it("throws an ApiError with the status of a non-2xx response", async () => {
    stubFetch({ "GET /api/notes": { status: 502 } });

    const error = await bffRequest("/api/notes", passThrough).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 502 });
  });
});
