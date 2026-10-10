# -*- coding: utf-8 -*-
"""
Windows 11 System Tray Structure Debugger
Helps understand the UIA structure of the system tray on different Windows versions.
"""

import logging
from typing import List, Dict, Any

try:
    import uiautomation as uia
    UIA_AVAILABLE = True
except ImportError:
    UIA_AVAILABLE = False
    print("❌ uiautomation not available. Install with: pip install uiautomation")

class SystemTrayDebugger:
    """Debug the system tray UIA structure"""
    
    def __init__(self):
        logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
        self.logger = logging.getLogger(__name__)
        
        if not UIA_AVAILABLE:
            raise ImportError("uiautomation package required")
    
    def debug_full_structure(self, max_depth: int = 6):
        """Print the full UIA structure starting from Shell_TrayWnd"""
        print("🔍 DEBUGGING SYSTEM TRAY UIA STRUCTURE")
        print("=" * 50)
        
        try:
            desktop = uia.GetRootControl()
            
            # Find Shell_TrayWnd
            shell_tray = desktop.SearchControl(searchDepth=3, ClassName="Shell_TrayWnd")
            
            if not shell_tray:
                print("❌ Could not find Shell_TrayWnd")
                return
            
            print(f"✅ Found Shell_TrayWnd")
            print(f"   Name: {getattr(shell_tray, 'Name', 'N/A')}")
            print(f"   ClassName: {getattr(shell_tray, 'ClassName', 'N/A')}")
            print(f"   ControlType: {getattr(shell_tray, 'ControlTypeName', 'N/A')}")
            print()
            
            # Recursively print the structure
            self._print_structure_recursive(shell_tray, depth=0, max_depth=max_depth)
            
        except Exception as e:
            print(f"❌ Error debugging structure: {e}")
    
    def _print_structure_recursive(self, control, depth: int, max_depth: int):
        """Recursively print UIA control structure"""
        if depth >= max_depth:
            return
        
        indent = "  " * depth
        
        try:
            children = control.GetChildren() if hasattr(control, 'GetChildren') else []
            
            for i, child in enumerate(children):
                name = getattr(child, 'Name', 'N/A')
                class_name = getattr(child, 'ClassName', 'N/A')
                control_type = getattr(child, 'ControlTypeName', 'N/A')
                automation_id = getattr(child, 'AutomationId', 'N/A')
                
                print(f"{indent}├── Child {i+1}:")
                print(f"{indent}    Name: '{name}'")
                print(f"{indent}    ClassName: '{class_name}'")
                print(f"{indent}    ControlType: {control_type}")
                print(f"{indent}    AutomationId: '{automation_id}'")
                
                # If it's a button with a meaningful name, highlight it
                if (control_type == "ButtonControl" and 
                    name and name.strip() and name != "N/A"):
                    print(f"{indent}    🎯 POTENTIAL SYSTEM TRAY ICON!")
                
                # If it looks like a notification area, highlight it
                if ("notify" in class_name.lower() or 
                    "tray" in class_name.lower() or 
                    "toolbar" in class_name.lower()):
                    print(f"{indent}    📋 POTENTIAL NOTIFICATION CONTAINER!")
                
                print()
                
                # Recurse
                self._print_structure_recursive(child, depth + 1, max_depth)
                
        except Exception as e:
            print(f"{indent}❌ Error reading children at depth {depth}: {e}")
    
    def find_all_buttons(self):
        """Find all button controls in the system tray area"""
        print("🔍 SEARCHING FOR ALL BUTTONS IN SYSTEM TRAY")
        print("=" * 50)
        
        try:
            desktop = uia.GetRootControl()
            shell_tray = desktop.SearchControl(searchDepth=3, ClassName="Shell_TrayWnd")
            
            if not shell_tray:
                print("❌ Could not find Shell_TrayWnd")
                return
            
            all_buttons = []
            self._find_buttons_recursive(shell_tray, all_buttons, max_depth=6)
            
            print(f"✅ Found {len(all_buttons)} buttons total")
            print()
            
            for i, button in enumerate(all_buttons, 1):
                name = getattr(button, 'Name', 'N/A')
                class_name = getattr(button, 'ClassName', 'N/A')
                automation_id = getattr(button, 'AutomationId', 'N/A')
                help_text = getattr(button, 'HelpText', 'N/A')
                
                try:
                    bounds = button.BoundingRectangle
                    bounds_str = f"({bounds.left}, {bounds.top}, {bounds.width()}, {bounds.height()})"
                except:
                    bounds_str = "N/A"
                
                print(f"Button {i}:")
                print(f"  Name: '{name}'")
                print(f"  ClassName: '{class_name}'")
                print(f"  AutomationId: '{automation_id}'")
                print(f"  HelpText: '{help_text}'")
                print(f"  Bounds: {bounds_str}")
                
                # Check if it looks like a system tray icon
                if (name and name.strip() and name not in ["Show hidden icons", "Chevron", "Start", "Search", "Task view"]):
                    print("  🎯 LIKELY SYSTEM TRAY ICON!")
                
                print()
                
        except Exception as e:
            print(f"❌ Error finding buttons: {e}")
    
    def _find_buttons_recursive(self, parent, button_list, current_depth=0, max_depth=6):
        """Recursively find all button controls"""
        if current_depth >= max_depth:
            return
        
        try:
            children = parent.GetChildren() if hasattr(parent, 'GetChildren') else []
            for child in children:
                if (hasattr(child, 'ControlType') and 
                    child.ControlType == uia.ControlType.ButtonControl):
                    button_list.append(child)
                
                # Recurse
                self._find_buttons_recursive(child, button_list, current_depth + 1, max_depth)
                
        except Exception as e:
            pass  # Ignore errors in recursive search
    
    def test_search_patterns(self):
        """Test different search patterns to find notification area"""
        print("🔍 TESTING DIFFERENT SEARCH PATTERNS")
        print("=" * 50)
        
        desktop = uia.GetRootControl()
        
        # Test patterns
        patterns = [
            {"Name": "Notification Area", "ControlType": uia.ControlType.ToolBarControl},
            {"Name": "System Tray", "ControlType": uia.ControlType.ToolBarControl},
            {"ClassName": "ToolbarWindow32"},
            {"ClassName": "TrayNotifyWnd"},
            {"ClassName": "Windows.UI.Input.InputSite.WindowClass"},
            {"ClassName": "Windows.UI.Composition.DesktopWindowContentBridge"},
            {"ControlType": uia.ControlType.ToolBarControl},
            {"ControlType": uia.ControlType.PaneControl},
        ]
        
        for i, pattern in enumerate(patterns, 1):
            try:
                print(f"Pattern {i}: {pattern}")
                result = desktop.SearchControl(searchDepth=6, **pattern)
                
                if result and result.Exists():
                    print(f"  ✅ FOUND!")
                    print(f"  Name: '{getattr(result, 'Name', 'N/A')}'")
                    print(f"  ClassName: '{getattr(result, 'ClassName', 'N/A')}'")
                    print(f"  ControlType: {getattr(result, 'ControlTypeName', 'N/A')}")
                    
                    # Try to get children
                    try:
                        children = result.GetChildren()
                        print(f"  Children count: {len(children)}")
                        
                        # Show first few children
                        for j, child in enumerate(children[:3]):
                            child_name = getattr(child, 'Name', 'N/A')
                            child_type = getattr(child, 'ControlTypeName', 'N/A')
                            print(f"    Child {j+1}: '{child_name}' ({child_type})")
                            
                    except Exception as e:
                        print(f"  ❌ Error getting children: {e}")
                        
                else:
                    print("  ❌ Not found")
                    
                print()
                
            except Exception as e:
                print(f"  ❌ Error with pattern: {e}")
                print()
    
    def check_overflow_area(self):
        """Check if we can find and access the overflow area"""
        print("🔍 CHECKING OVERFLOW/HIDDEN ICONS AREA")
        print("=" * 50)
        
        try:
            desktop = uia.GetRootControl()
            
            # Look for show hidden icons button
            show_hidden_patterns = [
                {"Name": "Show hidden icons", "ControlType": uia.ControlType.ButtonControl},
                {"Name": "Chevron", "ControlType": uia.ControlType.ButtonControl},
                {"AutomationId": "ShowHiddenIcons"},
            ]
            
            show_hidden_btn = None
            for pattern in show_hidden_patterns:
                try:
                    btn = desktop.SearchControl(searchDepth=6, **pattern)
                    if btn and btn.Exists():
                        show_hidden_btn = btn
                        print(f"✅ Found show hidden button with pattern: {pattern}")
                        break
                except:
                    continue
            
            if not show_hidden_btn:
                print("❌ No 'Show hidden icons' button found")
                return
            
            # Try clicking it
            print("🖱️ Clicking 'Show hidden icons' button...")
            show_hidden_btn.Click()
            
            import time
            time.sleep(0.5)  # Wait for overflow to appear
            
            # Look for overflow window
            overflow_patterns = [
                {"ClassName": "NotifyIconOverflowWindow"},
                {"AutomationId": "NotifyIconOverflowWindow"},
                {"Name": "Overflow"},
            ]
            
            overflow_window = None
            for pattern in overflow_patterns:
                try:
                    window = desktop.SearchControl(searchDepth=4, **pattern)
                    if window and window.Exists():
                        overflow_window = window
                        print(f"✅ Found overflow window with pattern: {pattern}")
                        break
                except:
                    continue
            
            if overflow_window:
                try:
                    children = overflow_window.GetChildren()
                    print(f"✅ Overflow window has {len(children)} children")
                    
                    for i, child in enumerate(children):
                        name = getattr(child, 'Name', 'N/A')
                        control_type = getattr(child, 'ControlTypeName', 'N/A')
                        print(f"  Child {i+1}: '{name}' ({control_type})")
                        
                except Exception as e:
                    print(f"❌ Error reading overflow children: {e}")
            else:
                print("❌ Could not find overflow window")
            
            # Click again to close
            show_hidden_btn.Click()
            
        except Exception as e:
            print(f"❌ Error checking overflow: {e}")


if __name__ == "__main__":
    if not UIA_AVAILABLE:
        print("❌ Please install uiautomation: pip install uiautomation")
        exit(1)
    
    print("Windows 11 System Tray Structure Debugger")
    print("=========================================")
    print("This will help diagnose the system tray structure on your system.")
    print("Press Enter to continue or Ctrl+C to exit...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\nExiting...")
        exit(0)
    
    debugger = SystemTrayDebugger()
    
    print("\n" + "="*60)
    print("1. TESTING SEARCH PATTERNS")
    print("="*60)
    debugger.test_search_patterns()
    
    print("\n" + "="*60)
    print("2. FINDING ALL BUTTONS")
    print("="*60)
    debugger.find_all_buttons()
    
    print("\n" + "="*60)
    print("3. CHECKING OVERFLOW AREA")
    print("="*60)
    debugger.check_overflow_area()
    
    print("\n" + "="*60)
    print("4. FULL STRUCTURE DEBUG (Limited depth)")
    print("="*60)
    print("This will show the full UIA tree structure...")
    print("Press Enter to continue or Ctrl+C to skip...")
    
    try:
        input()
        debugger.debug_full_structure(max_depth=4)  # Limited depth to avoid spam
    except KeyboardInterrupt:
        print("Skipped full structure debug")
    
    print("\n" + "="*60)
    print("DEBUG COMPLETE")
    print("="*60)
    print("Please share the output above to help diagnose the issue!")
    print("Look for lines marked with 🎯 LIKELY SYSTEM TRAY ICON")
    print("and 📋 POTENTIAL NOTIFICATION CONTAINER")