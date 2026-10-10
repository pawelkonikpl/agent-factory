import { useLogout } from "../hooks/use-session";
import type { User } from "../services/session-api";

interface HeaderBarProps {
  user: User;
}

export function HeaderBar({ user }: HeaderBarProps) {
  const logout = useLogout();

  return (
    <>
      <header className="header">
        <span data-testid="user-name">{user.name ?? user.sub}</span>
        {user.email !== null && <span className="muted">{user.email}</span>}
        <button
          type="button"
          onClick={() => logout.mutate()}
          disabled={logout.isPending}
          data-testid="logout-button"
        >
          Wyloguj
        </button>
      </header>
      {logout.isError && (
        <p className="error" role="alert" data-testid="logout-error">
          Nie udało się wylogować. Spróbuj ponownie.
        </p>
      )}
    </>
  );
}
