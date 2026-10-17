import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LoginScreen } from "./login-screen";

const AUTHORIZATION_FAILED = "Logowanie nie powiodło się. Spróbuj ponownie.";

const LOGIN_ERRORS = [
  ["access_denied", "Logowanie anulowane – nie udzielono zgody."],
  [
    "login_expired",
    "Logowanie wygasło albo zostało rozpoczęte w innej karcie. Spróbuj ponownie.",
  ],
  ["state_mismatch", "Odpowiedź logowania nie pasuje do tej przeglądarki. Spróbuj ponownie."],
  ["issuer_mismatch", "Odpowiedź przyszła od nieoczekiwanego serwera logowania."],
  ["invalid_id_token", "Serwer logowania zwrócił nieprawidłowy token."],
  ["authorization_failed", AUTHORIZATION_FAILED],
] as const;

function renderAt(url: string) {
  window.history.replaceState(null, "", url);
  render(<LoginScreen />);
}

describe("LoginScreen", () => {
  afterEach(() => {
    window.history.replaceState(null, "", "/");
  });

  it.each(LOGIN_ERRORS)("shows the message for login_error=%s", (code, message) => {
    renderAt(`/?login_error=${code}`);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveAttribute("data-testid", "login-error");
    expect(alert.textContent).toBe(message);
  });

  it("shows the authorization_failed message for an unknown code", () => {
    renderAt("/?login_error=something_else");

    expect(screen.getByTestId("login-error").textContent).toBe(AUTHORIZATION_FAILED);
  });

  it("shows no alert and the login button without login_error", () => {
    renderAt("/");

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zaloguj się" })).toBeInTheDocument();
  });
});
