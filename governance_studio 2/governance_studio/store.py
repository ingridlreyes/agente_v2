"""SQLite local. Cada lectura de contenido exige identidad, sin confiar en IDs del cliente."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4
from .models import Principal, Memory


def uid():
    return uuid4().hex


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "studio.sqlite3"
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, tenant TEXT, owner TEXT,
              theme TEXT, memory TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation TEXT,
              role TEXT, content TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY, tenant TEXT, owner TEXT, scope TEXT,
              conversation TEXT, title TEXT, locator TEXT, content TEXT);
            CREATE INDEX IF NOT EXISTS chunk_acl ON chunks(tenant,owner,scope,conversation);
            CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY, tenant TEXT, owner TEXT,
              conversation TEXT, path TEXT, mime TEXT);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, tenant TEXT, owner TEXT, conversation TEXT,
              status TEXT, stage TEXT, payload TEXT, result TEXT, created REAL, updated REAL);
            CREATE TABLE IF NOT EXISTS versions(artifact TEXT, version INTEGER, tenant TEXT, owner TEXT,
              conversation TEXT, spec TEXT, sources TEXT, formats TEXT, directory TEXT, created REAL,
              PRIMARY KEY(artifact, version));
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, tenant TEXT, owner TEXT,
              name TEXT, fields TEXT, created REAL);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_conversation(self, p: Principal, theme):
        cid = uid()
        with self.db() as db:
            db.execute("INSERT INTO conversations VALUES(?,?,?,?,?,?)",
                       (cid, p.tenant_id, p.user_id, dumps(theme), dumps(Memory().model_dump()), time.time()))
        return cid

    def conversation(self, p, cid):
        with self.db() as db:
            row = db.execute("SELECT * FROM conversations WHERE id=? AND tenant=? AND owner=?",
                             (cid, p.tenant_id, p.user_id)).fetchone()
        if not row:
            raise KeyError("Conversación no encontrada")
        d = dict(row)
        d["theme"], d["memory"] = json.loads(d["theme"]), json.loads(d["memory"])
        return d

    def messages(self, p, cid, limit=16):
        self.conversation(p, cid)
        with self.db() as db:
            rows = db.execute("SELECT role,content FROM messages WHERE conversation=? ORDER BY id DESC LIMIT ?",
                              (cid, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def add_message(self, p, cid, role, content):
        self.conversation(p, cid)
        with self.db() as db:
            db.execute("INSERT INTO messages(conversation,role,content,created) VALUES(?,?,?,?)",
                       (cid, role, content, time.time()))

    def update_memory(self, p, cid, memory):
        self.conversation(p, cid)
        with self.db() as db:
            db.execute("UPDATE conversations SET memory=? WHERE id=?", (dumps(memory), cid))

    def update_theme(self, p, cid, theme):
        self.conversation(p, cid)
        with self.db() as db:
            db.execute("UPDATE conversations SET theme=? WHERE id=?", (dumps(theme), cid))

    def chunks(self, p, cid):
        self.conversation(p, cid)
        with self.db() as db:
            rows = db.execute('''SELECT * FROM chunks WHERE tenant=? AND
              (scope IN ('base','public') OR (scope='private' AND owner=?) OR
               (scope='conversation' AND owner=? AND conversation=?))''',
                              (p.tenant_id, p.user_id, p.user_id, cid)).fetchall()
        return [dict(r) for r in rows]

    def add_chunk(self, p, scope, cid, title, locator, content, chunk_id=None):
        if scope not in ("base", "public", "private", "conversation"):
            raise ValueError("Biblioteca inválida")
        if scope in ("base", "public") and p.role != "admin":
            raise PermissionError("Solo administradores pueden publicar en bibliotecas compartidas")
        if scope == "conversation":
            self.conversation(p, cid)
        with self.db() as db:
            db.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?)", (chunk_id or uid(), p.tenant_id,
                       p.user_id, scope, cid if scope == "conversation" else "", title, locator, content))

    def add_asset(self, p, cid, path, mime, asset_id):
        self.conversation(p, cid)
        with self.db() as db:
            db.execute("INSERT INTO assets VALUES(?,?,?,?,?,?)", (asset_id, p.tenant_id, p.user_id, cid, str(path), mime))

    def asset(self, p, cid, asset_id):
        self.conversation(p, cid)
        with self.db() as db:
            r = db.execute("SELECT * FROM assets WHERE id=? AND tenant=? AND owner=? AND conversation=?",
                           (asset_id, p.tenant_id, p.user_id, cid)).fetchone()
        if not r:
            raise KeyError("Imagen no encontrada")
        return dict(r)

    def new_job(self, p, cid, payload):
        self.conversation(p, cid)
        jid = uid()
        now = time.time()
        with self.db() as db:
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)", (jid, p.tenant_id, p.user_id,
                       cid, "queued", "En cola", dumps(payload), "{}", now, now))
        return jid

    def job(self, p, jid):
        with self.db() as db:
            r = db.execute("SELECT * FROM jobs WHERE id=? AND tenant=? AND owner=?", (jid, p.tenant_id, p.user_id)).fetchone()
        if not r:
            raise KeyError("Trabajo no encontrado")
        d = dict(r)
        d["result"] = json.loads(d["result"])
        d.pop("payload")
        return d

    def job_update(self, jid, status, stage, result=None):
        with self.db() as db:
            if result is None:
                db.execute("UPDATE jobs SET status=?,stage=?,updated=? WHERE id=?", (status, stage, time.time(), jid))
            else:
                db.execute("UPDATE jobs SET status=?,stage=?,result=?,updated=? WHERE id=?",
                           (status, stage, dumps(result), time.time(), jid))

    def recover_jobs(self):
        with self.db() as db:
            db.execute("UPDATE jobs SET status='failed',stage='Proceso interrumpido. Reenvía la solicitud.' WHERE status IN ('queued','running')")

    def save_version(self, p, cid, aid, version, spec, sources, formats, directory):
        self.conversation(p, cid)
        with self.db() as db:
            db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?,?,?,?)", (aid, version, p.tenant_id,
                       p.user_id, cid, dumps(spec), dumps(sources), dumps(formats), str(directory), time.time()))

    def version(self, p, aid, version=None):
        with self.db() as db:
            q = "SELECT * FROM versions WHERE artifact=? AND tenant=? AND owner=?"
            args = [aid, p.tenant_id, p.user_id]
            if version is not None:
                q += " AND version=?"
                args.append(version)
            r = db.execute(q + " ORDER BY version DESC LIMIT 1", args).fetchone()
        if not r:
            raise KeyError("Entregable no encontrado")
        d = dict(r)
        for name in ("spec", "sources", "formats"):
            d[name] = json.loads(d[name])
        return d

    def list_versions(self, p, cid):
        self.conversation(p, cid)
        with self.db() as db:
            rows = db.execute("SELECT artifact,version,formats,created FROM versions WHERE conversation=? AND tenant=? AND owner=? ORDER BY created DESC",
                              (cid, p.tenant_id, p.user_id)).fetchall()
        return [{**dict(r), "formats": json.loads(r["formats"])} for r in rows]

    def event(self, p, name, fields):
        # Solo metadatos operativos, nunca prompts ni contenido documental.
        with self.db() as db:
            db.execute("INSERT INTO events(tenant,owner,name,fields,created) VALUES(?,?,?,?,?)",
                       (p.tenant_id, p.user_id, name, dumps(fields), time.time()))
