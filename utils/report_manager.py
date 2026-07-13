from utils.slack_reporter import post_test_report, generate_html_report

# -------------------------------
# TOGGLES (CHANGE HERE ANYTIME)
# -------------------------------
ENABLE_SLACK = True
ENABLE_HTML = True


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

    # -------------------------------
    # HTML REPORT
    # -------------------------------
    if ENABLE_HTML:
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
    if ENABLE_SLACK:
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