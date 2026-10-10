import { z } from "zod";

import { bffRequest } from "./bff-client";

const userSchema = z.object({
  sub: z.string(),
  name: z.string().nullable(),
  email: z.string().nullable(),
});

const sessionSchema = z.object({
  authenticated: z.boolean(),
  user: userSchema.nullable(),
});

const logoutSchema = z.object({ logout_url: z.url() });

export type User = z.infer<typeof userSchema>;
export type Session = z.infer<typeof sessionSchema>;

export function fetchSession(): Promise<Session> {
  return bffRequest("/bff/session", sessionSchema);
}

/** Full-page navigation: the BFF redirects the browser to the authorization server. */
export function startLogin(returnTo: string = window.location.pathname): void {
  window.location.assign(`/bff/login?${new URLSearchParams({ returnTo })}`);
}

/** Ends the BFF session, then sends the browser to the IdP to end the SSO session too. */
export async function logout(): Promise<void> {
  const { logout_url: logoutUrl } = await bffRequest("/bff/logout", logoutSchema, {
    method: "POST",
  });
  window.location.assign(logoutUrl);
}
