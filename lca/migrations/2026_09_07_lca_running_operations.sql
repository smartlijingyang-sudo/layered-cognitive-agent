-- Per ADR-0200 §3.2 + spec §3.2: NO status column on lca_running_operations.
-- Apply when Postgres-backed RunningOperationStore is wired (Task 12).

CREATE TABLE IF NOT EXISTS lca_running_operations (
    run_id                text PRIMARY KEY,
    topic_id              text NOT NULL,
    agent_id              text NOT NULL,
    assistant_message_id  text,
    scope                 text NOT NULL DEFAULT 'main',
    created_at            timestamptz NOT NULL DEFAULT now(),
    accepted_answer_keys  jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS lca_running_operations_topic_id_idx
    ON lca_running_operations (topic_id, created_at DESC);
