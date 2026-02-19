"""Web server for the action system: queue display, permission management UI."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from .core import ActionSystem
from .models import ActionStatus, Expiration, PermissionGrant

# Will be set by serve()
_system: ActionSystem | None = None


def _json_response(handler: "_Handler", data: Any, status: int = 200) -> None:
    body = json.dumps(data, default=str).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler: "_Handler") -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length))


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass  # quiet

    def do_GET(self) -> None:
        assert _system is not None
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/":
            self._serve_html()
        elif path == "/api/queue":
            items = _system.get_pending_actions()
            _json_response(self, [self._serialize_action(a) for a in items])
        elif path == "/api/queue/all":
            # Return all items from the store
            all_items = []
            for status in ActionStatus:
                all_items.extend(_system._store.get_actions_by_status(status))
            all_items.sort(key=lambda a: a.created_at, reverse=True)
            _json_response(self, [self._serialize_action(a) for a in all_items[:50]])
        elif path == "/api/grants":
            grants = _system.get_all_grants()
            _json_response(self, [self._serialize_grant(g) for g in grants])
        elif path.startswith("/api/permissions/"):
            item_id = path.split("/")[-1]
            try:
                action = _system.get_action_status(item_id)
            except Exception:
                _json_response(self, {"error": "not found"}, 404)
                return
            handler = _system._handlers.get(action.handler_id)
            granted = _system.check_permission(
                action.handler_id, action.permission_name, action.permission_scope
            )
            perm_def = None
            if handler:
                for p in handler.permissions:
                    if p.name == action.permission_name:
                        perm_def = p
                        break
            _json_response(self, {
                "item_id": item_id,
                "handler_id": action.handler_id,
                "permissions": [{
                    "name": action.permission_name,
                    "scope": action.permission_scope,
                    "granted": granted,
                    "description": perm_def.description if perm_def else "",
                    "parameters": perm_def.parameters if perm_def else {},
                }] if action.permission_name else [],
            })
        elif path == "/api/handlers":
            handlers = _system.list_handlers()
            _json_response(self, [
                {
                    "handler_id": h.handler_id,
                    "name": h.name,
                    "permissions": [
                        {"name": p.name, "description": p.description, "parameters": p.parameters}
                        for p in h.permissions
                    ],
                }
                for h in handlers
            ])
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        assert _system is not None
        path = urlparse(self.path).path

        if path == "/api/grant":
            body = _read_body(self)
            handler_id = body["handler_id"]
            permission_name = body["permission_name"]
            scope = body.get("scope", {})
            expiration = Expiration(body.get("expiration", "indefinite"))
            grant = _system.grant_permission(
                handler_id, permission_name, scope, expiration
            )
            # Auto-approve any pending actions that now have permission
            for action in _system.get_pending_actions():
                if (action.handler_id == handler_id
                        and action.permission_name == permission_name
                        and _system.check_permission(handler_id, permission_name, action.permission_scope)):
                    _system.approve_action(action.id)
            _json_response(self, self._serialize_grant(grant))

        elif path.startswith("/api/approve/"):
            item_id = path.split("/")[-1]
            try:
                result = _system.approve_action(item_id)
                _json_response(self, {"status": result.status.value, "result": result.result})
            except Exception as e:
                _json_response(self, {"error": str(e)}, 400)

        elif path.startswith("/api/revoke/"):
            grant_id = path.split("/")[-1]
            _system.revoke_permission(grant_id)
            _json_response(self, {"status": "ok"})

        else:
            self.send_error(404)

    def _serve_html(self) -> None:
        body = _HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _serialize_action(a: Any) -> dict[str, Any]:
        return {
            "id": a.id,
            "handler_id": a.handler_id,
            "action_name": a.action_name,
            "params": a.params,
            "permission_name": a.permission_name,
            "permission_scope": a.permission_scope,
            "status": a.status.value,
            "result": a.result,
            "error": a.error,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        }

    @staticmethod
    def _serialize_grant(g: PermissionGrant) -> dict[str, Any]:
        return {
            "id": g.id,
            "handler_id": g.handler_id,
            "permission_name": g.permission_name,
            "scope": g.scope,
            "expiration": g.expiration.value,
            "expires_at": g.expires_at.isoformat() if g.expires_at else None,
            "granted_at": g.granted_at.isoformat(),
            "granted_by": g.granted_by,
        }


def serve(system: ActionSystem, host: str = "0.0.0.0", port: int = 8991) -> None:
    """Start the action system web UI."""
    global _system
    _system = system
    server = HTTPServer((host, port), _Handler)
    print(f"Action System UI: http://{host}:{port}")
    server.serve_forever()


_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Action System</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; max-width: 700px; margin: 2rem auto; padding: 0 1rem; background: #0d1117; color: #c9d1d9; }
  h1 { margin-bottom: 1.5rem; color: #58a6ff; }
  h2 { margin: 1.5rem 0 .75rem; color: #8b949e; font-size: 1rem; }
  .item { border: 1px solid #30363d; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
  .item-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: .5rem; }
  .item-header h3 { color: #f0f6fc; font-size: 1rem; }
  .meta { font-size: .85rem; color: #8b949e; margin-bottom: .5rem; }
  pre { background: #161b22; padding: .5rem; border-radius: 4px; font-size: .85rem; overflow-x: auto; margin: .5rem 0; }
  .status { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: .75rem; font-weight: 600; }
  .status.pending { background: #d29922; color: #000; }
  .status.approved { background: #238636; color: #fff; }
  .status.completed { background: #58a6ff; color: #000; }
  .status.failed { background: #da3633; color: #fff; }
  .status.running { background: #a371f7; color: #fff; }
  .gear-btn { background: none; border: none; cursor: pointer; font-size: 1.2rem; padding: 2px 6px; opacity: 0.6; }
  .gear-btn:hover { opacity: 1; }
  .perm-panel { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: .75rem; margin-top: .5rem; display: none; }
  .perm-panel.open { display: block; }
  .perm-row { display: flex; justify-content: space-between; align-items: center; padding: .5rem 0; }
  .perm-name { font-weight: 600; color: #f0f6fc; }
  .perm-desc { font-size: .8rem; color: #8b949e; }
  .perm-status.granted { color: #3fb950; font-size: .85rem; }
  .perm-status.denied { color: #f85149; font-size: .85rem; }
  .grant-controls { display: flex; gap: .4rem; align-items: center; }
  .grant-controls select { background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 4px; padding: 2px 6px; font-size: .8rem; }
  .grant-btn { background: #238636; color: #fff; border: none; border-radius: 4px; padding: 4px 12px; cursor: pointer; font-size: .8rem; font-weight: 600; }
  .grant-btn:hover { background: #2ea043; }
  .empty { color: #8b949e; text-align: center; padding: 2rem; }
  .grants-section { margin-top: 2rem; }
  .grant-item { display: flex; justify-content: space-between; align-items: center; padding: .5rem .75rem; border: 1px solid #30363d; border-radius: 6px; margin-bottom: .4rem; font-size: .85rem; }
  .revoke-btn { background: #da3633; color: #fff; border: none; border-radius: 4px; padding: 2px 8px; cursor: pointer; font-size: .75rem; }
  .revoke-btn:hover { background: #f85149; }
  .tabs { display: flex; gap: .5rem; margin-bottom: 1rem; }
  .tab { padding: .4rem 1rem; border: 1px solid #30363d; border-radius: 6px; background: none; color: #8b949e; cursor: pointer; font-size: .85rem; }
  .tab.active { background: #30363d; color: #f0f6fc; }
</style>
</head>
<body>
<h1>⚡ Action System</h1>
<div class="tabs">
  <button class="tab active" onclick="showTab('pending')">Pending</button>
  <button class="tab" onclick="showTab('all')">All Actions</button>
  <button class="tab" onclick="showTab('grants')">Grants</button>
</div>
<div id="content"></div>

<script>
let currentTab = 'pending';

function esc(s) { const d = document.createElement('div'); d.textContent = String(s); return d.innerHTML; }

function showTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.textContent.toLowerCase().includes(tab === 'all' ? 'all' : tab)));
  loadContent();
}

async function loadContent() {
  if (currentTab === 'pending') await loadPending();
  else if (currentTab === 'all') await loadAll();
  else if (currentTab === 'grants') await loadGrants();
}

async function loadPending() {
  const res = await fetch('/api/queue');
  const items = await res.json();
  const div = document.getElementById('content');
  if (items.length === 0) {
    div.innerHTML = '<div class="empty">No pending actions</div>';
    return;
  }
  div.innerHTML = items.map(renderItem).join('');
}

async function loadAll() {
  const res = await fetch('/api/queue/all');
  const items = await res.json();
  const div = document.getElementById('content');
  if (items.length === 0) {
    div.innerHTML = '<div class="empty">No actions</div>';
    return;
  }
  div.innerHTML = items.map(renderItem).join('');
}

function renderItem(it) {
  return `
    <div class="item">
      <div class="item-header">
        <h3>${esc(it.handler_id)} → ${esc(it.action_name)}</h3>
        <button class="gear-btn" onclick="togglePerms('${it.id}')" title="Permissions">⚙️</button>
      </div>
      <span class="status ${it.status}">${it.status}</span>
      <div class="meta">${it.id} · ${new Date(it.created_at).toLocaleString()}</div>
      <pre>${esc(JSON.stringify(it.params, null, 2))}</pre>
      ${it.result ? '<pre>Result: ' + esc(JSON.stringify(it.result, null, 2)) + '</pre>' : ''}
      ${it.error ? '<pre style="color:#f85149">Error: ' + esc(it.error) + '</pre>' : ''}
      <div class="perm-panel" id="perms-${it.id}"></div>
    </div>`;
}

async function togglePerms(itemId) {
  const panel = document.getElementById('perms-' + itemId);
  if (panel.classList.contains('open')) { panel.classList.remove('open'); return; }
  panel.classList.add('open');
  panel.innerHTML = 'Loading...';
  try {
    const res = await fetch('/api/permissions/' + itemId);
    const data = await res.json();
    if (data.permissions.length === 0) {
      panel.innerHTML = '<div style="color:#8b949e;font-size:.85rem">No permissions defined</div>';
      return;
    }
    panel.innerHTML = data.permissions.map(p => `
      <div class="perm-row">
        <div>
          <div class="perm-name">${esc(p.name)}</div>
          <div class="perm-desc">${esc(p.description)}${Object.keys(p.scope).length ? ' · scope: ' + esc(JSON.stringify(p.scope)) : ''}</div>
        </div>
        <div>
          ${p.granted
            ? '<span class="perm-status granted">✓ Granted</span>'
            : '<div class="grant-controls">' +
              '<select id="exp-' + itemId + '-' + p.name + '">' +
              '<option value="1h">1 hour</option>' +
              '<option value="today">Today</option>' +
              '<option value="indefinite" selected>Indefinitely</option>' +
              '</select>' +
              '<button class="grant-btn" onclick="grantPerm(\\'' + esc(data.handler_id) + '\\', \\'' + esc(p.name) + '\\', ' + JSON.stringify(JSON.stringify(p.scope)) + ', \\'' + itemId + '\\')">Grant</button>' +
              '</div>'
          }
        </div>
      </div>
    `).join('');
  } catch(e) {
    panel.innerHTML = '<div style="color:#f85149">Error: ' + esc(e.message) + '</div>';
  }
}

async function grantPerm(handlerId, permName, scopeStr, itemId) {
  const sel = document.getElementById('exp-' + itemId + '-' + permName);
  const expiration = sel ? sel.value : 'indefinite';
  await fetch('/api/grant', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ handler_id: handlerId, permission_name: permName, scope: JSON.parse(scopeStr), expiration }),
  });
  // Re-toggle to refresh
  const panel = document.getElementById('perms-' + itemId);
  panel.classList.remove('open');
  setTimeout(() => { togglePerms(itemId); loadContent(); }, 500);
}

async function loadGrants() {
  const res = await fetch('/api/grants');
  const grants = await res.json();
  const div = document.getElementById('content');
  if (grants.length === 0) {
    div.innerHTML = '<div class="empty">No active permission grants</div>';
    return;
  }
  div.innerHTML = grants.map(g => `
    <div class="grant-item">
      <div>
        <strong>${esc(g.handler_id)}</strong> · ${esc(g.permission_name)}
        ${Object.keys(g.scope).length ? ' · ' + esc(JSON.stringify(g.scope)) : ''}
        <span style="color:#8b949e"> · ${g.expiration}${g.expires_at ? ' (expires ' + new Date(g.expires_at).toLocaleString() + ')' : ''}</span>
      </div>
      <button class="revoke-btn" onclick="revoke('${g.id}')">Revoke</button>
    </div>
  `).join('');
}

async function revoke(grantId) {
  await fetch('/api/revoke/' + grantId, { method: 'POST' });
  loadContent();
}

// Init
loadContent();
setInterval(loadContent, 5000);
</script>
</body>
</html>
"""
