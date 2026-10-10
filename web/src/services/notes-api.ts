import { z } from "zod";

import { bffRequest } from "./bff-client";

const noteSchema = z.object({
  id: z.string(),
  text: z.string(),
  created_at: z.iso.datetime({ offset: true }),
});

export type Note = z.infer<typeof noteSchema>;

// "/api/..." is proxied by the BFF, which adds the access token on the server side.
export function fetchNotes(): Promise<Note[]> {
  return bffRequest("/api/notes", z.array(noteSchema));
}

export function createNote(text: string): Promise<Note> {
  return bffRequest("/api/notes", noteSchema, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}
