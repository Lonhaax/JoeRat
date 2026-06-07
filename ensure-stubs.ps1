$root = "csharpsender/CSharpSender"

if (-not (Test-Path "$root/BuildConfig.cs")) {
    @'
namespace CSharpSender;
internal static class BuildConfig
{
    public const string DefaultWsUrl  = "ws://localhost:3000";
    public const string DefaultRoomId = "default-room";
    public const string DefaultSecret = "changeme";
    public const string ExeName       = "CSharpSender";
}
'@ | Out-File -FilePath "$root/BuildConfig.cs" -Encoding UTF8
}

if (-not (Test-Path "$root/TerminalSession.cs")) {
    @'
using System;
using System.Threading.Tasks;

namespace CSharpSender
{
    public sealed class TerminalSession : IDisposable
    {
        private readonly Func<string, Task> _onOutputAsync;
        private bool _isActive;

        public TerminalSession(Func<string, Task> onOutputAsync)
        {
            _onOutputAsync = onOutputAsync ?? throw new ArgumentNullException(nameof(onOutputAsync));
        }

        public void Start()
        {
            if (_isActive) return;
            _isActive = true;
            _ = _onOutputAsync("[TERMINAL] Interactive shell not available in this build.\n");
        }

        public void SendInput(string input)
        {
            if (!_isActive) return;
            _ = _onOutputAsync($"[TERMINAL] Ignored input: {input}\n");
        }

        public void Stop()
        {
            if (!_isActive) return;
            _isActive = false;
            _ = _onOutputAsync("[TERMINAL] Session closed.\n");
        }

        public void Dispose()
        {
            Stop();
        }
    }
}
'@ | Out-File -FilePath "$root/TerminalSession.cs" -Encoding UTF8
}

if (-not (Test-Path "$root/WebcamCapture.cs")) {
    @'
using System;
using System.Drawing;
using System.Drawing.Drawing2D;

namespace CSharpSender
{
    public static class WebcamCapture
    {
        public static void Cleanup()
        {
        }

        public static Bitmap CaptureFrame(int width = 640, int height = 480)
        {
            var bmp = new Bitmap(width, height);
            using (var g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.Clear(Color.DarkSlateBlue);

                var now = DateTime.Now;
                var font = new Font("Segoe UI", 18, FontStyle.Bold);
                var subFont = new Font("Segoe UI", 12, FontStyle.Regular);

                var headline = "Webcam stream unavailable";
                var timestamp = now.ToString("yyyy-MM-dd HH:mm:ss");

                var headlineSize = g.MeasureString(headline, font);
                g.DrawString(headline, font, Brushes.AliceBlue,
                    (width - headlineSize.Width) / 2,
                    (height - headlineSize.Height) / 2 - 20);

                var tsSize = g.MeasureString(timestamp, subFont);
                g.DrawString(timestamp, subFont, Brushes.Gainsboro,
                    (width - tsSize.Width) / 2,
                    (height - tsSize.Height) / 2 + 10);

                using var pen = new Pen(Color.LightSteelBlue, 4);
                g.DrawRectangle(pen, 10, 10, width - 20, height - 20);

                var indicatorSize = 40;
                var spin = (int)(now.Millisecond / 1000.0 * 360);
                using var brush = new LinearGradientBrush(new Rectangle(0, 0, indicatorSize, indicatorSize),
                    Color.DeepSkyBlue, Color.RoyalBlue, spin);
                g.FillEllipse(brush, width - indicatorSize - 20, height - indicatorSize - 20, indicatorSize, indicatorSize);
            }
            return bmp;
        }
    }
}
'@ | Out-File -FilePath "$root/WebcamCapture.cs" -Encoding UTF8
}

if (-not (Test-Path "$root/ChromeRecovery.cs")) {
    @'
using System.Text.Json;
using System.Threading.Tasks;

namespace CSharpSender
{
    public static class ChromeRecovery
    {
        public static Task<string> HandleChromeRecoveryCommand(string action, string machineId)
        {
            var response = new
            {
                type = "command-output",
                requestId = "chrome-recovery",
                machineId,
                status = "unsupported",
                action,
                message = "Chrome recovery tooling not included in this build"
            };

            return Task.FromResult(JsonSerializer.Serialize(response));
        }
    }
}
'@ | Out-File -FilePath "$root/ChromeRecovery.cs" -Encoding UTF8
}
