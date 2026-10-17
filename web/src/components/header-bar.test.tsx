import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { createMockUser } from "../test/mocks";
import { renderWithProviders, stubFetch } from "../test/utils";
import { HeaderBar } from "./header-bar";

describe("HeaderBar", () => {
  it("shows the name, or the sub when the name is null", () => {
    const { rerender } = renderWithProviders(<HeaderBar user={createMockUser()} />);
    expect(screen.getByTestId("user-name").textContent).toBe("Alice Example");

    rerender(<HeaderBar user={createMockUser({ name: null })} />);
    expect(screen.getByTestId("user-name").textContent).toBe("alice");
  });

  it("shows the email, and no email when it is null", () => {
    const { rerender } = renderWithProviders(<HeaderBar user={createMockUser()} />);
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();

    rerender(<HeaderBar user={createMockUser({ email: null })} />);
    expect(screen.queryByText("alice@example.com")).not.toBeInTheDocument();
  });

  it("shows an alert when logout fails", async () => {
    stubFetch({ "POST /bff/logout": { status: 502 } });
    const user = userEvent.setup();
    renderWithProviders(<HeaderBar user={createMockUser()} />);

    await user.click(screen.getByRole("button", { name: "Wyloguj" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Nie udało się wylogować. Spróbuj ponownie.",
    );
  });
});
