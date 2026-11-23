import { describe, expect, it } from "vitest";

import { passwordProblem, tokenFromHash } from "./validation";

describe("passwordProblem", () => {
  it("mirrors the API's 8–128 character policy", () => {
    expect(passwordProblem("short")).toMatch(/at least 8/);
    expect(passwordProblem("x".repeat(129))).toMatch(/at most 128/);
    expect(passwordProblem("long enough")).toBeNull();
  });
});

describe("tokenFromHash", () => {
  it("reads the token from the fragment", () => {
    expect(tokenFromHash("#token=abc_DEF-123")).toBe("abc_DEF-123");
    expect(tokenFromHash("#x=1&token=abc")).toBe("abc");
  });

  it("rejects missing or malformed tokens", () => {
    expect(tokenFromHash("")).toBeNull();
    expect(tokenFromHash("#token=")).toBeNull();
    expect(tokenFromHash("#token=<script>")).toBeNull();
    expect(tokenFromHash(`#token=${"a".repeat(129)}`)).toBeNull();
  });
});
