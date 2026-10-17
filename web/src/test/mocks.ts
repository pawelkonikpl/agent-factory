import type { Note } from "../services/notes-api";
import type { User } from "../services/session-api";

// The defaults are the stub values AGENTS.md gives for looking at signed-in pages.

export function createMockUser(overrides?: Partial<User>): User {
  return { sub: "alice", name: "Alice Example", email: "alice@example.com", ...overrides };
}

export function createMockNote(overrides?: Partial<Note>): Note {
  return { id: "1", text: "Notatka", created_at: "2026-10-10T15:03:00+02:00", ...overrides };
}
