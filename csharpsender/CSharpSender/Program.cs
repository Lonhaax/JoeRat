using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Threading;
using System.Windows.Forms;
using CSharpSender;

class Program
{
    private const int MOUSEEVENTF_ABSOLUTE = 0x8000;
    // Check if running as admin
    static bool IsAdministrator()
    {
        try
        {
            var identity = System.Security.Principal.WindowsIdentity.GetCurrent();
            var principal = new System.Security.Principal.WindowsPrincipal(identity);
            return principal.IsInRole(System.Security.Principal.WindowsBuiltInRole.Administrator);
        }
        catch { return false; }
    }
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    private struct MOUSEINPUT
    {
        public int dx;
        public int dy;
        public int mouseData;
        public int dwFlags;
        public int time;
        public IntPtr dwExtraInfo;
    }
    static string currentDirectory = Environment.CurrentDirectory;
    static void LogDebug(string message)
    {
        string logPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "sender-debug.log");
        string logEntry = $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {message}\n";
        try { File.AppendAllText(logPath, logEntry); } catch { }
    }

    private const byte VK_BACK = 0x08;
    private const uint KEYEVENTF_KEYUP = 0x0002;
    private const int MOUSEEVENTF_MIDDLEDOWN = 0x0020;
    static bool isJoined = false;
    [STAThread]
    static void Main(string[] args)
    {
        // Automatically add to startup if not already there
        try
        {
            string exePath = System.Environment.ProcessPath ?? "Unknown";
            ExitForm.Log($"Executable path: {exePath}");
            ExitForm.Log($"Checking startup status...");
            
            if (!StartupManager.IsInStartup())
            {
                ExitForm.Log("Not in startup, adding now...");
                bool success = StartupManager.AddToStartup();
                ExitForm.Log($"Startup add result: {success}");
            }
            else
            {
                ExitForm.Log("Already in startup");
            }

            // Check if in AppData, move if not
            ExitForm.Log("Checking AppData location...");
            if (!StartupManager.IsInAppData())
            {
                ExitForm.Log("Not in AppData, moving now...");
                bool moved = StartupManager.MoveToAppData();
                ExitForm.Log($"AppData move result: {moved}");
                
                if (moved)
                {
                    ExitForm.Log("File moved to AppData - you may close this instance and run from AppData");
                }
            }
            else
            {
                ExitForm.Log("Already in AppData location");
            }
        }
        catch (Exception ex)
        {
            LogDebug($"Failed to setup startup/AppData: {ex.Message}");
            ExitForm.Log($"Setup error: {ex.Message}");
        }
        
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException += (s, e) => LogDebug($"ThreadException: {e.Exception}");
        AppDomain.CurrentDomain.UnhandledException += (s, e) =>
        {
            var ex = (Exception)e.ExceptionObject;
            LogDebug($"UnhandledException: {ex}");
        };
        Application.Run(new Form1());
    }


    // Win32 mouse_event import
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern void mouse_event(int dwFlags, int dx, int dy, int dwData, int dwExtraInfo);
    private const int MOUSEEVENTF_LEFTDOWN = 0x02;
    private const int MOUSEEVENTF_LEFTUP = 0x04;
    private const int MOUSEEVENTF_RIGHTDOWN = 0x08;
    private const int MOUSEEVENTF_RIGHTUP = 0x10;
    private const int MOUSEEVENTF_WHEEL = 0x0800;

    // Win32 keybd_event import
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Explicit)]
    private struct INPUT
    {
        [System.Runtime.InteropServices.FieldOffset(0)]
        public int type;
        [System.Runtime.InteropServices.FieldOffset(8)]
        public MOUSEINPUT mi;
        [System.Runtime.InteropServices.FieldOffset(8)]
        public KEYBDINPUT ki;
    }
    private struct KEYBDINPUT
    {
        public ushort wVk;
        public ushort wScan;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    // Win32 window functions
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hWnd);
}

class ExitForm : Form
{
    private static ExitForm? _instance;
    private TextBox? _logBox;

    public static void Log(string message)
    {
        var timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
        AppendLog($"[{timestamp}] {message}");
    }

    public static void AppendLog(string line)
    {
        if (_instance?._logBox == null) return;
        if (_instance.InvokeRequired)
        {
            _instance.BeginInvoke(() => AppendLog(line));
            return;
        }
        _instance._logBox.AppendText(line + Environment.NewLine);
        _instance._logBox.ScrollToCaret();
    }

    public ExitForm()
    {
        _instance = this;
        this.Text = "Close to Exit";
        this.Size = new Size(500, 400);
        this.StartPosition = FormStartPosition.CenterScreen;
        this.TopMost = false;
        this.ShowInTaskbar = true;
        this.FormBorderStyle = FormBorderStyle.Sizable;
        this.MinimizeBox = true;
        this.MaximizeBox = true;
        this.Opacity = 0.95;

        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 2 };
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 30));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

        var closeLabel = new Label
        {
            Text = "Close this box to exit",
            TextAlign = ContentAlignment.MiddleCenter,
            Dock = DockStyle.Fill,
            Font = new Font(this.Font.FontFamily, 10, FontStyle.Bold)
        };
        layout.Controls.Add(closeLabel, 0, 0);

        _logBox = new TextBox
        {
            Multiline = true,
            ReadOnly = true,
            ScrollBars = ScrollBars.Both,
            WordWrap = false,
            Dock = DockStyle.Fill,
            Font = new Font("Consolas", 9),
            BackColor = Color.FromArgb(30, 30, 30),
            ForeColor = Color.LightGray,
            BorderStyle = BorderStyle.FixedSingle
        };
        layout.Controls.Add(_logBox, 0, 1);

        this.Controls.Add(layout);
        Log("Application started.");
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        _instance = null;
        base.OnFormClosed(e);
    }
}