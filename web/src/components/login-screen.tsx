import { startLogin } from "../services/session-api";

const LOGIN_ERROR_MESSAGES: Record<string, string> = {
  access_denied: "Logowanie anulowane – nie udzielono zgody.",
  login_expired: "Logowanie wygasło albo zostało rozpoczęte w innej karcie. Spróbuj ponownie.",
  state_mismatch: "Odpowiedź logowania nie pasuje do tej przeglądarki. Spróbuj ponownie.",
  issuer_mismatch: "Odpowiedź przyszła od nieoczekiwanego serwera logowania.",
  invalid_id_token: "Serwer logowania zwrócił nieprawidłowy token.",
  authorization_failed: "Logowanie nie powiodło się. Spróbuj ponownie.",
};

function readLoginError(): string | null {
  const code = new URLSearchParams(window.location.search).get("login_error");
  if (code === null) {
    return null;
  }
  return LOGIN_ERROR_MESSAGES[code] ?? LOGIN_ERROR_MESSAGES.authorization_failed ?? null;
}

export function LoginScreen() {
  const loginError = readLoginError();

  return (
    <main className="card">
      <h1>Notatki</h1>
      <p>
        Logowanie odbywa się w Keycloaku. Tokeny zostają w BFF, a przeglądarka dostaje tylko
        ciasteczko sesji niedostępne dla JavaScriptu.
      </p>
      {loginError !== null && (
        <p className="error" role="alert" data-testid="login-error">
          {loginError}
        </p>
      )}
      <button type="button" onClick={() => startLogin("/")} data-testid="login-button">
        Zaloguj się
      </button>
    </main>
  );
}
