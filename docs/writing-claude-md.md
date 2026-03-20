# Writing a good CLAUDE.md

The `CLAUDE.md` file is the most important lever for controlling both the **quality** and the **cost** of Octobot's analysis.

Before analyzing a bug ticket, Octobot sends the `CLAUDE.md` to Claude along with the list of all files in the repository and asks: *"which files should I read?"*. A good `CLAUDE.md` lets Claude skip exploration entirely and go straight to the relevant code. A missing or vague one forces Claude to guess — which means reading more files, more tokens, and worse results.

---

## What to include

### 1. Architecture overview

A brief description of the system: what it does, how it is structured, what the main layers or services are.

```markdown
## Architecture
Multi-module Java monorepo. The HTTP request lifecycle goes:
nginx → api module (Spring Boot) → system module (business logic) → model module (JPA entities + DB).
Async jobs are handled by the cron module.
```

### 2. Key entry points

Tell Claude where things start. This is the highest-value section.

```markdown
## Entry points
- HTTP requests: `api/src/main/java/com/example/api/controller/`
- Background jobs: `cron/src/main/java/com/example/cron/jobs/`
- DB schema: `model/src/main/resources/db/migration/` (Flyway)
- Config: `system/src/main/resources/application.yml`
```

### 3. Known bug-prone areas

If you know which parts of the code tend to produce bugs, say so explicitly.

```markdown
## Known fragile areas
- `ReservationService.calculateAvailability()` — complex date math, many edge cases
- `PaymentGatewayClient` — external API with inconsistent error responses
- Any code touching `MultiCameraConfig` — legacy, heavily stateful
```

### 4. Conventions and invariants

Things that are not obvious from reading a single file.

```markdown
## Conventions
- All monetary amounts are stored in cents (integer), never floats
- `Optional.empty()` means "not found", exceptions mean "system error"
- Database access only through Repository interfaces, never raw EntityManager
```

### 5. What NOT to do / common mistakes

```markdown
## Common mistakes to watch for
- Calling `session.flush()` inside a loop (N+1 writes)
- Using `==` instead of `.equals()` for entity comparison
- Forgetting to handle the `MULTI_CAMERA` case in switch statements
```

---

## What NOT to include

- **File contents** — Claude will read them directly.
- **Full API documentation** — too noisy. Reference the endpoint, not the full spec.
- **Git history or changelogs** — irrelevant to bug analysis.
- **Anything longer than ~500 lines** — the CLAUDE.md is sent on every analysis call. Keep it lean.

---

## One CLAUDE.md per module vs. one shared

In a multi-repo setup, each repository has its own `CLAUDE.md`. Octobot concatenates them, labelling each section with the repo name. Keep each one focused on its own module — don't repeat information that belongs in another repo's file.

---

## Template

See [`config/CLAUDE.md.example`](../config/CLAUDE.md.example) for a starting template.

---

## Iterating

After each analysis, read the comment Octobot left on YouTrack. If it:

- **Looked at the wrong files** → your entry points section is unclear. Be more specific.
- **Missed an obvious bug location** → add it to the "known fragile areas" section.
- **Made wrong assumptions about data types or conventions** → add a conventions entry.
- **Was correct but verbose** → the CLAUDE.md is probably fine; the ticket description was sparse.

The CLAUDE.md is versioned in your repository — treat it as a living document and improve it alongside the codebase.
