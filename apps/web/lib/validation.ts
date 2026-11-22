/** Mirrors the API's password policy (apps/api/app/schemas/user.py). The
 * server stays the authority; this only gives instant feedback. */
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 128;

export function passwordProblem(password: string): string | null {
  if (password.length < PASSWORD_MIN) return `Use at least ${PASSWORD_MIN} characters.`;
  if (password.length > PASSWORD_MAX) return `Use at most ${PASSWORD_MAX} characters.`;
  return null;
}

/** Reads `token` from a URL fragment like `#token=abc` (or `#abc=...&token=abc`). */
export function tokenFromHash(hash: string): string | null {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  const token = params.get("token");
  return token && /^[A-Za-z0-9_-]{1,128}$/.test(token) ? token : null;
}
