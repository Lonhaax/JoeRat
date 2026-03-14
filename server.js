const http = require('http');
const fs = require('fs');
const path = require('path');
const WebSocket = require('ws');
const crypto = require('crypto');
const dotenv = require('dotenv');

dotenv.config();

const PORT = Number(process.env.PORT || 3000);
const ROOM_SECRET = process.env.ROOM_SECRET || 'boi123';
const ADMIN_KEY = process.env.ADMIN_KEY || 'admin123';
const ROOM_SCAN_INTERVAL_MS = Number(process.env.ROOM_SCAN_INTERVAL_MS || 2000);
const CLIENT_ACTIVE_WINDOW_MS = Number(process.env.CLIENT_ACTIVE_WINDOW_MS || 15000);
const CLIENT_LIST_LOG_INTERVAL_MS = Number(process.env.CLIENT_LIST_LOG_INTERVAL_MS || 5000);
const CONTROL_PROTOCOL_VERSION = 'control-protocol-2026-03-08-v2';

// ── Security configuration (env vars or defaults) ──
const MAX_MESSAGE_SIZE_BYTES = Number(process.env.MAX_MESSAGE_SIZE_BYTES || 1000 * 1024 * 1024); // 50 MB
const RATE_LIMIT_WINDOW_MS = 1000;                                                              // 1 second window
const RATE_LIMIT_MAX_MESSAGES = Number(process.env.RATE_LIMIT_MAX_MESSAGES || 120);              // max msgs per window
const RATE_LIMIT_MAX_BINARY = Number(process.env.RATE_LIMIT_MAX_BINARY || 60);                   // max binary frames per window
const MAX_FAILED_AUTHS_PER_IP = Number(process.env.MAX_FAILED_AUTHS_PER_IP || 5);               // before temp ban
const AUTH_BAN_DURATION_MS = Number(process.env.AUTH_BAN_DURATION_MS || 60000);                  // 1 minute ban
const JOIN_TIMEOUT_MS = Number(process.env.JOIN_TIMEOUT_MS || 10000);                            // must join within 10s
const PENDING_REQUEST_TTL_MS = Number(process.env.PENDING_REQUEST_TTL_MS || 120000);             // 2 min TTL for pending requests
const MAX_ROOMS = Number(process.env.MAX_ROOMS || 50);
const MAX_SENDERS_PER_ROOM = Number(process.env.MAX_SENDERS_PER_ROOM || 20);
const MAX_RECEIVERS_PER_ROOM = Number(process.env.MAX_RECEIVERS_PER_ROOM || 5);
const MAX_ROOMID_LENGTH = 64;
const MAX_MACHINEID_LENGTH = 128;

// ── MOTD (Message of the Day) ──
let SERVER_MOTD = process.env.MOTD || '';
try {
  const motdPath = require('path').join(__dirname, 'motd.txt');
  if (require('fs').existsSync(motdPath)) {
    SERVER_MOTD = require('fs').readFileSync(motdPath, 'utf8').trim();
  }
} catch {}

// ── Brute-force protection: track failed auth attempts per IP ──
// Map<ip, { count, firstAttempt, bannedUntil }>
const authAttempts = new Map();

function isIPBanned(ip) {
  const entry = authAttempts.get(ip);
  if (!entry) return false;
  if (entry.bannedUntil && Date.now() < entry.bannedUntil) return true;
  // Reset if ban expired
  if (entry.bannedUntil && Date.now() >= entry.bannedUntil) {
    authAttempts.delete(ip);
    return false;
  }
  return false;
}

function recordFailedAuth(ip) {
  const now = Date.now();
  let entry = authAttempts.get(ip);
  if (!entry) {
    entry = { count: 0, firstAttempt: now, bannedUntil: null };
    authAttempts.set(ip, entry);
  }
  // Reset counter if window expired (5 minutes)
  if (now - entry.firstAttempt > 300000) {
    entry.count = 0;
    entry.firstAttempt = now;
    entry.bannedUntil = null;
  }
  entry.count++;
  if (entry.count >= MAX_FAILED_AUTHS_PER_IP) {
    entry.bannedUntil = now + AUTH_BAN_DURATION_MS;
    log(`[SECURITY] IP ${ip} temporarily banned for ${AUTH_BAN_DURATION_MS / 1000}s after ${entry.count} failed auth attempts`);
  }
}

function recordSuccessAuth(ip) {
  authAttempts.delete(ip);
}

// Periodically clean up expired bans (every 5 minutes)
setInterval(() => {
  const now = Date.now();
  for (const [ip, entry] of authAttempts.entries()) {
    if (entry.bannedUntil && now >= entry.bannedUntil) {
      authAttempts.delete(ip);
    } else if (now - entry.firstAttempt > 300000) {
      authAttempts.delete(ip);
    }
  }
}, 300000);

// ── Rate limiter per client ──
function checkRateLimit(ws, isBinary) {
  const now = Date.now();
  if (!ws._rateWindow || now - ws._rateWindowStart > RATE_LIMIT_WINDOW_MS) {
    ws._rateWindow = 0;
    ws._rateBinary = 0;
    ws._rateWindowStart = now;
  }
  ws._rateWindow++;
  if (isBinary) ws._rateBinary++;

  if (ws._rateWindow > RATE_LIMIT_MAX_MESSAGES) {
    if (!ws._rateLimitWarned) {
      ws._rateLimitWarned = true;
      log(`[RATE-LIMIT] Client ${ws.clientId} exceeded ${RATE_LIMIT_MAX_MESSAGES} msgs/sec — dropping messages`);
    }
    return false; // drop
  }
  if (isBinary && ws._rateBinary > RATE_LIMIT_MAX_BINARY) {
    return false; // drop excess binary frames
  }
  ws._rateLimitWarned = false;
  return true; // allow
}

// ── Pending request maps with TTL cleanup ──
const pendingFileRequests = new Map();     // requestId -> { ws, createdAt }
const pendingCommandRequests = new Map();  // requestId -> { ws, createdAt }
const pendingClipboardRequests = new Map();// requestId -> { ws, createdAt }

function setPendingRequest(map, requestId, ws) {
  map.set(requestId, { ws, createdAt: Date.now() });
}

function getPendingRequest(map, requestId) {
  const entry = map.get(requestId);
  if (!entry) return null;
  map.delete(requestId);
  if (Date.now() - entry.createdAt > PENDING_REQUEST_TTL_MS) {
    log(`[PENDING] Request ${requestId} expired (TTL ${PENDING_REQUEST_TTL_MS}ms)`);
    return null;
  }
  return entry.ws;
}

// Periodically purge expired pending requests
setInterval(() => {
  const now = Date.now();
  for (const [map, name] of [[pendingFileRequests, 'file'], [pendingCommandRequests, 'cmd'], [pendingClipboardRequests, 'clip']]) {
    let purged = 0;
    for (const [id, entry] of map.entries()) {
      if (now - entry.createdAt > PENDING_REQUEST_TTL_MS || !entry.ws || entry.ws.readyState !== WebSocket.OPEN) {
        map.delete(id);
        purged++;
      }
    }
    if (purged > 0) log(`[PENDING] Purged ${purged} expired ${name} request(s)`);
  }
}, 60000);

// ── Input sanitization ──
function sanitizeString(val, maxLen = 256) {
  if (typeof val !== 'string') return '';
  // Strip control characters except newline/tab, then truncate
  return val.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '').substring(0, maxLen);
}

function sanitizeRoomId(val) {
  if (typeof val !== 'string') return '';
  // Only allow alphanumeric, dash, underscore, dot
  return val.replace(/[^a-zA-Z0-9\-_.]/g, '').substring(0, MAX_ROOMID_LENGTH);
}

function sanitizeMachineId(val) {
  if (typeof val !== 'string') return '';
  // Allow alphanumeric, dash, underscore, dot, space
  return val.replace(/[^a-zA-Z0-9\-_. ]/g, '').substring(0, MAX_MACHINEID_LENGTH);
}

// ── Audit logger (security-sensitive actions) ──
function audit(action, details) {
  const timestamp = new Date().toISOString();
  const line = `[${timestamp}] [AUDIT] ${action} ${JSON.stringify(details)}`;
  try {
    require('fs').appendFileSync('server-audit.log', line + '\n', 'utf8');
  } catch {}
  log(line);
}

// ══════════════════════════════════════════════════════════════
// ── SQLite Database (rooms, admin users, audit log) ──
// ══════════════════════════════════════════════════════════════
const Database = require('better-sqlite3');
const DB_PATH = path.join(__dirname, 'server.db');
const db = new Database(DB_PATH);

// Enable WAL mode for better concurrent read performance
db.pragma('journal_mode = WAL');

// ── Schema ──
db.exec(`
  CREATE TABLE IF NOT EXISTS rooms (
    roomId    TEXT PRIMARY KEY,
    secret    TEXT NOT NULL,
    label     TEXT DEFAULT '',
    createdAt TEXT DEFAULT (datetime('now')),
    createdBy TEXT DEFAULT 'admin'
  );
  CREATE TABLE IF NOT EXISTS admin_users (
    username  TEXT PRIMARY KEY,
    key_hash  TEXT NOT NULL,
    role      TEXT DEFAULT 'admin',
    createdAt TEXT DEFAULT (datetime('now'))
  );
  CREATE TABLE IF NOT EXISTS audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    action    TEXT NOT NULL,
    details   TEXT DEFAULT '{}'
  );
`);

// ── Prepared statements (much faster than ad-hoc queries) ──
const stmts = {
  getRoom:      db.prepare('SELECT * FROM rooms WHERE roomId = ?'),
  getAllRooms:   db.prepare('SELECT * FROM rooms ORDER BY createdAt DESC'),
  insertRoom:   db.prepare('INSERT INTO rooms (roomId, secret, label, createdBy) VALUES (?, ?, ?, ?)'),
  updateRoom:   db.prepare('UPDATE rooms SET secret = ?, label = ? WHERE roomId = ?'),
  deleteRoom:   db.prepare('DELETE FROM rooms WHERE roomId = ?'),
  countRooms:   db.prepare('SELECT COUNT(*) as cnt FROM rooms'),
  insertAudit:  db.prepare('INSERT INTO audit_log (action, details) VALUES (?, ?)'),
  getAuditLog:  db.prepare('SELECT * FROM audit_log ORDER BY id DESC LIMIT ?'),
  getAdminUser: db.prepare('SELECT * FROM admin_users WHERE username = ?'),
};

// ── Migrate from rooms.json if it exists ──
try {
  const oldPath = path.join(__dirname, 'rooms.json');
  if (fs.existsSync(oldPath)) {
    const old = JSON.parse(fs.readFileSync(oldPath, 'utf8'));
    const insertMany = db.transaction((rooms) => {
      for (const [roomId, cfg] of Object.entries(rooms)) {
        if (!stmts.getRoom.get(roomId)) {
          stmts.insertRoom.run(roomId, cfg.secret || ROOM_SECRET, cfg.label || roomId, cfg.createdBy || 'migrated');
        }
      }
    });
    insertMany(old);
    fs.renameSync(oldPath, oldPath + '.bak');
    console.log(`[DB] Migrated ${Object.keys(old).length} rooms from rooms.json → server.db`);
  }
} catch (e) { console.log(`[DB] Migration skipped: ${e.message}`); }

// ── DB helper functions ──
function dbGetRoom(roomId) {
  return stmts.getRoom.get(roomId) || null;
}

function dbGetAllRooms() {
  return stmts.getAllRooms.all();
}

function dbCreateRoom(roomId, secret, label, createdBy) {
  stmts.insertRoom.run(roomId, secret, label || roomId, createdBy || 'admin');
}

function dbUpdateRoom(roomId, secret, label) {
  const existing = stmts.getRoom.get(roomId);
  if (!existing) return false;
  stmts.updateRoom.run(secret ?? existing.secret, label ?? existing.label, roomId);
  return true;
}

function dbDeleteRoom(roomId) {
  return stmts.deleteRoom.run(roomId).changes > 0;
}

function dbCountRooms() {
  return stmts.countRooms.get().cnt;
}

function dbAudit(action, details) {
  stmts.insertAudit.run(action, JSON.stringify(details));
}

// Get the secret for a room: per-room secret from DB, else global fallback
function getRoomSecret(roomId) {
  const row = dbGetRoom(roomId);
  if (row && row.secret) return row.secret;
  return ROOM_SECRET;
}

// ── Helper: read JSON body from HTTP request ──
function readBody(req) {
  return new Promise((resolve) => {
    let body = '';
    req.on('data', (chunk) => { body += chunk; if (body.length > 65536) { body = ''; req.destroy(); } });
    req.on('end', () => { try { resolve(JSON.parse(body)); } catch { resolve(null); } });
  });
}

// ── Helper: check admin key from header or query ──
function checkAdminKey(req) {
  const authHeader = req.headers['x-admin-key'] || '';
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const queryKey = url.searchParams.get('key') || '';
  return authHeader === ADMIN_KEY || queryKey === ADMIN_KEY;
}

// ── Load HTML files ──
let ADMIN_HTML = '';
try {
  const adminPath = path.join(__dirname, 'admin-panel.html');
  if (fs.existsSync(adminPath)) {
    ADMIN_HTML = fs.readFileSync(adminPath, 'utf8');
  }
} catch {}

// ── HTTP server (serves admin panel, API, user page + upgrades to WebSocket) ──
const httpServer = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = url.pathname;

  // ── CORS headers for API ──
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-Admin-Key');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  // ── GET /admin → serve the admin panel ──
  if (req.method === 'GET' && (pathname === '/admin' || pathname === '/admin/')) {
    if (!ADMIN_HTML) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('admin-panel.html not found. Place it next to server.js.');
      return;
    }
    const injected = ADMIN_HTML.replace(
      'value="ws://vnc.jake.cash:3000"',
      `value="ws://${req.headers.host || 'localhost:' + PORT}"`
    );
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(injected);
    return;
  }

  // ── GET /status → JSON health check (public) ──
  if (req.method === 'GET' && pathname === '/status') {
    const status = {
      ok: true,
      uptime: process.uptime(),
      rooms: rooms.size,
      clients: clients.size,
      protocol: CONTROL_PROTOCOL_VERSION,
      motd: SERVER_MOTD || null
    };
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(status, null, 2));
    return;
  }

  // ── POST /api/auth → verify admin key ──
  if (req.method === 'POST' && pathname === '/api/auth') {
    const body = await readBody(req);
    if (!body || body.key !== ADMIN_KEY) {
      res.writeHead(401, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Invalid admin key' }));
      return;
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true }));
    return;
  }

  // ══════════════════════════════════════════
  // ── ADMIN API (all require admin key) ──
  // ═════════════════════════════���════════════

  // ── GET /api/rooms → list all configured rooms + live status ──
  if (req.method === 'GET' && pathname === '/api/rooms') {
    if (!checkAdminKey(req)) { res.writeHead(401, { 'Content-Type': 'application/json' }); res.end('{"error":"Unauthorized"}'); return; }
    const dbRooms = dbGetAllRooms();
    const result = [];
    // Merge DB rooms + any live-only rooms (connected via global secret)
    const allRoomIds = new Set([...dbRooms.map(r => r.roomId), ...rooms.keys()]);
    for (const rid of allRoomIds) {
      const config = dbRooms.find(r => r.roomId === rid) || null;
      const live = rooms.get(rid);
      result.push({
        roomId: rid,
        label: config?.label || rid,
        secret: config?.secret || ROOM_SECRET,
        createdAt: config?.createdAt || null,
        createdBy: config?.createdBy || null,
        configured: !!config,
        senders: live ? Array.from(live.senders.keys()) : [],
        receivers: live ? live.receivers.size : 0,
        online: live ? (live.senders.size + live.receivers.size) : 0
      });
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(result));
    return;
  }

  // ── POST /api/rooms → create a new room config ──
  if (req.method === 'POST' && pathname === '/api/rooms') {
    if (!checkAdminKey(req)) { res.writeHead(401, { 'Content-Type': 'application/json' }); res.end('{"error":"Unauthorized"}'); return; }
    const body = await readBody(req);
    if (!body) { res.writeHead(400, { 'Content-Type': 'application/json' }); res.end('{"error":"Invalid JSON body"}'); return; }
    const roomId = sanitizeRoomId(body.roomId || '');
    if (!roomId) { res.writeHead(400, { 'Content-Type': 'application/json' }); res.end('{"error":"roomId is required (alphanumeric, dash, underscore, dot)"}'); return; }
    if (dbGetRoom(roomId)) { res.writeHead(409, { 'Content-Type': 'application/json' }); res.end('{"error":"Room already exists"}'); return; }
    if (dbCountRooms() >= MAX_ROOMS) { res.writeHead(400, { 'Content-Type': 'application/json' }); res.end('{"error":"Max room limit reached"}'); return; }
    const secret = sanitizeString(body.secret || '', 128) || crypto.randomBytes(8).toString('hex');
    const label = sanitizeString(body.label || roomId, 128);
    dbCreateRoom(roomId, secret, label, 'admin');
    audit('room-created', { roomId, label });
    dbAudit('room-created', { roomId, label });
    res.writeHead(201, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true, roomId, secret, label }));
    return;
  }

  // ── DELETE /api/rooms/:roomId → delete a room config + kick everyone ──
  const deleteMatch = pathname.match(/^\/api\/rooms\/([^/]+)$/);
  if (req.method === 'DELETE' && deleteMatch) {
    if (!checkAdminKey(req)) { res.writeHead(401, { 'Content-Type': 'application/json' }); res.end('{"error":"Unauthorized"}'); return; }
    const roomId = sanitizeRoomId(decodeURIComponent(deleteMatch[1]));
    if (!roomId) { res.writeHead(400, { 'Content-Type': 'application/json' }); res.end('{"error":"Invalid roomId"}'); return; }
    const existed = dbDeleteRoom(roomId);
    // Kick all connected clients in this room
    const live = rooms.get(roomId);
    if (live) {
      for (const [, senderWs] of live.senders) {
        try { sendJson(senderWs, { type: 'error', message: 'Room has been deleted by admin.' }); senderWs.close(4002, 'Room deleted'); } catch {}
      }
      for (const receiver of live.receivers) {
        try { sendJson(receiver, { type: 'error', message: 'Room has been deleted by admin.' }); receiver.close(4002, 'Room deleted'); } catch {}
      }
      rooms.delete(roomId);
    }
    audit('room-deleted', { roomId });
    dbAudit('room-deleted', { roomId });
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true, existed, roomId }));
    return;
  }

  // ── PUT /api/rooms/:roomId → update room config (label, secret) ──
  const putMatch = pathname.match(/^\/api\/rooms\/([^/]+)$/);
  if (req.method === 'PUT' && putMatch) {
    if (!checkAdminKey(req)) { res.writeHead(401, { 'Content-Type': 'application/json' }); res.end('{"error":"Unauthorized"}'); return; }
    const roomId = sanitizeRoomId(decodeURIComponent(putMatch[1]));
    const existing = dbGetRoom(roomId);
    if (!roomId || !existing) { res.writeHead(404, { 'Content-Type': 'application/json' }); res.end('{"error":"Room not found"}'); return; }
    const body = await readBody(req);
    if (!body) { res.writeHead(400, { 'Content-Type': 'application/json' }); res.end('{"error":"Invalid JSON body"}'); return; }
    const newSecret = body.secret !== undefined ? sanitizeString(body.secret, 128) : existing.secret;
    const newLabel = body.label !== undefined ? sanitizeString(body.label, 128) : existing.label;
    dbUpdateRoom(roomId, newSecret, newLabel);
    audit('room-updated', { roomId, label: newLabel });
    dbAudit('room-updated', { roomId, label: newLabel });
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true, roomId, secret: newSecret, label: newLabel }));
    return;
  }

  // ── GET /api/clients → list all connected clients (admin) ──
  if (req.method === 'GET' && pathname === '/api/clients') {
    if (!checkAdminKey(req)) { res.writeHead(401, { 'Content-Type': 'application/json' }); res.end('{"error":"Unauthorized"}'); return; }
    const result = [];
    for (const ws of clients.values()) {
      result.push({
        clientId: ws.clientId,
        ip: ws.remoteIP,
        role: ws.meta?.role || 'unknown',
        roomId: ws.meta?.roomId || null,
        machineId: ws.meta?.machineId || null,
        status: getClientStatus(ws),
        connectedAt: ws.connectedAt,
        lastActivity: ws.lastActivityAt
      });
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(result));
    return;
  }

  // ── GET / → redirect to /admin ──
  if (req.method === 'GET' && pathname === '/') {
    res.writeHead(302, { 'Location': '/admin' });
    res.end();
    return;
  }

  // Everything else → 404
  res.writeHead(404, { 'Content-Type': 'text/plain' });
  res.end('Not found. Try /admin or /status');
});

httpServer.listen(PORT);

// ── WebSocket server attached to HTTP server ──
const server = new WebSocket.Server({
  server: httpServer,
  maxPayload: MAX_MESSAGE_SIZE_BYTES,
  verifyClient: (info, cb) => {
    const ip = info.req.socket.remoteAddress || 'unknown';
    if (isIPBanned(ip)) {
      log(`[SECURITY] Rejected connection from banned IP: ${ip}`);
      cb(false, 403, 'Temporarily banned');
      return;
    }
    cb(true);
  }
});

// rooms[roomId] = { senders: Map<machineId, ws>, receivers: Set<ws> }
const rooms = new Map();
const clients = new Map();
let nextClientId = 1;

function log(msg) {
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] ${msg}`);
  try {
    require('fs').appendFileSync('server-debug.log', `[${timestamp}] ${msg}\n`, 'utf8');
  } catch {}
}

function logRoomState(roomId) {
  const room = rooms.get(roomId);
  if (!room) {
    log(`  Room "${roomId}" not found`);
    return;
  }
  const senders = Array.from(room.senders.keys());
  const receiverCount = room.receivers.size;
  log(`  Room "${roomId}": Senders=[${senders.join(', ')}], Receivers=${receiverCount}`);
}

function getRoom(roomId) {
  if (!rooms.has(roomId)) {
    rooms.set(roomId, { senders: new Map(), receivers: new Set() });
  }
  return rooms.get(roomId);
}

function registerClient(ws, ip) {
  const clientId = `c${nextClientId}`;
  nextClientId += 1;
  const now = Date.now();

  ws.clientId = clientId;
  ws.connectedAt = now;
  ws.lastActivityAt = now;
  ws.remoteIP = ip;

  clients.set(clientId, ws);
  return clientId;
}

function touchClient(ws) {
  if (!ws) return;
  ws.lastActivityAt = Date.now();
}

function getClientStatus(ws) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return 'disconnected';
  const lastActivityAt = ws.lastActivityAt || ws.connectedAt || 0;
  return (Date.now() - lastActivityAt) <= CLIENT_ACTIVE_WINDOW_MS ? 'active' : 'inactive';
}

function logClientList(reason) {
  log(`[CLIENTS] ${reason} | total=${clients.size}`);
  if (clients.size === 0) {
    log(`[CLIENTS] (none connected)`);
    return;
  }
  for (const ws of clients.values()) {
    const status = getClientStatus(ws);
    const role = ws.meta?.role || 'unknown';
    const roomId = ws.meta?.roomId || '-';
    const machineId = ws.meta?.machineId || '-';
    const targetMachineId = ws.meta?.targetMachineId || '-';
    const idleMs = Math.max(0, Date.now() - (ws.lastActivityAt || ws.connectedAt || Date.now()));
    log(`[CLIENT] id=${ws.clientId} ip=${ws.remoteIP || '-'} status=${status} role=${role} room=${roomId} machine=${machineId} target=${targetMachineId} idleMs=${idleMs}`);
  }
}

function sendJson(ws, payload) {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
  }
}

function broadcastRoomState(room) {
  const activeMachines = Array.from(room.senders.keys());
  for (const receiver of room.receivers) {
    if (receiver.readyState !== WebSocket.OPEN) continue;
    if (activeMachines.length > 0) {
      sendJson(receiver, { type: 'active-machines', machines: activeMachines });
      sendJson(receiver, { type: 'sender-online', machineId: activeMachines[0] });
    } else {
      sendJson(receiver, { type: 'waiting-for-sender' });
    }
  }
}

function pruneClosedSockets(room) {
  for (const receiver of Array.from(room.receivers)) {
    if (receiver.readyState !== WebSocket.OPEN) {
      room.receivers.delete(receiver);
    }
  }
  for (const [machineId, senderWs] of Array.from(room.senders.entries())) {
    if (senderWs.readyState !== WebSocket.OPEN) {
      room.senders.delete(machineId);
      for (const receiver of room.receivers) {
        sendJson(receiver, { type: 'sender-offline', machineId });
      }
    }
  }
}

function cleanupSocket(ws) {
  // Clear join timeout
  if (ws._joinTimeout) {
    clearTimeout(ws._joinTimeout);
    ws._joinTimeout = null;
  }

  if (ws?.clientId) {
    clients.delete(ws.clientId);
  }

  for (const [roomId, room] of rooms.entries()) {
    for (const [machineId, senderWs] of room.senders.entries()) {
      if (senderWs === ws) {
        room.senders.delete(machineId);
        for (const receiver of room.receivers) {
          sendJson(receiver, { type: 'sender-offline', machineId });
        }
        break;
      }
    }
    if (room.receivers.has(ws)) {
      room.receivers.delete(ws);
    }
    if (room.senders.size === 0 && room.receivers.size === 0) {
      rooms.delete(roomId);
    }
  }
}

// ── Resolve a machineId to a sender WebSocket in a room (case-insensitive + single-sender fallback) ──
function resolveSender(room, requestedMachineId) {
  let resolvedId = requestedMachineId;
  let senderWs = room.senders.get(resolvedId);

  if (!senderWs) {
    const lower = requestedMachineId.toLowerCase();
    for (const [mid, sender] of room.senders.entries()) {
      if (mid.toLowerCase() === lower) {
        resolvedId = mid;
        senderWs = sender;
        break;
      }
    }
  }

  if (!senderWs && room.senders.size === 1) {
    const [onlyId, onlySender] = room.senders.entries().next().value;
    resolvedId = onlyId;
    senderWs = onlySender;
  }

  return { resolvedId, senderWs };
}

// ══════════════════════════════════════════════════════════════
// ── CONNECTION HANDLER ──
// ══════════════════════════════════════════════════════════════
server.on('connection', (ws, req) => {
  const ip = req.headers['x-forwarded-for']?.split(',')[0]?.trim() || req.socket.remoteAddress || 'unknown';
  const clientId = registerClient(ws, ip);
  log(`[CONNECTION] New client id=${clientId} ip=${ip}`);
  ws.meta = { role: null, roomId: null, machineId: null, targetMachineId: null };

  // ── Join timeout: if client doesn't send a valid join within JOIN_TIMEOUT_MS, disconnect ──
  ws._joinTimeout = setTimeout(() => {
    if (!ws.meta.role) {
      log(`[SECURITY] Client ${clientId} ip=${ip} did not join within ${JOIN_TIMEOUT_MS / 1000}s — disconnecting`);
      sendJson(ws, { type: 'error', message: 'Join timeout. Send a join message within 10 seconds.' });
      ws.close(4001, 'Join timeout');
    }
  }, JOIN_TIMEOUT_MS);

  logClientList('after-connect');

  ws.on('message', (message, isBinary) => {
    touchClient(ws);

    // ── Rate limiting ──
    if (!checkRateLimit(ws, isBinary)) {
      return; // silently drop
    }

    // ══════════════════════════════════════════
    // ── BINARY FRAMES (screen capture) ──
    // ══════════════════════════════════════════
    if (isBinary) {
      if (ws.meta.role !== 'sender' || !ws.meta.roomId || !ws.meta.machineId) {
        return;
      }

      const room = rooms.get(ws.meta.roomId);
      if (!room || room.senders.get(ws.meta.machineId) !== ws) {
        return;
      }

      let forwarded = 0;
      for (const receiver of room.receivers) {
        if (receiver.readyState !== WebSocket.OPEN) continue;

        // Backpressure: skip slow receivers
        if (receiver.bufferedAmount > 2 * 1024 * 1024) continue;

        const subscribeAll = receiver.meta && receiver.meta.subscribeAll;
        if (!subscribeAll) {
          if (receiver.meta && receiver.meta.targetMachineId && receiver.meta.targetMachineId !== ws.meta.machineId) {
            continue;
          }
        }
        sendJson(receiver, { type: 'frame-from', machineId: ws.meta.machineId });
        receiver.send(message, { binary: true });
        forwarded++;
      }
      if (!ws._binaryCount) ws._binaryCount = 0;
      ws._binaryCount++;
      if (ws._binaryCount === 1 || ws._binaryCount % 100 === 0) {
        log(`[BINARY] sender=${ws.meta.machineId} room=${ws.meta.roomId} forwarded to ${forwarded} receiver(s) (frame #${ws._binaryCount})`);
      }
      return;
    }

    // ══════════════════════════════════════════
    // ── JSON MESSAGES ──
    // ══════════════════════════════════════════
    let data;
    try {
      data = JSON.parse(String(message));
    } catch {
      log(`[MESSAGE] Invalid JSON from ${ws.clientId}`);
      sendJson(ws, { type: 'error', message: 'Invalid JSON message.' });
      return;
    }

    // ── Require join before any other message type ──
    if (!ws.meta.role && data.type !== 'join') {
      log(`[SECURITY] Client ${ws.clientId} sent type="${data.type}" before joining — rejected`);
      sendJson(ws, { type: 'error', message: 'Must join a room first.' });
      return;
    }

    // ── file-list relay (sender → receivers) ──
    if (data.type === 'file-list') {
      if (ws.meta.role !== 'sender' || !ws.meta.roomId || !ws.meta.machineId) return;
      const room = rooms.get(ws.meta.roomId);
      if (!room || room.senders.get(ws.meta.machineId) !== ws) return;
      for (const receiver of room.receivers) {
        if (receiver.readyState !== WebSocket.OPEN) continue;
        if (receiver.meta && receiver.meta.targetMachineId && receiver.meta.targetMachineId !== ws.meta.machineId) continue;
        sendJson(receiver, data);
      }
      return;
    }

    // ── file-data relay (sender → specific requester) ──
    if (data.type === 'file-data') {
      if (ws.meta.role !== 'sender' || !ws.meta.roomId || !ws.meta.machineId) return;
      const room = rooms.get(ws.meta.roomId);
      if (!room || room.senders.get(ws.meta.machineId) !== ws) return;
      const reqId = data.requestId;
      const receiver = getPendingRequest(pendingFileRequests, reqId);
      if (receiver && receiver.readyState === WebSocket.OPEN) {
        sendJson(receiver, data);
        log(`[FILE-DATA] relayed from sender=${ws.meta.machineId} fileName=${data.fileName || '-'} to requester`);
      } else {
        log(`[FILE-DATA] no matching requestId=${reqId || '(none)'}, dropping`);
      }
      return;
    }

    // ── command-output relay ──
    if (data.type === 'command-output') {
      if (ws.meta.role !== 'sender' || !ws.meta.roomId || !ws.meta.machineId) return;
      const room = rooms.get(ws.meta.roomId);
      if (!room || room.senders.get(ws.meta.machineId) !== ws) return;
      const receiver = getPendingRequest(pendingCommandRequests, data.requestId);
      if (receiver && receiver.readyState === WebSocket.OPEN) sendJson(receiver, data);
      return;
    }

    // ── clipboard-content relay ──
    if (data.type === 'clipboard-content') {
      if (ws.meta.role !== 'sender' || !ws.meta.roomId || !ws.meta.machineId) return;
      const room = rooms.get(ws.meta.roomId);
      if (!room || room.senders.get(ws.meta.machineId) !== ws) return;
      const receiver = getPendingRequest(pendingClipboardRequests, data.requestId);
      if (receiver && receiver.readyState === WebSocket.OPEN) sendJson(receiver, data);
      return;
    }

    // ── system-info / telemetry relay ──
    if (data.type === 'system-info' || data.type === 'telemetry') {
      if (ws.meta.role !== 'sender' || !ws.meta.roomId || !ws.meta.machineId) return;
      const room = rooms.get(ws.meta.roomId);
      if (!room || room.senders.get(ws.meta.machineId) !== ws) return;

      const normalizedInfo = (data.info && typeof data.info === 'object')
        ? data.info
        : (data.systemInfo && typeof data.systemInfo === 'object')
          ? data.systemInfo
          : {
            cpuName: data.cpuName ?? data.cpuModel ?? null,
            cpuPercent: data.cpuPercent ?? data.cpuUsage ?? null,
            cpuCores: data.cpuCores ?? null,
            memoryPercent: data.memoryPercent ?? data.memoryUsage ?? null,
            usedMemMb: data.usedMemMb ?? data.memoryUsedMb ?? null,
            totalMemMb: data.totalMemMb ?? data.memoryTotalMb ?? null,
            uptimeSeconds: data.uptimeSeconds ?? null,
            hostname: data.hostname ?? null,
            platform: data.platform ?? null,
            arch: data.arch ?? null
          };

      const payload = {
        type: 'system-info',
        machineId: ws.meta.machineId,
        info: normalizedInfo,
        timestamp: Date.now()
      };
      for (const receiver of room.receivers) {
        if (receiver.readyState === WebSocket.OPEN) sendJson(receiver, payload);
      }
      return;
    }

    // ── select_sender ──
    if (data.type === 'select_sender') {
      if (ws.meta.role !== 'receiver' || !ws.meta.roomId) return;
      const newTarget = sanitizeString(data.sender || '', MAX_MACHINEID_LENGTH) || null;
      ws.meta.targetMachineId = newTarget;
      log(`[SELECT] receiver id=${ws.clientId} now targeting machine="${newTarget || '(any)'}"`);
      return;
    }

    // ── set-subscribe-all ──
    if (data.type === 'set-subscribe-all') {
      if (ws.meta.role !== 'receiver' || !ws.meta.roomId) return;
      ws.meta.subscribeAll = Boolean(data.enabled);
      log(`[SUBSCRIBE] receiver id=${ws.clientId} subscribe-all=${ws.meta.subscribeAll}`);
      return;
    }

    // ── remote-control ──
    if (data.type === 'remote-control') {
      if (ws.meta.role !== 'receiver' || !ws.meta.roomId) return;

      const room = rooms.get(ws.meta.roomId);
      if (!room) return;

      const requestedMachineId = sanitizeMachineId(data.machineId || ws.meta.targetMachineId || '');
      if (!requestedMachineId) {
        sendJson(ws, { type: 'error', message: 'remote-control requires machineId.' });
        return;
      }

      const { resolvedId, senderWs } = resolveSender(room, requestedMachineId);

      if (!senderWs || senderWs.readyState !== WebSocket.OPEN) {
        sendJson(ws, { type: 'error', message: `Target machine "${requestedMachineId}" is offline.` });
        return;
      }

      // Track pending requests with TTL
      if (data.action === 'file-download' && data.requestId) {
        setPendingRequest(pendingFileRequests, data.requestId, ws);
      }
      if (data.action === 'execute-command' && data.requestId) {
        setPendingRequest(pendingCommandRequests, data.requestId, ws);
        audit('execute-command', { receiver: ws.clientId, ip: ws.remoteIP, machine: resolvedId, command: sanitizeString(data.command || '', 500) });
      }
      if (data.action === 'clipboard-get' && data.requestId) {
        setPendingRequest(pendingClipboardRequests, data.requestId, ws);
      }

      // Audit dangerous actions
      if (data.action === 'file-upload') {
        audit('file-upload', { receiver: ws.clientId, ip: ws.remoteIP, machine: resolvedId, remotePath: data.remotePath, fileName: data.fileName });
      }
      if (data.action === 'file-download') {
        audit('file-download', { receiver: ws.clientId, ip: ws.remoteIP, machine: resolvedId, path: data.path, fileName: data.fileName });
      }

      sendJson(senderWs, {
        type: 'remote-control',
        machineId: resolvedId,
        action: data.action,
        xNorm: data.xNorm,
        yNorm: data.yNorm,
        button: data.button,
        delta: data.delta,
        key: data.key,
        keyCode: data.keyCode,
        pid: data.pid,
        processName: data.processName,
        packageName: data.packageName,
        forceKill: data.forceKill,
        filename: data.filename,
        fileName: data.fileName,
        remotePath: data.remotePath,
        data: data.data,
        destPath: data.destPath,
        text: data.text,
        path: data.path,
        locked: data.locked,
        requestId: data.requestId,
        command: data.command,
        timestamp: Date.now()
      });

      log(`[CONTROL] relayed to sender machine=${resolvedId} action=${data.action || '-'}`);
      return;
    }

    // ── stream-quality ──
    if (data.type === 'stream-quality') {
      if (ws.meta.role !== 'receiver' || !ws.meta.roomId) return;
      const room = rooms.get(ws.meta.roomId);
      if (!room) return;

      const requestedMachineId = sanitizeMachineId(data.machineId || ws.meta.targetMachineId || '');
      if (!requestedMachineId) {
        sendJson(ws, { type: 'error', message: 'stream-quality requires machineId.' });
        return;
      }

      const { resolvedId, senderWs } = resolveSender(room, requestedMachineId);
      if (!senderWs || senderWs.readyState !== WebSocket.OPEN) {
        sendJson(ws, { type: 'error', message: `Target machine "${requestedMachineId}" is offline.` });
        return;
      }

      sendJson(senderWs, {
        type: 'stream-quality',
        machineId: resolvedId,
        qualityLevel: data.qualityLevel,
        jpegQuality: data.jpegQuality,
        timestamp: Date.now()
      });
      log(`[QUALITY] relayed to sender machine=${resolvedId} qualityLevel=${data.qualityLevel} jpegQuality=${data.jpegQuality}`);
      return;
    }

    // ── chat-message ──
    if (data.type === 'chat-message') {
      if ((ws.meta.role !== 'receiver' && ws.meta.role !== 'sender') || !ws.meta.roomId) return;
      const room = rooms.get(ws.meta.roomId);
      if (!room) return;

      const requestedMachineId = sanitizeMachineId(data.machineId || ws.meta.targetMachineId || ws.meta.machineId || '');
      if (!requestedMachineId) {
        sendJson(ws, { type: 'error', message: 'chat-message requires machineId.' });
        return;
      }

      let resolvedMachineId = requestedMachineId;
      let senderWs = room.senders.get(resolvedMachineId);
      if (!senderWs) {
        const lower = requestedMachineId.toLowerCase();
        for (const [mid, sender] of room.senders.entries()) {
          if (mid.toLowerCase() === lower) { resolvedMachineId = mid; senderWs = sender; break; }
        }
      }

      const messageText = sanitizeString(data.message || '', 2000);
      if (!messageText) return;

      if (ws.meta.role === 'receiver' && (!senderWs || senderWs.readyState !== WebSocket.OPEN)) {
        sendJson(ws, { type: 'error', message: `Target machine "${requestedMachineId}" is offline.` });
        return;
      }
      if (ws.meta.role === 'sender') {
        if (!ws.meta.machineId) return;
        resolvedMachineId = ws.meta.machineId;
        senderWs = ws;
      }

      const payload = {
        type: 'chat-message',
        machineId: resolvedMachineId,
        roomId: ws.meta.roomId,
        senderName: sanitizeString(data.senderName || ws.clientId || 'Operator', 64),
        senderId: sanitizeString(data.senderId || ws.clientId || '', 64),
        message: messageText,
        timestamp: Date.now()
      };

      if (ws.meta.role === 'receiver' && senderWs && senderWs.readyState === WebSocket.OPEN) {
        sendJson(senderWs, payload);
      }
      for (const receiver of room.receivers) {
        if (receiver.readyState !== WebSocket.OPEN) continue;
        if (receiver.meta && receiver.meta.targetMachineId && receiver.meta.targetMachineId !== resolvedMachineId) continue;
        sendJson(receiver, payload);
      }
      log(`[CHAT] room=${ws.meta.roomId} machine=${resolvedMachineId} sender=${payload.senderName} len=${messageText.length}`);
      return;
    }

    // ── set-motd (receivers only — senders should not change MOTD) ──
    if (data.type === 'set-motd') {
      if (ws.meta.role !== 'receiver' || !ws.meta.roomId) {
        sendJson(ws, { type: 'error', message: 'Only receivers can set MOTD.' });
        return;
      }
      SERVER_MOTD = sanitizeString(data.message || '', 500);
      audit('set-motd', { client: ws.clientId, ip: ws.remoteIP, message: SERVER_MOTD });
      try {
        const motdPath = require('path').join(__dirname, 'motd.txt');
        require('fs').writeFileSync(motdPath, SERVER_MOTD, 'utf8');
      } catch {}
      for (const [, rm] of rooms.entries()) {
        for (const receiver of rm.receivers) {
          sendJson(receiver, { type: 'motd', message: SERVER_MOTD, timestamp: Date.now() });
        }
      }
      return;
    }

    // ── chat-close ──
    if (data.type === 'chat-close') {
      if (ws.meta.role !== 'receiver' || !ws.meta.roomId) return;
      const room = rooms.get(ws.meta.roomId);
      if (!room) return;

      const requestedMachineId = sanitizeMachineId(data.machineId || ws.meta.targetMachineId || '');
      if (!requestedMachineId) return;

      const { resolvedId, senderWs } = resolveSender(room, requestedMachineId);
      if (!senderWs || senderWs.readyState !== WebSocket.OPEN) return;

      sendJson(senderWs, {
        type: 'chat-close',
        machineId: resolvedId,
        senderName: sanitizeString(data.senderName || ws.clientId || 'Operator', 64),
        senderId: sanitizeString(data.senderId || ws.clientId || '', 64),
        timestamp: Date.now()
      });
      log(`[CHAT] close requested room=${ws.meta.roomId} machine=${resolvedId}`);
      return;
    }

    // ══════════════════════════════════════════
    // ── JOIN HANDLER ──
    // ══════════════════════════════════════════
    if (data.type !== 'join') {
      log(`[MESSAGE] Unknown type="${data.type}" from ${ws.clientId}`);
      sendJson(ws, { type: 'error', message: `Unknown message type: ${data.type}` });
      return;
    }

    // Clear join timeout since they're attempting to join
    if (ws._joinTimeout) {
      clearTimeout(ws._joinTimeout);
      ws._joinTimeout = null;
    }

    const role = data.role;
    const roomId = sanitizeRoomId(data.roomId || '');
    const secret = String(data.secret || '');
    const machineId = sanitizeMachineId(data.machineId || '');
    const targetMachineId = sanitizeMachineId(data.targetMachineId || '');

    log(`[JOIN] role=${role}, roomId=${roomId}, machineId=${machineId}, ip=${ip}`);

    // ── Validate roomId ──
    if (!roomId) {
      sendJson(ws, { type: 'error', message: 'roomId is required.' });
      return;
    }

    // ── Validate role ──
    if (role !== 'sender' && role !== 'receiver' && role !== 'discovery') {
      sendJson(ws, { type: 'error', message: 'role must be sender, receiver, or discovery.' });
      return;
    }

    // ── Authenticate (per-room secret or global fallback, constant-time) ──
    const expectedSecret = getRoomSecret(roomId);
    const secretBuf = Buffer.from(secret);
    const expectedBuf = Buffer.from(expectedSecret);
    const authOk = secretBuf.length === expectedBuf.length && crypto.timingSafeEqual(secretBuf, expectedBuf);

    if (!authOk) {
      recordFailedAuth(ip);
      log(`[SECURITY] Auth failed from ip=${ip} clientId=${ws.clientId} role=${role} room=${roomId}`);
      audit('auth-failed', { ip, clientId: ws.clientId, role, roomId });
      sendJson(ws, { type: 'error', message: 'Authentication failed.' });
      return;
    }

    // Auth succeeded — clear any failed attempt tracking for this IP
    recordSuccessAuth(ip);

    // ── Room capacity limits ──
    if (!rooms.has(roomId) && rooms.size >= MAX_ROOMS) {
      sendJson(ws, { type: 'error', message: 'Server room limit reached.' });
      return;
    }

    const room = getRoom(roomId);

    if (role === 'sender') {
      if (!machineId) {
        sendJson(ws, { type: 'error', message: 'machineId is required for senders.' });
        return;
      }
      if (room.senders.has(machineId)) {
        sendJson(ws, { type: 'error', message: `Machine ID "${machineId}" is already in use in this room.` });
        return;
      }
      if (room.senders.size >= MAX_SENDERS_PER_ROOM) {
        sendJson(ws, { type: 'error', message: 'Room sender limit reached.' });
        return;
      }

      room.senders.set(machineId, ws);
      ws.meta = { role, roomId, machineId };
      log(`[SENDER JOINED] "${machineId}" in room "${roomId}" ip=${ip}`);
      audit('sender-joined', { ip, clientId: ws.clientId, machineId, roomId });
      logRoomState(roomId);
      logClientList('after-join');
      sendJson(ws, { type: 'joined', role, roomId, machineId });

      for (const receiver of room.receivers) {
        sendJson(receiver, { type: 'sender-online', machineId });
      }
      broadcastRoomState(room);
      return;
    }

    if (role === 'discovery') {
      if (room.receivers.size >= MAX_RECEIVERS_PER_ROOM) {
        sendJson(ws, { type: 'error', message: 'Room receiver limit reached.' });
        return;
      }
      room.receivers.add(ws);
      ws.meta = { role, roomId, targetMachineId: null };
      log(`[DISCOVERY JOINED] room "${roomId}" ip=${ip}`);
      logRoomState(roomId);
      logClientList('after-join');
      sendJson(ws, { type: 'joined', role, roomId });

      const activeMachines = Array.from(room.senders.keys());
      if (activeMachines.length > 0) {
        sendJson(ws, { type: 'room-state', activeMachines });
      } else {
        sendJson(ws, { type: 'waiting-for-sender' });
      }
      return;
    }

    // ── Receiver joining ──
    if (room.receivers.size >= MAX_RECEIVERS_PER_ROOM) {
      sendJson(ws, { type: 'error', message: 'Room receiver limit reached.' });
      return;
    }

    room.receivers.add(ws);
    ws.meta = { role, roomId, targetMachineId: targetMachineId || null };
    log(`[RECEIVER JOINED] room "${roomId}", targetMachineId=${targetMachineId || '(any)'} ip=${ip}`);
    audit('receiver-joined', { ip, clientId: ws.clientId, roomId });
    logRoomState(roomId);
    logClientList('after-join');
    sendJson(ws, { type: 'joined', role, roomId });

    if (SERVER_MOTD) {
      sendJson(ws, { type: 'motd', message: SERVER_MOTD, timestamp: Date.now() });
    }

    const activeMachines = Array.from(room.senders.keys());
    if (activeMachines.length > 0) {
      sendJson(ws, { type: 'active-machines', machines: activeMachines });
      sendJson(ws, { type: 'sender-online', machineId: activeMachines[0] });
    } else {
      sendJson(ws, { type: 'waiting-for-sender' });
    }
  });

  ws.on('close', () => {
    log(`[DISCONNECT] Client id=${ws.clientId} ip=${ws.remoteIP} role=${ws.meta?.role} room=${ws.meta?.roomId} machine=${ws.meta?.machineId}`);
    cleanupSocket(ws);
    logClientList('after-disconnect');
  });

  ws.on('error', (err) => {
    log(`[ERROR] ${err.message} (client=${ws.clientId} ip=${ws.remoteIP})`);
    cleanupSocket(ws);
    logClientList('after-error');
  });
});

// ── Graceful shutdown ──
function gracefulShutdown(signal) {
  log(`[SHUTDOWN] Received ${signal}, closing all connections...`);
  for (const ws of clients.values()) {
    try {
      sendJson(ws, { type: 'error', message: 'Server shutting down.' });
      ws.close(1001, 'Server shutting down');
    } catch {}
  }
  server.close(() => {
    try { db.close(); log('[SHUTDOWN] Database closed.'); } catch {}
    log(`[SHUTDOWN] Server closed.`);
    process.exit(0);
  });
  // Force exit after 5 seconds if graceful close hangs
  setTimeout(() => { try { db.close(); } catch {} process.exit(0); }, 5000);
}
process.on('SIGINT', () => gracefulShutdown('SIGINT'));
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));

// ── Periodic room scan ──
setInterval(() => {
  for (const [roomId, room] of rooms.entries()) {
    pruneClosedSockets(room);
    if (room.senders.size === 0 && room.receivers.size === 0) {
      log(`[SCAN] Deleting empty room "${roomId}"`);
      rooms.delete(roomId);
      continue;
    }
    broadcastRoomState(room);
  }
  if (rooms.size > 0) {
    log(`[SCAN] Active rooms: ${rooms.size}`);
    for (const roomId of rooms.keys()) {
      logRoomState(roomId);
    }
  }
}, ROOM_SCAN_INTERVAL_MS);

if (CLIENT_LIST_LOG_INTERVAL_MS > 0) {
  setInterval(() => {
    logClientList('periodic-snapshot');
  }, CLIENT_LIST_LOG_INTERVAL_MS);
}

// ── Startup banner ──
console.log(`\n==== RELAY SERVER STARTING ====`);
log(`Relay server listening on ws://0.0.0.0:${PORT}`);
log(`Admin panel: http://0.0.0.0:${PORT}/admin`);
log(`Database: ${DB_PATH} (SQLite WAL, ${dbCountRooms()} rooms stored)`);
log(`Protocol: ${CONTROL_PROTOCOL_VERSION}`);
log(`Security: maxPayload=${MAX_MESSAGE_SIZE_BYTES / 1024 / 1024}MB, rateLimit=${RATE_LIMIT_MAX_MESSAGES}msg/s, authBan=${AUTH_BAN_DURATION_MS / 1000}s after ${MAX_FAILED_AUTHS_PER_IP} failures`);
log(`Limits: maxRooms=${MAX_ROOMS}, maxSenders/room=${MAX_SENDERS_PER_ROOM}, maxReceivers/room=${MAX_RECEIVERS_PER_ROOM}`);
log(`Timers: roomScan=${ROOM_SCAN_INTERVAL_MS}ms, joinTimeout=${JOIN_TIMEOUT_MS}ms, pendingTTL=${PENDING_REQUEST_TTL_MS}ms`);
log(`Audit log: server-audit.log + audit_log table`);
console.log(`============================\n`);
