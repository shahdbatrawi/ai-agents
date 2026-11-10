-- embeddings.sql
-- Stores embeddings for various entities (e.g. positions, experiences, etc.).

CREATE TABLE IF NOT EXISTS embeddings (
    embedding_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type     TEXT    NOT NULL  CHECK(entity_type IN ('position', 'experience','institution','skill')),   -- e.g. 'position', 'experience', etc.
    entity_id       INTEGER NOT NULL ,   -- ID of the entity (e.g. position_id, experience_id)
    embed_text        TEXT    NOT NULL,   -- the text that was embedded
    model           TEXT    NOT NULL,   -- the model used to generate the embedding
    vector          JSON    NOT NULL,   -- the embedding vector
    created_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
    unique(entity_type, entity_id)

);