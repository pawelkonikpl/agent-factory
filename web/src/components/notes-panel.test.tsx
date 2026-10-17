import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Note } from "../services/notes-api";
import { createMockNote } from "../test/mocks";
import { renderWithProviders, stubFetch, waitForQueriesToSettle } from "../test/utils";
import { NotesPanel } from "./notes-panel";

describe("NotesPanel", () => {
  it("shows the empty state for an empty list", async () => {
    stubFetch({ "GET /api/notes": { body: [] } });
    renderWithProviders(<NotesPanel />);

    expect(await screen.findByText("Brak notatek. Dodaj pierwszą.")).toBeInTheDocument();
  });

  it("shows each note's text and creation time", async () => {
    const notes = [
      createMockNote(),
      createMockNote({ id: "2", text: "Druga notatka", created_at: "2026-10-11T09:30:00+02:00" }),
    ];
    stubFetch({ "GET /api/notes": { body: notes } });
    renderWithProviders(<NotesPanel />);

    const list = await screen.findByTestId("notes-list");
    expect(within(list).getAllByRole("listitem")).toHaveLength(notes.length);
    for (const note of notes) {
      const item = within(list).getByText(note.text).closest("li");
      // The formatted time depends on the machine's timezone, so only dateTime is checked.
      expect(item?.querySelector("time")).toHaveAttribute("datetime", note.created_at);
    }
  });

  it("shows an error when the notes can't be loaded", async () => {
    stubFetch({ "GET /api/notes": { status: 500 } });
    renderWithProviders(<NotesPanel />);

    expect(await screen.findByText("Nie udało się pobrać notatek.")).toBeInTheDocument();
  });

  it("sends the trimmed text, clears the input and shows the new note", async () => {
    const notes: Note[] = [];
    const fetchMock = stubFetch({
      "GET /api/notes": () => ({ body: notes }),
      "POST /api/notes": () => {
        const note = createMockNote({ text: "Nowa notatka" });
        notes.push(note);
        return { status: 201, body: note };
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<NotesPanel />);
    await screen.findByText("Brak notatek. Dodaj pierwszą.");

    const input = screen.getByRole("textbox", { name: "Treść notatki" });
    await user.type(input, "  Nowa notatka  ");
    await user.click(screen.getByRole("button", { name: "Dodaj" }));

    const list = await screen.findByTestId("notes-list");
    expect(await within(list).findByText("Nowa notatka")).toBeInTheDocument();
    expect(input).toHaveValue("");
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(1);
    expect(posts[0]?.[1]?.body).toBe(JSON.stringify({ text: "Nowa notatka" }));
  });

  it("sends nothing for whitespace-only input", async () => {
    const fetchMock = stubFetch({ "GET /api/notes": { body: [] } });
    const user = userEvent.setup();
    const { queryClient } = renderWithProviders(<NotesPanel />);

    await user.type(screen.getByRole("textbox", { name: "Treść notatki" }), "   ");
    await user.click(screen.getByRole("button", { name: "Dodaj" }));
    await waitForQueriesToSettle(queryClient);

    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });
});
