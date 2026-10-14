"""Nullable ingestion metadata on content_nodes. Rows stay insert-only.

0001 already rejects every UPDATE of a content node. This revision does not
narrow that function: a column-specific check would allow mutation of content,
digest, trust, and the other fields 0001 already freezes. Replacing the
function here records that the new metadata is covered by the same rule
without editing the applied 0001 definition.
"""

from alembic import op

revision = "0003_secure_ingestion"
down_revision = "0002_worker_claim"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE content_nodes
          ADD COLUMN declared_media_type text,
          ADD COLUMN representation_kind text,
          ADD COLUMN parser_id text,
          ADD COLUMN parser_version text,
          ADD COLUMN charset text,
          ADD COLUMN byte_size integer
        """
    )
    # NULL remains legal so M002 rows are not backfilled with guessed types.
    op.execute(
        """
        ALTER TABLE content_nodes
          ADD CONSTRAINT content_declared_media_type CHECK (
            declared_media_type IS NULL OR declared_media_type IN (
              'text/plain','application/json','text/markdown','text/html','message/rfc822'
            )
          ),
          ADD CONSTRAINT content_representation_kind CHECK (
            representation_kind IS NULL OR representation_kind IN (
              'original','canonical_text','decoded_text','active_content'
            )
          ),
          ADD CONSTRAINT content_charset CHECK (
            charset IS NULL OR charset IN ('utf-8','us-ascii')
          ),
          ADD CONSTRAINT content_byte_size CHECK (byte_size IS NULL OR byte_size >= 0),
          ADD CONSTRAINT content_parser_id_length CHECK (
            parser_id IS NULL OR (
              parser_id = btrim(parser_id) AND char_length(parser_id) BETWEEN 1 AND 80
            )
          ),
          ADD CONSTRAINT content_parser_version_length CHECK (
            parser_version IS NULL OR (
              parser_version = btrim(parser_version)
              AND char_length(parser_version) BETWEEN 1 AND 80
            )
          ),
          ADD CONSTRAINT content_parser_pair CHECK (
            (parser_id IS NULL AND parser_version IS NULL)
            OR (parser_id IS NOT NULL AND parser_version IS NOT NULL)
          ),
          ADD CONSTRAINT content_derived_parser CHECK (
            representation_kind IS NULL
            OR representation_kind NOT IN (
              'canonical_text','decoded_text','active_content'
            )
            OR (parser_id IS NOT NULL AND parser_version IS NOT NULL)
          )
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN content_nodes.declared_media_type IS
          'Lowercase allowlisted type, parameters removed. Not authority. NULL means not recorded.';
        COMMENT ON COLUMN content_nodes.representation_kind IS
          'original, canonical_text, decoded_text, or active_content. NULL means not recorded.';
        COMMENT ON COLUMN content_nodes.parser_id IS
          'Derived-representation parser id. NULL on legacy rows and normally on originals.';
        COMMENT ON COLUMN content_nodes.parser_version IS
          'Version paired with parser_id. Both are null or both are set.';
        COMMENT ON COLUMN content_nodes.charset IS
          'utf-8 or us-ascii when recorded. NULL means not recorded.';
        COMMENT ON COLUMN content_nodes.byte_size IS
          'UTF-8 byte length of this node content when recorded. Not a second budget.';
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_content() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          -- Insert-only: M003 metadata uses the same rejection as content, digest, and trust.
          RAISE EXCEPTION 'immutable_content';
        END $$
        """
    )


def downgrade() -> None:
    raise RuntimeError("Destructive rollback requires an explicit operator recovery plan")
