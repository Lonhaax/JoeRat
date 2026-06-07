using System;
using System.Drawing;
using System.Drawing.Drawing2D;

namespace CSharpSender
{
    /// <summary>
    /// Placeholder webcam capture implementation. Generates a synthetic frame to keep the sender
    /// functional when webcam dependencies (AForge video) are not present.
    /// </summary>
    public static class WebcamCapture
    {
        public static void Cleanup()
        {
            // Nothing to clean up in the stub implementation.
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

                // Decorative border
                using var pen = new Pen(Color.LightSteelBlue, 4);
                g.DrawRectangle(pen, 10, 10, width - 20, height - 20);

                // Moving indicator so viewers know the frame is being refreshed
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
