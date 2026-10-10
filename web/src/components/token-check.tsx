/** Shows, for learning purposes, what JavaScript on this page can see: no tokens. */
export function TokenCheck() {
  const visibleCookies = document.cookie === "" ? "(puste)" : document.cookie;
  const storageEntries = window.localStorage.length + window.sessionStorage.length;

  return (
    <aside className="card muted" data-testid="token-check">
      <h2>Co widzi JavaScript na tej stronie</h2>
      <p>
        <code>document.cookie</code>: {visibleCookies}
      </p>
      <p>Wpisy w localStorage i sessionStorage: {storageEntries}</p>
      <p>Ciasteczko sesji ma flagę HttpOnly, a access token i refresh token są tylko w BFF.</p>
    </aside>
  );
}
