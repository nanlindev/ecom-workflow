"""P2 n8n workflow builders (Competitor, Pricing, Insights, Marketing, Slack Actions)."""

from __future__ import annotations

from typing import Any

# Import shared node helpers from the P1 generator module.
from generate_workflows import (  # type: ignore
    SIDECAR,
    BATCH_CODE_MODE,
    code_node,
    connect,
    connect_error,
    cron_node,
    execute_trigger,
    http_json_post,
    if_bool_node,
    nid,
    noop,
    save_workflow,
    slack_node,
    webhook_node,
    respond_to_webhook_node,
    error_message_prelude,
    _retry_settings,
)


def slack_blocks_node(name: str, position: list[int]) -> dict:
    return {
        "parameters": {
            "authentication": "accessToken",
            "resource": "message",
            "operation": "post",
            "select": "channel",
            "channelId": {
                "__rl": True,
                "mode": "id",
                "value": "={{ $env.SLACK_ECOM_CHANNEL_ID || 'SLACK_ECOM_CHANNEL_ID' }}",
            },
            "messageType": "block",
            "blocksUi": "={{ JSON.stringify($json.slack_blocks) }}",
            "text": "={{ $json.slack_text }}",
            "otherOptions": {"includeLinkToWorkflow": False},
        },
        "type": "n8n-nodes-base.slack",
        "typeVersion": 2.2,
        "position": position,
        "id": nid(name),
        "name": name,
        **_retry_settings(),
        "onError": "continueErrorOutput",
        # Use Slack API (Access Token / xoxb), NOT OAuth2 — OAuth2 posts as the installing user.
        "credentials": {"slackApi": {"id": "SLACK_BOT_CREDENTIAL_ID", "name": "Slack ecom bot"}},
        "notes": "Bind Slack API credential with Bot User OAuth Token (xoxb-). OAuth2 posts as you.",
        "notesInFlow": True,
    }


def slack_update_blocks_node(name: str, position: list[int]) -> dict:
    return {
        "parameters": {
            "authentication": "accessToken",
            "resource": "message",
            "operation": "update",
            "select": "channel",
            "channelId": {
                "__rl": True,
                "mode": "id",
                "value": "={{ $json.channel_id || $env.SLACK_ECOM_CHANNEL_ID || 'SLACK_ECOM_CHANNEL_ID' }}",
            },
            "ts": "={{ $json.message_ts }}",
            "messageType": "block",
            # slack_blocks is already { blocks: [...] } — do not wrap again
            "blocksUi": "={{ JSON.stringify($json.slack_blocks) }}",
            "text": "={{ $json.slack_text }}",
            "otherOptions": {},
        },
        "type": "n8n-nodes-base.slack",
        "typeVersion": 2.2,
        "position": position,
        "id": nid(name),
        "name": name,
        **_retry_settings(),
        "onError": "continueErrorOutput",
        "credentials": {"slackApi": {"id": "SLACK_BOT_CREDENTIAL_ID", "name": "Slack ecom bot"}},
    }


def http_get_url(name: str, position: list[int], url_expr: str) -> dict:
    return {
        "parameters": {
            "url": url_expr,
            "options": {"timeout": 20000, "response": {"response": {"fullResponse": False, "neverError": True}}},
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.4,
        "position": position,
        "id": nid(name),
        "name": name,
        **_retry_settings(),
        "onError": "continueErrorOutput",
        "notes": "Fetch competitor page HTML (whitelist URL only).",
        "notesInFlow": True,
    }


# ---- JS snippets ----

LOAD_TARGETS_JS = r"""
const res = $input.item.json || {};
const body = res.body && typeof res.body === 'object' ? res.body : res;
const targets = Array.isArray(body.targets) ? body.targets : [];
const store_id = body.store_id || $env.ECOM_DEMO_STORE_ID || '';
const defaultSku = body.sku || 'TEE-BLACK-M';
if (!targets.length) {
  return [{
    json: {
      store_id,
      url: 'https://example.com/products/tee-black-m',
      sku: defaultSku,
      source_name: 'example-comp',
      correlation_id: require('crypto').randomUUID(),
      demo_html: '<html><body><h1>Demo Tee</h1><p>Price: $84.00</p></body></html>',
    },
  }];
}
return targets.map((t) => ({
  json: {
    store_id,
    url: t.url || t,
    sku: t.sku || defaultSku,
    source_name: t.source_name || 'competitor',
    correlation_id: require('crypto').randomUUID(),
    demo_html: '',
  },
}));
"""

PREPARE_PARSE_JS = r"""
// HTTP Fetch replaces item json with response body — restore context from Expand Targets.
const item = $input.item.json || {};
let ctx = {};
try { ctx = $('Expand Targets').item.json || {}; } catch (_) { ctx = {}; }

const store_id = item.store_id || ctx.store_id || $env.ECOM_DEMO_STORE_ID || '';
const url = item.url || ctx.url || 'https://example.com/products/tee-black-m';
const sku = item.sku || ctx.sku || 'TEE-BLACK-M';
const source_name = item.source_name || ctx.source_name || 'competitor';
const correlation_id = item.correlation_id || ctx.correlation_id || require('crypto').randomUUID();
const demo_html = item.demo_html || ctx.demo_html || '<html><body><h1>Demo Tee</h1><p>Price: $84.00</p></body></html>';

let raw = '';
if (typeof item === 'string') {
  raw = item;
} else if (typeof item.data === 'string') {
  raw = item.data;
} else if (typeof item.body === 'string') {
  raw = item.body;
} else if (item.data != null || item.body != null) {
  const fetched = item.data || item.body;
  raw = typeof fetched === 'string' ? fetched : JSON.stringify(fetched);
} else if (item.raw_content) {
  raw = String(item.raw_content);
} else {
  // Plain HTML response often lands as a single-field object or stray keys — stringify whole item as last resort only if it looks like HTML.
  const asText = typeof item === 'object' ? (item.html || item.content || '') : '';
  raw = asText || '';
  if (!raw && Object.keys(item).length === 1) {
    const only = item[Object.keys(item)[0]];
    if (typeof only === 'string') raw = only;
  }
  // n8n sometimes puts the entire HTML string as the json value via weird shapes — detect doctype
  if (!raw) {
    const blob = JSON.stringify(item);
    if (blob.includes('<html') || blob.includes('<!doctype')) {
      // Prefer extracting from known string fields first; if item IS effectively the HTML document fields
      raw = Object.values(item).find((v) => typeof v === 'string' && v.includes('<')) || '';
    }
  }
}

raw = String(raw || '');
// Example Domain / empty pages have no price — use seeded demo HTML for reliable demos.
const hasPrice = /\$\s*\d|price[\s:=]/i.test(raw);
if (!hasPrice || raw.length < 20) {
  raw = demo_html;
}

if (!store_id) {
  throw new Error('store_id missing — set ECOM_DEMO_STORE_ID in n8n env or ensure /competitors/targets returns store_id');
}

return {
  store_id,
  url,
  sku,
  source_name,
  raw_content: raw.slice(0, 8000),
  correlation_id,
};
"""

PRICING_SEED_JS = r"""
return {
  store_id: $env.ECOM_DEMO_STORE_ID || '',
  sku: $env.ECOM_DEMO_PRICING_SKU || 'TEE-BLACK-M',
  current_price: 89,
  cost: 35,
  correlation_id: require('crypto').randomUUID(),
};
"""

FLATTEN_PRICING_JS = r"""
const prep = $('Prepare Pricing Body').item.json;
const res = $input.item.json || {};
const body = res.body && typeof res.body === 'object' ? res.body : res;
const recId = body.recommendation_id || '';
const sku = body.sku || prep.sku || '';
const approveVal = JSON.stringify({ recommendation_id: recId, action: 'approve', sku });
const rejectVal = JSON.stringify({ recommendation_id: recId, action: 'reject', sku });
const slack_text = `Pricing recommendation for ${sku}: ${body.current_price} → ${body.recommended_price}`;
const slack_blocks = {
  blocks: [
    { type: 'header', text: { type: 'plain_text', text: 'Pricing recommendation' } },
    {
      type: 'section',
      fields: [
        { type: 'mrkdwn', text: `*SKU:*\n${sku}` },
        { type: 'mrkdwn', text: `*Current → Recommended:*\n${body.current_price} → ${body.recommended_price}` },
        { type: 'mrkdwn', text: `*Strategy:*\n${body.strategy || 'n/a'}` },
        { type: 'mrkdwn', text: `*Fallback:*\n${body.fallback_used ? 'yes' : 'no'}` },
      ],
    },
    { type: 'section', text: { type: 'mrkdwn', text: `*Reasoning:*\n${body.reasoning || 'n/a'}` } },
    {
      type: 'actions',
      elements: [
        { type: 'button', text: { type: 'plain_text', text: 'Approve' }, style: 'primary', action_id: 'approve_pricing', value: approveVal },
        { type: 'button', text: { type: 'plain_text', text: 'Reject' }, style: 'danger', action_id: 'reject_pricing', value: rejectVal },
      ],
    },
  ],
};
return {
  ...prep,
  ...body,
  slack_text,
  slack_blocks,
  should_alert_slack: body.should_alert_slack !== false,
};
"""

INSIGHTS_SEED_JS = r"""
return {
  store_id: $env.ECOM_DEMO_STORE_ID || '',
  correlation_id: require('crypto').randomUUID(),
};
"""

MARKETING_ADVANCE_SEED_JS = r"""
return {
  store_id: $env.ECOM_DEMO_STORE_ID || null,
  limit: 20,
  correlation_id: require('crypto').randomUUID(),
};
"""

FLATTEN_MARKETING_JS = r"""
const res = $input.item.json || {};
const body = res.body && typeof res.body === 'object' ? res.body : res;
const advanced = body.advanced || [];
const lines = [
  `Marketing advance: ${body.count || 0} enrollment(s)`,
  `mode=${body.mode} allow_send=${body.allow_send}`,
  ...advanced.slice(0, 5).map((a) => `${a.email}: step=${a.step} status=${a.status} send=${a.send_status}`),
];
return {
  ...body,
  slack_text: lines.join('\n'),
  should_alert_slack: false,
  first: advanced[0] || null,
};
"""

VERIFY_SLACK_SIG_JS = r"""
const crypto = require('crypto');

const item = $input.item;
const json = item.json || {};
const headers = json.headers || {};
const body = json.body ?? json;
const signingSecret = ($env.SLACK_SIGNING_SECRET || '').trim();
const skipTimestampCheck = String($env.SLACK_SKIP_TIMESTAMP_CHECK || '').toLowerCase() === 'true';
const maxAgeSeconds = parseInt($env.SLACK_SIGNATURE_MAX_AGE_SECONDS || '300', 10);

const signatureHeader =
  headers['x-slack-signature'] || headers['X-Slack-Signature'] || '';
const timestampHeader =
  headers['x-slack-request-timestamp'] || headers['X-Slack-Request-Timestamp'] || '';

function readRawBody() {
  if (json.rawBody) return { rawBody: json.rawBody, raw_body_source: 'json.rawBody' };

  const binary = item.binary?.data;
  if (binary?.data) {
    return {
      rawBody: Buffer.from(binary.data, binary.encoding || 'base64').toString('utf8'),
      raw_body_source: 'binary.data',
    };
  }

  if (typeof body === 'string') {
    return { rawBody: body, raw_body_source: 'body_string' };
  }

  // Slack interactivity is application/x-www-form-urlencoded: payload=<json>
  if (body && body.payload != null) {
    return {
      rawBody:
        'payload=' +
        encodeURIComponent(
          typeof body.payload === 'string' ? body.payload : JSON.stringify(body.payload),
        ),
      raw_body_source: 'payload_reencoded',
    };
  }

  return { rawBody: JSON.stringify(body || {}), raw_body_source: 'json_stringified' };
}

function computeSignature(secret, timestamp, payload) {
  return 'v0=' + crypto.createHmac('sha256', secret).update(`v0:${timestamp}:${payload}`).digest('hex');
}

function signaturesMatch(signature, expected) {
  try {
    return (
      signature.length === expected.length &&
      crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected))
    );
  } catch {
    return false;
  }
}

const { rawBody, raw_body_source } = readRawBody();
let signature_valid = true;
let verify_reason = 'verification_skipped';
let age_seconds = null;

if (!signingSecret) {
  signature_valid = true;
  verify_reason = 'verification_skipped';
} else if (!signatureHeader || !timestampHeader) {
  signature_valid = false;
  verify_reason = 'missing_signature';
} else {
  const requestTs = parseInt(timestampHeader, 10);
  const now = Math.floor(Date.now() / 1000);
  age_seconds = Number.isFinite(requestTs) ? Math.abs(now - requestTs) : null;
  const timestampFresh =
    skipTimestampCheck ||
    (Number.isFinite(requestTs) && age_seconds <= (Number.isFinite(maxAgeSeconds) ? maxAgeSeconds : 300));
  const expected = computeSignature(signingSecret, timestampHeader, rawBody);
  const signatureMatch = signaturesMatch(signatureHeader, expected);
  if (!timestampFresh) {
    signature_valid = false;
    verify_reason = signatureMatch ? 'timestamp_expired' : 'timestamp_expired_invalid_signature';
  } else {
    signature_valid = signatureMatch;
    verify_reason = signatureMatch ? 'ok' : 'invalid_signature';
  }
}

return {
  ...json,
  headers,
  body,
  rawBody,
  raw_body_source,
  signature_valid,
  verify_reason,
  age_seconds,
};
"""

PARSE_SLACK_ACTION_JS = r"""
const item = $input.item.json || {};
const body = item.body || {};
let payload = {};
try {
  if (body.payload) {
    payload = typeof body.payload === 'string' ? JSON.parse(body.payload) : body.payload;
  } else {
    const raw = item.rawBody || '';
    const params = new URLSearchParams(
      String(raw).includes('payload=') ? String(raw) : `payload=${raw}`,
    );
    const p = params.get('payload') || '';
    payload = p ? JSON.parse(p) : {};
  }
} catch (e) {
  payload = {};
}
const action = (payload.actions && payload.actions[0]) || {};
let value = {};
try { value = JSON.parse(action.value || '{}'); } catch { value = {}; }
const admins = String($env.SLACK_ADMIN_USERS || '').split(',').map(s => s.trim()).filter(Boolean);
const userId = payload.user?.id || '';
const authorized = admins.length === 0 || admins.includes(userId);
return {
  signature_valid: item.signature_valid !== false,
  authorized,
  action_id: action.action_id || '',
  recommendation_id: value.recommendation_id || '',
  sku: value.sku || '',
  action: value.action || (String(action.action_id || '').includes('reject') ? 'reject' : 'approve'),
  actor: payload.user?.username || payload.user?.name || userId,
  channel_id: payload.channel?.id || '',
  message_ts: payload.message?.ts || payload.container?.message_ts || '',
  response_url: payload.response_url || '',
  correlation_id: require('crypto').randomUUID(),
  verify_reason: item.verify_reason || '',
};
"""

FLATTEN_PRICING_ACTION_JS = r"""
const prep = $('Parse Slack Action').item.json;
const res = $input.item.json || {};
const body = res.body && typeof res.body === 'object' ? res.body : res;
const status = body.status || 'unknown';
const sku = body.sku || prep.sku || 'n/a';
const wb = body.writeback_status || 'n/a';
const idem = body.idempotent === true;
const note = body.message
  ? `\nNote: ${body.message}`
  : (idem ? '\nNote: already decided (same recommendation reused)' : '');
const title = idem ? `Pricing ${prep.action} (idempotent)` : `Pricing ${prep.action}`;
const slack_text = `${title}: ${sku} → ${status} (writeback=${wb})`;
const blocks = [
  {
    type: 'section',
    text: {
      type: 'mrkdwn',
      text: `*${title}*\nSKU: ${sku}\nStatus: *${status}*\nWriteback: ${wb}\nBy: ${prep.actor || 'n/a'}${note}`,
    },
  },
];
// Prefer response_url (hooks.slack.com) over chat.update — avoids OAuth/proxy flakes on Update.
const slack_response_body = {
  replace_original: true,
  text: slack_text,
  blocks,
};
return {
  ...prep,
  ...body,
  sku,
  slack_text,
  slack_blocks: { blocks },
  slack_response_body,
};
"""

HANDLE_SIDECAR_ACTION_ERROR_JS = (
    error_message_prelude("Sidecar pricing action failed")
    + r"""
const prep = $('Parse Slack Action').first()?.json || {};
const slack_text = `Pricing ${prep.action || 'action'} failed for ${prep.sku || prep.recommendation_id || 'n/a'}: ${errorMessage}`;
const blocks = [
  {
    type: 'section',
    text: {
      type: 'mrkdwn',
      text: `*Pricing action failed*\nSKU: ${prep.sku || 'n/a'}\nAction: ${prep.action || 'n/a'}\nError: ${errorMessage}\nBy: ${prep.actor || 'n/a'}`,
    },
  },
];
return {
  ...prep,
  ok: false,
  stage: 'sidecar_pricing_action_failed',
  error_message: errorMessage,
  slack_text,
  slack_response_body: { replace_original: true, text: slack_text, blocks },
  _metadata: {
    processing_stage: 'slack_action_sidecar_error',
    severity: 'high',
    error_message: errorMessage,
    correlation_id: prep.correlation_id || '',
  },
};
"""
)

HANDLE_NOTIFY_FAIL_JS = (
    error_message_prelude("Slack response_url update failed")
    + r"""
let ctx = {};
try { ctx = $('Flatten Pricing Action').first()?.json || {}; } catch (_) {}
if (!ctx.response_url) {
  try { ctx = { ...($('Parse Slack Action').first()?.json || {}), ...ctx }; } catch (_) {}
}
const sku = ctx.sku || 'n/a';
const status = ctx.status || 'unknown';
const slack_text =
  `Pricing update for ${sku} may have applied (status=${status}), but Slack card refresh failed: ${errorMessage}`;
return {
  ...ctx,
  ok: false,
  stage: 'slack_notify_failed',
  notify_error_message: errorMessage,
  slack_text,
  _metadata: {
    processing_stage: 'slack_action_notify_error',
    severity: 'medium',
    error_message: errorMessage,
    correlation_id: ctx.correlation_id || '',
  },
};
"""
)

HANDLE_UNAUTHORIZED_NOTIFY_FAIL_JS = (
    error_message_prelude("Unauthorized Slack response_url failed")
    + r"""
const prep = $('Unauthorized Reply').first()?.json || $('Parse Slack Action').first()?.json || {};
return {
  ...prep,
  ok: false,
  stage: 'unauthorized_notify_failed',
  notify_error_message: errorMessage,
  _metadata: {
    processing_stage: 'slack_action_unauthorized_notify_error',
    severity: 'low',
    error_message: errorMessage,
    correlation_id: prep.correlation_id || '',
  },
};
"""
)

HANDLE_FAILURE_NOTIFY_FAIL_JS = (
    error_message_prelude("Failure response_url post failed")
    + r"""
const prep = $('Handle Sidecar Action Error').first()?.json || $('Parse Slack Action').first()?.json || {};
return {
  ...prep,
  ok: false,
  stage: 'failure_notify_failed',
  notify_error_message: errorMessage,
  slack_text: prep.slack_text || `Pricing action failed: ${prep.error_message || errorMessage}`,
  _metadata: {
    processing_stage: 'slack_action_failure_notify_error',
    severity: 'high',
    error_message: errorMessage,
    correlation_id: prep.correlation_id || '',
  },
};
"""
)

UNAUTHORIZED_SLACK_JS = r"""
const prep = $input.item.json || {};
const slack_text = `Unauthorized pricing action by ${prep.actor || 'unknown'}`;
const blocks = [
  { type: 'section', text: { type: 'mrkdwn', text: `*Unauthorized*\nYou are not in SLACK_ADMIN_USERS.\nActor: ${prep.actor || 'n/a'}` } },
];
return {
  ...prep,
  slack_text,
  slack_response_body: { replace_original: true, text: slack_text, blocks },
};
"""


def build_competitor_price_crawl() -> None:
    nodes = [
        cron_node("Competitor Crawl Cron", [0, 0]),
        http_get_url("Load Competitor Targets", [220, 0], f"{SIDECAR}/competitors/targets"),
        code_node(
            "Handle Targets HTTP Error",
            error_message_prelude("Load competitor targets failed")
            + "\nreturn { ok: false, targets_error_message: errorMessage, _metadata: { processing_stage: 'competitor_targets_error', severity: 'medium', error_message: errorMessage } };\n",
            [220, 160],
        ),
        code_node("Expand Targets", LOAD_TARGETS_JS, [440, 0], mode=BATCH_CODE_MODE),
        http_get_url("Fetch Competitor Page", [660, 0], "={{ $json.url }}"),
        code_node("Prepare Parse Body", PREPARE_PARSE_JS, [880, 0]),
        http_json_post(
            "Sidecar Competitor Parse",
            [1100, 0],
            f"{SIDECAR}/competitors/parse",
            "={{ JSON.stringify({ store_id: $json.store_id, url: $json.url, raw_content: $json.raw_content, sku: $json.sku, source_name: $json.source_name, correlation_id: $json.correlation_id }) }}",
            notes="LLM/regex parse → price_snapshots",
        ),
        code_node(
            "Handle Crawl HTTP Error",
            error_message_prelude("Competitor crawl/parse failed")
            + "\nreturn { ok: false, crawl_error_message: errorMessage };\n",
            [1100, 200],
        ),
        noop("Crawl Done", [1320, 0]),
    ]
    conn: dict = {}
    connect(conn, "Competitor Crawl Cron", "Load Competitor Targets")
    connect(conn, "Load Competitor Targets", "Expand Targets")
    connect_error(conn, "Load Competitor Targets", "Handle Targets HTTP Error")
    connect(conn, "Handle Targets HTTP Error", "Crawl Done")
    connect(conn, "Expand Targets", "Fetch Competitor Page")
    connect_error(conn, "Fetch Competitor Page", "Prepare Parse Body")
    connect(conn, "Fetch Competitor Page", "Prepare Parse Body")
    connect(conn, "Prepare Parse Body", "Sidecar Competitor Parse")
    connect_error(conn, "Sidecar Competitor Parse", "Handle Crawl HTTP Error")
    connect(conn, "Sidecar Competitor Parse", "Crawl Done")
    connect(conn, "Handle Crawl HTTP Error", "Crawl Done")
    save_workflow("Ecom Competitor Price Crawl", nodes, conn)


def build_pricing_engine() -> None:
    nodes = [
        cron_node("Pricing Engine Cron", [0, 0]),
        execute_trigger(
            "When Executed by Another Workflow",
            [0, 160],
            [
                {"name": "store_id"},
                {"name": "sku"},
                {"name": "current_price", "type": "number"},
                {"name": "cost", "type": "number"},
                {"name": "correlation_id"},
            ],
        ),
        code_node("Cron Pricing Seed", PRICING_SEED_JS, [220, 0], mode=BATCH_CODE_MODE),
        code_node(
            "Prepare Pricing Body",
            """
const item = $input.item.json || {};
return {
  store_id: item.store_id || $env.ECOM_DEMO_STORE_ID || '',
  sku: item.sku || 'TEE-BLACK-M',
  current_price: item.current_price == null || item.current_price === '' ? null : Number(item.current_price),
  cost: item.cost == null || item.cost === '' ? null : Number(item.cost),
  correlation_id: item.correlation_id || require('crypto').randomUUID(),
};
""",
            [440, 80],
        ),
        http_json_post(
            "Sidecar Pricing Recommend",
            [660, 80],
            f"{SIDECAR}/pricing/recommend",
            "={{ JSON.stringify({ store_id: $json.store_id, sku: $json.sku, current_price: $json.current_price, cost: $json.cost, correlation_id: $json.correlation_id }) }}",
            notes="Writes pricing_recommendations pending row",
        ),
        code_node(
            "Handle Pricing HTTP Error",
            error_message_prelude("Pricing recommend failed")
            + "\nconst prep = $('Prepare Pricing Body').item.json;\nreturn { ...prep, ok: false, should_alert_slack: false, pricing_error_message: errorMessage };\n",
            [660, 260],
        ),
        code_node("Flatten Pricing Result", FLATTEN_PRICING_JS, [880, 80]),
        if_bool_node("Should Slack Pricing?", [1100, 80], "={{ $json.should_alert_slack }}"),
        slack_blocks_node("Slack Pricing Approval", [1320, 0]),
        code_node(
            "Log Slack Pricing Error",
            error_message_prelude("Slack pricing approval post failed")
            + "\nconst prep = $('Flatten Pricing Result').first()?.json || {};\nreturn { ...prep, ok: false, slack_error_message: errorMessage, _metadata: { processing_stage: 'pricing_slack_error', severity: 'medium', error_message: errorMessage } };\n",
            [1320, 200],
        ),
        noop("No Pricing Slack", [1320, 320]),
        noop("Pricing Done", [1540, 80]),
    ]
    conn: dict = {}
    connect(conn, "Pricing Engine Cron", "Cron Pricing Seed")
    connect(conn, "Cron Pricing Seed", "Prepare Pricing Body")
    connect(conn, "When Executed by Another Workflow", "Prepare Pricing Body")
    connect(conn, "Prepare Pricing Body", "Sidecar Pricing Recommend")
    connect_error(conn, "Sidecar Pricing Recommend", "Handle Pricing HTTP Error")
    connect(conn, "Sidecar Pricing Recommend", "Flatten Pricing Result")
    connect(conn, "Handle Pricing HTTP Error", "Flatten Pricing Result")
    connect(conn, "Flatten Pricing Result", "Should Slack Pricing?")
    connect(conn, "Should Slack Pricing?", "Slack Pricing Approval", src_output=0)
    connect(conn, "Should Slack Pricing?", "No Pricing Slack", src_output=1)
    connect(conn, "Slack Pricing Approval", "Pricing Done")
    connect_error(conn, "Slack Pricing Approval", "Log Slack Pricing Error")
    connect(conn, "Log Slack Pricing Error", "Pricing Done")
    connect(conn, "No Pricing Slack", "Pricing Done")
    save_workflow("Ecom Pricing Engine", nodes, conn)


def build_customer_insights() -> None:
    nodes = [
        cron_node("Customer Insights Cron", [0, 0]),
        code_node("Insights Seed", INSIGHTS_SEED_JS, [220, 0], mode=BATCH_CODE_MODE),
        http_json_post(
            "Sidecar RFM",
            [440, 0],
            f"{SIDECAR}/insights/rfm",
            "={{ JSON.stringify({ store_id: $json.store_id, correlation_id: $json.correlation_id }) }}",
        ),
        code_node(
            "Handle RFM HTTP Error",
            error_message_prelude("Insights RFM failed")
            + "\nconst prep = $('Insights Seed').first()?.json || {};\nreturn { ...prep, ok: false, rfm_error_message: errorMessage, _metadata: { processing_stage: 'insights_rfm_error', severity: 'medium', error_message: errorMessage } };\n",
            [440, 160],
        ),
        http_json_post(
            "Sidecar Churn",
            [660, 0],
            f"{SIDECAR}/insights/churn",
            "={{ JSON.stringify({ store_id: $('Insights Seed').item.json.store_id, correlation_id: $('Insights Seed').item.json.correlation_id }) }}",
        ),
        code_node(
            "Handle Churn HTTP Error",
            error_message_prelude("Insights churn failed")
            + "\nconst prep = $('Insights Seed').first()?.json || {};\nreturn { ...prep, ok: false, churn_error_message: errorMessage, _metadata: { processing_stage: 'insights_churn_error', severity: 'medium', error_message: errorMessage } };\n",
            [660, 160],
        ),
        noop("Insights Done", [880, 0]),
    ]
    conn: dict = {}
    connect(conn, "Customer Insights Cron", "Insights Seed")
    connect(conn, "Insights Seed", "Sidecar RFM")
    connect(conn, "Sidecar RFM", "Sidecar Churn")
    connect_error(conn, "Sidecar RFM", "Handle RFM HTTP Error")
    connect(conn, "Handle RFM HTTP Error", "Insights Done")
    connect(conn, "Sidecar Churn", "Insights Done")
    connect_error(conn, "Sidecar Churn", "Handle Churn HTTP Error")
    connect(conn, "Handle Churn HTTP Error", "Insights Done")
    save_workflow("Ecom Customer Insights", nodes, conn)


def build_marketing_orchestrator() -> None:
    nodes = [
        cron_node("Marketing Advance Cron", [0, 0]),
        execute_trigger(
            "When Executed by Another Workflow",
            [0, 180],
            [
                {"name": "store_id"},
                {"name": "email"},
                {"name": "campaign_key"},
                {"name": "campaign_type"},
                {"name": "correlation_id"},
            ],
        ),
        code_node(
            "Route Enroll Or Advance",
            """
const item = $input.item.json || {};
const hasEmail = !!(item.email && String(item.email).trim());
return {
  ...item,
  store_id: item.store_id || $env.ECOM_DEMO_STORE_ID || '',
  campaign_key: item.campaign_key || 'abandon_cart_default',
  campaign_type: item.campaign_type || 'abandon_cart',
  correlation_id: item.correlation_id || require('crypto').randomUUID(),
  do_enroll: hasEmail,
};
""",
            [220, 180],
        ),
        code_node("Cron Advance Seed", MARKETING_ADVANCE_SEED_JS, [220, 0], mode=BATCH_CODE_MODE),
        if_bool_node("Do Enroll?", [440, 180], "={{ $json.do_enroll }}"),
        http_json_post(
            "Sidecar Marketing Enroll",
            [660, 100],
            f"{SIDECAR}/marketing/enroll",
            "={{ JSON.stringify({ store_id: $json.store_id, email: $json.email, campaign_key: $json.campaign_key, campaign_type: $json.campaign_type, correlation_id: $json.correlation_id }) }}",
        ),
        code_node(
            "Handle Marketing Enroll Error",
            error_message_prelude("Marketing enroll failed")
            + "\nconst prep = $('Route Enroll Or Advance').first()?.json || {};\nreturn { ...prep, ok: false, enroll_error_message: errorMessage, first: null, _metadata: { processing_stage: 'marketing_enroll_error', severity: 'medium', error_message: errorMessage } };\n",
            [660, 260],
        ),
        http_json_post(
            "Sidecar Marketing Advance",
            [660, 0],
            f"{SIDECAR}/marketing/advance",
            "={{ JSON.stringify({ store_id: $json.store_id || null, limit: $json.limit || 20, correlation_id: $json.correlation_id }) }}",
        ),
        code_node(
            "Handle Marketing Advance Error",
            error_message_prelude("Marketing advance failed")
            + "\nconst prep = $('Cron Advance Seed').first()?.json || $('Route Enroll Or Advance').first()?.json || {};\nreturn { ...prep, ok: false, advance_error_message: errorMessage, first: null, _metadata: { processing_stage: 'marketing_advance_error', severity: 'medium', error_message: errorMessage } };\n",
            [660, 160],
        ),
        code_node("Flatten Marketing", FLATTEN_MARKETING_JS, [880, 0]),
        if_bool_node("Should Send Email?", [1100, 0], "={{ $json.first && $json.first.should_send_email }}"),
        code_node(
            "Prepare Resend Payload",
            """
const first = $json.first || {};
return {
  ...($json),
  to: first.email,
  subject: first.subject,
  text: `${first.body}\\n\\n${first.cta || ''}`,
  send_status: first.send_status,
};
""",
            [1320, -80],
        ),
        # Resend Mail API — gated; test path never reaches with should_send_email false.
        # Free tier: from onboarding@resend.dev can only send to your Resend account email until a domain is verified.
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.resend.com/emails",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Authorization", "value": "=Bearer {{ $env.RESEND_API_KEY }}"},
                        {"name": "Content-Type", "value": "application/json"},
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ from: $env.RESEND_FROM_EMAIL || 'Ecom Demo <onboarding@resend.dev>', to: [$json.to], subject: $json.subject, text: $json.text }) }}",
                "options": {"timeout": 30000},
            },
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.4,
            "position": [1540, -80],
            "id": nid("Resend Send"),
            "name": "Resend Send",
            **_retry_settings(),
            "onError": "continueErrorOutput",
            "notes": "Only runs when allow_send; set RESEND_API_KEY + RESEND_FROM_EMAIL in platform-n8n/.env.",
            "notesInFlow": True,
        },
        code_node(
            "Handle Resend Error",
            error_message_prelude("Resend send failed")
            + "\nconst prep = $('Prepare Resend Payload').first()?.json || {};\nreturn { ...prep, ok: false, resend_error_message: errorMessage, _metadata: { processing_stage: 'marketing_resend_error', severity: 'high', error_message: errorMessage } };\n",
            [1540, 40],
        ),
        noop("Skip Send (test)", [1320, 120]),
        noop("Marketing Done", [1760, 0]),
    ]
    conn: dict = {}
    connect(conn, "Marketing Advance Cron", "Cron Advance Seed")
    connect(conn, "Cron Advance Seed", "Sidecar Marketing Advance")
    connect(conn, "When Executed by Another Workflow", "Route Enroll Or Advance")
    connect(conn, "Route Enroll Or Advance", "Do Enroll?")
    connect(conn, "Do Enroll?", "Sidecar Marketing Enroll", src_output=0)
    connect(conn, "Do Enroll?", "Sidecar Marketing Advance", src_output=1)
    connect(conn, "Sidecar Marketing Enroll", "Flatten Marketing")
    connect_error(conn, "Sidecar Marketing Enroll", "Handle Marketing Enroll Error")
    connect(conn, "Handle Marketing Enroll Error", "Marketing Done")
    connect(conn, "Sidecar Marketing Advance", "Flatten Marketing")
    connect_error(conn, "Sidecar Marketing Advance", "Handle Marketing Advance Error")
    connect(conn, "Handle Marketing Advance Error", "Marketing Done")
    connect(conn, "Flatten Marketing", "Should Send Email?")
    connect(conn, "Should Send Email?", "Prepare Resend Payload", src_output=0)
    connect(conn, "Should Send Email?", "Skip Send (test)", src_output=1)
    connect(conn, "Prepare Resend Payload", "Resend Send")
    connect(conn, "Resend Send", "Marketing Done")
    connect_error(conn, "Resend Send", "Handle Resend Error")
    connect(conn, "Handle Resend Error", "Marketing Done")
    connect(conn, "Skip Send (test)", "Marketing Done")
    save_workflow("Ecom Marketing Orchestrator", nodes, conn)


def build_slack_actions() -> None:
    nodes = [
        webhook_node("Slack Interactivity", [0, 0], "ecom-slack-interactions"),
        code_node("Verify Slack Signature", VERIFY_SLACK_SIG_JS, [220, 0]),
        if_bool_node("Signature OK?", [440, 0], "={{ $json.signature_valid }}"),
        respond_to_webhook_node(
            "Respond 401",
            [660, -160],
            response_code=401,
            response_body='={{ { "ok": false, "error": "invalid_signature" } }}',
        ),
        respond_to_webhook_node(
            "Ack Slack",
            [660, 0],
            response_code=200,
            response_body='={{ { "ok": true } }}',
        ),
        code_node("Parse Slack Action", PARSE_SLACK_ACTION_JS, [880, 0]),
        if_bool_node("Authorized Admin?", [1100, 0], "={{ $json.authorized }}"),
        code_node("Unauthorized Reply", UNAUTHORIZED_SLACK_JS, [1320, -160]),
        http_json_post(
            "Sidecar Pricing Action",
            [1320, 0],
            f"{SIDECAR}/pricing/action",
            "={{ JSON.stringify({ recommendation_id: $json.recommendation_id, action: $json.action, actor: $json.actor, correlation_id: $json.correlation_id }) }}",
            notes="Approve/reject → PG status; writeback gated",
        ),
        code_node(
            "Handle Sidecar Action Error",
            HANDLE_SIDECAR_ACTION_ERROR_JS,
            [1540, 200],
            notes="Business failed after Ack — tell user via response_url",
        ),
        code_node("Flatten Pricing Action", FLATTEN_PRICING_ACTION_JS, [1540, 0]),
        # Prefer Slack response_url over chat.update (OAuth Update was failing with connection closed).
        http_json_post(
            "Post Slack response_url",
            [1760, 0],
            "={{ $json.response_url }}",
            "={{ $json.slack_response_body }}",
            correlation=False,
            notes="replace_original via interaction response_url",
        ),
        http_json_post(
            "Post Failure response_url",
            [1760, 200],
            "={{ $json.response_url }}",
            "={{ $json.slack_response_body }}",
            correlation=False,
            notes="Card error state when sidecar fails",
        ),
        http_json_post(
            "Post Unauthorized response_url",
            [1540, -160],
            "={{ $json.response_url }}",
            "={{ $json.slack_response_body }}",
            correlation=False,
        ),
        code_node(
            "Handle Notify Fail",
            HANDLE_NOTIFY_FAIL_JS,
            [1980, 80],
            notes="Business may have succeeded; card refresh failed → channel fallback",
        ),
        code_node(
            "Handle Failure Notify Fail",
            HANDLE_FAILURE_NOTIFY_FAIL_JS,
            [1980, 200],
            notes="Sidecar failed AND response_url failed → channel fallback",
        ),
        code_node(
            "Handle Unauthorized Notify Fail",
            HANDLE_UNAUTHORIZED_NOTIFY_FAIL_JS,
            [1760, -160],
        ),
        slack_node(
            "Slack Fallback Notify",
            [2200, 80],
            "={{ $json.slack_text }}",
        ),
        slack_node(
            "Slack Fallback Failure",
            [2200, 200],
            "={{ $json.slack_text }}",
        ),
        noop("Slack Actions End", [2420, 0]),
    ]
    conn: dict = {}
    connect(conn, "Slack Interactivity", "Verify Slack Signature")
    connect(conn, "Verify Slack Signature", "Signature OK?")
    connect(conn, "Signature OK?", "Ack Slack", src_output=0)
    connect(conn, "Signature OK?", "Respond 401", src_output=1)
    connect(conn, "Ack Slack", "Parse Slack Action")
    connect(conn, "Parse Slack Action", "Authorized Admin?")
    connect(conn, "Authorized Admin?", "Sidecar Pricing Action", src_output=0)
    connect(conn, "Authorized Admin?", "Unauthorized Reply", src_output=1)
    connect(conn, "Sidecar Pricing Action", "Flatten Pricing Action")
    connect_error(conn, "Sidecar Pricing Action", "Handle Sidecar Action Error")
    connect(conn, "Flatten Pricing Action", "Post Slack response_url")
    connect(conn, "Post Slack response_url", "Slack Actions End")
    connect_error(conn, "Post Slack response_url", "Handle Notify Fail")
    connect(conn, "Handle Notify Fail", "Slack Fallback Notify")
    connect(conn, "Slack Fallback Notify", "Slack Actions End")
    connect_error(conn, "Slack Fallback Notify", "Slack Actions End")
    connect(conn, "Handle Sidecar Action Error", "Post Failure response_url")
    connect(conn, "Post Failure response_url", "Slack Actions End")
    connect_error(conn, "Post Failure response_url", "Handle Failure Notify Fail")
    connect(conn, "Handle Failure Notify Fail", "Slack Fallback Failure")
    connect(conn, "Slack Fallback Failure", "Slack Actions End")
    connect_error(conn, "Slack Fallback Failure", "Slack Actions End")
    connect(conn, "Unauthorized Reply", "Post Unauthorized response_url")
    connect(conn, "Post Unauthorized response_url", "Slack Actions End")
    connect_error(conn, "Post Unauthorized response_url", "Handle Unauthorized Notify Fail")
    connect(conn, "Handle Unauthorized Notify Fail", "Slack Actions End")
    save_workflow("Ecom Slack Actions", nodes, conn)


def build_all_p2() -> None:
    build_competitor_price_crawl()
    build_pricing_engine()
    build_customer_insights()
    build_marketing_orchestrator()
    build_slack_actions()
    print("P2 workflows generated.")
