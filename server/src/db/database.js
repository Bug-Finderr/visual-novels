import initSqlJs from 'sql.js';
import fs from 'fs';
import config from '../config.js';
import { ensureDir } from '../utils/fileUtils.js';
import path from 'path';
import logger from '../utils/logger.js';

let db;

export function getDb() {
  if (!db) {
    throw new Error('Database not initialized. Call initDatabase() first.');
  }
  return db;
}

/**
 * Wrapper around sql.js Database that provides a better-sqlite3-compatible API.
 */
class DbWrapper {
  constructor(sqlDb, dbPath) {
    this._db = sqlDb;
    this._dbPath = dbPath;
  }

  exec(sql) {
    this._db.run(sql);
    this._save();
  }

  prepare(sql) {
    return new StatementWrapper(this, sql);
  }

  pragma(str) {
    try {
      this._db.run(`PRAGMA ${str}`);
    } catch {
      // Some pragmas may not be supported in sql.js
    }
  }

  _save() {
    const data = this._db.export();
    fs.writeFileSync(this._dbPath, Buffer.from(data));
  }
}

class StatementWrapper {
  constructor(dbWrapper, sql) {
    this._dbWrapper = dbWrapper;
    this._sql = sql;
  }

  run(...args) {
    const params = this._resolveParams(args);
    this._dbWrapper._db.run(this._sql, params);
    this._dbWrapper._save();
    return { changes: this._dbWrapper._db.getRowsModified() };
  }

  get(...args) {
    const params = this._resolveParams(args);
    const stmt = this._dbWrapper._db.prepare(this._sql);
    stmt.bind(params);
    if (stmt.step()) {
      const row = stmt.getAsObject();
      stmt.free();
      return row;
    }
    stmt.free();
    return undefined;
  }

  all(...args) {
    const params = this._resolveParams(args);
    const results = [];
    const stmt = this._dbWrapper._db.prepare(this._sql);
    stmt.bind(params);
    while (stmt.step()) {
      results.push(stmt.getAsObject());
    }
    stmt.free();
    return results;
  }

  /**
   * Resolve parameters: supports both positional (?, ?, ?) and named (@key) binding.
   * better-sqlite3 uses .run({key: val}) for named params and .run(val1, val2) for positional.
   * sql.js uses arrays for positional and objects with $key/:key/@key for named.
   */
  _resolveParams(args) {
    if (args.length === 0) return {};
    if (args.length === 1 && typeof args[0] === 'object' && !Array.isArray(args[0])) {
      // Named parameters — convert @key to $key for sql.js
      const obj = args[0];
      const result = {};
      for (const [key, value] of Object.entries(obj)) {
        result[`@${key}`] = value === undefined ? null : value;
      }
      return result;
    }
    // Positional parameters
    return args.flat();
  }
}

export async function initDatabase() {
  await ensureDir(path.dirname(config.DB_PATH));

  const SQL = await initSqlJs();

  let sqlDb;
  if (fs.existsSync(config.DB_PATH)) {
    const buffer = fs.readFileSync(config.DB_PATH);
    sqlDb = new SQL.Database(buffer);
  } else {
    sqlDb = new SQL.Database();
  }

  db = new DbWrapper(sqlDb, config.DB_PATH);
  db.pragma('foreign_keys = ON');
  runMigrations();
  logger.info('Database initialized at', config.DB_PATH);
}

function runMigrations() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS sessions (
      id                          TEXT PRIMARY KEY,
      title                       TEXT NOT NULL,
      status                      TEXT NOT NULL DEFAULT 'created',
      setup_genre                 TEXT NOT NULL,
      setup_art_style             TEXT NOT NULL,
      setup_setting               TEXT NOT NULL,
      setup_protagonist_name      TEXT NOT NULL,
      setup_protagonist_personality TEXT NOT NULL,
      setup_tone                  TEXT NOT NULL,
      setup_premise               TEXT,
      world_lore                  TEXT,
      plot_arc                    TEXT,
      current_scene_id            TEXT,
      current_label               TEXT DEFAULT 'Start',
      created_at                  DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at                  DATETIME DEFAULT CURRENT_TIMESTAMP,
      last_played_at              DATETIME
    );

    CREATE TABLE IF NOT EXISTS characters (
      id                TEXT NOT NULL,
      session_id        TEXT NOT NULL,
      name              TEXT NOT NULL,
      color             TEXT NOT NULL DEFAULT '#FFFFFF',
      role              TEXT,
      personality       TEXT,
      appearance        TEXT,
      backstory         TEXT,
      relationship      TEXT,
      speech_style      TEXT,
      quirks            TEXT,
      sprites_generated INTEGER DEFAULT 0,
      is_dynamic        INTEGER DEFAULT 0,
      created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id, session_id),
      FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS scenes (
      id                TEXT NOT NULL,
      session_id        TEXT NOT NULL,
      name              TEXT NOT NULL,
      description       TEXT,
      narrative_context TEXT,
      image_generated   INTEGER DEFAULT 0,
      is_dynamic        INTEGER DEFAULT 0,
      created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id, session_id),
      FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS script_labels (
      session_id  TEXT NOT NULL,
      label_name  TEXT NOT NULL,
      statements  TEXT NOT NULL,
      sort_order  INTEGER DEFAULT 0,
      created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (session_id, label_name),
      FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS dialogue_history (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      session_id    TEXT NOT NULL,
      role          TEXT NOT NULL,
      content       TEXT NOT NULL,
      label_context TEXT,
      created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_dialogue_history_session
      ON dialogue_history(session_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_characters_session
      ON characters(session_id);
    CREATE INDEX IF NOT EXISTS idx_scenes_session
      ON scenes(session_id);
    CREATE INDEX IF NOT EXISTS idx_script_labels_session
      ON script_labels(session_id);
  `);
}
