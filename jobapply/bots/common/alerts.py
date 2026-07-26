"""Audio & Visual Alerts for manual prompt notifications."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .paths import APP_ROOT


def play_notification_sound(sound_path: str | None = None, app_root: Path = APP_ROOT) -> None:
    """
    Plays a notification sound when a manual question input is required.
    
    Supports:
    - Custom MP3 files via ctypes (Windows)
    - WAV files via winsound (Windows)
    - Fallback system beep
    - Terminal bell for cross-platform support
    
    Args:
        sound_path: Optional path to custom sound file
        app_root: Application root directory for resolving relative paths
    """
    # Resolve sound path with multiple fallback locations
    resolved_path = None
    
    if sound_path and os.path.exists(sound_path):
        resolved_path = sound_path
    else:
        # Try default locations
        script_dir = Path(__file__).parent
        candidates = [
            app_root / "notify" / "job.mp3",
            script_dir.parent.parent / "notify" / "job.mp3",
            script_dir / ".." / ".." / "notify" / "job.mp3",
        ]
        
        for candidate in candidates:
            if candidate.is_file():
                resolved_path = str(candidate)
                break
    
    # Play custom sound if available
    if resolved_path and os.path.exists(resolved_path):
        try:
            sound_path_abs = os.path.abspath(resolved_path)
            
            # Handle MP3 files on Windows using Media Control Interface
            if sound_path_abs.lower().endswith(".mp3") and os.name == "nt":
                import ctypes
                try:
                    ctypes.windll.winmm.mciSendStringW("close my_sound", None, 0, 0)
                    ctypes.windll.winmm.mciSendStringW(
                        f'open "{sound_path_abs}" type mpegvideo alias my_sound', 
                        None, 
                        0, 
                        0
                    )
                    ctypes.windll.winmm.mciSendStringW("play my_sound", None, 0, 0)
                    return
                except Exception as e:
                    _log_alert_error(f"MCI playback failed: {e}")
            
            # Handle WAV/other files on Windows using winsound
            elif os.name == "nt":
                import winsound
                try:
                    winsound.PlaySound(sound_path_abs, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    return
                except Exception as e:
                    _log_alert_error(f"winsound.PlaySound failed: {e}")
            
            # Cross-platform fallback using playsound if available
            else:
                try:
                    from playsound import playsound
                    playsound(sound_path_abs, block=False)
                    return
                except ImportError:
                    pass
                except Exception as e:
                    _log_alert_error(f"playsound failed: {e}")
                    
        except Exception as e:
            _log_alert_error(f"Custom sound playback failed: {e}")
    
    # Fallback to system sounds
    _play_system_alert()


def _play_system_alert() -> None:
    """Play system alert sounds as fallback."""
    if os.name == "nt":
        # Windows system alerts
        try:
            import winsound
            # Play asterisk sound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            # Play custom beep (1000Hz for 500ms)
            winsound.Beep(1000, 500)
            return
        except Exception as e:
            _log_alert_error(f"Windows beep failed: {e}")
    
    # Unix/Linux/macOS terminal bell
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:
        pass


def _log_alert_error(message: str) -> None:
    """Log alert system errors without breaking the flow."""
    # Silent logging to avoid cluttering output
    pass


def show_visual_alert(driver: Any, message: str = "Action Required") -> None:
    """
    Display a visual alert in the browser when manual input is needed.
    
    Args:
        driver: Selenium WebDriver instance
        message: Alert message to display
    """
    try:
        # Execute JavaScript to show a non-blocking notification
        driver.execute_script("""
            // Create notification element if it doesn't exist
            let notification = document.getElementById('jobapply-alert');
            if (!notification) {
                notification = document.createElement('div');
                notification.id = 'jobapply-alert';
                notification.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    z-index: 999999;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px 30px;
                    border-radius: 10px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.3);
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    font-size: 16px;
                    font-weight: 600;
                    animation: slideIn 0.3s ease-out;
                `;
                
                // Add animation styles
                const style = document.createElement('style');
                style.textContent = `
                    @keyframes slideIn {
                        from { transform: translateX(400px); opacity: 0; }
                        to { transform: translateX(0); opacity: 1; }
                    }
                    @keyframes pulse {
                        0%, 100% { transform: scale(1); }
                        50% { transform: scale(1.05); }
                    }
                `;
                document.head.appendChild(style);
                document.body.appendChild(notification);
            }
            
            // Update message
            notification.textContent = arguments[0];
            notification.style.animation = 'slideIn 0.3s ease-out, pulse 1s ease-in-out infinite';
            
            // Auto-remove after 10 seconds
            setTimeout(() => {
                if (notification && notification.parentNode) {
                    notification.style.animation = 'slideIn 0.3s ease-out reverse';
                    setTimeout(() => notification.remove(), 300);
                }
            }, 10000);
        """, message)
    except Exception:
        # Silently fail if JavaScript execution fails
        pass
