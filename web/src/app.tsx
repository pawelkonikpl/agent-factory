import { HeaderBar } from "./components/header-bar";
import { LoginScreen } from "./components/login-screen";
import { NotesPanel } from "./components/notes-panel";
import { TokenCheck } from "./components/token-check";
import { useSession } from "./hooks/use-session";

export function App() {
  const session = useSession();

  if (session.isPending) {
    return <p className="muted">Sprawdzanie sesji…</p>;
  }
  if (session.isError) {
    return <p className="error">Nie udało się sprawdzić sesji.</p>;
  }
  if (!session.data.authenticated || session.data.user === null) {
    return <LoginScreen />;
  }
  return (
    <>
      <HeaderBar user={session.data.user} />
      <NotesPanel />
      <TokenCheck />
    </>
  );
}
