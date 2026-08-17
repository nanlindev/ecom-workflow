#!/usr/bin/env python3
"""Generate Ecom n8n workflow JSON with cross-cutting defaults baked in (P1).

Conventions:
- Code nodes default to runOnceForEachItem; config/merge wrappers use runOnceForAllItems.
- External I/O (HTTP/SaaS/Slack/sidecar/DB): onError=continueErrorOutput + maxTries=3 / waitBetweenTries=5000
  **and** a wired connect_error handler (dangling error ports are forbidden — failures will not hit Error Handler).
- Important nodes: English notes.
- settings.errorWorkflow = Ecom Error Handler (re-bind after import); safety net only, not a substitute for node-level handlers.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / "workflows"

SIDECAR = "http://ecom_python_ai:8001"
DEFAULT_CODE_MODE = "runOnceForEachItem"
BATCH_CODE_MODE = "runOnceForAllItems"
ERROR_WORKFLOW = "Ecom Error Handler"


def nid(name: str = "") -> str:
    return str(uuid.uuid4())


def connect(connections: dict, src: str, dst: str, src_output: int = 0, dst_input: int = 0) -> None:
    connections.setdefault(src, {}).setdefault("main", [])
    while len(connections[src]["main"]) <= src_output:
        connections[src]["main"].append([])
    connections[src]["main"][src_output].append({"node": dst, "type": "main", "index": dst_input})


def connect_error(connections: dict, src: str, dst: str, dst_input: int = 0) -> None:
    connect(connections, src, dst, src_output=1, dst_input=dst_input)


def _retry_settings() -> dict:
    return {"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 5000}


def code_node(name: str, js: str, position: list[int], mode: str = DEFAULT_CODE_MODE, notes: str = "") -> dict:
    node: dict[str, Any] = {
        "parameters": {"mode": mode, "jsCode": js},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": position,
        "id": nid(name),
        "name": name,
    }
    if notes:
        node["notes"] = notes
        node["notesInFlow"] = True
    return node


def noop(name: str, position: list[int]) -> dict:
    return {
        "parameters": {},
        "type": "n8n-nodes-base.noOp",
        "typeVersion": 1,
        "position": position,
        "id": nid(name),
        "name": name,
    }


def if_bool_node(name: str, position: list[int], condition_left: str) -> dict:
    return {
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 2,
                },
                "conditions": [
                    {
                        "id": nid(),
                        "leftValue": condition_left,
                        "rightValue": "true",
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": position,
        "id": nid(name),
        "name": name,
    }


def merge_node(name: str, position: list[int], mode: str = "append") -> dict:
    parameters = {"mode": "append", "options": {}} if mode == "append" else {
        "mode": "combine",
        "combineBy": mode,
        "options": {},
    }
    return {
        "parameters": parameters,
        "type": "n8n-nodes-base.merge",
        "typeVersion": 3,
        "position": position,
        "id": nid(name),
        "name": name,
        "notes": "Merge multi-source inventory observations before master conflict resolution.",
        "notesInFlow": True,
    }


def webhook_node(
    name: str,
    position: list[int],
    path: str,
    *,
    http_method: str = "POST",
    response_mode: str = "responseNode",
    raw_body: bool = True,
) -> dict:
    params: dict[str, Any] = {"path": path, "httpMethod": http_method, "responseMode": response_mode, "options": {}}
    if raw_body:
        params["options"]["rawBody"] = True
    return {
        "parameters": params,
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": position,
        "id": nid(name),
        "name": name,
        "webhookId": nid(path),
        "notes": "Shopify webhook ingress; rawBody required for HMAC verification.",
        "notesInFlow": True,
    }


def respond_to_webhook_node(
    name: str,
    position: list[int],
    *,
    response_code: int = 200,
    response_body: str = '={{ { "ok": true } }}',
) -> dict:
    return {
        "parameters": {
            "respondWith": "json",
            "responseBody": response_body,
            "options": {"responseCode": response_code},
        },
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1.1,
        "position": position,
        "id": nid(name),
        "name": name,
    }


def execute_workflow(
    name: str,
    position: list[int],
    target_workflow: str,
    *,
    inputs: dict[str, str] | None = None,
) -> dict:
    parameters: dict[str, Any] = {
        "workflowId": {"__rl": True, "mode": "name", "value": target_workflow},
        "options": {},
    }
    if inputs is not None:
        parameters["workflowInputs"] = {
            "mappingMode": "defineBelow",
            "value": inputs,
            "matchingColumns": [],
            # number fields (amount / days_since_order) must stay numeric — string coerce fails n8n schema
            "attemptToConvertTypes": True,
            "convertFieldsToString": False,
        }
    return {
        "parameters": parameters,
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1.2,
        "position": position,
        "id": nid(name),
        "name": name,
        "notes": f"Map Execute Workflow inputs → {target_workflow}.",
        "notesInFlow": True,
    }


def execute_trigger(name: str, position: list[int], inputs: list[dict[str, Any]]) -> dict:
    return {
        "parameters": {"workflowInputs": {"values": inputs}},
        "type": "n8n-nodes-base.executeWorkflowTrigger",
        "typeVersion": 1.1,
        "position": position,
        "id": nid(name),
        "name": name,
    }


def cron_node(name: str, position: list[int], hours: str = "*/6") -> dict:
    return {
        "parameters": {
            "rule": {"interval": [{"field": "hours", "hoursInterval": 6}]},
        },
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": position,
        "id": nid(name),
        "name": name,
        "notes": "Periodic inventory reconciliation when webhooks are missed.",
        "notesInFlow": True,
    }


def http_json_post(
    name: str,
    position: list[int],
    url: str,
    json_body: str,
    *,
    correlation: bool = True,
    notes: str = "",
) -> dict:
    parameters: dict[str, Any] = {
        "method": "POST",
        "url": url,
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": json_body,
        "options": {"timeout": 45000},
    }
    if correlation:
        parameters["sendHeaders"] = True
        parameters["headerParameters"] = {
            "parameters": [{"name": "X-Correlation-Id", "value": "={{ $json.correlation_id }}"}]
        }
    node: dict[str, Any] = {
        "parameters": parameters,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.4,
        "position": position,
        "id": nid(name),
        "name": name,
        **_retry_settings(),
        "onError": "continueErrorOutput",
    }
    if notes:
        node["notes"] = notes
        node["notesInFlow"] = True
    return node


def http_get(name: str, position: list[int], url: str) -> dict:
    return {
        "parameters": {"method": "GET", "url": url, "options": {"timeout": 30000}},
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.4,
        "position": position,
        "id": nid(name),
        "name": name,
        **_retry_settings(),
        "onError": "continueErrorOutput",
    }


def slack_node(name: str, position: list[int], text: str) -> dict:
    return {
        "parameters": {
            # accessToken + slackApi (xoxb) posts as bot; oAuth2 posts as installing user
            "authentication": "accessToken",
            "select": "channel",
            "channelId": {
                "__rl": True,
                "mode": "id",
                "value": "={{ $env.SLACK_ECOM_CHANNEL_ID || 'SLACK_ECOM_CHANNEL_ID' }}",
            },
            "text": text,
        },
        "type": "n8n-nodes-base.slack",
        "typeVersion": 2.2,
        "position": position,
        "id": nid(name),
        "name": name,
        **_retry_settings(),
        "onError": "continueErrorOutput",
        "credentials": {"slackApi": {"id": "SLACK_BOT_CREDENTIAL_ID", "name": "Slack ecom bot"}},
        "notes": "Bind Slack API Access Token = Bot User OAuth Token (xoxb-). Do not use OAuth2.",
        "notesInFlow": True,
    }


def error_message_prelude(default_message: str) -> str:
    return f"""const item = $input.item;
const errJson = item.json || {{}};
const errorObj = item.error || errJson.error || {{}};
const errorMessage =
  errorObj.message ||
  errorObj.description ||
  errJson.message ||
  errJson.description ||
  (typeof errJson.error === 'string' ? errJson.error : null) ||
  '{default_message}';
"""


def save_workflow(name: str, nodes: list, connections: dict, *, error_workflow: str | None = ERROR_WORKFLOW) -> Path:
    WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "callerPolicy": "workflowsFromSameOwner",
        },
        "tags": [{"name": "ecom-workflow"}],
        "meta": {"templateCredsSetupCompleted": False},
    }
    if error_workflow:
        data["settings"]["errorWorkflow"] = error_workflow
    path = WORKFLOWS_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {path.relative_to(ROOT)}")
    return path


# JS snippets

ERROR_EXTRACT_JS = r"""
const err = $input.item.json || {};
const execution = err.execution || {};
const error = err.error || {};

function asText(v) {
  if (v == null) return '';
  if (typeof v === 'string') {
    const t = v.trim();
    return t && t !== '{}' && t !== '[object Object]' ? t : '';
  }
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  return '';
}

function pickMessage(e, depth = 0) {
  if (e == null || depth > 4) return '';
  if (typeof e === 'string') return asText(e);
  if (typeof e !== 'object') return String(e);
  // n8n sometimes sets message to {} / nested Error-like objects
  const nested = [
    e.message,
    e.description,
    e.error,
    e.cause,
    e.reason,
    e.statusMessage,
    e.messages?.[0],
    e.response?.body?.message,
    e.response?.data?.message,
    e.context?.description,
    e.context?.message,
  ];
  for (const c of nested) {
    const direct = asText(c);
    if (direct) return direct;
    if (c && typeof c === 'object') {
      const inner = pickMessage(c, depth + 1);
      if (inner) return inner;
    }
  }
  if (typeof e.name === 'string' && e.name && e.name !== 'Error' && e.name !== 'NodeOperationError') {
    return e.name;
  }
  try {
    const s = JSON.stringify(e);
    if (s && s !== '{}' && s !== 'null') return s.slice(0, 500);
  } catch (_) {}
  return '';
}

const nodeName =
  error.node?.name ||
  (typeof error.node === 'string' ? error.node : null) ||
  err.node?.name ||
  execution.lastNodeExecuted ||
  'unknown';

const message =
  pickMessage(error) ||
  pickMessage(err) ||
  asText(err.message) ||
  'unknown_error';

return {
  workflow: err.workflow?.name || err.workflow || 'unknown',
  execution_id: String(execution.id || err.executionId || ''),
  node: typeof nodeName === 'string' ? nodeName : 'unknown',
  message,
  stack: error.stack || err.stack || '',
  correlation_id:
    error.context?.correlation_id ||
    execution.customData?.correlation_id ||
    err.correlation_id ||
    '',
  retry_suggestion: 'manual',
  timestamp: new Date().toISOString(),
  _metadata: { processing_stage: 'global_error_logged', severity: 'critical' },
};
"""

PREPARE_ERROR_LOG_JS = r"""
const item = $input.item.json;
return {
  ...item,
  correlation_id: item.correlation_id || '',
  workflow_name: item.workflow || 'unknown',
  node_name: item.node || 'unknown',
  error_message: item.message || '',
  detail: {
    stack: item.stack || '',
    execution_id: item.execution_id || '',
    retry_suggestion: item.retry_suggestion || 'manual',
    timestamp: item.timestamp || new Date().toISOString(),
  },
};
"""

HANDLE_ERROR_LOG_HTTP_JS = error_message_prelude("Failed to write error_logs") + r"""
const prev = $('Prepare Error Log Body').item.json;
return {
  ...prev,
  error_log_write_failed: true,
  error_log_error_message: errorMessage,
  _metadata: { processing_stage: 'error_log_write_failed', severity: 'high' },
};
"""

CHECK_ERROR_ALERT_JS = r"""
const extracted = $('Extract Error Details').first()?.json || {};
const cfg = $('Get Config For Alert').first()?.json || {};
const mode = String(cfg.mode || cfg.flat?.mode || 'test').toLowerCase();
const flat = cfg.flat || {};
const enabled = String(flat.error_alert_enabled || 'true').toLowerCase() === 'true';
const slackEnabled = String(flat.slack_enabled || 'true').toLowerCase() === 'true';
return {
  ...extracted,
  mode,
  should_alert_slack: mode === 'production' && enabled && slackEnabled,
};
"""

LOG_SLACK_ERROR_JS = error_message_prelude("Unknown Slack Error Alert failure") + r"""
const prev = $('Check Error Alert Enabled').item.json;
return {
  ...prev,
  slack_alert_failed: true,
  slack_error_message: errorMessage,
  _metadata: { processing_stage: 'error_slack_failed', severity: 'low' },
};
"""

PREPARE_INGEST_BODY_JS = r"""
const crypto = require('crypto');
const item = $input.item;
const json = item.json || {};
const headers = json.headers || {};

// Prefer webhook rawBody / binary for HMAC (required for verify).
let rawBody = null;
if (typeof json.rawBody === 'string' && json.rawBody.length) {
  rawBody = json.rawBody;
} else if (item.binary && item.binary.data) {
  const bin = item.binary.data;
  rawBody = Buffer.from(bin.data, bin.encoding || 'base64').toString('utf8');
} else if (typeof json.body === 'string') {
  rawBody = json.body;
}

// Do not HMAC-verify a JSON.stringify(object) stand-in when raw body is missing.
const canVerify = typeof rawBody === 'string' && rawBody.length > 0;
if (!canVerify) {
  rawBody = JSON.stringify(json.body ?? {});
}

const correlation_id =
  headers['x-correlation-id'] ||
  headers['X-Correlation-Id'] ||
  crypto.randomUUID();

const isWoo = !!(
  headers['x-wc-webhook-topic'] ||
  headers['X-WC-Webhook-Topic'] ||
  headers['x-wc-webhook-signature'] ||
  headers['X-WC-Webhook-Signature'] ||
  String(headers['user-agent'] || '').includes('WooCommerce')
);
const platform = isWoo ? 'woocommerce' : 'shopify';

const store_key =
  $env.ECOM_DEMO_STORE_KEY ||
  (platform === 'shopify'
    ? (headers['x-shopify-shop-domain'] || '').replace('.myshopify.com', '')
    : ($env.ECOM_DEMO_WOO_STORE_KEY || '')) ||
  'demo-shopify';

return {
  correlation_id,
  store_key,
  platform,
  is_woo: isWoo,
  raw_body: rawBody,
  headers,
  // Skip verify when raw body unavailable (avoids spurious 401).
  skip_verify: !canVerify,
};
"""

HANDLE_INGEST_HTTP_JS = error_message_prelude("Ingest sidecar call failed") + r"""
function getPrep() {
  const names = [
    'Prepare Shopify Ingest Request',
    'Prepare Woo Ingest Request',
    'Prepare Ingest Request',
  ];
  for (const name of names) {
    try {
      return $(name).item.json;
    } catch (e) {}
  }
  return {};
}
const prep = getPrep();
return {
  ...prep,
  ok: false,
  signature_valid: false,
  ingest_error_message: errorMessage,
  http_status: 502,
  dispatch: { inventory: false, order: false, returns: false },
  _metadata: { processing_stage: 'ingest_http_failed', severity: 'high' },
};
"""

NORMALIZE_INGEST_RESULT_JS = r"""
function getPrep() {
  const names = [
    'Prepare Shopify Ingest Request',
    'Prepare Woo Ingest Request',
    'Prepare Ingest Request',
  ];
  for (const name of names) {
    try {
      return $(name).item.json;
    } catch (e) {}
  }
  return {};
}

const prep = getPrep();
const res = $input.item.json || {};
const body = res.body && typeof res.body === 'object' ? res.body : res;
const eventType = body.event_type || '';
const primary = body.entities?.primary_id || '';
const entities = body.entities || {};

return {
  ...prep,
  ...body,
  correlation_id: body.correlation_id || prep.correlation_id,
  signature_valid: body.signature_valid !== false && body.ok !== false,
  dispatch: body.dispatch || { inventory: false, order: false, returns: false },
  sku: entities.sku || '',
  order_id: eventType === 'order' ? primary : (entities.order_id || ''),
  return_id: eventType === 'return' ? primary : '',
  external_order_id: entities.external_order_id || '',
  external_return_id: entities.external_return_id || '',
  amount: entities.amount ?? null,
  reason: entities.reason || '',
  days_since_order: Number(body.days_since_order ?? 0),
};
"""

CRON_INVENTORY_SEED_JS = r"""
return {
  store_id: $env.ECOM_DEMO_STORE_ID || '',
  store_key: $env.ECOM_DEMO_STORE_KEY || 'demo-shopify',
  sku: '',
  correlation_id: require('crypto').randomUUID(),
  slave_levels: [],
  trigger_source: 'cron',
};
"""

PREPARE_INVENTORY_SYNC_JS = r"""
const item = $input.item.json || {};
const slave = item.slave_levels;
let slave_levels = [];
if (Array.isArray(slave)) slave_levels = slave;
else if (typeof slave === 'string' && slave.trim()) {
  try { slave_levels = JSON.parse(slave); } catch { slave_levels = []; }
}
return {
  store_id: item.store_id || null,
  store_key: item.store_key || null,
  sku: item.sku || null,
  correlation_id: item.correlation_id || '',
  slave_levels: slave_levels.length ? slave_levels : null,
};
"""

HANDLE_INVENTORY_HTTP_JS = error_message_prelude("Inventory sync sidecar failed") + r"""
const prep = $('Prepare Inventory Sync Body').item.json;
return {
  ...prep,
  ok: false,
  has_drift: false,
  should_alert_slack: false,
  writeback_status: 'failed',
  inventory_error_message: errorMessage,
  _metadata: { processing_stage: 'inventory_sync_failed', severity: 'high' },
};
"""

FLATTEN_INVENTORY_RESULT_JS = r"""
const prep = $('Prepare Inventory Sync Body').item.json;
const res = $input.item.json || {};
const body = res.body && typeof res.body === 'object' ? res.body : res;
const drifts = body.drifts || [];
const channels = (body.channel_writebacks || [])
  .map(c => `${c.slave_channel || c.channel}=${c.live_status || 'n/a'}`)
  .slice(0, 5)
  .join(', ');
return {
  ...prep,
  ...body,
  correlation_id: body.correlation_id || prep.correlation_id,
  slack_text: [
    '📦 Inventory drift detected',
    `Store: ${body.store_id || prep.store_id}`,
    `Master: ${body.master_channel || 'shopify'}`,
    `Drifts: ${drifts.length}`,
    drifts.slice(0, 5).map(d => `${d.sku}: ${d.slave_channel}=${d.slave_available} vs master=${d.master_available}`).join('\n'),
    `Writeback: ${body.writeback_status || 'n/a'}${channels ? ` (${channels})` : ''}`,
    `Correlation: ${body.correlation_id || prep.correlation_id}`,
  ].filter(Boolean).join('\n'),
};
"""

PREPARE_ORDER_TRACK_JS = r"""
const item = $input.item.json || {};
return {
  store_id: item.store_id,
  order_id: item.order_id || null,
  external_order_id: item.external_order_id || null,
  new_status: item.new_status || null,
  correlation_id: item.correlation_id || '',
};
"""

HANDLE_ORDER_HTTP_JS = error_message_prelude("Order track sidecar failed") + r"""
const prep = $('Prepare Order Track Body').item.json;
return {
  ...prep,
  ok: false,
  is_anomaly: false,
  should_alert_slack: false,
  order_error_message: errorMessage,
  _metadata: { processing_stage: 'order_track_failed', severity: 'high' },
};
"""

FLATTEN_ORDER_RESULT_JS = r"""
const prep = $('Prepare Order Track Body').item.json;
const res = $input.item.json || {};
const body = res.body && typeof res.body === 'object' ? res.body : res;
const reasons = body.anomaly_reasons || [];
return {
  ...prep,
  ...body,
  correlation_id: body.correlation_id || prep.correlation_id,
  slack_text: [
    '⚠️ Order anomaly',
    `Order: ${body.external_order_id || body.order_id}`,
    `Status: ${body.previous_status || '?'} → ${body.status || '?'}`,
    `Reasons: ${reasons.join(', ') || 'n/a'}`,
    `Correlation: ${body.correlation_id || prep.correlation_id}`,
  ].join('\n'),
};
"""

PREPARE_RETURN_DECIDE_JS = r"""
const item = $input.item.json || {};
const amount = item.amount === '' || item.amount == null ? null : Number(item.amount);
const days = item.days_since_order === '' || item.days_since_order == null ? null : Number(item.days_since_order);
return {
  store_id: item.store_id,
  return_id: item.return_id || null,
  external_return_id: item.external_return_id || null,
  order_id: item.order_id || null,
  amount,
  days_since_order: days,
  reason: item.reason || null,
  correlation_id: item.correlation_id || '',
};
"""

HANDLE_RETURN_HTTP_JS = error_message_prelude("Returns decide sidecar failed") + r"""
const prep = $('Prepare Return Decide Body').item.json;
return {
  ...prep,
  ok: false,
  needs_manual_review: false,
  should_alert_slack: false,
  returns_error_message: errorMessage,
  _metadata: { processing_stage: 'returns_decide_failed', severity: 'high' },
};
"""

FLATTEN_RETURN_RESULT_JS = r"""
const prep = $('Prepare Return Decide Body').item.json;
const res = $input.item.json || {};
const body = res.body && typeof res.body === 'object' ? res.body : res;
const adminUrl = body.shopify_admin_url || '';
const lines = [
  '↩️ Return needs manual review',
  `Return: ${body.external_return_id || body.return_id}`,
  `Shopify order: ${body.shopify_order_id || 'n/a'}`,
  `Amount: ${body.amount}`,
  `Reason: ${body.reason || prep.reason || 'n/a'}`,
  `Days since order: ${body.days_since_order}`,
  `Why flagged: ${body.review_reason || 'n/a'}`,
  `Decision: ${body.decision}`,
  `Action: Open in Shopify (no Slack approve — process refund/return in Admin)`,
  adminUrl ? `Shopify Admin: ${adminUrl}` : 'Shopify Admin: (set store external_shop_id / SHOPIFY_STORE_HANDLE)',
  `Correlation: ${body.correlation_id || prep.correlation_id}`,
];
return {
  ...prep,
  ...body,
  correlation_id: body.correlation_id || prep.correlation_id,
  slack_text: lines.join('\n'),
};
"""

# Explicit Execute Workflow input maps
INGEST_TO_INVENTORY = {
    "store_id": "={{ $json.store_id }}",
    "store_key": "={{ $json.store_key || '' }}",
    "sku": "={{ $json.sku || $json.entities?.sku || '' }}",
    "correlation_id": "={{ $json.correlation_id }}",
    "slave_levels": "={{ JSON.stringify($json.slave_levels || []) }}",
}

INGEST_TO_ORDER = {
    "store_id": "={{ $json.store_id }}",
    "order_id": "={{ $json.order_id || $json.entities?.order_id || ($json.event_type === 'order' ? ($json.entities?.primary_id || '') : '') || '' }}",
    "external_order_id": "={{ $json.external_order_id || $json.entities?.external_order_id || '' }}",
    "new_status": "={{ $json.new_status || '' }}",
    "correlation_id": "={{ $json.correlation_id }}",
}

INGEST_TO_RETURNS = {
    "store_id": "={{ $json.store_id }}",
    "return_id": "={{ $json.return_id || $json.entities?.primary_id || '' }}",
    "external_return_id": "={{ $json.external_return_id || $json.entities?.external_return_id || '' }}",
    "order_id": "={{ $json.order_id || $json.entities?.order_id || '' }}",
    "amount": "={{ Number($json.amount ?? $json.entities?.amount ?? 0) }}",
    "days_since_order": "={{ Number($json.days_since_order ?? 0) }}",
    "reason": "={{ $json.reason || $json.entities?.reason || '' }}",
    "correlation_id": "={{ $json.correlation_id }}",
}

INVENTORY_INPUTS = [
    {"name": "store_id"},
    {"name": "store_key"},
    {"name": "sku"},
    {"name": "correlation_id"},
    {"name": "slave_levels"},
]

ORDER_INPUTS = [
    {"name": "store_id"},
    {"name": "order_id"},
    {"name": "external_order_id"},
    {"name": "new_status"},
    {"name": "correlation_id"},
]

RETURNS_INPUTS = [
    {"name": "store_id"},
    {"name": "return_id"},
    {"name": "external_return_id"},
    {"name": "order_id"},
    {"name": "amount", "type": "number"},
    {"name": "days_since_order", "type": "number"},
    {"name": "reason"},
    {"name": "correlation_id"},
]


def build_error_handler() -> None:
    nodes = [
        {
            "parameters": {},
            "type": "n8n-nodes-base.errorTrigger",
            "typeVersion": 1,
            "position": [0, 0],
            "id": nid("error"),
            "name": "Error Trigger",
            "notes": "Workflow-level errors. Re-bind as Error Workflow on other Ecom flows after import.",
            "notesInFlow": True,
        },
        code_node("Extract Error Details", ERROR_EXTRACT_JS, [220, 0], notes="Normalize n8n error payload."),
        code_node("Prepare Error Log Body", PREPARE_ERROR_LOG_JS, [440, 0]),
        http_json_post(
            "Write error_logs",
            [660, 0],
            f"{SIDECAR}/errors/log",
            "={{ JSON.stringify({ workflow_name: $json.workflow_name, node_name: $json.node_name, error_message: $json.error_message, correlation_id: $json.correlation_id, detail: $json.detail }) }}",
            notes="Persist to ecom_postgres.error_logs via sidecar.",
        ),
        code_node("Handle error_logs Write Failure", HANDLE_ERROR_LOG_HTTP_JS, [660, 200]),
        http_get("Get Config For Alert", [880, 0], f"{SIDECAR}/config"),
        code_node(
            "Handle Config HTTP Error",
            error_message_prelude("Get config for error alert failed")
            + "\nconst extracted = $('Extract Error Details').first()?.json || {};\nreturn { ...extracted, config_error_message: errorMessage, mode: 'production', should_alert_slack: true, _metadata: { processing_stage: 'error_handler_config_failed', severity: 'high', error_message: errorMessage } };\n",
            [880, 200],
            notes="Config unavailable → still attempt Slack alert",
        ),
        code_node("Check Error Alert Enabled", CHECK_ERROR_ALERT_JS, [1100, 0], mode=BATCH_CODE_MODE),
        if_bool_node("Should Alert Slack?", [1320, 0], "={{ $json.should_alert_slack }}"),
        slack_node(
            "Slack Error Alert",
            [1540, 0],
            "=🚨 Ecom Workflow Error\nWorkflow: {{ $json.workflow }}\nNode: {{ $json.node }}\nMessage: {{ $json.message }}\nCorrelation: {{ $json.correlation_id }}",
        ),
        code_node("Log Slack Error", LOG_SLACK_ERROR_JS, [1760, 120]),
        noop("No Slack Alert", [1540, 200]),
    ]
    conn: dict = {}
    connect(conn, "Error Trigger", "Extract Error Details")
    connect(conn, "Extract Error Details", "Prepare Error Log Body")
    connect(conn, "Prepare Error Log Body", "Write error_logs")
    connect_error(conn, "Write error_logs", "Handle error_logs Write Failure")
    connect(conn, "Write error_logs", "Get Config For Alert")
    connect(conn, "Handle error_logs Write Failure", "Get Config For Alert")
    connect(conn, "Get Config For Alert", "Check Error Alert Enabled")
    connect_error(conn, "Get Config For Alert", "Handle Config HTTP Error")
    connect(conn, "Handle Config HTTP Error", "Should Alert Slack?")
    connect(conn, "Check Error Alert Enabled", "Should Alert Slack?")
    connect(conn, "Should Alert Slack?", "Slack Error Alert", src_output=0)
    connect(conn, "Should Alert Slack?", "No Slack Alert", src_output=1)
    connect_error(conn, "Slack Error Alert", "Log Slack Error")
    save_workflow("Ecom Error Handler", nodes, conn, error_workflow=None)


def build_platform_ingest() -> None:
    # Prepare before merge so webhook binary/rawBody is not dropped.
    nodes = [
        webhook_node("Shopify Webhook", [0, -120], "ecom-shopify"),
        webhook_node("Woo Webhook", [0, 120], "ecom-woo"),
        code_node(
            "Prepare Shopify Ingest Request",
            PREPARE_INGEST_BODY_JS,
            [220, -120],
            notes="HMAC prep (Shopify).",
        ),
        code_node(
            "Prepare Woo Ingest Request",
            PREPARE_INGEST_BODY_JS,
            [220, 120],
            notes="HMAC prep (Woo; ping acked in sidecar).",
        ),
        merge_node("Merge Ingest Triggers", [440, 0], mode="append"),
        if_bool_node("Is Woo Ingest?", [640, 0], "={{ $json.is_woo }}"),
        http_json_post(
            "Sidecar Ingest Shopify",
            [860, -120],
            f"{SIDECAR}/ingest/shopify",
            "={{ JSON.stringify({ raw_body: $json.raw_body, headers: $json.headers, store_key: $json.store_key, correlation_id: $json.correlation_id, skip_verify: $json.skip_verify }) }}",
            notes="Shopify ingest → PG upsert.",
        ),
        http_json_post(
            "Sidecar Ingest Woo",
            [860, 120],
            f"{SIDECAR}/ingest/woocommerce",
            "={{ JSON.stringify({ raw_body: $json.raw_body, headers: $json.headers, store_key: $json.store_key, correlation_id: $json.correlation_id, skip_verify: $json.skip_verify }) }}",
            notes="Woo ingest → PG upsert.",
        ),
        code_node("Handle Ingest HTTP Error", HANDLE_INGEST_HTTP_JS, [860, 300]),
        code_node("Normalize Ingest Result", NORMALIZE_INGEST_RESULT_JS, [1080, 0]),
        if_bool_node("Signature Valid?", [1300, 0], "={{ $json.signature_valid }}"),
        respond_to_webhook_node(
            "Respond 401",
            [1520, -160],
            response_code=401,
            response_body='{ "ok": false, "error": "invalid_signature" }',
        ),
        respond_to_webhook_node(
            "Respond 200",
            [1520, 0],
            response_code=200,
            response_body='={\n  "ok": true,\n  "correlation_id": "={{ $json.correlation_id }}",\n  "event_type": "={{ $json.event_type }}",\n  "platform": "={{ $json.platform }}"\n}',
        ),
        if_bool_node("Dispatch Inventory?", [1740, 0], "={{ $json.dispatch.inventory }}"),
        execute_workflow("Execute Inventory Sync", [1960, -80], "Ecom Inventory Sync", inputs=INGEST_TO_INVENTORY),
        if_bool_node("Dispatch Order?", [1740, 160], "={{ $json.dispatch.order }}"),
        execute_workflow("Execute Order Tracker", [1960, 160], "Ecom Order Tracker", inputs=INGEST_TO_ORDER),
        if_bool_node("Dispatch Returns?", [1740, 320], "={{ $json.dispatch.returns }}"),
        execute_workflow("Execute Returns Automation", [1960, 320], "Ecom Returns Automation", inputs=INGEST_TO_RETURNS),
        noop("No Downstream", [1960, 480]),
    ]
    conn: dict = {}
    connect(conn, "Shopify Webhook", "Prepare Shopify Ingest Request")
    connect(conn, "Woo Webhook", "Prepare Woo Ingest Request")
    connect(conn, "Prepare Shopify Ingest Request", "Merge Ingest Triggers", dst_input=0)
    connect(conn, "Prepare Woo Ingest Request", "Merge Ingest Triggers", dst_input=1)
    connect(conn, "Merge Ingest Triggers", "Is Woo Ingest?")
    connect(conn, "Is Woo Ingest?", "Sidecar Ingest Woo", src_output=0)
    connect(conn, "Is Woo Ingest?", "Sidecar Ingest Shopify", src_output=1)
    connect_error(conn, "Sidecar Ingest Shopify", "Handle Ingest HTTP Error")
    connect_error(conn, "Sidecar Ingest Woo", "Handle Ingest HTTP Error")
    connect(conn, "Sidecar Ingest Shopify", "Normalize Ingest Result")
    connect(conn, "Sidecar Ingest Woo", "Normalize Ingest Result")
    connect(conn, "Handle Ingest HTTP Error", "Normalize Ingest Result")
    connect(conn, "Normalize Ingest Result", "Signature Valid?")
    connect(conn, "Signature Valid?", "Respond 200", src_output=0)
    connect(conn, "Signature Valid?", "Respond 401", src_output=1)
    connect(conn, "Respond 200", "Dispatch Inventory?")
    connect(conn, "Dispatch Inventory?", "Execute Inventory Sync", src_output=0)
    connect(conn, "Dispatch Inventory?", "Dispatch Order?", src_output=1)
    connect(conn, "Execute Inventory Sync", "Dispatch Order?")
    connect(conn, "Dispatch Order?", "Execute Order Tracker", src_output=0)
    connect(conn, "Dispatch Order?", "Dispatch Returns?", src_output=1)
    connect(conn, "Execute Order Tracker", "Dispatch Returns?")
    connect(conn, "Dispatch Returns?", "Execute Returns Automation", src_output=0)
    connect(conn, "Dispatch Returns?", "No Downstream", src_output=1)
    save_workflow("Ecom Platform Ingest", nodes, conn)


def build_inventory_sync() -> None:
    # Two triggers: Execute Workflow + Cron. Merge append then sync.
    nodes = [
        execute_trigger("When Executed by Another Workflow", [0, 0], INVENTORY_INPUTS),
        cron_node("Inventory Reconcile Cron", [0, 220]),
        code_node("Cron Seed Payload", CRON_INVENTORY_SEED_JS, [220, 220], mode=BATCH_CODE_MODE),
        merge_node("Merge Inventory Triggers", [440, 80], mode="append"),
        code_node(
            "Prepare Inventory Sync Body",
            PREPARE_INVENTORY_SYNC_JS,
            [660, 80],
            notes="Normalize Execute/Cron payload; optional slave_levels from Merge upstream.",
        ),
        http_json_post(
            "Sidecar Inventory Sync",
            [880, 80],
            f"{SIDECAR}/inventory/sync",
            "={{ JSON.stringify({ store_id: $json.store_id || null, store_key: $json.store_key || null, sku: $json.sku || null, correlation_id: $json.correlation_id, slave_levels: $json.slave_levels }) }}",
            notes="Master wins; live writeback if creds else SoT-only.",
        ),
        code_node("Handle Inventory HTTP Error", HANDLE_INVENTORY_HTTP_JS, [880, 260]),
        code_node("Flatten Inventory Result", FLATTEN_INVENTORY_RESULT_JS, [1100, 80]),
        if_bool_node("Should Alert Drift?", [1320, 80], "={{ $json.should_alert_slack }}"),
        slack_node("Slack Inventory Drift", [1540, 0], "={{ $json.slack_text }}"),
        code_node(
            "Log Slack Drift Error",
            error_message_prelude("Slack drift alert failed")
            + "\nconst prev = $('Flatten Inventory Result').item.json;\n"
            + "return { ...prev, slack_failed: true, slack_error_message: errorMessage };\n",
            [1760, 120],
        ),
        noop("No Drift Alert", [1540, 200]),
    ]
    conn: dict = {}
    connect(conn, "When Executed by Another Workflow", "Merge Inventory Triggers", dst_input=0)
    connect(conn, "Inventory Reconcile Cron", "Cron Seed Payload")
    connect(conn, "Cron Seed Payload", "Merge Inventory Triggers", dst_input=1)
    connect(conn, "Merge Inventory Triggers", "Prepare Inventory Sync Body")
    connect(conn, "Prepare Inventory Sync Body", "Sidecar Inventory Sync")
    connect_error(conn, "Sidecar Inventory Sync", "Handle Inventory HTTP Error")
    connect(conn, "Sidecar Inventory Sync", "Flatten Inventory Result")
    connect(conn, "Handle Inventory HTTP Error", "Flatten Inventory Result")
    connect(conn, "Flatten Inventory Result", "Should Alert Drift?")
    connect(conn, "Should Alert Drift?", "Slack Inventory Drift", src_output=0)
    connect(conn, "Should Alert Drift?", "No Drift Alert", src_output=1)
    connect_error(conn, "Slack Inventory Drift", "Log Slack Drift Error")
    save_workflow("Ecom Inventory Sync", nodes, conn)


def build_order_tracker() -> None:
    nodes = [
        execute_trigger("When Executed by Another Workflow", [0, 0], ORDER_INPUTS),
        code_node("Prepare Order Track Body", PREPARE_ORDER_TRACK_JS, [220, 0]),
        http_json_post(
            "Sidecar Order Track",
            [440, 0],
            f"{SIDECAR}/orders/track",
            "={{ JSON.stringify({ store_id: $json.store_id, order_id: $json.order_id || null, external_order_id: $json.external_order_id || null, new_status: $json.new_status || null, correlation_id: $json.correlation_id }) }}",
            notes="Status machine + anomaly heuristics.",
        ),
        code_node("Handle Order HTTP Error", HANDLE_ORDER_HTTP_JS, [440, 200]),
        code_node("Flatten Order Result", FLATTEN_ORDER_RESULT_JS, [660, 0]),
        if_bool_node("Should Alert Anomaly?", [880, 0], "={{ $json.should_alert_slack }}"),
        slack_node("Slack Order Anomaly", [1100, 0], "={{ $json.slack_text }}"),
        code_node(
            "Log Slack Order Error",
            error_message_prelude("Slack order alert failed")
            + "\nconst prev = $('Flatten Order Result').item.json;\n"
            + "return { ...prev, slack_failed: true, slack_error_message: errorMessage };\n",
            [1320, 120],
        ),
        noop("No Order Alert", [1100, 200]),
    ]
    conn: dict = {}
    connect(conn, "When Executed by Another Workflow", "Prepare Order Track Body")
    connect(conn, "Prepare Order Track Body", "Sidecar Order Track")
    connect_error(conn, "Sidecar Order Track", "Handle Order HTTP Error")
    connect(conn, "Sidecar Order Track", "Flatten Order Result")
    connect(conn, "Handle Order HTTP Error", "Flatten Order Result")
    connect(conn, "Flatten Order Result", "Should Alert Anomaly?")
    connect(conn, "Should Alert Anomaly?", "Slack Order Anomaly", src_output=0)
    connect(conn, "Should Alert Anomaly?", "No Order Alert", src_output=1)
    connect_error(conn, "Slack Order Anomaly", "Log Slack Order Error")
    save_workflow("Ecom Order Tracker", nodes, conn)


def build_returns_automation() -> None:
    nodes = [
        execute_trigger("When Executed by Another Workflow", [0, 0], RETURNS_INPUTS),
        code_node("Prepare Return Decide Body", PREPARE_RETURN_DECIDE_JS, [220, 0]),
        http_json_post(
            "Sidecar Returns Decide",
            [440, 0],
            f"{SIDECAR}/returns/decide",
            "={{ JSON.stringify({ store_id: $json.store_id, return_id: $json.return_id || null, external_return_id: $json.external_return_id || null, order_id: $json.order_id || null, amount: $json.amount, days_since_order: $json.days_since_order, reason: $json.reason, correlation_id: $json.correlation_id }) }}",
            notes="Rules: amount + days → auto_approve | manual_review | reject.",
        ),
        code_node("Handle Return HTTP Error", HANDLE_RETURN_HTTP_JS, [440, 200]),
        code_node("Flatten Return Result", FLATTEN_RETURN_RESULT_JS, [660, 0]),
        if_bool_node("Needs Manual Review Slack?", [880, 0], "={{ $json.should_alert_slack }}"),
        slack_node("Slack Return Review", [1100, 0], "={{ $json.slack_text }}"),
        code_node(
            "Log Slack Return Error",
            error_message_prelude("Slack return alert failed")
            + "\nconst prev = $('Flatten Return Result').item.json;\n"
            + "return { ...prev, slack_failed: true, slack_error_message: errorMessage };\n",
            [1320, 120],
        ),
        noop("No Return Alert", [1100, 200]),
    ]
    conn: dict = {}
    connect(conn, "When Executed by Another Workflow", "Prepare Return Decide Body")
    connect(conn, "Prepare Return Decide Body", "Sidecar Returns Decide")
    connect_error(conn, "Sidecar Returns Decide", "Handle Return HTTP Error")
    connect(conn, "Sidecar Returns Decide", "Flatten Return Result")
    connect(conn, "Handle Return HTTP Error", "Flatten Return Result")
    connect(conn, "Flatten Return Result", "Needs Manual Review Slack?")
    connect(conn, "Needs Manual Review Slack?", "Slack Return Review", src_output=0)
    connect(conn, "Needs Manual Review Slack?", "No Return Alert", src_output=1)
    connect_error(conn, "Slack Return Review", "Log Slack Return Error")
    save_workflow("Ecom Returns Automation", nodes, conn)


def main() -> None:
    build_error_handler()
    build_platform_ingest()
    build_inventory_sync()
    build_order_tracker()
    build_returns_automation()
    print("P1 workflows generated.")
    # P2 builders live in sibling module to keep this file readable.
    from generate_workflows_p2 import build_all_p2

    build_all_p2()
    from generate_workflows_p3 import build_all_p3

    build_all_p3()


if __name__ == "__main__":
    main()
