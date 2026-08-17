#!/usr/bin/env python3
"""Generate Ecom P3 n8n workflows: Daily/Weekly Summary + Health Keepalive.

Imports helpers from generate_workflows.py. Call build_all_p3() from main().
"""

from __future__ import annotations

from generate_workflows import (
    BATCH_CODE_MODE,
    SIDECAR,
    code_node,
    connect,
    connect_error,
    error_message_prelude,
    http_json_post,
    if_bool_node,
    noop,
    save_workflow,
    slack_node,
)

PREPARE_DAILY_SUMMARY_JS = r"""
const crypto = require('crypto');
const item = $input.item.json || {};
return {
  period: 'daily',
  store_id: item.store_id || $env.ECOM_DEMO_STORE_ID || null,
  store_key: item.store_key || $env.ECOM_DEMO_STORE_KEY || 'demo-shopify',
  correlation_id: item.correlation_id || crypto.randomUUID(),
};
"""

PREPARE_WEEKLY_SUMMARY_JS = r"""
const crypto = require('crypto');
const item = $input.item.json || {};
return {
  period: 'weekly',
  store_id: item.store_id || $env.ECOM_DEMO_STORE_ID || null,
  store_key: item.store_key || $env.ECOM_DEMO_STORE_KEY || 'demo-shopify',
  correlation_id: item.correlation_id || crypto.randomUUID(),
};
"""

HANDLE_SUMMARY_HTTP_JS = error_message_prelude("Ops summary sidecar failed") + r"""
const prep = $('Prepare Summary Body').item.json;
return {
  ...prep,
  ok: false,
  should_alert_slack: false,
  summary_error_message: errorMessage,
  slack_text: `Ecom summary failed: ${errorMessage}`,
  _metadata: { processing_stage: 'ops_summary_failed', severity: 'high' },
};
"""

FLATTEN_SUMMARY_JS = r"""
const prep = $('Prepare Summary Body').item.json;
const res = $input.item.json || {};
const body = res.body && typeof res.body === 'object' ? res.body : res;
return {
  ...prep,
  ...body,
  correlation_id: body.correlation_id || prep.correlation_id,
  should_alert_slack: body.should_alert_slack === true,
  slack_text: body.slack_text || `Ecom ${prep.period} summary`,
};
"""

PREPARE_KEEPALIVE_JS = r"""
return {
  correlation_id: require('crypto').randomUUID(),
  ping_channels: true,
};
"""

HANDLE_KEEPALIVE_HTTP_JS = error_message_prelude("Keepalive sidecar failed") + r"""
return {
  ok: false,
  should_alert_slack: true,
  keepalive_error_message: errorMessage,
  slack_text: `🚨 Ecom Keepalive HTTP failed: ${errorMessage}`,
  _metadata: { processing_stage: 'keepalive_failed', severity: 'critical' },
};
"""

FLATTEN_KEEPALIVE_JS = r"""
const res = $input.item.json || {};
const body = res.body && typeof res.body === 'object' ? res.body : res;
return {
  ...body,
  should_alert_slack: body.should_alert_slack === true,
  slack_text: body.slack_text || 'Ecom keepalive ok',
};
"""


def _schedule_daily_9am(name: str, position: list[int]) -> dict:
    from generate_workflows import nid

    return {
        "parameters": {"rule": {"interval": [{"field": "days", "triggerAtHour": 9}]}},
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": position,
        "id": nid(name),
        "name": name,
        "notes": "Daily 09:00 UTC ops digest.",
        "notesInFlow": True,
    }


def _schedule_friday_17(name: str, position: list[int]) -> dict:
    from generate_workflows import nid

    return {
        "parameters": {
            "rule": {
                "interval": [{"field": "weeks", "triggerAtDay": [5], "triggerAtHour": 17}],
            }
        },
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": position,
        "id": nid(name),
        "name": name,
        "notes": "Friday 17:00 UTC weekly ops digest.",
        "notesInFlow": True,
    }


def _schedule_keepalive(name: str, position: list[int]) -> dict:
    from generate_workflows import nid

    return {
        "parameters": {
            "rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]},
        },
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": position,
        "id": nid(name),
        "name": name,
        "notes": "Every 15m: sidecar keepalive + optional channel pings.",
        "notesInFlow": True,
    }


def build_daily_summary() -> None:
    nodes = [
        _schedule_daily_9am("Daily 9am", [0, 0]),
        code_node(
            "Prepare Summary Body",
            PREPARE_DAILY_SUMMARY_JS,
            [220, 0],
            notes="period=daily; store from env when unset.",
        ),
        http_json_post(
            "Sidecar Ops Summary",
            [440, 0],
            f"{SIDECAR}/ops/summary",
            "={{ JSON.stringify({ period: $json.period, store_id: $json.store_id || null, store_key: $json.store_key || null, correlation_id: $json.correlation_id }) }}",
            notes="Aggregate orders/returns/pricing/errors for digest.",
        ),
        code_node("Handle Summary HTTP Error", HANDLE_SUMMARY_HTTP_JS, [440, 200]),
        code_node("Flatten Summary Result", FLATTEN_SUMMARY_JS, [660, 0], mode=BATCH_CODE_MODE),
        if_bool_node("Should Send Daily?", [880, 0], "={{ $json.should_alert_slack }}"),
        slack_node("Slack Daily Summary", [1100, -80], "={{ $json.slack_text }}"),
        code_node(
            "Log Slack Daily Error",
            error_message_prelude("Slack daily summary failed")
            + "\nconst prev = $('Flatten Summary Result').item.json;\n"
            + "return { ...prev, slack_failed: true, slack_error_message: errorMessage };\n",
            [1320, 40],
        ),
        noop("Skip Daily Slack", [1100, 160]),
    ]
    conn: dict = {}
    connect(conn, "Daily 9am", "Prepare Summary Body")
    connect(conn, "Prepare Summary Body", "Sidecar Ops Summary")
    connect_error(conn, "Sidecar Ops Summary", "Handle Summary HTTP Error")
    connect(conn, "Sidecar Ops Summary", "Flatten Summary Result")
    connect(conn, "Handle Summary HTTP Error", "Flatten Summary Result")
    connect(conn, "Flatten Summary Result", "Should Send Daily?")
    connect(conn, "Should Send Daily?", "Slack Daily Summary", src_output=0)
    connect(conn, "Should Send Daily?", "Skip Daily Slack", src_output=1)
    connect_error(conn, "Slack Daily Summary", "Log Slack Daily Error")
    save_workflow("Ecom Daily Summary", nodes, conn)


def build_weekly_summary() -> None:
    nodes = [
        _schedule_friday_17("Friday 5pm", [0, 0]),
        code_node(
            "Prepare Summary Body",
            PREPARE_WEEKLY_SUMMARY_JS,
            [220, 0],
            notes="period=weekly; store from env when unset.",
        ),
        http_json_post(
            "Sidecar Ops Summary",
            [440, 0],
            f"{SIDECAR}/ops/summary",
            "={{ JSON.stringify({ period: $json.period, store_id: $json.store_id || null, store_key: $json.store_key || null, correlation_id: $json.correlation_id }) }}",
            notes="Weekly window (7d) ops digest.",
        ),
        code_node("Handle Summary HTTP Error", HANDLE_SUMMARY_HTTP_JS, [440, 200]),
        code_node("Flatten Summary Result", FLATTEN_SUMMARY_JS, [660, 0], mode=BATCH_CODE_MODE),
        if_bool_node("Should Send Weekly?", [880, 0], "={{ $json.should_alert_slack }}"),
        slack_node("Slack Weekly Summary", [1100, -80], "={{ $json.slack_text }}"),
        code_node(
            "Log Slack Weekly Error",
            error_message_prelude("Slack weekly summary failed")
            + "\nconst prev = $('Flatten Summary Result').item.json;\n"
            + "return { ...prev, slack_failed: true, slack_error_message: errorMessage };\n",
            [1320, 40],
        ),
        noop("Skip Weekly Slack", [1100, 160]),
    ]
    conn: dict = {}
    connect(conn, "Friday 5pm", "Prepare Summary Body")
    connect(conn, "Prepare Summary Body", "Sidecar Ops Summary")
    connect_error(conn, "Sidecar Ops Summary", "Handle Summary HTTP Error")
    connect(conn, "Sidecar Ops Summary", "Flatten Summary Result")
    connect(conn, "Handle Summary HTTP Error", "Flatten Summary Result")
    connect(conn, "Flatten Summary Result", "Should Send Weekly?")
    connect(conn, "Should Send Weekly?", "Slack Weekly Summary", src_output=0)
    connect(conn, "Should Send Weekly?", "Skip Weekly Slack", src_output=1)
    connect_error(conn, "Slack Weekly Summary", "Log Slack Weekly Error")
    save_workflow("Ecom Weekly Summary", nodes, conn)


def build_health_keepalive() -> None:
    nodes = [
        _schedule_keepalive("Keepalive Cron", [0, 0]),
        code_node("Prepare Keepalive Body", PREPARE_KEEPALIVE_JS, [220, 0]),
        http_json_post(
            "Sidecar Keepalive",
            [440, 0],
            f"{SIDECAR}/ops/keepalive",
            "={{ JSON.stringify({ correlation_id: $json.correlation_id, ping_channels: $json.ping_channels }) }}",
            notes="PG ping + optional Woo/Shopify Admin light ping.",
        ),
        code_node("Handle Keepalive HTTP Error", HANDLE_KEEPALIVE_HTTP_JS, [440, 200]),
        code_node("Flatten Keepalive Result", FLATTEN_KEEPALIVE_JS, [660, 0]),
        if_bool_node("Should Alert Keepalive?", [880, 0], "={{ $json.should_alert_slack }}"),
        slack_node("Slack Keepalive Alert", [1100, -80], "={{ $json.slack_text }}"),
        code_node(
            "Log Slack Keepalive Error",
            error_message_prelude("Slack keepalive alert failed")
            + "\nconst prev = $('Flatten Keepalive Result').item.json;\n"
            + "return { ...prev, slack_failed: true, slack_error_message: errorMessage };\n",
            [1320, 40],
        ),
        noop("Keepalive Healthy", [1100, 160]),
    ]
    conn: dict = {}
    connect(conn, "Keepalive Cron", "Prepare Keepalive Body")
    connect(conn, "Prepare Keepalive Body", "Sidecar Keepalive")
    connect_error(conn, "Sidecar Keepalive", "Handle Keepalive HTTP Error")
    connect(conn, "Sidecar Keepalive", "Flatten Keepalive Result")
    connect(conn, "Handle Keepalive HTTP Error", "Flatten Keepalive Result")
    connect(conn, "Flatten Keepalive Result", "Should Alert Keepalive?")
    connect(conn, "Should Alert Keepalive?", "Slack Keepalive Alert", src_output=0)
    connect(conn, "Should Alert Keepalive?", "Keepalive Healthy", src_output=1)
    connect_error(conn, "Slack Keepalive Alert", "Log Slack Keepalive Error")
    save_workflow("Ecom Health Keepalive", nodes, conn)


def build_all_p3() -> None:
    build_daily_summary()
    build_weekly_summary()
    build_health_keepalive()
    print("P3 workflows generated.")
