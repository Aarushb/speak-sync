import sys
import platform
from pywinauto.application import Application
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError

# A list of keywords to identify the cloud apps we want to monitor.
# We use lowercase to make matching case-insensitive.
CLOUD_KEYWORDS = [
    'dropbox',
    'onedrive',
    'google drive',
    'megasync',
    'icloud',
]

def _get_windows_version_info():
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
        print(f"Warning: Could not parse Windows version. Defaulting to legacy. Error: {e}", file=sys.stderr)
        return False, False

def _get_icons_from_container(container):
    """
    Given a pywinauto container, iterates its children to find
    icon buttons and returns their names (tooltips).
    """
    try:
        # The 'container' is already a found UIAWrapper element.
        icons = [
            child.window_text() 
            for child in container.children(control_type="Button")
        ]
        return icons
    except Exception as e:
        print(f"Error enumerating children from container: {e}", file=sys.stderr)
        return []

def _get_all_tray_icons():
    """
    Finds *all* system tray icons using the branching logic
    from the NVDA 'sysTryList' addon.
    Returns a list of strings, e.g., ["Dropbox...", "Volume...", etc.]
    """
    is_win11, is_win11_22h2 = _get_windows_version_info()
    
    all_icons = []
    
    try:
        app = Application(backend="uia").connect(path="explorer.exe")
        taskbar = app.window(class_name="Shell_TrayWnd")
        icon_container = None
        
        if is_win11_22h2:
            try:
                icon_container = taskbar.child_window(
                    class_name="Windows.UI.Input.InputSite.WindowClass"
                ).wait('visible', timeout=5)
            except (ElementNotFoundError, TimeoutError):
                pass # Fallback
        
        if icon_container is None and is_win11:
            try:
                bridge_container = taskbar.child_window(
                    class_name="Windows.UI.Composition.DesktopWindowContentBridge"
                ).wait('visible', timeout=5)
                if bridge_container.children():
                    icon_container = bridge_container.children()[0]
            except (ElementNotFoundError, TimeoutError):
                pass # Fallback
        
        if icon_container is None:
            try:
                icon_container = taskbar.child_window(
                    class_name="TrayNotifyWnd"
                ).child_window(
                    class_name="SysPager"
                ).child_window(
                    class_name="ToolbarWindow32"
                ).wait('visible', timeout=5)
            except (ElementNotFoundError, TimeoutError) as e:
                print(f"Legacy path failed: {e}", file=sys.stderr)

        if icon_container:
            all_icons = _get_icons_from_container(icon_container)
            
    except Exception as e:
        print(f"An unexpected error occurred connecting to explorer: {e}", file=sys.stderr)

    # Clean up the list
    all_icons_filtered = list(filter(None, all_icons))
    return sorted(list(set(all_icons_filtered)))


class TrayMonitor:
    """
    Monitors cloud-app icons in the system tray and reports changes.
    """
    def __init__(self):
        # This dictionary will store the last known state, e.g.:
        # {"Dropbox": "Dropbox... Up to date", "OneDrive": "OneDrive... Synced"}
        self.last_known_cloud_state = {}

    def _parse_and_filter_icons(self, all_icons_list):
        """
        Filters the full icon list for cloud apps and organizes them
        into a clean dictionary.
        """
        current_cloud_state = {}
        for full_icon_text in all_icons_list:
            lower_text = full_icon_text.lower()
            
            # Find which keyword this icon matches
            for keyword in CLOUD_KEYWORDS:
                if keyword in lower_text:
                    # We've found a match. We'll use the *keyword* as the
                    # main key to avoid issues with version numbers in the name.
                    # e.g., "Dropbox 235.4.5905" and "Dropbox 236.1.0"
                    # will both be stored under the key "dropbox".
                    
                    # We find the *first* matching keyword and use it.
                    app_name = keyword
                    
                    # --- FIX for Multiline Statuses ---
                    # 1. Replace all newline (\n) and carriage returns (\r) with a space.
                    clean_text = full_icon_text.replace(chr(10), ' ').replace(chr(13), ' ')
                    # 2. Normalize all whitespace (e.g., "a   b" becomes "a b")
                    #    by splitting the string by spaces and re-joining with one space.
                    clean_text = ' '.join(clean_text.split())
                    
                    current_cloud_state[app_name] = clean_text
                    break # Move to the next icon
                    
        return current_cloud_state

    def check_for_changes(self):
        """
        Gets the current tray icons, compares them to the last known state,
        and returns a list of any changes.
        """
        all_icons = _get_all_tray_icons()
        current_cloud_state = self._parse_and_filter_icons(all_icons)
        
        changes = []
        
        # 1. Check for changes and new icons
        for app_name, new_status in current_cloud_state.items():
            if app_name not in self.last_known_cloud_state:
                # This is a new app that just appeared
                change_type = "appeared"
                changes.append((app_name, change_type, new_status))
            elif self.last_known_cloud_state[app_name] != new_status:
                # The status text has changed!
                change_type = "changed"
                changes.append((app_name, change_type, new_status))
        
        # 2. Check for icons that disappeared
        for app_name in self.last_known_cloud_state:
            if app_name not in current_cloud_state:
                change_type = "disappeared"
                changes.append((app_name, change_type, f"{app_name} has disappeared"))
        
        # 3. Update the state for the next check
        self.last_known_cloud_state = current_cloud_state
        
        # Return a list of tuples: [(app_name, type_of_change, full_text), ...]
        return changes

# --- This block is for testing the module directly ---
if __name__ == "__main__":
    import time
    print("--- Testing TrayMonitor ---")
    monitor = TrayMonitor()
    
    print("Performing initial check...")
    # The first run will report all found icons as "appeared"
    initial_changes = monitor.check_for_changes()
    
    if not initial_changes:
        print("No cloud icons found on first run.")
    else:
        print("--- Initial Icons Found ---")
        for app, change_type, status in initial_changes:
            # No cleaning needed here, as it was already cleaned before saving
            print(f"[{change_type.upper()}] {app}: {status}")
    
    print("\nStarting monitor loop. Press Ctrl+C to stop.")
    print("Try pausing/resuming sync on Dropbox or OneDrive to see changes.")
    
    try:
        while True:
            time.sleep(3) # Check every 3 seconds
            changes_found = monitor.check_for_changes()
            
            if changes_found:
                print("\n--- STATUS CHANGE DETECTED ---")
                for app, change_type, status in changes_found:
                    # No cleaning needed here, as it was already cleaned before saving
                    print(f"[{change_type.upper()}] {app}: {status}")
            else:
                print(".", end="", flush=True) # Print a dot to show it's working
                
    except KeyboardInterrupt:
        print("\nMonitor stopped.")
