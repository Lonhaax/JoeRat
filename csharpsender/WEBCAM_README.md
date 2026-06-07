# Webcam Integration Guide

## Current Implementation

The current implementation includes a **placeholder webcam capture** that creates a simulated webcam feed with:
- "WEBCAM STREAM" text
- Live timestamp
- Border and recording indicator
- Error handling

## How to Add Real Webcam Support

### Option 1: AForge.NET (Recommended for simplicity)

1. **Install NuGet packages:**
   ```bash
   Install-Package AForge.Video
   Install-Package AForge.Video.DirectShow
   ```

2. **Uncomment and use the AForge.NET code** in `WebcamCapture.cs`:
   - Uncomment the AForge.NET section
   - Call `WebcamCapture.InitializeWebcam()` when starting
   - Use `WebcamCapture.CaptureRealFrame()` instead of placeholder
   - Call `WebcamCapture.Cleanup()` when stopping

### Option 2: DirectShow.NET (More complex)

1. **Install NuGet package:**
   ```bash
   Install-Package DirectShow.NET
   ```

2. **Implement DirectShow capture** using the DirectShow.NET APIs

### Option 3: OpenCVSharp (Cross-platform)

1. **Install NuGet package:**
   ```bash
   Install-Package OpenCvSharp4
   Install-Package OpenCvSharp4.runtime.win
   ```

2. **Use OpenCV VideoCapture:**
   ```csharp
   using OpenCvSharp;
   
   var capture = new VideoCapture(0); // 0 = default webcam
   var mat = new Mat();
   capture.Read(mat);
   return BitmapConverter.ToBitmap(mat);
   ```

## Integration Steps

1. **Choose your webcam library** and install the NuGet packages
2. **Modify `WebcamCapture.cs`** to use real webcam capture
3. **Update `Form1.cs`** if needed (optional: add webcam initialization/cleanup)
4. **Test the implementation** by running the sender and toggling webcam from the viewer

## Testing

1. Start the C# sender
2. Connect with the Qt viewer
3. Click the "📷 Webcam" button in the viewer
4. You should see either:
   - Placeholder webcam feed (current implementation)
   - Real webcam feed (if you implemented real capture)

## Notes

- The current placeholder implementation is fully functional for testing
- Real webcam implementation requires additional dependencies
- Webcam frames are automatically routed to the viewer's floating webcam window
- Desktop and webcam streams can be toggled independently
- The server handles multiple viewers requesting webcam from the same sender
