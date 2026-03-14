import sys
from PyQt5.QtWidgets import QLabel
import asyncio
import websockets
import json
import os
import math
import time
import base64
import uuid
from qasync import QEventLoop, asyncSlot, QApplication as QAsyncApplication

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QTextEdit, QLineEdit, QSplitter, QGroupBox, QFormLayout, QFileDialog, QGraphicsDropShadowEffect, QStackedWidget, QStyle, QMessageBox, QFrame, QToolButton, QCheckBox, QBoxLayout, QSizePolicy, QScrollArea, QListWidget, QToolTip, QTabWidget, QListWidgetItem, QSlider, QSpinBox)
from PyQt5.QtGui import QPixmap, QImage, QColor, QPainter, QLinearGradient, QRadialGradient, QPainterPath, QIcon, QCursor, QTransform
from PyQt5.QtCore import Qt, QTimer, QSize, QPropertyAnimation, QEasingCurve, QPoint, QEvent, pyqtProperty, QRectF, QTime, QProcess, QThread, pyqtSignal

# Custom QLabel subclass for keyboard and mouse events
class StreamLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self._original_pixmap = None
        self._scaled_pixmap = None
        self._quality_mode = Qt.SmoothTransformation
        self._maintain_aspect = True

    def setHighQualityPixmap(self, pixmap):
        """Set pixmap with high-quality scaling"""
        self._original_pixmap = pixmap
        self._update_scaled_pixmap()
    
    def _update_scaled_pixmap(self):
        """Update scaled pixmap based on current size and quality settings"""
        if not self._original_pixmap or self._original_pixmap.isNull():
            return
        
        label_size = self.size()
        if label_size.width() <= 0 or label_size.height() <= 0:
            return
        
        # Choose scaling mode based on quality setting - show FULL image
        scaled_image = self._original_pixmap.scaled(
            label_size, 
            Qt.IgnoreAspectRatio,  # Don't crop - show full screen including taskbar
            self._quality_mode
        )
        
        self._scaled_pixmap = QPixmap.fromImage(scaled_image)
        super().setPixmap(self._scaled_pixmap)
    
    def resizeEvent(self, event):
        """Handle resize events to maintain image quality"""
        super().resizeEvent(event)
        self._update_scaled_pixmap()
    
    def setQualityMode(self, mode):
        """Set image quality mode"""
        self._quality_mode = mode
        self._update_scaled_pixmap()
    
    def setMaintainAspectRatio(self, maintain):
        """Set whether to maintain aspect ratio"""
        self._maintain_aspect = maintain
        self._update_scaled_pixmap()

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


class FrameProcessor(QThread):
    """Background thread for processing frames"""
    frame_processed = pyqtSignal(QPixmap)
    
    def __init__(self):
        super().__init__()
        self._frames_queue = []
        self._processing = False
        self._quality_mode = Qt.SmoothTransformation
        self._target_size = None
        
    def add_frame(self, image_data):
        """Add frame to processing queue"""
        self._frames_queue.append(image_data)
        
    def set_quality_mode(self, mode):
        """Set processing quality mode"""
        self._quality_mode = mode
        
    def set_target_size(self, size):
        """Set target size for scaling"""
        self._target_size = size
        
    def run(self):
        """Process frames in background"""
        self._processing = True
        while self._processing:
            if self._frames_queue:
                frame_data = self._frames_queue.pop(0)
                try:
                    image = QImage.fromData(frame_data)
                    if not image.isNull():
                        # Apply quality processing - show FULL image without cropping
                        if self._target_size:
                            scaled_image = image.scaled(
                                self._target_size,
                                Qt.IgnoreAspectRatio,  # Don't crop - show full image
                                self._quality_mode
                            )
                        else:
                            scaled_image = image
                        
                        pixmap = QPixmap.fromImage(scaled_image)
                        self.frame_processed.emit(pixmap)
                except Exception as e:
                    print(f"[ERROR] Frame processing failed: {e}")
            
            self.msleep(1)  # Small delay to prevent CPU overload
    
    def stop(self):
        """Stop processing"""
        self._processing = False


class ViewerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Enhanced streaming settings
        self._stream_quality = "High"  # Low, Medium, High, Ultra
        self._target_fps = 60
        self._frame_skip_enabled = True
        self._adaptive_quality = True
        self._buffer_size = 3  # Frame buffer size
        
        # Performance monitoring
        self._fps_counter = 0
        self._fps_timer = QTime()
        self._last_frame_time = 0
        self._frame_times = []
        
        # Frame buffer for smooth playback
        self._frame_buffer = []
        self._buffer_mutex = None
        
        # Initialize UI
        self.initUI()
        self.setup_quality_controls()
        
        # Start frame processor
        self.frame_processor = FrameProcessor()
        self.frame_processor.frame_processed.connect(self.on_frame_processed)
        self.frame_processor.start()
        
        # Performance monitoring timer
        self.performance_timer = QTimer(self)
        self.performance_timer.timeout.connect(self.update_performance_stats)
        self.performance_timer.start(1000)  # Update every second
        
    def initUI(self):
        """Initialize the user interface"""
        self.setWindowTitle("Monitor Relay - Enhanced Viewer")
        self.setGeometry(100, 100, 1200, 800)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout(central_widget)
        
        # Left panel for controls
        left_panel = QWidget()
        left_panel.setMaximumWidth(300)
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
        self.quality_combo.currentTextChanged.connect(self.on_quality_changed)
        quality_layout.addWidget(QLabel("Quality Preset:"))
        quality_layout.addWidget(self.quality_combo)
        
        # FPS control
        self.fps_slider = QSlider(Qt.Horizontal)
        self.fps_slider.setRange(15, 120)
        self.fps_slider.setValue(60)
        self.fps_slider.valueChanged.connect(self.on_fps_changed)
        quality_layout.addWidget(QLabel("Target FPS:"))
        quality_layout.addWidget(self.fps_slider)
        self.fps_label = QLabel("60 FPS")
        quality_layout.addWidget(self.fps_label)
        
        # Aspect ratio toggle
        self.aspect_checkbox = QCheckBox("Maintain Aspect Ratio")
        self.aspect_checkbox.setChecked(True)
        self.aspect_checkbox.toggled.connect(self.on_aspect_changed)
        quality_layout.addWidget(self.aspect_checkbox)
        
        # Adaptive quality
        self.adaptive_checkbox = QCheckBox("Adaptive Quality")
        self.adaptive_checkbox.setChecked(True)
        quality_layout.addWidget(self.adaptive_checkbox)
        
        left_layout.addWidget(quality_group)
        
        # Performance stats
        stats_group = QGroupBox("Performance")
        stats_layout = QVBoxLayout(stats_group)
        
        self.fps_display = QLabel("FPS: 0")
        self.latency_display = QLabel("Latency: 0ms")
        self.frames_display = QLabel("Frames: 0")
        self.quality_display = QLabel("Quality: High")
        
        stats_layout.addWidget(self.fps_display)
        stats_layout.addWidget(self.latency_display)
        stats_layout.addWidget(self.frames_display)
        stats_layout.addWidget(self.quality_display)
        
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
                background-color: #1a1a1a;
                border: 2px solid #333;
                border-radius: 8px;
                color: #fff;
                font-size: 14px;
            }
        """)
        
        # Add to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(self.stream_label, 1)
        
        # Connection state
        self.ws = None
        self.selected_sender = None
        
    def setup_quality_controls(self):
        """Setup quality control mappings"""
        self.quality_settings = {
            "Low": {
                "transform": Qt.FastTransformation,
                "compression": 70,
                "max_fps": 30,
                "buffer_size": 2
            },
            "Medium": {
                "transform": Qt.SmoothTransformation,
                "compression": 80,
                "max_fps": 45,
                "buffer_size": 3
            },
            "High": {
                "transform": Qt.SmoothTransformation,
                "compression": 90,
                "max_fps": 60,
                "buffer_size": 4
            },
            "Ultra": {
                "transform": Qt.SmoothTransformation,
                "compression": 95,
                "max_fps": 120,
                "buffer_size": 6
            }
        }
        
    def on_quality_changed(self, quality):
        """Handle quality preset change"""
        self._stream_quality = quality
        settings = self.quality_settings[quality]
        
        # Update frame processor
        self.frame_processor.set_quality_mode(settings["transform"])
        
        # Update FPS limit
        self._target_fps = settings["max_fps"]
        self.fps_slider.setValue(settings["max_fps"])
        
        # Update buffer size
        self._buffer_size = settings["buffer_size"]
        
        # Update stream label
        self.stream_label.setQualityMode(settings["transform"])
        
        # Update display
        self.quality_display.setText(f"Quality: {quality}")
        
        print(f"[INFO] Quality changed to: {quality}")
        
    def on_fps_changed(self, value):
        """Handle FPS slider change"""
        self._target_fps = value
        self.fps_label.setText(f"{value} FPS")
        print(f"[INFO] Target FPS changed to: {value}")
        
    def on_aspect_changed(self, checked):
        """Handle aspect ratio toggle"""
        self.stream_label.setMaintainAspectRatio(checked)
        print(f"[INFO] Maintain aspect ratio: {checked}")
        
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
        
    def on_frame_processed(self, pixmap):
        """Handle processed frame from background thread"""
        if pixmap and not pixmap.isNull():
            # Update frame counter
            self._fps_counter += 1
            
            # Calculate frame time
            current_time = time.time() * 1000
            if self._last_frame_time > 0:
                frame_time = current_time - self._last_frame_time
                self._frame_times.append(frame_time)
                # Keep only last 10 frame times
                if len(self._frame_times) > 10:
                    self._frame_times.pop(0)
            self._last_frame_time = current_time
            
            # Update display
            self.stream_label.setHighQualityPixmap(pixmap)
            self.frames_display.setText(f"Frames: {self._fps_counter}")
            
            # Adaptive quality adjustment
            if self._adaptive_quality and self.adaptive_checkbox.isChecked():
                self.adjust_quality_based_on_performance()
                
    def adjust_quality_based_on_performance(self):
        """Automatically adjust quality based on performance"""
        if len(self._frame_times) < 5:
            return
            
        avg_frame_time = sum(self._frame_times) / len(self._frame_times)
        target_frame_time = 1000 / self._target_fps
        
        # If performance is poor, reduce quality
        if avg_frame_time > target_frame_time * 1.5:
            if self._stream_quality == "Ultra":
                self.quality_combo.setCurrentText("High")
            elif self._stream_quality == "High":
                self.quality_combo.setCurrentText("Medium")
        # If performance is good, can increase quality
        elif avg_frame_time < target_frame_time * 0.8:
            if self._stream_quality == "Medium":
                self.quality_combo.setCurrentText("High")
            elif self._stream_quality == "Low":
                self.quality_combo.setCurrentText("Medium")
                
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
        """Enhanced server listener with quality optimization"""
        try:
            self._fps_timer.start()
            
            async for message in self.ws:
                # Handle binary messages as images
                if isinstance(message, bytes):
                    frame_start_time = time.time() * 1000
                    
                    # Frame rate limiting
                    if self._last_frame_time > 0:
                        time_since_last = frame_start_time - self._last_frame_time
                        min_interval = 1000 / self._target_fps
                        
                        if time_since_last < min_interval and self._frame_skip_enabled:
                            continue  # Skip frame to maintain target FPS
                    
                    # Process frame in background thread
                    self.frame_processor.add_frame(message)
                    
                    # Update telemetry
                    if len(message) > 0:
                        self.telemetry_panel.append(f"Frame received: {len(message)} bytes")
                        
                # Handle JSON messages
                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    if msg_type == 'active-machines':
                        self.sender_list.clear()
                        machines = data.get('machines', [])
                        self.sender_list.addItems(machines)
                        
                        # Auto-select first machine
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
            if self.frame_processor:
                self.frame_processor.stop()
                self.frame_processor.wait(1000)
            
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
    
    window = ViewerWindow()
    window.show()
    
    with loop:
        loop.run_forever()


if __name__ == '__main__':
    main()
