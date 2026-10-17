import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Without Vitest's globals Testing Library can't unmount by itself. Unstubbing fetch keeps
// one test's stubFetch routes out of the next test.
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
