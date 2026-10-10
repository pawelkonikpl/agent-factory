import { type FormEvent, useState } from "react";

import { useCreateNote, useNotes } from "../hooks/use-notes";

const NOTE_MAX_LENGTH = 500;
const dateFormat = new Intl.DateTimeFormat("pl-PL", { dateStyle: "short", timeStyle: "short" });

export function NotesPanel() {
  const notes = useNotes();
  const createNote = useCreateNote();
  const [text, setText] = useState("");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = text.trim();
    if (trimmed === "") {
      return;
    }
    createNote.mutate(trimmed, { onSuccess: () => setText("") });
  };

  return (
    <main className="card">
      <h2>Twoje notatki</h2>
      <form onSubmit={handleSubmit} className="note-form">
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          maxLength={NOTE_MAX_LENGTH}
          placeholder="Nowa notatka"
          aria-label="Treść notatki"
          data-testid="note-input"
        />
        <button type="submit" disabled={createNote.isPending} data-testid="note-submit">
          Dodaj
        </button>
      </form>
      {createNote.isError && <p className="error">Nie udało się zapisać notatki.</p>}

      {notes.isPending && <p className="muted">Ładowanie…</p>}
      {notes.isError && <p className="error">Nie udało się pobrać notatek.</p>}
      {notes.isSuccess && notes.data.length === 0 && (
        <p className="muted">Brak notatek. Dodaj pierwszą.</p>
      )}
      {notes.isSuccess && (
        <ul className="notes" data-testid="notes-list">
          {notes.data.map((note) => (
            <li key={note.id}>
              <span>{note.text}</span>
              <time dateTime={note.created_at} className="muted">
                {dateFormat.format(new Date(note.created_at))}
              </time>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
