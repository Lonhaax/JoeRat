using System;
using System.Diagnostics;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace CSharpSender;

/// <summary>
/// Minimal console-based screen sender - no UI, no dependencies
/// </summary>
class MinimalSender
{
    private static ClientWebSocket? ws;
    private static CancellationTokenSource? cts;
    private static bool isConnected = false;

    static async Task Main(string[] args)
    {
        Console.WriteLine("╔════════════════════════════════════════╗");
        Console.WriteLine("║  Monitor Relay - Minimal Sender       ║");
        Console.WriteLine("║  Version 1.0.0                        ║");
        Console.WriteLine("╚════════════════════════════════════════╝");
        Console.WriteLine();

        // Parse arguments or use defaults
        string serverUrl = args.Length > 0 ? args[0] : "ws://localhost:3000";
        string roomId = args.Length > 1 ? args[1] : "ops-room";
        string secret = args.Length > 2 ? args[2] : "boi123";

        Console.WriteLine($"Server: {serverUrl}");
        Console.WriteLine($"Room: {roomId}");
        Console.WriteLine($"Secret: {secret}");
        Console.WriteLine();

        // Try to start embedded server
        Console.WriteLine("Starting embedded server...");
        bool serverStarted = await StartEmbeddedServerAsync();
        if (serverStarted)
        {
            Console.WriteLine("✓ Server started");
        }
        else
        {
            Console.WriteLine("⚠ Could not start server (Node.js may not be installed)");
        }

        Console.WriteLine();
        Console.WriteLine("Connecting to relay server...");

        // Connect and stream
        cts = new CancellationTokenSource();
        await ConnectAndStreamAsync(serverUrl, roomId, secret, cts.Token);

        Console.WriteLine("Disconnected. Press any key to exit...");
        Console.ReadKey();
    }

    static async Task<bool> StartEmbeddedServerAsync()
    {
        try
        {
            // Check if Node.js is available
            var psi = new ProcessStartInfo
            {
                FileName = "node",
                Arguments = "--version",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                CreateNoWindow = true
            };
            using var proc = Process.Start(psi);
            if (proc == null) return false;
            proc.WaitForExit(5000);
            if (proc.ExitCode != 0) return false;

            // Start server
            var serverPsi = new ProcessStartInfo
            {
                FileName = "node",
                Arguments = "server.js",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
                EnvironmentVariables =
                {
                    ["PORT"] = "3000",
                    ["ADMIN_KEY"] = "admin123",
                    ["ROOM_SECRET"] = "boi123"
                }
            };
            var serverProc = Process.Start(serverPsi);
            if (serverProc == null) return false;

            await Task.Delay(2000);
            return true;
        }
        catch
        {
            return false;
        }
    }

    static async Task ConnectAndStreamAsync(string url, string roomId, string secret, CancellationToken ct)
    {
        try
        {
            ws = new ClientWebSocket();
            await ws.ConnectAsync(new Uri(url), ct);
            Console.WriteLine("✓ Connected to server");

            // Send join message
            var machineId = Environment.MachineName;
            var join = new
            {
                type = "join",
                role = "sender",
                roomId = roomId,
                secret = secret,
                machineId = machineId
            };
            var joinJson = JsonSerializer.Serialize(join);
            var joinBytes = Encoding.UTF8.GetBytes(joinJson);
            await ws.SendAsync(new ArraySegment<byte>(joinBytes), WebSocketMessageType.Text, true, ct);

            Console.WriteLine($"✓ Joined room as {machineId}");
            Console.WriteLine();
            Console.WriteLine("Streaming... (Press Ctrl+C to stop)");
            isConnected = true;

            // Listen for messages
            _ = ListenForMessagesAsync(ct);

            // Stream frames
            await StreamFramesAsync(ct);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"✗ Error: {ex.Message}");
        }
        finally
        {
            isConnected = false;
            ws?.Dispose();
        }
    }

    static async Task ListenForMessagesAsync(CancellationToken ct)
    {
        var buffer = new byte[65536];
        try
        {
            while (ws?.State == WebSocketState.Open && !ct.IsCancellationRequested)
            {
                var result = await ws.ReceiveAsync(new ArraySegment<byte>(buffer), ct);
                if (result.MessageType == WebSocketMessageType.Close)
                    break;

                var msg = Encoding.UTF8.GetString(buffer, 0, result.Count);
                try
                {
                    using var doc = JsonDocument.Parse(msg);
                    var root = doc.RootElement;
                    if (root.TryGetProperty("type", out var typeElem))
                    {
                        var type = typeElem.GetString();
                        if (type == "chat-message")
                        {
                            var sender = root.TryGetProperty("senderName", out var sn) ? sn.GetString() : "Unknown";
                            var text = root.TryGetProperty("message", out var m) ? m.GetString() : "";
                            Console.WriteLine($"[CHAT] {sender}: {text}");
                        }
                    }
                }
                catch { }
            }
        }
        catch { }
    }

    static async Task StreamFramesAsync(CancellationToken ct)
    {
        int frameCount = 0;
        while (ws?.State == WebSocketState.Open && !ct.IsCancellationRequested)
        {
            try
            {
                // Simulate frame data (in real implementation, capture screen)
                var frameData = Encoding.UTF8.GetBytes($"frame-{frameCount++}");
                await ws.SendAsync(new ArraySegment<byte>(frameData), WebSocketMessageType.Binary, true, ct);
                await Task.Delay(500, ct); // 2 FPS
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"✗ Stream error: {ex.Message}");
                break;
            }
        }
    }
}
