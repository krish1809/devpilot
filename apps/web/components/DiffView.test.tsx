// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { classifyLine, DiffView } from "./DiffView";

afterEach(cleanup);

const DIFF = `--- a/units.py
+++ b/units.py
@@ -1,3 +1,3 @@
 def c(f):
-    return (f - 32) * 5 / 8
+    return (f - 32) * 5 / 9
`;

describe("DiffView", () => {
  it("classifies unified-diff lines", () => {
    expect(classifyLine("+++ b/x")).toBe("meta");
    expect(classifyLine("--- a/x")).toBe("meta");
    expect(classifyLine("@@ -1 +1 @@")).toBe("hunk");
    expect(classifyLine("+x")).toBe("add");
    expect(classifyLine("-x")).toBe("del");
    expect(classifyLine(" x")).toBe("ctx");
  });

  it("counts changes and labels changed lines for screen readers", () => {
    render(<DiffView diff={DIFF} />);
    expect(screen.getByText("+1")).toBeTruthy();
    expect(screen.getByText("−1")).toBeTruthy();
    expect(screen.getAllByText("added:")).toHaveLength(1);
    expect(screen.getAllByText("removed:")).toHaveLength(1);
  });
});
