/** The only module that calls fetch. Every request goes to the BFF on the same origin. */

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Anything with a zod-style `parse`, e.g. a zod schema. */
export interface Parser<T> {
  parse(data: unknown): T;
}

// A page on another origin cannot add a custom header without a CORS preflight, and the
// BFF answers none, so this header tells the BFF the request really comes from this app.
const CSRF_HEADER = "X-CSRF";

export async function bffRequest<T>(
  path: string,
  parser: Parser<T>,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set(CSRF_HEADER, "1");
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  // The HttpOnly session cookie is attached by the browser; this code never sees it
  // and never handles a token.
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  return parser.parse(await response.json());
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}
