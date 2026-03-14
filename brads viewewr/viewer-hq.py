import sys
import asyncio
import websockets
import json
import os
import time
import base64
from qasync import QEventLoop, asyncSlot, QApplication as QAsyncApplication

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QTextEdit, QLineEdit, QGroupBox, QFormLayout, QSlider, QCheckBox, QSpinBox)
from PyQt5.QtGui import QPixmap, QImage, QColor, QPainter, QMovie
from PyQt5.QtCore import Qt, QTimer, QSize, QBuffer, QIODevice
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget

# Try to import OpenCV for better image processing
try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("[WARNING] OpenCV not available. Using basic image processing.")

class StreamLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self._movie = None
        self._current_frame = None
        self._use_opencv = OPENCV_AVAILABLE
        
    def setH264Stream(self, frame_data):
        """Handle H.264 frame data"""
        try:
            if self._use_opencv:
                # Use OpenCV for better image processing
                self._process_with_opencv(frame_data)
            else:
                # Fallback to basic processing
                self._process_basic(frame_data)
        except Exception as e:
            print(f"[ERROR] Frame processing failed: {e}")
            self.setText(f"Error: {e}")
    
    def _process_with_opencv(self, frame_data):
        """Process frame using OpenCV for better quality"""
        try:
            # Convert bytes to numpy array
            nparr = np.frombuffer(frame_data, np.uint8)
            
            # Try to decode as image (for JPEG fallback)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is not None:
                # Convert RGB to BGR (OpenCV uses BGR)
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                
                # Get label size
                label_size = self.size()
                if label_size.width() > 0 and label_size.height() > 0:
                    # High-quality scaling
                    resized = cv2.resize(image_rgb, 
                                      (label_size.width(), label_size.height()),
                                      interpolation=cv2.INTER_LANCZOS4)
                    
                    # Convert to QPixmap
                    height, width, channel = resized.shape
                    bytes_per_line = 3 * width
                    q_image = QImage(resized.data, width, height, bytes_per_line, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(q_image)
                    self.setPixmap(pixmap)
                else:
                    self._current_frame = image_rgb
                    self._display_current_frame()
            else:
                # Try to decode as H.264 frame (this would need additional libraries)
                self._process_basic(frame_data)
                
        except Exception as e:
            print(f"[ERROR] OpenCV processing failed: {e}")
            self._process_basic(frame_data)
    
    def _process_basic(self, frame_data):
        """Basic frame processing without OpenCV"""
        try:
            # Try to decode as image directly
            image = QImage.fromData(frame_data)
            if not image.isNull():
                # Scale to fit label
                label_size = self.size()
                if label_size.width() > 0 and label_size.height() > 0:
                    scaled_image = image.scaled(
                        label_size,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    pixmap = QPixmap.fromImage(scaled_image)
                    self.setPixmap(pixmap)
            else:
                # If that fails, try as JPEG
                from io import BytesIO
                from PIL import Image
                try:
                    pil_image = Image.open(BytesIO(frame_data))
                    # Convert to QPixmap
                    width, height = pil_image.size
                    bytes_data = pil_image.tobytes()
                    q_image = QImage(bytes_data, width, height, width * 3, QImage.Format_RGB888)
                    
                    label_size = self.size()
                    if label_size.width() > 0 and label_size.height() > 0:
                        scaled_image = q_image.scaled(
                            label_size,
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation
                        )
                        self.setPixmap(QPixmap.fromImage(scaled_image))
                except ImportError:
                    self.setText("PIL not available. Cannot decode image.")
                except Exception as e:
                    self.setText(f"Image decode error: {e}")
                    
        except Exception as e:
            print(f"[ERROR] Basic processing failed: {e}")
            self.setText(f"Processing error: {e}")
    
    def _display_current_frame(self):
        """Display the current frame"""
        if self._current_frame is not None:
            label_size = self.size()
            if label_size.width() > 0 and label_size.height() > 0:
                resized = cv2.resize(self._current_frame,
                                   (label_size.width(), label_size.height()),
                                   interpolation=cv2.INTER_LANCZOS4)
                
                height, width, channel = resized.shape
                bytes_per_line = 3 * width
                q_image = QImage(resized.data, width, height, bytes_per_line, QImage.Format_RGB888)
                self.setPixmap(QPixmap.fromImage(q_image))
    
    def resizeEvent(self, event):
        """Handle resize to maintain image quality"""
        super().resizeEvent(event)
        if self._current_frame is not None:
            self._display_current_frame()

    def mousePressEvent(self, event):
        self.setFocus()
        if hasattr(self.parent(), 'handle_mouse_press'):
            self.parent().handle_mouse_press(event)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if hasattr(self.parent(), 'handle_mouse_release'):
            self.parent().handle_mouse_release(event)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        self.setFocus()
        if hasattr(self.parent(), 'handle_key_press'):
            self.parent().handle_key_press(event)

    def keyReleaseEvent(self, event):
        if hasattr(self.parent(), 'handle_key_release'):
            self.parent().handle_key_release(event)


class HighQualityViewerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Enhanced streaming settings
        self._stream_quality = "High"
        self._target_fps = 30
        self._frame_counter = 0
        self._fps_timer = QTime()
        self._last_frame_time = 0
        self._frame_times = []
        
        # Initialize UI
        self.initUI()
        
        # Performance monitoring
        self.performance_timer = QTimer(self)
        self.performance_timer.timeout.connect(self.update_performance_stats)
        self.performance_timer.start(1000)
        
    def initUI(self):
        """Initialize the user interface"""
        self.setWindowTitle("Monitor Relay - High Quality Viewer")
        self.setGeometry(100, 100, 1400, 900)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout(central_widget)
        
        # Left panel for controls
        left_panel = QWidget()
        left_panel.setMaximumWidth(350)
        left_layout = QVBoxLayout(left_panel)
        
        # Connection controls
        connection_group = QGroupBox("Connection")
        connection_layout = QFormLayout(connection_group)
        
        self.url_input = QLineEdit("ws://vnc.jake.cash:3000")
        connection_layout.addRow("Server URL:", self.url_input)
        
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_to_server)
        connection_layout.addRow(self.connect_button)
        
        # Machine selection
        self.sender_list = QComboBox()
        connection_layout.addRow("Select Machine:", self.sender_list)
        
        left_layout.addWidget(connection_group)
        
        # Quality controls
        quality_group = QGroupBox("Quality Settings")
        quality_layout = QVBoxLayout(quality_group)
        
        # Quality preset
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Low", "Medium", "High", "Ultra"])
        self.quality_combo.setCurrentText("High")
        quality_layout.addWidget(QLabel("Quality Preset:"))
        quality_layout.addWidget(self.quality_combo)
        
        # FPS control
        self.fps_slider = QSlider(Qt.Horizontal)
        self.fps_slider.setRange(15, 60)
        self.fps_slider.setValue(30)
        self.fps_slider.valueChanged.connect(self.on_fps_changed)
        quality_layout.addWidget(QLabel("Target FPS:"))
        quality_layout.addWidget(self.fps_slider)
        self.fps_label = QLabel("30 FPS")
        quality_layout.addWidget(self.fps_label)
        
        # Processing info
        self.processing_info = QLabel("Processing: OpenCV Available" if OPENCV_AVAILABLE else "Processing: Basic Mode")
        self.processing_info.setStyleSheet("color: #00ff00;" if OPENCV_AVAILABLE else "color: #ffaa00;")
        quality_layout.addWidget(self.processing_info)
        
        # Aspect ratio toggle
        self.aspect_checkbox = QCheckBox("Maintain Aspect Ratio")
        self.aspect_checkbox.setChecked(True)
        quality_layout.addWidget(self.aspect_checkbox)
        
        left_layout.addWidget(quality_group)
        
        # Performance stats
        stats_group = QGroupBox("Performance")
        stats_layout = QVBoxLayout(stats_group)
        
        self.fps_display = QLabel("FPS: 0")
        self.latency_display = QLabel("Latency: 0ms")
        self.frames_display = QLabel("Frames: 0")
        self.quality_display = QLabel("Quality: High")
        self.codec_display = QLabel("Codec: H.264")
        
        stats_layout.addWidget(self.fps_display)
        stats_layout.addWidget(self.latency_display)
        stats_layout.addWidget(self.frames_display)
        stats_layout.addWidget(self.quality_display)
        stats_layout.addWidget(self.codec_display)
        
        left_layout.addWidget(stats_group)
        
        # Telemetry
        self.telemetry_panel = QTextEdit()
        self.telemetry_panel.setReadOnly(True)
        self.telemetry_panel.setMaximumHeight(200)
        left_layout.addWidget(QLabel("Telemetry:"))
        left_layout.addWidget(self.telemetry_panel)
        
        left_layout.addStretch()
        
        # Stream display
        self.stream_label = StreamLabel(self)
        self.stream_label.setText('Waiting for stream...')
        self.stream_label.setAlignment(Qt.AlignCenter)
        self.stream_label.setStyleSheet("""
            QLabel {
                background-color: #0a0a0a;
                border: 2px solid #333;
                border-radius: 8px;
                color: #fff;
                font-size: 14px;
                font-family: 'Consolas', monospace;
            }
        """)
        
        # Add to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(self.stream_label, 1)
        
        # Connection state
        self.ws = None
        self.selected_sender = None
        
    def on_fps_changed(self, value):
        """Handle FPS slider change"""
        self._target_fps = value
        self.fps_label.setText(f"{value} FPS")
        print(f"[INFO] Target FPS changed to: {value}")
        
    def update_performance_stats(self):
        """Update performance statistics display"""
        # Calculate FPS
        if self._fps_timer.isValid() and self._fps_timer.elapsed() > 0:
            elapsed = self._fps_timer.elapsed() / 1000.0
            fps = self._fps_counter / elapsed
            self.fps_display.setText(f"FPS: {fps:.1f}")
        
        # Calculate average latency
        if self._frame_times:
            avg_latency = sum(self._frame_times) / len(self._frame_times)
            self.latency_display.setText(f"Latency: {avg_latency:.1f}ms")
        
        # Reset counter
        if self._fps_timer.elapsed() > 1000:
            self._fps_counter = 0
            self._fps_timer.restart()
            self._frame_times = []
        
    async def connect_to_server(self):
        """Connect to WebSocket server"""
        try:
            self.ws_url = self.url_input.text().strip()
            print(f"[INFO] Connecting to: {self.ws_url}")
            
            self.ws = await websockets.connect(self.ws_url)
            print("[INFO] Connected to server")
            
            # Start listening
            await self.listen_server()
            
        except Exception as e:
            print(f"[ERROR] Connection failed: {e}")
            self.telemetry_panel.append(f"Connection failed: {e}")
            
    async def listen_server(self):
        """Enhanced server listener for high-quality streams"""
        try:
            self._fps_timer.start()
            
            async for message in self.ws:
                # Handle binary messages as H.264 frames
                if isinstance(message, bytes):
                    frame_start_time = time.time() * 1000
                    
                    # Frame rate limiting
                    if self._last_frame_time > 0:
                        time_since_last = frame_start_time - self._last_frame_time
                        min_interval = 1000 / self._target_fps
                        
                        if time_since_last < min_interval:
                            continue  # Skip frame to maintain target FPS
                    
                    # Process high-quality frame
                    self.stream_label.setH264Stream(message)
                    
                    # Update counters
                    self._fps_counter += 1
                    current_time = time.time() * 1000
                    if self._last_frame_time > 0:
                        frame_time = current_time - self._last_frame_time
                        self._frame_times.append(frame_time)
                        if len(self._frame_times) > 10:
                            self._frame_times.pop(0)
                    self._last_frame_time = current_time
                    
                    # Update telemetry
                    self.frames_display.setText(f"Frames: {self._fps_counter}")
                    if len(message) > 0:
                        self.telemetry_panel.append(f"H.264 frame: {len(message)} bytes")
                        
                # Handle JSON messages
                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    if msg_type == 'active-machines':
                        self.sender_list.clear()
                        machines = data.get('machines', [])
                        self.sender_list.addItems(machines)
                        
                        if machines and not self.selected_sender:
                            self.sender_list.setCurrentIndex(0)
                            self.selected_sender = self.sender_list.itemText(0)
                            print(f"[INFO] Auto-selected sender: {self.selected_sender}")
                            
                    elif msg_type == 'system-info':
                        info = data.get('info')
                        if info and info.get('summary'):
                            self.telemetry_panel.append(f"System info: {info['summary']}")
                            
                except Exception as e:
                    print(f"[ERROR] Failed to parse message: {e}")
                    
        except Exception as e:
            print(f"[ERROR] Server listener error: {e}")
            self.telemetry_panel.append(f"Listener error: {e}")
            
    def closeEvent(self, event):
        """Clean up on close"""
        try:
            if self.ws:
                asyncio.create_task(self.ws.close())
        except:
            pass
            
        super().closeEvent(event)


def main():
    app = QAsyncApplication.instance()
    if app is None:
        app = QAsyncApplication(sys.argv)
    
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    window = HighQualityViewerWindow()
    window.show()
    
    with loop:
        loop.run_forever()


if __name__ == '__main__':
    main()
