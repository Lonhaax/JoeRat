using System.Runtime.InteropServices;

namespace CSharpSender;

/// <summary>
/// Blocks local keyboard and mouse input when lock is enabled (viewer controls remotely).
/// </summary>
static class InputLockHelper
{
    private const int WH_KEYBOARD_LL = 13;
    private const int WH_MOUSE_LL = 14;
    private const int HC_ACTION = 0;

    private static IntPtr _keyboardHookId = IntPtr.Zero;
    private static IntPtr _mouseHookId = IntPtr.Zero;
    private static readonly object _lock = new object();
    private static bool _locked;
    private static LowLevelKeyboardProc? _keyboardProc;
    private static LowLevelMouseProc? _mouseProc;

    private delegate IntPtr LowLevelKeyboardProc(int nCode, IntPtr wParam, IntPtr lParam);
    private delegate IntPtr LowLevelMouseProc(int nCode, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(int idHook, LowLevelKeyboardProc lpfn, IntPtr hMod, uint dwThreadId);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(int idHook, LowLevelMouseProc lpfn, IntPtr hMod, uint dwThreadId);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool UnhookWindowsHookEx(IntPtr hhk);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr CallNextHookEx(IntPtr hhk, int nCode, IntPtr wParam, IntPtr lParam);

    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr GetModuleHandle(string lpModuleName);

    /// <summary>Enable or disable blocking of local keyboard and mouse. Call from UI thread.</summary>
    public static void SetLock(bool locked)
    {
        lock (_lock)
        {
            if (_locked == locked) return;
            _locked = locked;
            if (locked)
            {
                _keyboardProc ??= KeyboardHookCallback;
                _mouseProc ??= MouseHookCallback;
                var hMod = GetModuleHandle(null);
                if (hMod != IntPtr.Zero)
                {
                    _keyboardHookId = SetWindowsHookEx(WH_KEYBOARD_LL, _keyboardProc, hMod, 0);
                    _mouseHookId = SetWindowsHookEx(WH_MOUSE_LL, _mouseProc, hMod, 0);
                }
            }
            else
            {
                if (_keyboardHookId != IntPtr.Zero)
                {
                    UnhookWindowsHookEx(_keyboardHookId);
                    _keyboardHookId = IntPtr.Zero;
                }
                if (_mouseHookId != IntPtr.Zero)
                {
                    UnhookWindowsHookEx(_mouseHookId);
                    _mouseHookId = IntPtr.Zero;
                }
            }
        }
    }

    public static bool IsLocked => _locked;

    private static IntPtr KeyboardHookCallback(int nCode, IntPtr wParam, IntPtr lParam)
    {
        if (nCode == HC_ACTION && _locked)
            return (IntPtr)1;
        return CallNextHookEx(_keyboardHookId, nCode, wParam, lParam);
    }

    private static IntPtr MouseHookCallback(int nCode, IntPtr wParam, IntPtr lParam)
    {
        if (nCode == HC_ACTION && _locked)
            return (IntPtr)1;
        return CallNextHookEx(_mouseHookId, nCode, wParam, lParam);
    }
}
