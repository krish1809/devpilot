// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StatusBadge } from "./badge";

afterEach(cleanup);

describe("StatusBadge", () => {
  it("renders the status with spaces instead of underscores", () => {
    render(<StatusBadge status="review_failed" />);
    expect(screen.getByText("review failed")).toBeTruthy();
  });

  it("falls back to a neutral style for unknown statuses", () => {
    render(<StatusBadge status="mystery" />);
    expect(screen.getByText("mystery").className).toContain("bg-muted");
  });
});
