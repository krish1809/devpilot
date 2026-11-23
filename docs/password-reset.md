# Password reset — design and reasoning

Added 2026-11-22 (an approved addition outside [PLAN.md](PLAN.md)'s phases). Code:
[`app/services/password_reset.py`](../apps/api/app/services/password_reset.py),
[`app/api/auth.py`](../apps/api/app/api/auth.py),
[`app/integrations/email.py`](../apps/api/app/integrations/email.py),
[`app/api/deps.py`](../apps/api/app/api/deps.py) (session check), web pages
[`/forgot-password`](../apps/web/app/forgot-password/page.tsx) and
[`/reset-password`](../apps/web/app/reset-password/page.tsx). Tests:
[`tests/test_password_reset.py`](../apps/api/tests/test_password_reset.py) (30).

## The flow

```mermaid
sequenceDiagram
  participant U as User (browser)
  participant W as Web (Vercel)
  participant A as API (FastAPI)
  participant D as Postgres
  participant E as Email (Resend)
  U->>W: /forgot-password, enter email
  W->>A: POST /auth/forgot-password {email}
  A->>A: rate limit (per IP + per email)
  A->>D: account exists? → store SHA-256(token), expires in 30 min
  A-->>W: 202 "If an account exists…" (always the same)
  A--)E: (background, after the response) email with link
  E--)U: https://app/reset-password#token=…
  U->>W: open link; page reads #token, strips it from the URL
  W->>A: POST /auth/reset-password {token, new_password}
  A->>D: lock token row; check not used / not expired
  A->>D: new password hash · mark all user's tokens used · token_version += 1
  A-->>W: 200 → redirect to /login
  Note over A: every JWT issued before the reset now fails (ver ≠ token_version)
```

## Each decision, and why

**1. The same response whether or not the account exists.** `forgot-password` always
returns `202` with one fixed message. If it said "no account with that email", anyone could
test a list of addresses and learn who uses the service (*user enumeration*), which is the
first step of targeted phishing or credential stuffing. Three details keep the answer the same:
- **Status code and body:** a test asserts the bytes match for a real account, an unknown
  one, and a malformed address.
- **Timing:** sending an email to a provider takes hundreds of milliseconds, so if the
  request waited for it, "account exists" would be measurably slower. The email is sent in a
  FastAPI background task *after* the response is returned. (One small database insert still
  differs; that is noise next to network jitter.)
- **Errors:** delivery failures are logged, never returned, and a missing `RESEND_API_KEY`
  only surfaces at send time, so it can't turn the endpoint into a 500 for real accounts only.

**2. Rate limiting, per IP and per email.** Per-IP (5 / 15 min) stops one client from
spraying requests. Per-email (3 / hour) stops someone from flooding *one victim's* inbox from
many IPs. The per-email counter applies to any string, registered or not, so a `429` reveals
nothing either. The email key is a SHA-256, so the limiter's memory holds no raw addresses.
`reset-password` is limited like login (10 / min per IP). Behind Render's proxy the API must
trust `X-Forwarded-For` (`FORWARDED_ALLOW_IPS`), or every visitor shares the proxy's IP.

**3. A random token from `secrets`, and only its hash in the database.**
`secrets.token_urlsafe(32)` is 256 bits from the OS cryptographic random generator, so it's
unguessable. The database stores `SHA-256(token)`, not the token. A reset token is a
*password-equivalent*: whoever holds it can take over the account. If the table leaked
(backup, SQL injection, a misplaced dump), plain tokens would be usable immediately; hashes
are not. Why SHA-256 and not scrypt like passwords? Slow hashes exist because human passwords
have little entropy and can be brute-forced. A 256-bit random token cannot, so a fast hash is
enough, and it allows a direct indexed lookup by hash.

**4. A 30-minute expiry and single use.** Links sit in inboxes, get forwarded, synced to
other devices, and leak through mail scanners. A short expiry bounds how long a leaked link
stays useful. Single use (`used_at`) means a link that worked can never work again. On a
successful reset **every** outstanding token for that user is marked used, so an older link
from an earlier request can't be redeemed later. Every failure (unknown, expired, used,
inactive account) returns the same `400`, so the response doesn't say which.

**5. No double-spend race.** Redemption runs in one transaction and loads the token row
`SELECT … FOR UPDATE`. Two simultaneous requests with the same token serialize on that
lock, and the second sees `used_at` already set.

**6. Resetting the password logs out every existing session (`token_version`).** If an
attacker had a session (stolen laptop, leaked token), changing the password must kick them
out. JWTs are stateless and can't be "deleted", so each user has a `token_version` integer,
every token carries it as a `ver` claim, and the auth dependency rejects a token whose `ver`
doesn't match. A reset increments the version, which invalidates all earlier tokens at once.
- **Why not `password_changed_at` vs the token's `iat`?** `iat` has one-second resolution, so
  a login in the same second as a reset is ambiguous, and clock edge cases creep in. An
  integer comparison is exact.
- **Why not a revocation list?** It needs a table that grows with every token. The user row is
  already loaded on every request, so the check is free.
- **Old tokens:** tokens from before this change have no `ver` and count as version 0 (the
  column default), so the deploy logged nobody out.
- The web app listens for any `401` on a signed-in request, clears the session everywhere,
  and the login page says "Your session has ended".

**7. The link puts the token in the URL fragment (`#token=…`), not the query string.**
Browsers never send the fragment to a server, so the token can't appear in Vercel's access
logs, proxy logs, or a `Referer` header to third parties. The reset page reads it, removes it
from the address bar and history (`history.replaceState`), and sets `referrer: no-referrer`
as an extra layer.

**8. The link's host comes from configuration.** `FRONTEND_URL` builds the link. Never use
the request's `Host` header: an attacker could send a reset request with a forged `Host` and
the victim would get a genuine email pointing at the attacker's domain (*host-header
poisoning*).

**9. The same password rules as registration.** One validator (`validate_new_password`,
8–128 characters) is shared, so the two can't drift apart. A request that fails validation
(`422`) doesn't use up the token.

**10. Audit without secrets.** `user.password_reset.requested` and
`user.password_reset.completed` record the user id (when known) and the IP. For an unknown
address the typed email is kept, like failed logins, to spot enumeration attempts. No token,
hash or password ever goes into the audit log or application logs. Tests check this.

**11. Email behind a small interface.** `EmailSender` has three implementations:
- `console` for local development: prints the email, which is the dev inbox.
- `resend` for production, over HTTPS: Render's free plan blocks outbound SMTP ports.
- in-memory for tests.

The console backend is the one intended place a link is printed, and it refuses to print
when `ENVIRONMENT=production`. A misconfigured deploy therefore fails *closed* (no email, a
warning) instead of leaking links into hosted logs.

**12. Special accounts.** The shared showcase demo user is excluded: `demo@devpilot.dev` is
on a real domain, and whoever controls that mailbox would otherwise get a takeover link.
Inactive accounts get nothing. The read-only showcase allows exactly the two reset endpoints,
and they can only change the caller's own password.

## Bootstrap account (showcase deployments)

Production runs as a read-only showcase where sign-up is off. `BOOTSTRAP_USER_EMAIL` makes
the API create that one account on startup with a random, never-shown password. The owner
then sets a real password through *Forgot password?*. The reset flow doubles as onboarding,
and no database credentials have to leave the host. Idempotent: if the account exists,
nothing happens.

## Known limits (deliberate, for a portfolio project)

- Rate limits are in memory, per process. A multi-replica deployment needs a shared store
  (Redis).
- Used and expired token rows aren't purged. They're tiny; a periodic cleanup would be the
  next step.
- No "your password was changed" notification email, and no check against breached-password
  lists (e.g. HIBP k-anonymity). Both are natural follow-ups.
- The reset page can't tell an expired link from a valid one until it's submitted. That's
  deliberate: no extra "check token" endpoint to protect.
