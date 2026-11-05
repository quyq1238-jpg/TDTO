import json
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

SCHEMA='''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES(1);
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id) ON DELETE CASCADE,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts(identity TEXT PRIMARY KEY,attempts INTEGER NOT NULL,last REAL NOT NULL);
CREATE TABLE IF NOT EXISTS exams(id TEXT PRIMARY KEY,owner TEXT REFERENCES users(id) ON DELETE CASCADE,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS classes(id TEXT PRIMARY KEY,owner TEXT REFERENCES users(id) ON DELETE CASCADE,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,owner TEXT REFERENCES users(id) ON DELETE CASCADE,name TEXT NOT NULL,mime TEXT NOT NULL,content BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS scan_sessions(id TEXT PRIMARY KEY,owner TEXT REFERENCES users(id) ON DELETE CASCADE,exam_id TEXT REFERENCES exams(id),data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scans(id TEXT PRIMARY KEY,owner TEXT REFERENCES users(id) ON DELETE CASCADE,exam_id TEXT REFERENCES exams(id),data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS results(id TEXT PRIMARY KEY,owner TEXT REFERENCES users(id) ON DELETE CASCADE,exam_id TEXT REFERENCES exams(id),sbd TEXT NOT NULL,scan_id TEXT UNIQUE REFERENCES scans(id),data TEXT NOT NULL,UNIQUE(exam_id,sbd));
CREATE INDEX IF NOT EXISTS results_owner ON results(owner,exam_id);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,owner TEXT REFERENCES users(id) ON DELETE CASCADE,entity TEXT NOT NULL,at TEXT NOT NULL,data TEXT NOT NULL);
'''

def root():
    path=Path(os.environ.get('OMR_DATA_DIR','/workspace/omr-data'))
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    return path

@contextmanager
def db():
    connection=sqlite3.connect(root()/'omr.sqlite3',timeout=15)
    connection.row_factory=sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback(); raise
    finally: connection.close()

def init():
    with db() as c:
        c.executescript(SCHEMA)
        c.execute('PRAGMA journal_mode=WAL')
    os.chmod(root()/'omr.sqlite3',0o600)

def encode(data): return json.dumps(data,ensure_ascii=False,allow_nan=False)
def decode(row): return json.loads(row['data'])
