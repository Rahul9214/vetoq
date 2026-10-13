"""Initial eleven-table PostgreSQL schema, installed only through Alembic."""

DDL = r"""
CREATE TABLE workspaces (
 id text PRIMARY KEY, name text NOT NULL, active boolean NOT NULL DEFAULT true,
 policy_revision text NOT NULL DEFAULT 'support-triage/1'
);
CREATE TABLE memberships (
 workspace_id text REFERENCES workspaces(id), principal text NOT NULL,
 role text NOT NULL CHECK(role IN ('operator','reviewer')),
 active boolean NOT NULL DEFAULT true, PRIMARY KEY(workspace_id,principal)
);
CREATE TABLE runs (
 id text PRIMARY KEY, workspace_id text NOT NULL REFERENCES workspaces(id), principal text NOT NULL,
 submission_key text NOT NULL, submission_digest text NOT NULL, envelope jsonb NOT NULL,
 state text NOT NULL CHECK(state IN (
  'QUEUED','INSPECTING','PROPOSING','AUTHORIZING','AWAITING_REVIEW',
  'VERIFYING','COMPLETED','NO_ACTION','BLOCKED','FAILED','CANCELLED','EXPIRED'
 )),
 created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
 writes integer NOT NULL DEFAULT 0 CHECK(writes BETWEEN 0 AND 1),
 proposals integer NOT NULL DEFAULT 0 CHECK(proposals BETWEEN 0 AND 3),
 continuations integer NOT NULL DEFAULT 0 CHECK(continuations BETWEEN 0 AND 1),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 4),
 cancelled boolean NOT NULL DEFAULT false, complete boolean NOT NULL DEFAULT false,
 uncertain boolean NOT NULL DEFAULT false,
 lease_until timestamptz, fence bigint NOT NULL DEFAULT 0, analysis jsonb, failure text,
 UNIQUE(workspace_id,principal,submission_key), UNIQUE(workspace_id,id),
 FOREIGN KEY(workspace_id,principal) REFERENCES memberships(workspace_id,principal)
);
CREATE TABLE content_nodes (
 id text PRIMARY KEY, workspace_id text NOT NULL, run_id text NOT NULL, origin text NOT NULL,
 supplier text NOT NULL, digest text NOT NULL, content text NOT NULL,
 trust text NOT NULL CHECK(trust='untrusted'), complete boolean NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
 UNIQUE(workspace_id,run_id,id),
 FOREIGN KEY(workspace_id,run_id)
  REFERENCES runs(workspace_id,id) ON DELETE CASCADE
);
CREATE TABLE content_edges (
 id text PRIMARY KEY, workspace_id text NOT NULL, run_id text NOT NULL,
 parent_id text NOT NULL, child_id text NOT NULL,
 transform text NOT NULL, version text NOT NULL, lossy boolean NOT NULL,
 FOREIGN KEY(workspace_id,run_id,parent_id)
  REFERENCES content_nodes(workspace_id,run_id,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,run_id,child_id)
  REFERENCES content_nodes(workspace_id,run_id,id) ON DELETE CASCADE,
 CHECK(parent_id<>child_id), UNIQUE(parent_id,child_id)
);
CREATE TABLE findings (
 id text PRIMARY KEY, workspace_id text NOT NULL, run_id text NOT NULL, node_id text NOT NULL,
 origin text NOT NULL CHECK(origin IN ('deterministic','model')),
 family text NOT NULL, explanation text NOT NULL,
 start_offset integer NOT NULL CHECK(start_offset>=0),
 end_offset integer NOT NULL CHECK(end_offset>=start_offset), version text NOT NULL,
 FOREIGN KEY(workspace_id,run_id,node_id)
  REFERENCES content_nodes(workspace_id,run_id,id) ON DELETE CASCADE
);
CREATE TABLE actions (
 id text PRIMARY KEY, workspace_id text NOT NULL, run_id text NOT NULL, proposal jsonb NOT NULL,
 digest text NOT NULL, verdict text CHECK(verdict IN ('ALLOW','BLOCK','REVIEW')),
 reasons jsonb NOT NULL DEFAULT '[]',
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(workspace_id,run_id,id),
 FOREIGN KEY(workspace_id,run_id)
  REFERENCES runs(workspace_id,id) ON DELETE CASCADE
);
CREATE TABLE reviews (
 id text PRIMARY KEY, workspace_id text NOT NULL, run_id text NOT NULL,
 action_id text NOT NULL UNIQUE,
 digest text NOT NULL, expires_at timestamptz NOT NULL, reviewer text,
 decision text CHECK(decision IN ('approve','reject')),
 consumed boolean NOT NULL DEFAULT false,
 FOREIGN KEY(workspace_id,run_id,action_id)
  REFERENCES actions(workspace_id,run_id,id) ON DELETE CASCADE
);
CREATE TABLE tickets (
 id text PRIMARY KEY, workspace_id text NOT NULL, run_id text NOT NULL UNIQUE,
 action_id text NOT NULL UNIQUE,
 title text NOT NULL CHECK(length(title) BETWEEN 1 AND 160),
 body text NOT NULL CHECK(length(body) BETWEEN 1 AND 8000),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(workspace_id,run_id,id),
 FOREIGN KEY(workspace_id,run_id,action_id)
  REFERENCES actions(workspace_id,run_id,id) ON DELETE CASCADE
);
CREATE TABLE executions (
 id text PRIMARY KEY, workspace_id text NOT NULL, run_id text NOT NULL,
 action_id text NOT NULL UNIQUE, ticket_id text NOT NULL UNIQUE,
 digest text NOT NULL, committed_at timestamptz NOT NULL DEFAULT now(), verified_at timestamptz,
 FOREIGN KEY(workspace_id,run_id,action_id)
  REFERENCES actions(workspace_id,run_id,id) ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,run_id,ticket_id)
  REFERENCES tickets(workspace_id,run_id,id) ON DELETE CASCADE
);
CREATE TABLE audit_events (
 id bigserial PRIMARY KEY, workspace_id text NOT NULL REFERENCES workspaces(id),
 run_id text NOT NULL,
 sequence integer NOT NULL, actor text NOT NULL, type text NOT NULL, detail jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(run_id,sequence)
);
CREATE INDEX runnable ON runs(state,lease_until,created_at);
CREATE INDEX workspace_runs ON runs(workspace_id,created_at DESC);
CREATE FUNCTION protect_run() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' THEN
  IF OLD.created_at > now()-interval '24 hours' THEN
   RAISE EXCEPTION 'retention_not_due';
  END IF;
  RETURN OLD;
 END IF;
 IF NEW.envelope IS DISTINCT FROM OLD.envelope
    OR NEW.workspace_id<>OLD.workspace_id OR NEW.principal<>OLD.principal
    OR NEW.expires_at<>OLD.expires_at
    OR NEW.submission_digest<>OLD.submission_digest
    OR NEW.submission_key<>OLD.submission_key
    OR NEW.created_at<>OLD.created_at THEN
  RAISE EXCEPTION 'immutable_goal_lock';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_run BEFORE UPDATE OR DELETE ON runs
 FOR EACH ROW EXECUTE FUNCTION protect_run();
CREATE FUNCTION protect_action() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.proposal IS DISTINCT FROM OLD.proposal OR NEW.digest<>OLD.digest
    OR NEW.run_id<>OLD.run_id OR NEW.workspace_id<>OLD.workspace_id THEN
  RAISE EXCEPTION 'immutable_action';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_action BEFORE UPDATE ON actions
 FOR EACH ROW EXECUTE FUNCTION protect_action();
CREATE FUNCTION protect_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='UPDATE' OR OLD.created_at > now()-interval '30 days' THEN
  RAISE EXCEPTION 'append_only_audit';
 END IF;
 RETURN OLD;
END $$;
CREATE TRIGGER append_only_audit BEFORE UPDATE OR DELETE ON audit_events
 FOR EACH ROW EXECUTE FUNCTION protect_audit();
CREATE FUNCTION protect_content() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 RAISE EXCEPTION 'immutable_content';
END $$;
CREATE TRIGGER immutable_content BEFORE UPDATE ON content_nodes
 FOR EACH ROW EXECUTE FUNCTION protect_content();
"""
