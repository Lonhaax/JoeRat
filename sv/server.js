const WebSocket = require('ws');
const dotenv = require('dotenv');

dotenv.config();

const PORT = Number(process.env.PORT || 3000);
const ROOM_SECRET = process.env.ROOM_SECRET || 'boi123';
const ROOM_SCAN_INTERVAL_MS = Number(process.env.ROOM_SCAN_INTERVAL_MS || 2000);
const CLIENT_ACTIVE_WINDOW_MS = Number(process.env.CLIENT_ACTIVE_WINDOW_MS || 15000);
const CLIENT_LIST_LOG_INTERVAL_MS = Number(process.env.CLIENT_LIST_LOG_INTERVAL_MS || 5000);
const CONTROL_PROTOCOL_VERSION = 'control-protocol-2026-03-08-v1';

// ── MOTD (Message of the Day) ──
// Set via MOTD env var, or edit motd.txt in the server directory, or change at runtime via admin message.
let SERVER_MOTD = process.env.MOTD || '';
try {
  const motdPath = require('path').join(__dirname, 'motd.txt');
  if (require('fs').existsSync(motdPath)) {
    SERVER_MOTD = require('fs').readFileSync(motdPath, 'utf8').trim();
  }
} catch {}

const server = new WebSocket.Server({ port: PORT });

// rooms[roomId] = { senders: Map<machineId, ws>, receivers: Set<ws> }
const rooms = new Map();
const clients = new Map();
let nextClientId = 1;

function log(msg) {
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] ${msg}`);
  // Write to server-debug.log for persistent troubleshooting
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

function registerClient(ws) {
  const clientId = `c${nextClientId}`;
  nextClientId += 1;
  const now = Date.now();

  ws.clientId = clientId;
  ws.connectedAt = now;
  ws.lastActivityAt = now;

  clients.set(clientId, ws);
  return clientId;
}

function touchClient(ws) {
  if (!ws) {
    return;
  }
  ws.lastActivityAt = Date.now();
}

function getClientStatus(ws) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return 'disconnected';
  }

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

    log(
      `[CLIENT] id=${ws.clientId} status=${status} role=${role} room=${roomId} machine=${machineId} target=${targetMachineId} idleMs=${idleMs}`
    );
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
    if (receiver.readyState !== WebSocket.OPEN) {
      continue;
    }

    if (activeMachines.length > 0) {
      sendJson(receiver, { type: 'active-machines', machines: activeMachines });
      sendJson(receiver, { type: 'sender-online', machineId: activeMachines[0] });
    } else {
      sendJson(receiver, { type: 'waiting-for-sender' });
    }
  }
}

function pruneClosedSockets(room) {
  // Remove disconnected receivers.
  for (const receiver of Array.from(room.receivers)) {
    if (receiver.readyState !== WebSocket.OPEN) {
      room.receivers.delete(receiver);
    }
  }

  // Remove disconnected senders and notify receivers.
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
  if (ws?.clientId) {
    clients.delete(ws.clientId);
  }

  for (const [roomId, room] of rooms.entries()) {
    // Check if this was a sender
    for (const [machineId, senderWs] of room.senders.entries()) {
      if (senderWs === ws) {
        room.senders.delete(machineId);
        // Notify receivers that this machine went offline
        for (const receiver of room.receivers) {
          sendJson(receiver, { type: 'sender-offline', machineId });
        }
        break;
      }
    }

    // Check if this was a receiver
    if (room.receivers.has(ws)) {
      room.receivers.delete(ws);
    }

    // Clean up empty rooms
    if (room.senders.size === 0 && room.receivers.size === 0) {
      rooms.delete(roomId);
    }
  }
}

server.on('connection', (ws) => {
  const clientId = registerClient(ws);
  log(`[CONNECTION] New client connected (id=${clientId})`);
  ws.meta = { role: null, roomId: null, machineId: null, targetMachineId: null };
  logClientList('after-connect');

  ws.on('message', (message, isBinary) => {
    touchClient(ws);

    if (isBinary) {
      if (ws.meta.role !== 'sender' || !ws.meta.roomId || !ws.meta.machineId) {
        log(`[BINARY] Ignored binary from non-sender or incomplete meta`);
        return;
      }

      const room = rooms.get(ws.meta.roomId);
      if (!room || room.senders.get(ws.meta.machineId) !== ws) {
        log(`[BINARY] Sender "${ws.meta.machineId}" not in room "${ws.meta.roomId}"`);
        return;
      }

      for (const receiver of room.receivers) {
        if (receiver.readyState === WebSocket.OPEN) {
          // If receiver subscribed to a specific machine, only forward that stream.
          if (receiver.meta && receiver.meta.targetMachineId && receiver.meta.targetMachineId !== ws.meta.machineId) {
            continue;
          }

          // Send raw JPEG bytes so ffplay/viewers can decode immediately.
          receiver.send(message, { binary: true });
        }
      }
      return;
    }

    let data;
    try {
      data = JSON.parse(String(message));
    } catch {
      log(`[MESSAGE] Invalid JSON received`);
      sendJson(ws, { type: 'error', message: 'Invalid JSON message.' });
      return;
    }

    // Relay file-list responses from sender to receivers
    if (data.type === 'file-list') {
      if (ws.meta.role !== 'sender' || !ws.meta.roomId || !ws.meta.machineId) {
        return;
      }
      const room = rooms.get(ws.meta.roomId);
      if (!room || room.senders.get(ws.meta.machineId) !== ws) {
        return;
      }
      // Relay file-list to all receivers in the room
      for (const receiver of room.receivers) {
        if (receiver.readyState !== WebSocket.OPEN) {
          continue;
        }
        // Optionally filter by targetMachineId
        if (receiver.meta && receiver.meta.targetMachineId && receiver.meta.targetMachineId !== ws.meta.machineId) {
          continue;
        }
        sendJson(receiver, data);
      }
      return;
    }
    // Allow sender telemetry updates after join.
    if (data.type === 'system-info' || data.type === 'telemetry') {
      if (ws.meta.role !== 'sender' || !ws.meta.roomId || !ws.meta.machineId) {
        return;
      }

      const room = rooms.get(ws.meta.roomId);
      if (!room || room.senders.get(ws.meta.machineId) !== ws) {
        return;
      }

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
        if (receiver.readyState !== WebSocket.OPEN) {
          continue;
        }

        if (receiver.meta && receiver.meta.targetMachineId && receiver.meta.targetMachineId !== ws.meta.machineId) {
          continue;
        }

        sendJson(receiver, payload);
      }
      return;
    }

    if (data.type === 'remote-control') {
      if (ws.meta.role !== 'receiver' || !ws.meta.roomId) {
        return;
      }

      log(`[CONTROL] received from receiver id=${ws.clientId} room=${ws.meta.roomId} machine=${data.machineId || ws.meta.targetMachineId || '-'} action=${data.action || '-'}`);

      const room = rooms.get(ws.meta.roomId);
      if (!room) {
        return;
      }

      const requestedMachineId = String(data.machineId || ws.meta.targetMachineId || '').trim();
      if (!requestedMachineId) {
        sendJson(ws, { type: 'error', message: 'remote-control requires machineId.' });
        return;
      }

      let resolvedMachineId = requestedMachineId;
      let senderWs = room.senders.get(resolvedMachineId);

      if (!senderWs) {
        const normalizedRequested = requestedMachineId.toLowerCase();
        for (const [machineId, sender] of room.senders.entries()) {
          if (machineId.toLowerCase() === normalizedRequested) {
            resolvedMachineId = machineId;
            senderWs = sender;
            break;
          }
        }
      }

      // If IDs don't line up but exactly one sender is active, route to it.
      if (!senderWs && room.senders.size === 1) {
        const [onlyMachineId, onlySender] = room.senders.entries().next().value;
        resolvedMachineId = onlyMachineId;
        senderWs = onlySender;
        log(`[CONTROL] fallback target selected machine=${resolvedMachineId} for requested=${requestedMachineId}`);
      }

      if (!senderWs || senderWs.readyState !== WebSocket.OPEN) {
        sendJson(ws, { type: 'error', message: `Target machine "${requestedMachineId}" is offline.` });
        return;
      }

      sendJson(senderWs, {
        type: 'remote-control',
        machineId: resolvedMachineId,
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
        // Relay file-manager fields
        path: data.path,
        // Relay file-transfer fields
        filename: data.filename,
        data: data.data,
        destPath: data.destPath,
        // Relay clipboard fields
        text: data.text,
        timestamp: Date.now()
      });

      log(`[CONTROL] relayed to sender machine=${resolvedMachineId}`);
      return;
    }

    if (data.type === 'stream-quality') {
      if (ws.meta.role !== 'receiver' || !ws.meta.roomId) {
        return;
      }

      const room = rooms.get(ws.meta.roomId);
      if (!room) {
        return;
      }

      const requestedMachineId = String(data.machineId || ws.meta.targetMachineId || '').trim();
      if (!requestedMachineId) {
        sendJson(ws, { type: 'error', message: 'stream-quality requires machineId.' });
        return;
      }

      let resolvedMachineId = requestedMachineId;
      let senderWs = room.senders.get(resolvedMachineId);

      if (!senderWs) {
        const normalizedRequested = requestedMachineId.toLowerCase();
        for (const [machineId, sender] of room.senders.entries()) {
          if (machineId.toLowerCase() === normalizedRequested) {
            resolvedMachineId = machineId;
            senderWs = sender;
            break;
          }
        }
      }

      if (!senderWs && room.senders.size === 1) {
        const [onlyMachineId, onlySender] = room.senders.entries().next().value;
        resolvedMachineId = onlyMachineId;
        senderWs = onlySender;
      }

      if (!senderWs || senderWs.readyState !== WebSocket.OPEN) {
        sendJson(ws, { type: 'error', message: `Target machine "${requestedMachineId}" is offline.` });
        return;
      }

      sendJson(senderWs, {
        type: 'stream-quality',
        machineId: resolvedMachineId,
        qualityLevel: data.qualityLevel,
        jpegQuality: data.jpegQuality,
        timestamp: Date.now()
      });

      log(`[QUALITY] relayed to sender machine=${resolvedMachineId} qualityLevel=${data.qualityLevel} jpegQuality=${data.jpegQuality}`);
      return;
    }

    if (data.type === 'chat-message') {
      if ((ws.meta.role !== 'receiver' && ws.meta.role !== 'sender') || !ws.meta.roomId) {
        return;
      }

      const room = rooms.get(ws.meta.roomId);
      if (!room) {
        return;
      }

      const requestedMachineId = String(data.machineId || ws.meta.targetMachineId || ws.meta.machineId || '').trim();
      if (!requestedMachineId) {
        sendJson(ws, { type: 'error', message: 'chat-message requires machineId.' });
        return;
      }

      let resolvedMachineId = requestedMachineId;
      let senderWs = room.senders.get(resolvedMachineId);

      if (!senderWs) {
        const normalizedRequested = requestedMachineId.toLowerCase();
        for (const [machineId, sender] of room.senders.entries()) {
          if (machineId.toLowerCase() === normalizedRequested) {
            resolvedMachineId = machineId;
            senderWs = sender;
            break;
          }
        }
      }

      const messageText = String(data.message || '').trim();
      if (!messageText) {
        return;
      }

      if (ws.meta.role === 'receiver' && (!senderWs || senderWs.readyState !== WebSocket.OPEN)) {
        sendJson(ws, { type: 'error', message: `Target machine "${requestedMachineId}" is offline.` });
        return;
      }

      if (ws.meta.role === 'sender') {
        if (!ws.meta.machineId) {
          return;
        }

        resolvedMachineId = ws.meta.machineId;
        senderWs = ws;
      }

      const payload = {
        type: 'chat-message',
        machineId: resolvedMachineId,
        roomId: ws.meta.roomId,
        senderName: String(data.senderName || ws.clientId || 'Operator'),
        senderId: String(data.senderId || ws.clientId || ''),
        message: messageText,
        timestamp: Date.now()
      };

      // Send to the active sender when the viewer sends a message.
      if (ws.meta.role === 'receiver' && senderWs && senderWs.readyState === WebSocket.OPEN) {
        sendJson(senderWs, payload);
      }

      for (const receiver of room.receivers) {
        if (receiver.readyState !== WebSocket.OPEN) {
          continue;
        }

        // Route chat to receiver sockets attached to this machine.
        if (receiver.meta && receiver.meta.targetMachineId && receiver.meta.targetMachineId !== resolvedMachineId) {
          continue;
        }

        sendJson(receiver, payload);
      }

      log(`[CHAT] room=${ws.meta.roomId} machine=${resolvedMachineId} sender=${payload.senderName} len=${messageText.length}`);
      return;
    }

    // ── Handle set-motd from any authenticated client ──
    if (data.type === 'set-motd') {
      if (!ws.meta.role || !ws.meta.roomId) {
        sendJson(ws, { type: 'error', message: 'Must join a room before setting MOTD.' });
        return;
      }
      SERVER_MOTD = String(data.message || '').trim();
      log(`[MOTD] Updated by ${ws.clientId}: "${SERVER_MOTD}"`);
      // Save to motd.txt for persistence
      try {
        const motdPath = require('path').join(__dirname, 'motd.txt');
        require('fs').writeFileSync(motdPath, SERVER_MOTD, 'utf8');
      } catch {}
      // Broadcast to all receivers in all rooms
      for (const [, rm] of rooms.entries()) {
        for (const receiver of rm.receivers) {
          sendJson(receiver, { type: 'motd', message: SERVER_MOTD, timestamp: Date.now() });
        }
      }
      return;
    }

    if (data.type === 'chat-close') {
      if (ws.meta.role !== 'receiver' || !ws.meta.roomId) {
        return;
      }

      const room = rooms.get(ws.meta.roomId);
      if (!room) {
        return;
      }

      const requestedMachineId = String(data.machineId || ws.meta.targetMachineId || '').trim();
      if (!requestedMachineId) {
        sendJson(ws, { type: 'error', message: 'chat-close requires machineId.' });
        return;
      }

      let resolvedMachineId = requestedMachineId;
      let senderWs = room.senders.get(resolvedMachineId);

      if (!senderWs) {
        const normalizedRequested = requestedMachineId.toLowerCase();
        for (const [machineId, sender] of room.senders.entries()) {
          if (machineId.toLowerCase() === normalizedRequested) {
            resolvedMachineId = machineId;
            senderWs = sender;
            break;
          }
        }
      }

      if (!senderWs || senderWs.readyState !== WebSocket.OPEN) {
        return;
      }

      sendJson(senderWs, {
        type: 'chat-close',
        machineId: resolvedMachineId,
        senderName: String(data.senderName || ws.clientId || 'Operator'),
        senderId: String(data.senderId || ws.clientId || ''),
        timestamp: Date.now()
      });

      log(`[CHAT] close requested room=${ws.meta.roomId} machine=${resolvedMachineId}`);
      return;
    }

    if (data.type !== 'join') {
      sendJson(ws, { type: 'error', message: 'First message must be type=join.' });
      return;
    }

    const role = data.role;
    const roomId = String(data.roomId || '').trim();
    const secret = String(data.secret || '');
    const machineId = String(data.machineId || '').trim();
    const targetMachineId = String(data.targetMachineId || '').trim();

    log(`[JOIN] role=${role}, roomId=${roomId}, machineId=${machineId}, targetMachineId=${targetMachineId}`);
    log(`[JOIN] payload: ${JSON.stringify(data)}`);

    if (!roomId) {
      log(`[JOIN] ERROR: No roomId provided`);
      sendJson(ws, { type: 'error', message: 'roomId is required.' });
      return;
    }

    if (role !== 'sender' && role !== 'receiver' && role !== 'discovery') {
      log(`[JOIN] ERROR: Invalid role "${role}"`);
      sendJson(ws, { type: 'error', message: 'role must be sender, receiver, or discovery.' });
      return;
    }

    if (secret !== ROOM_SECRET) {
      log(`[JOIN] ERROR: Invalid secret (got "${secret}", expected "${ROOM_SECRET}")`);
      log(`[JOIN] ERROR: Sender authentication failed. Full payload: ${JSON.stringify(data)}`);
      sendJson(ws, { type: 'error', message: 'Authentication failed.' });
      return;
    }

    const room = getRoom(roomId);

    if (role === 'sender') {
      if (!machineId) {
        log(`[JOIN] ERROR: Sender missing machineId`);
        log(`[JOIN] ERROR: Sender join failed. Full payload: ${JSON.stringify(data)}`);
        sendJson(ws, { type: 'error', message: 'machineId is required for senders.' });
        return;
      }

      if (room.senders.has(machineId)) {
        log(`[JOIN] ERROR: machineId "${machineId}" already in use`);
        log(`[JOIN] ERROR: Sender join failed due to duplicate machineId. Full payload: ${JSON.stringify(data)}`);
        sendJson(ws, { type: 'error', message: `Machine ID "${machineId}" is already in use in this room.` });
        return;
      }

      room.senders.set(machineId, ws);
      ws.meta = { role, roomId, machineId };
      log(`[SENDER JOINED] "${machineId}" in room "${roomId}"`);
      log(`[SENDER JOINED] payload: ${JSON.stringify(data)}`);
      logRoomState(roomId);
      logClientList('after-join');
      sendJson(ws, { type: 'joined', role, roomId, machineId });

      // Notify receivers that this machine is online
      for (const receiver of room.receivers) {
        sendJson(receiver, { type: 'sender-online', machineId });
      }
      broadcastRoomState(room);
      return;
    }

    if (role === 'discovery') {
      room.receivers.add(ws);
      ws.meta = { role, roomId, targetMachineId: null };
      log(`[DISCOVERY JOINED] room "${roomId}"`);
      logRoomState(roomId);
      logClientList('after-join');
      sendJson(ws, { type: 'joined', role, roomId });

      // Send list of active machines
      const activeMachines = Array.from(room.senders.keys());
      if (activeMachines.length > 0) {
        sendJson(ws, { type: 'room-state', activeMachines });
      } else {
        sendJson(ws, { type: 'waiting-for-sender' });
      }
      return;
    }

    // Receiver joining
    room.receivers.add(ws);
    ws.meta = { role, roomId, targetMachineId: targetMachineId || null };
    log(`[RECEIVER JOINED] room "${roomId}", targetMachineId=${targetMachineId || '(any)'}`);
    logRoomState(roomId);
    logClientList('after-join');
    sendJson(ws, { type: 'joined', role, roomId, machineId: ws.clientId });

    // Send MOTD if set
    if (SERVER_MOTD) {
      sendJson(ws, { type: 'motd', message: SERVER_MOTD, timestamp: Date.now() });
    }

    // Send list of active machines in this room
    const activeMachines = Array.from(room.senders.keys());
    if (activeMachines.length > 0) {
      sendJson(ws, { type: 'active-machines', machines: activeMachines });
      sendJson(ws, { type: 'sender-online', machineId: activeMachines[0] });
    } else {
      sendJson(ws, { type: 'waiting-for-sender' });
    }
  });

  ws.on('close', () => {
    log(`[DISCONNECT] Client disconnected, role=${ws.meta?.role}, roomId=${ws.meta?.roomId}, machineId=${ws.meta?.machineId}`);
    cleanupSocket(ws);
    logClientList('after-disconnect');
  });
  ws.on('error', (err) => {
    log(`[ERROR] ${err.message}`);
    cleanupSocket(ws);
    logClientList('after-error');
  });
});

setInterval(() => {
  for (const [roomId, room] of rooms.entries()) {
    pruneClosedSockets(room);

    if (room.senders.size === 0 && room.receivers.size === 0) {
      log(`[SCAN] Deleting empty room "${roomId}"`);
      rooms.delete(roomId);
      continue;
    }

    // Periodically re-announce room status so receivers auto-discover new senders.
    broadcastRoomState(room);
  }
  
  // Log overall state
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

console.log(`\n==== RELAY SERVER STARTING ====`);
log(`Relay server listening on ws://0.0.0.0:${PORT}`);
log(`Multiple senders per room supported with unique machine IDs`);
log(`Room scanning enabled every ${ROOM_SCAN_INTERVAL_MS}ms`);
log(`Client active window: ${CLIENT_ACTIVE_WINDOW_MS}ms`);
log(`Client list logging interval: ${CLIENT_LIST_LOG_INTERVAL_MS}ms`);
log(`Room secret: ${ROOM_SECRET}`);
log(`Control protocol: ${CONTROL_PROTOCOL_VERSION}`);
console.log(`============================\n`);
