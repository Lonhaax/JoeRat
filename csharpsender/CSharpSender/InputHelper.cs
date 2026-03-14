using System.Runtime.InteropServices;

namespace CSharpSender;

/// <summary>
/// Injects mouse and keyboard input from remote-control messages.
/// </summary>
static class InputHelper
{
    private const int MOUSEEVENTF_ABSOLUTE = 0x8000;
    private const int MOUSEEVENTF_LEFTDOWN = 0x02;
    private const int MOUSEEVENTF_LEFTUP = 0x04;
    private const int MOUSEEVENTF_RIGHTDOWN = 0x08;
    private const int MOUSEEVENTF_RIGHTUP = 0x10;
    private const int MOUSEEVENTF_MIDDLEDOWN = 0x20;
    private const int MOUSEEVENTF_MIDDLEUP = 0x40;
    private const int MOUSEEVENTF_WHEEL = 0x0800;
    private const uint KEYEVENTF_KEYUP = 0x0002;

    [DllImport("user32.dll")]
    private static extern void mouse_event(int dwFlags, int dx, int dy, int dwData, int dwExtraInfo);

    [DllImport("user32.dll")]
    private static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);

    /// <summary>Convert Qt key codes to Windows virtual key codes.</summary>
    public static byte? QtKeyToVk(int qtKeyCode, string? key)
    {
        // Qt special keys (approximate values)
        if (qtKeyCode >= 0x01000000)
        {
            return qtKeyCode switch
            {
                0x01000000 => 0x1B,   // Qt.Key_Escape -> VK_ESCAPE
                0x01000001 => 0x09,   // Qt.Key_Tab -> VK_TAB
                0x01000003 => 0x08,   // Qt.Key_Backspace -> VK_BACK
                0x01000004 or 0x01000005 => 0x0D,  // Qt.Key_Return/Enter -> VK_RETURN
                0x01000007 => 0x2E,   // Qt.Key_Delete -> VK_DELETE
                0x01000010 => 0x10,   // Qt.Key_Shift -> VK_SHIFT
                0x01000011 => 0x11,   // Qt.Key_Control -> VK_CONTROL
                0x01000012 => 0x12,   // Qt.Key_Alt -> VK_MENU
                0x01000032 => 0x25,   // Qt.Key_Left -> VK_LEFT
                0x01000033 => 0x26,   // Qt.Key_Up -> VK_UP
                0x01000034 => 0x27,   // Qt.Key_Right -> VK_RIGHT
                0x01000035 => 0x28,   // Qt.Key_Down -> VK_DOWN
                0x01000036 => 0x24,   // Qt.Key_Home -> VK_HOME
                0x01000037 => 0x23,   // Qt.Key_End -> VK_END
                0x01000038 => 0x21,   // Qt.Key_PageUp -> VK_PRIOR
                0x01000039 => 0x22,   // Qt.Key_PageDown -> VK_NEXT
                0x0100003A => 0x2D,   // Qt.Key_Insert -> VK_INSERT
                _ => (qtKeyCode >= 0x01000040 && qtKeyCode <= 0x01000057) ? (byte)(0x70 + (qtKeyCode - 0x01000040)) : null  // F1-F24
            };
        }
        // Printable: Qt often uses ASCII for A-Z, 0-9
        if (qtKeyCode >= 32 && qtKeyCode <= 126)
            return (byte)qtKeyCode;
        if (!string.IsNullOrEmpty(key) && key.Length == 1)
            return (byte)key[0];
        return null;
    }

    public static void MouseDown(double xNorm, double yNorm, string button)
    {
        var (dx, dy) = NormToAbsolute(xNorm, yNorm);
        int flags = ButtonToFlags(button, down: true);
        if (flags != 0)
            mouse_event(flags | MOUSEEVENTF_ABSOLUTE, dx, dy, 0, 0);
    }

    public static void MouseUp(double xNorm, double yNorm, string button)
    {
        var (dx, dy) = NormToAbsolute(xNorm, yNorm);
        int flags = ButtonToFlags(button, down: false);
        if (flags != 0)
            mouse_event(flags | MOUSEEVENTF_ABSOLUTE, dx, dy, 0, 0);
    }

    public static void MouseMove(double xNorm, double yNorm)
    {
        var bounds = Screen.PrimaryScreen.Bounds;
        int x = (int)(xNorm * bounds.Width);
        int y = (int)(yNorm * bounds.Height);
        x = Math.Clamp(x, 0, bounds.Width - 1);
        y = Math.Clamp(y, 0, bounds.Height - 1);
        Cursor.Position = new Point(bounds.X + x, bounds.Y + y);
    }

    public static void MouseWheel(double xNorm, double yNorm, int delta)
    {
        var (dx, dy) = NormToAbsolute(xNorm, yNorm);
        mouse_event(MOUSEEVENTF_WHEEL | MOUSEEVENTF_ABSOLUTE, dx, dy, delta, 0);
    }

    public static void KeyPress(byte vk)
    {
        keybd_event(vk, 0, 0, 0);
    }

    public static void KeyRelease(byte vk)
    {
        keybd_event(vk, 0, KEYEVENTF_KEYUP, 0);
    }

    private static (int dx, int dy) NormToAbsolute(double xNorm, double yNorm)
    {
        xNorm = Math.Clamp(xNorm, 0, 1);
        yNorm = Math.Clamp(yNorm, 0, 1);
        int dx = (int)(xNorm * 65535);
        int dy = (int)(yNorm * 65535);
        return (dx, dy);
    }

    private static int ButtonToFlags(string button, bool down)
    {
        return (button?.ToLowerInvariant()) switch
        {
            "left" => down ? MOUSEEVENTF_LEFTDOWN : MOUSEEVENTF_LEFTUP,
            "right" => down ? MOUSEEVENTF_RIGHTDOWN : MOUSEEVENTF_RIGHTUP,
            "middle" => down ? MOUSEEVENTF_MIDDLEDOWN : MOUSEEVENTF_MIDDLEUP,
            _ => 0
        };
    }
}
