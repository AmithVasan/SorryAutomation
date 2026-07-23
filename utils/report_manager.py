import os
from utils.slack_reporter import post_test_report, generate_html_report

# -------------------------------
# TOGGLES (CHANGE HERE ANYTIME)
# -------------------------------
# These module defaults are the manual switch.  They can be overridden
# per-run via env vars (SAT_ENABLE_SLACK / SAT_ENABLE_HTML) — this is how the
# web GUI passes its Slack / HTML checkboxes through to a run without editing
# code.  When the env var is absent, the module default below is used, so the
# interactive/Eclipse flow behaves exactly as before.
ENABLE_SLACK = True
ENABLE_HTML = True


def _flag(env_name, default):
    """Resolve a boolean toggle: env var wins if set, else the module default."""
    v = os.getenv(env_name)
    if v is None:
        return default
    return v.strip().lower() not in ("0", "false", "off", "no", "")


def send_reports(
    results,
    total_duration,
    apk_name,
    run_type,
    device_id,
    device_info,
    start_time,
    end_time
):
    """
    Controls Slack + HTML reporting
    """

    report_file = None

    enable_html = _flag("SAT_ENABLE_HTML", ENABLE_HTML)
    enable_slack = _flag("SAT_ENABLE_SLACK", ENABLE_SLACK)

    # -------------------------------
    # HTML REPORT
    # -------------------------------
    if enable_html:
        try:
            report_file = generate_html_report(
                results=results,
                total_duration=total_duration,
                apk_name=apk_name,
                run_type=run_type,
                device_info=device_info,
                start_time=start_time,
                end_time=end_time
            )
            print("✅ HTML report generated")
        except Exception as e:
            print(f"❌ HTML generation failed: {e}")

    # -------------------------------
    # SLACK REPORT
    # -------------------------------
    if enable_slack:
        try:
            post_test_report(
                results=results,
                total_duration=total_duration,
                apk_name=apk_name,
                run_type=run_type,
                device_id=device_id,
                start_time=start_time,
                end_time=end_time
            )
            print("✅ Slack report sent")
        except Exception as e:
            print(f"❌ Slack failed: {e}")

    return report_file