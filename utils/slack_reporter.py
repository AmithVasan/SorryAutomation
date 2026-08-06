import os
import re
import requests
import subprocess

from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import ADB_PATH
import utils.event_tracker as event_tracker


PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL")

ENABLE_SLACK = True
ENABLE_HTML = True


# ---------------------------------------------------
# DEVICE INFO
# ---------------------------------------------------
def get_device_info(device_id):

    def adb(cmd):
        try:
            return subprocess.check_output(
                f'{ADB_PATH} -s {device_id} shell {cmd}',
                shell=True
            ).decode("utf-8").strip()

        except Exception:
            return "Unknown"

    manufacturer = adb("getprop ro.product.manufacturer")
    model = adb("getprop ro.product.model")

    return {
        "device_id": device_id,
        "device_name": f"{manufacturer} {model}",
        "device_brand": manufacturer,
        "android_version": adb("getprop ro.build.version.release"),
        "resolution": adb("wm size").replace("Physical size:", "").strip(),
        "device_type": (
            "Emulator"
            if "emulator" in device_id.lower()
            else "Real Device"
        ),
        "platform": "Android"
    }


# ---------------------------------------------------
# HTML REPORT
# ---------------------------------------------------
def generate_html_report(
    results,
    total_duration,
    apk_name="Unknown",
    run_type="complete",
    device_info=None,
    start_time=None,
    end_time=None
):

    total = len(results)

    passed = len([
        r for r in results
        if r["status"] == "PASS"
    ])

    failed = len([
        r for r in results
        if r["status"] == "FAIL"
    ])

    final_status = "PASSED" if failed == 0 else "FAILED"

    status_color = "#22c55e" if failed == 0 else "#ef4444"

    rows = ""
    details_blocks = ""

    for result in results:

        color = (
            "#22c55e"
            if result["status"] == "PASS"
            else "#ef4444"
        )

        rows += f"""
        <tr>
            <td>{result['name']}</td>
            <td style="color:{color};font-weight:bold;text-align:center;">
                {result['status']}
            </td>
        </tr>
        """

        steps_html = ""
        safe_name = re.sub(r'[^A-Za-z0-9]+', '_', result['name']).strip('_') or 'test'

        for _si, step in enumerate(result.get("steps", []), 1):

            if isinstance(step, dict):

                step_status = step.get("status", "INFO")
                step_text = step.get("step", "")
                timestamp = step.get("timestamp", "")
                shot = step.get("screenshot", "")

                step_color = {
                    "PASS": "#22c55e",
                    "FAIL": "#ef4444",
                    "WARN": "#f59e0b",
                    "INFO": "#38bdf8"
                }.get(step_status, "#38bdf8")

                shot_name = f"{safe_name}_{_si:03d}"
                shot_html = (
                    f'<img class="step-shot" data-name="{shot_name}" src="{shot}" '
                    f'loading="lazy" alt="step screenshot" '
                    f'onclick="this.classList.toggle(\'zoom\')">'
                    if shot else ""
                )

                steps_html += f"""
                <div class="step-card">
                    <div class="step-header">
                        <span class="badge"
                              style="background:{step_color}">
                              {step_status}
                        </span>

                        <span class="timestamp">
                            {timestamp}
                        </span>
                    </div>

                    <div class="step-text">
                        {step_text}
                    </div>
                    {shot_html}
                </div>
                """

            else:

                steps_html += f"""
                <div class="step-card">
                    <div class="step-text">{step}</div>
                </div>
                """

        details_blocks += f"""
        <details class="accordion">
            <summary>
                {result['name']} — {result['status']}
            </summary>

            <div class="details-container">
                {steps_html}
            </div>

        </details>
        """

    # ── Build "What Was Handled" section ────────────────────────────────
    _all_events = event_tracker.get_all()
    handled_html = ""

    if _all_events:
        _groups_html = ""

        for _section, _events in _all_events.items():
            if not _events:
                continue

            _items_html = ""
            for _ev in _events:
                _status = _ev.get("status", "PASS")
                _icon   = "✅" if _status == "PASS" else ("❌" if _status == "FAIL" else "➖")
                _detail = _ev.get("detail", "")
                _detail_span = (
                    f'<span class="handled-detail">({_detail})</span>'
                    if _detail else ""
                )
                _items_html += f"""
                <div class="handled-item">
                    <span class="handled-icon">{_icon}</span>
                    <span class="handled-name">{_ev['name']}{_detail_span}</span>
                </div>"""

            _groups_html += f"""
        <div class="handled-group">
            <div class="handled-group-title">{_section}</div>
            {_items_html}
        </div>"""

        handled_html = f"""
<h2 style="margin-top:35px;">What Was Handled</h2>
<div class="handled-wrapper">
{_groups_html}
</div>"""
    # ────────────────────────────────────────────────────────────────────

    html = f"""
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>Automation Report</title>

<style>

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    padding: 20px;

    background: #020617;

    color: #e2e8f0;

    font-family:
        Inter,
        -apple-system,
        BlinkMacSystemFont,
        sans-serif;
}}

.container {{
    max-width: 1300px;
    margin: auto;
}}

.header {{
    text-align: center;
    margin-bottom: 30px;
}}

.title {{
    font-size: 38px;
    font-weight: 700;
}}

.status {{
    margin-top: 12px;
    font-size: 20px;
    font-weight: bold;
    color: {status_color};
}}

.grid {{
    display: grid;

    grid-template-columns:
        repeat(auto-fit, minmax(220px, 1fr));

    gap: 16px;

    margin-top: 25px;
}}

.card {{
    background: rgba(15, 23, 42, 0.95);

    border: 1px solid rgba(148, 163, 184, 0.15);

    border-radius: 18px;

    padding: 20px;

    backdrop-filter: blur(8px);

    box-shadow:
        0 0 20px rgba(59, 130, 246, 0.08);

    transition: 0.25s ease;
}}

.card:hover {{
    transform: translateY(-3px);
}}

.card h4 {{
    margin: 0 0 10px 0;

    font-size: 13px;

    color: #94a3b8;

    text-transform: uppercase;

    letter-spacing: 1px;
}}

.card p {{
    margin: 0;

    font-size: 20px;

    font-weight: 700;
}}

table {{
    width: 100%;

    border-collapse: collapse;

    margin-top: 20px;

    overflow: hidden;

    border-radius: 16px;
}}

th {{
    background: #1e293b;

    padding: 14px;

    text-align: left;
}}

td {{
    background: #0f172a;

    padding: 14px;
}}

tr:nth-child(even) td {{
    background: #111c30;
}}

.accordion {{
    margin-top: 14px;

    border-radius: 16px;

    overflow: hidden;

    background: #0f172a;

    border: 1px solid rgba(148, 163, 184, 0.12);
}}

summary {{
    cursor: pointer;

    padding: 18px;

    font-size: 16px;

    font-weight: 700;

    background: #111827;
}}

.details-container {{
    padding: 18px;
}}

.step-card {{

    background: rgba(30, 41, 59, 0.95);

    border-radius: 14px;

    padding: 14px;

    margin-bottom: 12px;

    border-left: 4px solid #38bdf8;
}}

.step-header {{
    display: flex;

    justify-content: space-between;

    align-items: center;

    margin-bottom: 8px;
}}

.badge {{
    padding: 4px 10px;

    border-radius: 999px;

    font-size: 11px;

    font-weight: bold;

    color: white;
}}

.timestamp {{
    color: #94a3b8;

    font-size: 12px;
}}

.step-text {{
    font-size: 14px;

    line-height: 1.6;
}}

/* Per-step screenshot thumbnail — click to zoom (no JS needed) */
.step-shot {{
    display: block;
    margin-top: 10px;
    max-width: 200px;
    border-radius: 10px;
    border: 1px solid rgba(148, 163, 184, 0.25);
    cursor: zoom-in;
    transition: max-width 0.2s ease;
}}

.step-shot.zoom {{
    max-width: 100%;
    cursor: zoom-out;
}}

.footer {{
    margin-top: 35px;

    text-align: center;

    color: #64748b;

    font-size: 12px;
}}

/* ── What Was Handled section ───────────────────────────────── */

.handled-wrapper {{
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin-top: 20px;
}}

.handled-group {{
    background: rgba(15, 23, 42, 0.95);
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 18px;
    padding: 20px;
    flex: 1 1 200px;
    min-width: 180px;
    box-shadow: 0 0 20px rgba(59, 130, 246, 0.06);
}}

.handled-group-title {{
    font-size: 11px;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    font-weight: 700;
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}}

.handled-item {{
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 6px 0;
    border-bottom: 1px solid rgba(148, 163, 184, 0.06);
    font-size: 13px;
    line-height: 1.5;
}}

.handled-item:last-child {{
    border-bottom: none;
    padding-bottom: 0;
}}

.handled-icon {{
    flex-shrink: 0;
    font-size: 14px;
    margin-top: 1px;
}}

.handled-name {{
    flex: 1;
    color: #e2e8f0;
}}

.handled-detail {{
    font-size: 11px;
    color: #64748b;
    margin-left: 4px;
    white-space: nowrap;
}}

</style>
</head>

<body>

<div class="container">

<div class="header">

<div class="title">
Sorry! World Automation Report
</div>

<div class="status">
{final_status}
</div>

</div>


<div class="grid">

<div class="card">
<h4>APK</h4>
<p>{apk_name}</p>
</div>

<div class="card">
<h4>Run Type</h4>
<p>{run_type}</p>
</div>

<div class="card">
<h4>Duration</h4>
<p>{total_duration}</p>
</div>

<div class="card">
<h4>Total Tests</h4>
<p>{total}</p>
</div>

<div class="card">
<h4>Passed</h4>
<p>{passed}</p>
</div>

<div class="card">
<h4>Failed</h4>
<p>{failed}</p>
</div>

</div>


<h2>Device Info</h2>

<div class="grid">

<div class="card">
<h4>Device</h4>
<p>{device_info.get("device_name")}</p>
</div>

<div class="card">
<h4>Platform</h4>
<p>{device_info.get("platform")}</p>
</div>

<div class="card">
<h4>OS Version</h4>
<p>{device_info.get("android_version")}</p>
</div>

<div class="card">
<h4>Resolution</h4>
<p>{device_info.get("resolution")}</p>
</div>

<div class="card">
<h4>Device Type</h4>
<p>{device_info.get("device_type")}</p>
</div>

</div>


<h2>Test Summary</h2>

<table>

<tr>
<th>Test Name</th>
<th>Status</th>
</tr>

{rows}

</table>

{handled_html}

<h2 style="margin-top:35px;">Detailed Execution Logs</h2>

{details_blocks}


<div class="footer">

Generated at
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

</div>

</div>
</body>
</html>
"""

    report_path = os.path.join(
        PROJECT_ROOT,
        "automation_report.html"
    )

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ HTML report generated: {report_path}")

    return report_path


# ---------------------------------------------------
# SLACK REPORT
# ---------------------------------------------------
def post_test_report(
    results,
    total_duration="N/A",
    apk_name="Unknown",
    run_type="complete",
    device_id="Unknown",
    start_time=None,
    end_time=None
):

    device_info = get_device_info(device_id)

    total = len(results)

    passed = len([
        r for r in results
        if r["status"] == "PASS"
    ])

    failed = len([
        r for r in results
        if r["status"] == "FAIL"
    ])

    final_status = (
        "PASSED"
        if failed == 0
        else "FAILED"
    )

    report_file = None

    # ---------------------------------------------------
    # GENERATE HTML
    # ---------------------------------------------------

    if ENABLE_HTML:

        report_file = generate_html_report(
            results,
            total_duration,
            apk_name,
            run_type,
            device_info,
            start_time,
            end_time
        )

    # ---------------------------------------------------
    # SLACK SUMMARY
    # ---------------------------------------------------

    if ENABLE_SLACK:

        blocks = [

            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Automation Report — {final_status}"
                }
            },

            {
                "type": "section",
                "fields": [

                    {
                        "type": "mrkdwn",
                        "text": f"*APK:*\n{apk_name}"
                    },

                    {
                        "type": "mrkdwn",
                        "text": f"*Run Type:*\n{run_type}"
                    },

                    {
                        "type": "mrkdwn",
                        "text": f"*Device:*\n{device_info['device_name']}"
                    },

                    {
                        "type": "mrkdwn",
                        "text": f"*OS:*\nAndroid {device_info['android_version']}"
                    },

                    {
                        "type": "mrkdwn",
                        "text": f"*Duration:*\n{total_duration}"
                    },

                    {
                        "type": "mrkdwn",
                        "text": f"*Result:*\n{passed} Passed / {failed} Failed"
                    }
                ]
            },

            {"type": "divider"}
        ]

        for result in results:

            emoji = (
                "✅"
                if result["status"] == "PASS"
                else "❌"
            )

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text":
                        f"{emoji} "
                        f"*{result['name']}* — "
                        f"{result['status']}"
                }
            })

        requests.post(
            SLACK_WEBHOOK_URL,
            json={"blocks": blocks}
        )

        print("✅ Slack summary sent")

    # ---------------------------------------------------
    # UPLOAD HTML
    # ---------------------------------------------------

    if ENABLE_HTML and report_file:

        try:

            client = WebClient(
                token=SLACK_BOT_TOKEN
            )

            client.files_upload_v2(
                channel=SLACK_CHANNEL,
                file=report_file,
                title="Automation HTML Report",
                initial_comment="Detailed automation report attached"
            )

            print("✅ HTML uploaded to Slack")

        except SlackApiError as e:

            print(
                f"❌ HTML upload failed:"
                f" {e.response['error']}"
            )