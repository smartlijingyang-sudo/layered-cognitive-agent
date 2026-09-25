-- ADR-0252 D3: LCA 自有数据库（用户↔助理归属关系）。
-- 开发默认走 SQLite（~/.lca/lca.sqlite3，DDL 见 user_store.py）；
-- 本迁移供生产 Postgres 库使用。LobeHub 后端不读不写这些表。

CREATE TABLE IF NOT EXISTS lca_users (
    user_id          text PRIMARY KEY,
    username         text,
    email            text,
    onboarding_state text NOT NULL DEFAULT 'pending',
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lca_user_assistants (
    user_id        text NOT NULL REFERENCES lca_users(user_id) ON DELETE CASCADE,
    assistant_id   text PRIMARY KEY,
    client_id      text NOT NULL,
    role_id        text,
    initial_skills jsonb NOT NULL DEFAULT '[]'::jsonb,
    agent_id       text,
    status         text NOT NULL DEFAULT 'pending',
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, client_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS lca_user_assistants_agent_idx
    ON lca_user_assistants (agent_id) WHERE agent_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS lca_user_assistants_user_id_idx
    ON lca_user_assistants (user_id);