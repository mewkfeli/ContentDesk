import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "contentdesk.db"
SCHEMA_VERSION = 9


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, ddl: str) -> None:
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_db() -> None:
    with get_connection() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_meta (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("INSERT OR IGNORE INTO schema_meta(id, version) VALUES (1, 1)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                domain TEXT NOT NULL UNIQUE,
                cms TEXT DEFAULT '',
                project_type TEXT DEFAULT '',
                content_style TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _ensure_column(conn, "projects", "notes", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "projects", "sitemap_url", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "projects", "exclude_patterns", "TEXT NOT NULL DEFAULT ''")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                project_id INTEGER,
                project_name TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'Не указан',
                deadline TEXT NOT NULL DEFAULT 'Не указан',
                status TEXT NOT NULL DEFAULT 'new',
                parsed_json TEXT NOT NULL,
                done_json TEXT NOT NULL DEFAULT '[]',
                resolved_urls_json TEXT NOT NULL DEFAULT '[]',
                source_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS site_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                sitemap_url TEXT NOT NULL DEFAULT '', score INTEGER NOT NULL DEFAULT 0,
                pages_total INTEGER NOT NULL DEFAULT 0, pages_success INTEGER NOT NULL DEFAULT 0,
                critical INTEGER NOT NULL DEFAULT 0, warnings INTEGER NOT NULL DEFAULT 0,
                recommendations INTEGER NOT NULL DEFAULT 0, result_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS internal_link_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
                sitemap_url TEXT NOT NULL DEFAULT '', score INTEGER NOT NULL DEFAULT 0,
                pages_total INTEGER NOT NULL DEFAULT 0, links_total INTEGER NOT NULL DEFAULT 0,
                orphans INTEGER NOT NULL DEFAULT 0, broken_links INTEGER NOT NULL DEFAULT 0,
                result_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE TABLE IF NOT EXISTS project_content_profiles (project_id INTEGER PRIMARY KEY, profile_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)")
        conn.execute("CREATE TABLE IF NOT EXISTS assistant_settings (id INTEGER PRIMARY KEY CHECK(id=1), settings_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS app_settings (id INTEGER PRIMARY KEY CHECK(id=1), settings_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("INSERT OR IGNORE INTO app_settings(id, settings_json) VALUES (1, '{}')")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assistant_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER, title TEXT NOT NULL DEFAULT 'Новый диалог',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
            )
        """)
        conn.execute("CREATE TABLE IF NOT EXISTS assistant_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, tools_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(conversation_id) REFERENCES assistant_conversations(id) ON DELETE CASCADE)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_project_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                kind TEXT NOT NULL DEFAULT 'fact',
                title TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'user',
                confidence TEXT NOT NULL DEFAULT 'confirmed',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_project_memory_project ON ai_project_memory(project_id, kind, id DESC)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_memory_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL, event_type TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}', source TEXT NOT NULL DEFAULT 'ContentDesk',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_memory_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL, state_key TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}', source TEXT NOT NULL DEFAULT 'ContentDesk',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, state_key),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_memory_events_project ON project_memory_events(project_id, id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_memory_state_project ON project_memory_state(project_id, updated_at DESC)")
        conn.execute("CREATE TABLE IF NOT EXISTS activity_log (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, title TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', href TEXT NOT NULL DEFAULT '', project_id INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS app_release_meta (id INTEGER PRIMARY KEY CHECK(id=1), installed_version TEXT NOT NULL DEFAULT '2.8.0', first_run_completed INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("INSERT OR IGNORE INTO app_release_meta(id, installed_version, first_run_completed) VALUES (1, '2.8.0', 0)")
        conn.execute("UPDATE app_release_meta SET installed_version='2.8.0', updated_at=CURRENT_TIMESTAMP WHERE id=1")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS background_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                project_id INTEGER,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                progress_current INTEGER NOT NULL DEFAULT 0,
                progress_total INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                finished_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta_description_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                source_name TEXT NOT NULL DEFAULT '',
                sitemap_url TEXT NOT NULL DEFAULT '',
                urls_total INTEGER NOT NULL DEFAULT 0,
                ok_count INTEGER NOT NULL DEFAULT 0,
                review_count INTEGER NOT NULL DEFAULT 0,
                replace_count INTEGER NOT NULL DEFAULT 0,
                technical_count INTEGER NOT NULL DEFAULT 0,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS indexing_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                source_name TEXT NOT NULL DEFAULT '',
                sitemap_url TEXT NOT NULL DEFAULT '',
                urls_total INTEGER NOT NULL DEFAULT 0,
                ok_count INTEGER NOT NULL DEFAULT 0,
                content_count INTEGER NOT NULL DEFAULT 0,
                developer_count INTEGER NOT NULL DEFAULT 0,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        _ensure_column(conn, "indexing_checks", "insufficient_count", "INTEGER NOT NULL DEFAULT 0")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_indexing_checks_project ON indexing_checks(project_id, id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_background_jobs_status ON background_jobs(status, id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_background_jobs_project ON background_jobs(project_id, id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assistant_conversations_project ON assistant_conversations(project_id, updated_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assistant_messages_conversation ON assistant_messages(conversation_id, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_internal_link_audits_project ON internal_link_audits(project_id, id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_site_audits_project ON site_audits(project_id, id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_saved_tasks_status ON saved_tasks(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_saved_tasks_project ON saved_tasks(project_id)")
        conn.execute("UPDATE schema_meta SET version=?, updated_at=CURRENT_TIMESTAMP WHERE id=1", (SCHEMA_VERSION,))
        conn.commit()
