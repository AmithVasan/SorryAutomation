def handle_permissions(driver):
    for btn in [
        "com.android.permissioncontroller:id/permission_allow_button",
        "com.android.permissioncontroller:id/permission_allow_foreground_only_button",
    ]:
        try:
            driver.find_element("id", btn).click()
            return True
        except:
            pass
    return False