from alttester.by import By

def handle_error_display(unity_driver):
    try:
        close_btn = unity_driver.find_object(By.PATH, "/ErrorDisplayScreen/Background/buttons/CloseButton/text", timeout=2)
        if close_btn:
            print("[INFO] ErrorDisplay detected, tapping Close...")
            close_btn.tap()
        else:
            print("[INFO] No ErrorDisplay popup found.")
    except Exception as e:
        print(f"[WARNING] Could not handle ErrorDisplay popup: {e}")
def safe_action(unity_driver, action_fn, *args, **kwargs):
    # Always check before doing anything
    handle_error_display(unity_driver)

    # Perform the intended action
    result = action_fn(unity_driver, *args, **kwargs)

    # Always check again afterwards
    handle_error_display(unity_driver)

    return result