# AI Usage

AI tools were used during development as a coding and documentation
assistant. They helped compare implementation options, draft parts of the
demo script and documentation, and suggest test cases.

Specifically Co pilot, autocompletions and codex was used.

Representative prompts included:

- “How would we make this minimal?”
- “Should this use the ORM or PostgreSQL SQL?”
- “Explain how the outbox worker handles duplicates and an outage.”
- “Update the README and solution to match the implementation.”
- “Keep only the two most important tests.”

The reasoning was to keep PostgreSQL as the durable source of truth, use the
ORM for normal application work, and use raw `ON CONFLICT ... RETURNING` only
for the concurrent order-idempotency decision. A transactional outbox and a
simple polling worker met the catch-up requirement without adding Celery,
Redis, or Kafka. The feed was chosen as the required Option A integration
surface because it is easy for another service to poll and demonstrate.
