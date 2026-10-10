import sys
import platform
from pywinauto.application import Application
from pywinauto import Desktop

# --- FIX 1: Corrected Import Locations ---
# These are the actual modules where the exceptions live.
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError

def get_windows_version_info():
    """
    Uses the platform module to replicate the NVDA addon's version check.
    Returns: (is_win11, is_win11_22h2_or_later)
    """
    try:
        ver = platform.win32_ver()
        release_str = ver[0]
        build_str = ver[1].split('.')[2] # Gets '22621'
        
        build = int(build_str)
        
        is_win11 = (release_str == '11' or build >= 22000)
        is_win11_22h2_or_later = (is_win11 and build >= 22621)
        
        return is_win11, is_win11_22h2_or_later
    except Exception as e:
        print(f"Warning: Could not parse Windows version. Defaulting to legacy. Error: {e}")
        return False, False

def get_icons_from_container(container):
    """
    Given a pywinauto container, iterates its children to find
    icon buttons and returns their names (tooltips).
    """
    try:
        # --- FIX 2: Removed Redundant .wait() ---
        # The 'container' is already a found UIAWrapper element,
        # so we can't (and don't need to) call .wait() on it.
        
        icons = [
            child.window_text() 
            for child in container.children(control_type="Button")
        ]
        return icons
    except Exception as e:
        print(f"Error enumerating children from container: {e}")
        return []

def get_system_tray_icons_nvda_method():
    """
    Finds system tray icons using the branching logic
    from the NVDA 'sysTryList' addon.
    """
    print("--- Starting SysTray Enumeration (NVDA-based Logic) ---")
    
    is_win11, is_win11_22h2 = get_windows_version_info()
    print(f"OS Detected: Win11={is_win11}, 22H2+={is_win11_22h2}")
    
    all_icons = []
    
    try:
        print("Connecting to explorer.exe...")
        app = Application(backend="uia").connect(path="explorer.exe")
        print("Connected.")
        
        taskbar = app.window(class_name="Shell_TrayWnd")
        
        icon_container = None
        
        if is_win11_22h2:
            print("Trying Win 11 (22H2+) path: 'Windows.UI.Input.InputSite.WindowClass'")
            try:
                icon_container = taskbar.child_window(
                    class_name="Windows.UI.Input.InputSite.WindowClass"
                ).wait('visible', timeout=5)
            except (ElementNotFoundError, TimeoutError) as e:
                print(f"22H2 path failed: {e}. Falling back.")
        
        if icon_container is None and is_win11:
            print("Trying Win 11 (pre-22H2) path: 'Windows.UI.Composition.DesktopWindowContentBridge'")
            try:
                bridge_container = taskbar.child_window(
                    class_name="Windows.UI.Composition.DesktopWindowContentBridge"
                ).wait('visible', timeout=5)
                
                if bridge_container.children():
                    icon_container = bridge_container.children()[0]
                else:
                    print("ContentBridge was found but has no children.")
            except (ElementNotFoundError, TimeoutError) as e:
                print(f"Win11-pre22H2 path failed: {e}. Falling back.")
        
        if icon_container is None:
            print("Trying legacy (Win 10 / Fallback) path: 'ToolbarWindow32'")
            try:
                icon_container = taskbar.child_window(
                    class_name="TrayNotifyWnd"
                ).child_window(
                    class_name="SysPager"
                ).child_window(
                    class_name="ToolbarWindow32"
                ).wait('visible', timeout=5)
            except (ElementNotFoundError, TimeoutError) as e:
                print(f"Legacy path failed: {e}")

        # --- NOW GET THE ICONS ---
        if icon_container:
            print(f"Successfully found icon container: {icon_container.class_name()}")
            all_icons = get_icons_from_container(icon_container)
        else:
            print("CRITICAL: No icon container was found using any known method.")
            
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    # --- Step 5: Consolidate and display results ---
    print("\n" + "---" * 10)
    print("--- Complete List of System Tray Icons ---")
    
    all_icons_filtered = list(filter(None, all_icons))
    all_icons_final = sorted(list(set(all_icons_filtered)))

    if all_icons_final:
        for i, icon_name in enumerate(all_icons_final):
            print(f"{i + 1}: {icon_name}")
    else:
        print("No icons were found.")
    print("---" * 10 + "\n")

if __name__ == "__main__":
    print("This script requires 'pywinauto': pip install pywinauto\n")
    get_system_tray_icons_nvda_method()