# Code Slop Patterns

Use this when writing or reviewing code, comments, types, tests, or generated patches.

## A1 — Boundary confusion

Slop:

```python
def total(items: list[Order]) -> float:
    if items is None:
        return 0.0
    if not isinstance(items, list):
        raise TypeError("items must be a list")
    return sum(o.amount for o in items if o is not None)
```

Fix:

```python
def total(items: list[Order]) -> float:
    return sum(o.amount for o in items)
```

Keep guards at real boundaries: user input, public API, filesystem, network, auth, payments, migrations, serialization, and security-sensitive paths.

## A2 — Try/except without recovery

Slop:

```python
try:
    return parse_config(path)
except Exception as exc:
    raise RuntimeError(f"Failed to parse config: {exc}") from exc
```

Fix when no recovery is added:

```python
return parse_config(path)
```

Keep `try/except` when it adds retry, fallback, cleanup, user-facing diagnostics, metric context, or domain-specific error translation.

## A3 — Single-use abstraction

Slop:

```python
class UserService:
    def get_user(self, user_id: str) -> User:
        return db.users.get(user_id)
```

Fix:

```python
user = db.users.get(user_id)
```

Keep abstraction for public interfaces, dependency inversion at boundaries, test seams that remove real pain, or at least two real implementations/callers.

## A4 — Generic names

Slop names:

- `data`
- `item`
- `helper`
- `manager`
- `processor`
- `handler`
- `utils`
- `service`

Fix by naming the domain object, action, or boundary:

- `invoice_rows`
- `retry_policy`
- `stripe_webhook`
- `parse_lockfile`
- `render_invoice`

## A5 — Comments that restate code

Slop:

```ts
// Increment count by one
count += 1
```

Fix: delete.

Keep comments for non-obvious invariants, weird platform constraints, security tradeoffs, browser quirks, compatibility reasons, or migration deadlines.

## A6 — Narration logs

Slop:

```ts
console.log("Starting process")
console.log("Processing data")
console.log("Process complete")
```

Fix: delete or keep one actionable log with identifiers and failure context.

## A7 — Premature configurability

Slop:

```ts
const DEFAULT_RETRY_COUNT = process.env.RETRY_COUNT ?? 3
```

when there is no documented operator need.

Fix:

```ts
const RETRY_COUNT = 3
```

Keep configuration for deployment-specific values, secrets, environment URLs, operator-tuned limits, or product settings.

## A8 — Dead compatibility

Slop:

```ts
export const oldClient = newClient
```

without callers or migration notes.

Fix: delete.

Keep compatibility only when a public API, versioned migration, or known downstream consumer needs it.

## A9 — Type/interface inflation

Slop:

```ts
interface UserRepository {
  getUser(id: string): Promise<User>
}

class DatabaseUserRepository implements UserRepository {
  getUser(id: string) {
    return db.user.findUnique({ where: { id } })
  }
}
```

Fix until a second implementation exists:

```ts
const getUser = (id: string) => db.user.findUnique({ where: { id } })
```

## A10 — Artificial regions and banners

Slop:

```ts
// ==========================================
// Helper Functions
// ==========================================
```

Fix: use file/module structure or simple comments only where they clarify.

## Test slop

Block:

- tests that assert implementation details with no behavior value
- snapshots generated only to make coverage look bigger
- fake "test passed" claims
- mocks that avoid the real boundary being tested
- duplicated cases with changed names only

Keep:

- regression cases
- boundary cases
- security and parsing edge cases
- compatibility tests
- tests that document real product behavior
