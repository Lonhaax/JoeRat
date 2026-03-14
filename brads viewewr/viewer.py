import sys
from PyQt5.QtWidgets import QLabel

# Custom QLabel subclass for keyboard and mouse events
class StreamLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)

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

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QTextEdit, QLineEdit, QSplitter, QGroupBox, QFormLayout, QFileDialog, QGraphicsDropShadowEffect, QStackedWidget, QStyle, QMessageBox, QFrame, QToolButton, QCheckBox, QBoxLayout, QSizePolicy, QScrollArea, QListWidget, QToolTip, QTabWidget, QListWidgetItem)
from PyQt5.QtGui import QPixmap, QImage, QColor, QPainter, QLinearGradient, QRadialGradient, QPainterPath, QIcon, QCursor
from PyQt5.QtCore import Qt, QTimer, QSize, QPropertyAnimation, QEasingCurve, QPoint, QEvent, pyqtProperty, QRectF, QTime, QProcess

class ViewerWindow(QMainWindow):
    def get_active_stream_label(self):
        label = self.stream_label
        if not label.hasFocus():
            label.setFocus()
        return label

    class BubbleOrbButton(QPushButton):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._hovered = False
            self._pressed = False
            self.setFlat(True)
            self.setCursor(Qt.PointingHandCursor)

        def enterEvent(self, event):
            self._hovered = True
            self.update()
            super().enterEvent(event)

        def leaveEvent(self, event):
            self._hovered = False
            self._pressed = False
            self.update()
            super().leaveEvent(event)

        def mousePressEvent(self, event):
            self._pressed = True
            self.update()
            super().mousePressEvent(event)

        def mouseReleaseEvent(self, event):
            self._pressed = False
            self.update()
            super().mouseReleaseEvent(event)

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(Qt.NoPen)

            outer = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
            if outer.width() <= 2 or outer.height() <= 2:
                return

            shift_y = 0.7 if self._pressed else 0.0
            if shift_y:
                outer.translate(0, shift_y)

            parent_window = self.window()

            # AKKA mode orb: neon core with hard white ring.
            if getattr(parent_window, 'akka_mode', False):
                akka_fill = QRadialGradient(
                    outer.center().x() - outer.width() * 0.16,
                    outer.center().y() - outer.height() * 0.18,
                    outer.width() * 0.62,
                )
                akka_fill.setColorAt(0.0, QColor(178, 255, 140, 255 if self._hovered else 240))
                akka_fill.setColorAt(0.45, QColor(92, 232, 66, 248 if self._hovered else 236))
                akka_fill.setColorAt(1.0, QColor(30, 126, 18, 252))
                painter.setBrush(akka_fill)
                painter.drawEllipse(outer)

                rim = QRadialGradient(outer.center(), outer.width() * 0.54)
                rim.setColorAt(0.76, QColor(255, 255, 255, 0))
                rim.setColorAt(1.0, QColor(255, 255, 255, 240))
                painter.setBrush(rim)
                painter.drawEllipse(outer)
                return

            # RGB mode orb: hue-reactive bubble using the global RGB hue.
            if getattr(parent_window, 'rgb_mode', False):
                hue = int(getattr(parent_window, '_rgb_hue', 0) % 360)
                c0 = QColor.fromHsv(hue, 40, 255, 248)
                c1 = QColor.fromHsv((hue + 22) % 360, 88, 248, 236)
                c2 = QColor.fromHsv((hue + 86) % 360, 128, 214, 228)
                c3 = QColor.fromHsv((hue + 160) % 360, 156, 150, 244)

                rgb_fill = QRadialGradient(
                    outer.center().x() - outer.width() * 0.18,
                    outer.center().y() - outer.height() * 0.22,
                    outer.width() * 0.64,
                    outer.center().x() - outer.width() * 0.24,
                    outer.center().y() - outer.height() * 0.28,
                )
                rgb_fill.setColorAt(0.0, c0)
                rgb_fill.setColorAt(0.24, c1)
                rgb_fill.setColorAt(0.58, c2)
                rgb_fill.setColorAt(1.0, c3)
                painter.setBrush(rgb_fill)
                painter.drawEllipse(outer)

                rgb_rim = QRadialGradient(outer.center(), outer.width() * 0.54)
                rgb_rim.setColorAt(0.72, QColor(255, 255, 255, 0))
                rgb_rim.setColorAt(1.0, QColor(255, 255, 255, 184))
                painter.setBrush(rgb_rim)
                painter.drawEllipse(outer)
                return

            if getattr(parent_window, 'noctua_mode', False):
                noctua_fill = QRadialGradient(
                    outer.center().x() - outer.width() * 0.20,
                    outer.center().y() - outer.height() * 0.24,
                    outer.width() * 0.64,
                    outer.center().x() - outer.width() * 0.26,
                    outer.center().y() - outer.height() * 0.30,
                )
                noctua_fill.setColorAt(0.0, QColor(255, 246, 236, 248))
                noctua_fill.setColorAt(0.26, QColor(237, 214, 186, 236))
                noctua_fill.setColorAt(0.62, QColor(170, 126, 90, 240))
                noctua_fill.setColorAt(1.0, QColor(101, 48, 36, 248))
                painter.setBrush(noctua_fill)
                painter.drawEllipse(outer)

                noctua_rim = QRadialGradient(outer.center(), outer.width() * 0.54)
                noctua_rim.setColorAt(0.72, QColor(255, 255, 255, 0))
                noctua_rim.setColorAt(1.0, QColor(255, 241, 225, 188))
                painter.setBrush(noctua_rim)
                painter.drawEllipse(outer)
                return

            # Outer shell depth.
            shell = QRadialGradient(
                outer.center().x() - outer.width() * 0.18,
                outer.center().y() - outer.height() * 0.22,
                outer.width() * 0.62,
                outer.center().x() - outer.width() * 0.26,
                outer.center().y() - outer.height() * 0.30,
            )
            shell.setColorAt(0.00, QColor(255, 255, 255, 210 if self._hovered else 190))
            shell.setColorAt(0.18, QColor(226, 242, 252, 194 if self._hovered else 174))
            shell.setColorAt(0.48, QColor(154, 194, 224, 176 if self._hovered else 160))
            shell.setColorAt(0.78, QColor(92, 138, 184, 192 if self._hovered else 176))
            shell.setColorAt(1.00, QColor(40, 74, 118, 214 if self._hovered else 198))
            painter.setBrush(shell)
            painter.drawEllipse(outer)

            # Glass rim ring.
            ring = QRadialGradient(outer.center(), outer.width() * 0.52)
            ring.setColorAt(0.68, QColor(255, 255, 255, 0))
            ring.setColorAt(0.86, QColor(236, 246, 255, 108 if self._hovered else 92))
            ring.setColorAt(1.00, QColor(255, 255, 255, 176 if self._hovered else 154))
            painter.setBrush(ring)
            painter.drawEllipse(outer)

            # Inner refracted body.
            inner = outer.adjusted(4.0, 4.0, -4.0, -4.0)
            inner_fill = QRadialGradient(
                inner.center().x() - inner.width() * 0.20,
                inner.center().y() - inner.height() * 0.22,
                inner.width() * 0.66,
                inner.center().x() - inner.width() * 0.24,
                inner.center().y() - inner.height() * 0.28,
            )
            inner_fill.setColorAt(0.00, QColor(255, 255, 255, 164 if self._hovered else 144))
            inner_fill.setColorAt(0.30, QColor(216, 238, 250, 148 if self._hovered else 132))
            inner_fill.setColorAt(0.66, QColor(132, 178, 212, 134 if self._hovered else 120))
            inner_fill.setColorAt(1.00, QColor(62, 102, 148, 154 if self._hovered else 138))
            painter.setBrush(inner_fill)
            painter.drawEllipse(inner)

            # Main specular highlight.
            spec_main = QRectF(
                outer.left() + outer.width() * 0.18,
                outer.top() + outer.height() * 0.10,
                outer.width() * 0.38,
                outer.height() * 0.26,
            )
            hl_main = QRadialGradient(spec_main.center(), spec_main.width() * 0.62)
            hl_main.setColorAt(0.0, QColor(255, 255, 255, 232 if self._hovered else 214))
            hl_main.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(hl_main)
            painter.drawEllipse(spec_main)

            # Secondary highlight for realism.
            spec_secondary = QRectF(
                outer.left() + outer.width() * 0.30,
                outer.top() + outer.height() * 0.30,
                outer.width() * 0.18,
                outer.height() * 0.12,
            )
            hl_secondary = QRadialGradient(spec_secondary.center(), spec_secondary.width() * 0.72)
            hl_secondary.setColorAt(0.0, QColor(255, 255, 255, 146 if self._hovered else 128))
            hl_secondary.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(hl_secondary)
            painter.drawEllipse(spec_secondary)

            # Bottom caustic glow.
            caustic = QRectF(
                outer.left() + outer.width() * 0.20,
                outer.top() + outer.height() * 0.62,
                outer.width() * 0.60,
                outer.height() * 0.26,
            )
            caustic_grad = QLinearGradient(caustic.left(), caustic.top(), caustic.left(), caustic.bottom())
            caustic_grad.setColorAt(0.0, QColor(188, 226, 250, 0))
            caustic_grad.setColorAt(0.55, QColor(188, 226, 250, 94 if self._hovered else 80))
            caustic_grad.setColorAt(1.0, QColor(188, 226, 250, 0))
            painter.setBrush(caustic_grad)
            painter.drawEllipse(caustic)

    class BubbleNavButton(QPushButton):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._is_hovered = False
            self._jump_offset = 12
            self._anchor_pos = QPoint(self.pos())
            self._anchor_valid = False
            self._jump_anim_running = False
            self._jump_anim = QPropertyAnimation(self, b'pos', self)
            self._jump_anim.setDuration(210)
            self._jump_anim.setEasingCurve(QEasingCurve.OutQuart)
            self._jump_anim.finished.connect(self._on_jump_finished)
            self._base_icon_size = 34
            self._lift_progress = 0.0
            self._lift_anim = QPropertyAnimation(self, b'liftProgress', self)
            self._lift_anim.setDuration(240)
            self._lift_anim.setEasingCurve(QEasingCurve.InOutCubic)
            self._shimmer_progress = -0.6
            self._shimmer_anim = QPropertyAnimation(self, b'shimmerProgress', self)
            self._shimmer_anim.setDuration(2600)
            self._shimmer_anim.setStartValue(-0.9)
            self._shimmer_anim.setEndValue(1.9)
            self._shimmer_anim.setLoopCount(-1)
            self._shimmer_anim.setEasingCurve(QEasingCurve.InOutQuad)
            self._shimmer_phase = (id(self) % 997) / 997.0 * math.tau
            self._active_line_opacity = 0.0
            self._active_line_anim = QPropertyAnimation(self, b'activeLineOpacity', self)
            self._active_line_anim.setDuration(300)
            self._active_line_anim.setEasingCurve(QEasingCurve.InOutCubic)

        def showEvent(self, event):
            if not self._is_hovered:
                self._anchor_pos = QPoint(self.pos())
                self._anchor_valid = True
            super().showEvent(event)

        def moveEvent(self, event):
            if not self._jump_anim_running and not self._is_hovered:
                self._anchor_pos = QPoint(self.pos())
                self._anchor_valid = True
            super().moveEvent(event)

        def _on_jump_finished(self):
            self._jump_anim_running = False
            if not self._is_hovered:
                self._anchor_pos = QPoint(self.pos())
                self._anchor_valid = True

        def enterEvent(self, event):
            if getattr(self.window(), 'reduced_effects_mode', False):
                self._is_hovered = True
                super().enterEvent(event)
                return
            if self._is_hovered:
                super().enterEvent(event)
                return
            self._is_hovered = True
            if not self._anchor_valid:
                self._anchor_pos = QPoint(self.pos())
                self._anchor_valid = True
            self._jump_anim_running = True
            self._jump_anim.stop()
            self._jump_anim.setStartValue(self.pos())
            self._jump_anim.setEndValue(QPoint(self._anchor_pos.x(), self._anchor_pos.y() - self._jump_offset))
            self._jump_anim.start()
            self._lift_anim.stop()
            self._lift_anim.setStartValue(self._lift_progress)
            self._lift_anim.setEndValue(1.0)
            self._lift_anim.start()
            super().enterEvent(event)

        def leaveEvent(self, event):
            if getattr(self.window(), 'reduced_effects_mode', False):
                self._is_hovered = False
                super().leaveEvent(event)
                return
            self._is_hovered = False
            if not self._anchor_valid:
                self._anchor_pos = QPoint(self.pos())
                self._anchor_valid = True
            self._jump_anim_running = True
            self._jump_anim.stop()
            self._jump_anim.setStartValue(self.pos())
            self._jump_anim.setEndValue(QPoint(self._anchor_pos.x(), self._anchor_pos.y()))
            self._jump_anim.start()
            self._lift_anim.stop()
            self._lift_anim.setStartValue(self._lift_progress)
            self._lift_anim.setEndValue(0.0)
            self._lift_anim.start()
            super().leaveEvent(event)

        def get_lift_progress(self):
            return self._lift_progress

        def set_lift_progress(self, value):
            self._lift_progress = max(0.0, min(1.0, float(value)))
            # Keep hover growth bounded so icons never exceed their slot.
            icon_px = int(self._base_icon_size + (8 * self._lift_progress))
            max_icon_px = max(16, min(self.width(), self.height()) - 8)
            icon_px = min(icon_px, max_icon_px)
            self.setIconSize(QSize(icon_px, icon_px))

            effect = self.graphicsEffect()
            if isinstance(effect, QGraphicsDropShadowEffect):
                effect.setYOffset(6 - (6 * self._lift_progress))
                effect.setBlurRadius(18 + (10 * self._lift_progress))
                effect.setColor(QColor(0, 0, 0, int(130 + (55 * self._lift_progress))))
            self.update()

        liftProgress = pyqtProperty(float, fget=get_lift_progress, fset=set_lift_progress)

        def set_active(self, is_active):
            self._active_line_anim.stop()
            self._active_line_anim.setStartValue(self._active_line_opacity)
            self._active_line_anim.setEndValue(1.0 if is_active else 0.0)
            self._active_line_anim.start()

        def get_active_line_opacity(self):
            return self._active_line_opacity

        def set_active_line_opacity(self, value):
            self._active_line_opacity = max(0.0, min(1.0, float(value)))
            self.update()

        activeLineOpacity = pyqtProperty(float, fget=get_active_line_opacity, fset=set_active_line_opacity)

        def get_shimmer_progress(self):
            return self._shimmer_progress

        def set_shimmer_progress(self, value):
            self._shimmer_progress = value
            self.update()

        shimmerProgress = pyqtProperty(float, fget=get_shimmer_progress, fset=set_shimmer_progress)

        def paintEvent(self, event):
            super().paintEvent(event)
            if getattr(self.window(), 'reduced_effects_mode', False):
                return

            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(Qt.NoPen)

            rect = QRectF(self.rect().adjusted(0, 0, -1, -1))
            clip_path = QPainterPath()
            clip_path.addRoundedRect(rect, 3, 3)
            painter.setClipPath(clip_path)
            shimmer_strength = 1.0 if self._is_hovered else 0.24

            # Persistent full-surface gloss so shimmer effect always covers the full button area.
            base_gloss = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
            base_gloss.setColorAt(0.0, QColor(255, 255, 255, int(10 * shimmer_strength)))
            base_gloss.setColorAt(0.45, QColor(255, 255, 255, int(4 * shimmer_strength)))
            base_gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, base_gloss)

            # Use a wide sweep so the animated highlight occupies most of the button at once.
            band_width = max(24.0, rect.width() * 0.38)
            x0 = rect.left() + (rect.width() * self._shimmer_progress)
            pulse = 0.78 + 0.22 * math.sin((self._shimmer_progress * math.tau * 1.35) + self._shimmer_phase)
            gradient = QLinearGradient(x0 - band_width, rect.top(), x0 + band_width, rect.bottom())
            gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
            gradient.setColorAt(0.5, QColor(255, 255, 255, int(40 * pulse * shimmer_strength)))
            gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, gradient)

            # Secondary, softer sweep offset for non-uniform shimmer motion.
            x1 = rect.left() + (rect.width() * (self._shimmer_progress - 0.28))
            gradient2 = QLinearGradient(x1 - (band_width * 0.6), rect.top(), x1 + (band_width * 0.6), rect.bottom())
            gradient2.setColorAt(0.0, QColor(255, 255, 255, 0))
            gradient2.setColorAt(0.5, QColor(255, 255, 255, int(14 * pulse * shimmer_strength)))
            gradient2.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, gradient2)

            # Extra top crescent highlight to exaggerate dome curvature.
            crescent = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.top() + (rect.height() * 0.42))
            crescent.setColorAt(0.0, QColor(255, 255, 255, int(42 * shimmer_strength)))
            crescent.setColorAt(1.0, QColor(255, 255, 255, 0))
            crescent_path = QPainterPath()
            crescent_path.addRoundedRect(QRectF(rect.left() + (rect.width() * 0.03), rect.top() + (rect.height() * 0.04), rect.width() * 0.94, rect.height() * 0.36), 3, 3)
            painter.fillPath(crescent_path, crescent)

            # Lift halo to make hover animation visibly "pop" without moving layout geometry.
            glow_alpha = int(64 * self._lift_progress)
            if glow_alpha > 0:
                glow = QRadialGradient(self.width() * 0.5, self.height() * 0.48, self.width() * 0.58)
                glow.setColorAt(0.0, QColor(255, 255, 255, glow_alpha))
                glow.setColorAt(0.55, QColor(255, 255, 255, int(glow_alpha * 0.28)))
                glow.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.fillPath(clip_path, glow)

            # Active taskbar indicator line (fades in/out).
            if self._active_line_opacity > 0.01:
                line_w = int(self.width() * 0.80)
                line_x = (self.width() - line_w) // 2
                line_y = self.height() - 6
                line_h = 4
                painter.setOpacity(self._active_line_opacity)
                painter.setBrush(QColor(72, 196, 255))
                painter.drawRoundedRect(QRectF(line_x, line_y, line_w, line_h), 2, 2)
                painter.setOpacity(1.0)

    class ShimmerTaskbar(QWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._shimmer_progress = -0.8
            self._bar_shimmer_anim = QPropertyAnimation(self, b'shimmerProgress', self)
            self._bar_shimmer_anim.setDuration(9800)
            self._bar_shimmer_anim.setStartValue(-0.8)
            self._bar_shimmer_anim.setEndValue(1.8)
            self._bar_shimmer_anim.setLoopCount(-1)
            self._bar_shimmer_anim.setEasingCurve(QEasingCurve.InOutSine)
            self._bar_shimmer_anim.start()
            self._shimmer_phase = (id(self) % 991) / 991.0 * math.tau

        def get_shimmer_progress(self):
            return self._shimmer_progress

        def set_shimmer_progress(self, value):
            self._shimmer_progress = value
            self.update()

        shimmerProgress = pyqtProperty(float, fget=get_shimmer_progress, fset=set_shimmer_progress)

        def paintEvent(self, event):
            super().paintEvent(event)
            if getattr(self.window(), 'reduced_effects_mode', False):
                return
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(Qt.NoPen)

            rect = self.rect().adjusted(2, 2, -2, -2)
            if getattr(self.window(), 'akka_mode', False):
                painter.setBrush(QColor(0, 0, 0))
                painter.drawRoundedRect(QRectF(rect), 10, 10)
                return
            if getattr(self.window(), 'noctua_mode', False):
                # In bottom-taskbar mode, let individual button styles carry NOCTUA chrome.
                if not getattr(self.window(), 'taskbar_left_mode', False):
                    return
                painter.setBrush(QColor('#E7CEB5'))
                painter.drawRoundedRect(QRectF(rect), 10, 10)
                rim_pen = QColor('#653024')
                rim_pen.setAlpha(180)
                painter.setPen(rim_pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
                return

            clip_path = QPainterPath()
            clip_path.addRoundedRect(QRectF(rect), 10, 10)
            painter.setClipPath(clip_path)

            # Inner top edge shadow to simulate a slightly raised bar profile.
            inner_shadow = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.top() + 8)
            inner_shadow.setColorAt(0.0, QColor(0, 0, 0, 20))
            inner_shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), 8), inner_shadow)

            # Subtle glossy top reflection band.
            reflection = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.top() + (rect.height() * 0.45))
            reflection.setColorAt(0.0, QColor(255, 255, 255, 16))
            reflection.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, reflection)

            band_width = max(80.0, rect.width() * 0.24)
            x0 = rect.left() + rect.width() * self._shimmer_progress
            pulse = 0.72 + 0.28 * math.sin((self._shimmer_progress * math.tau * 1.2) + self._shimmer_phase)
            gradient = QLinearGradient(x0 - band_width, rect.top(), x0 + band_width, rect.bottom())
            gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
            gradient.setColorAt(0.5, QColor(255, 255, 255, int(14 * pulse)))
            gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, gradient)

            x1 = rect.left() + rect.width() * (self._shimmer_progress - 0.42)
            gradient2 = QLinearGradient(x1 - (band_width * 0.55), rect.top(), x1 + (band_width * 0.55), rect.bottom())
            gradient2.setColorAt(0.0, QColor(255, 255, 255, 0))
            gradient2.setColorAt(0.5, QColor(255, 255, 255, int(8 * pulse)))
            gradient2.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, gradient2)

            top_gloss = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.top() + rect.height() * 0.45)
            top_gloss.setColorAt(0.0, QColor(255, 255, 255, int(14 * pulse)))
            top_gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, top_gloss)

    class ShimmerGlassPanel(QWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._shimmer_progress = -1.0
            self._panel_shimmer_anim = QPropertyAnimation(self, b'shimmerProgress', self)
            self._panel_shimmer_anim.setDuration(6200)
            self._panel_shimmer_anim.setStartValue(-1.0)
            self._panel_shimmer_anim.setEndValue(2.0)
            self._panel_shimmer_anim.setLoopCount(-1)
            self._panel_shimmer_anim.setEasingCurve(QEasingCurve.InOutSine)
            self._panel_shimmer_anim.start()
            self._shimmer_phase = (id(self) % 983) / 983.0 * math.tau

        def get_shimmer_progress(self):
            return self._shimmer_progress

        def set_shimmer_progress(self, value):
            self._shimmer_progress = value
            self.update()

        shimmerProgress = pyqtProperty(float, fget=get_shimmer_progress, fset=set_shimmer_progress)

        def paintEvent(self, event):
            super().paintEvent(event)
            if getattr(self.window(), 'reduced_effects_mode', False):
                return
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(Qt.NoPen)

            rect = self.rect().adjusted(2, 2, -2, -2)
            if getattr(self.window(), 'akka_mode', False):
                painter.setBrush(QColor(0, 0, 0))
                painter.setPen(QColor(255, 255, 255))
                painter.drawRoundedRect(QRectF(rect), 12, 12)
                return
            if getattr(self.window(), 'noctua_mode', False):
                painter.setBrush(QColor('#E7CEB5'))
                rim_pen = QColor('#653024')
                rim_pen.setAlpha(188)
                painter.setPen(rim_pen)
                painter.drawRoundedRect(QRectF(rect), 12, 12)
                return

            clip_path = QPainterPath()
            clip_path.addRoundedRect(QRectF(rect), 12, 12)
            painter.setClipPath(clip_path)

            band_width = max(70.0, rect.width() * 0.20)
            x0 = rect.left() + rect.width() * self._shimmer_progress
            pulse = 0.7 + 0.3 * math.sin((self._shimmer_progress * math.tau) + self._shimmer_phase)
            sheen = QLinearGradient(x0 - band_width, rect.top(), x0 + band_width, rect.bottom())
            sheen.setColorAt(0.0, QColor(255, 255, 255, 0))
            sheen.setColorAt(0.5, QColor(255, 255, 255, int(42 * pulse)))
            sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, sheen)

            x1 = rect.left() + rect.width() * (self._shimmer_progress - 0.35)
            sheen2 = QLinearGradient(x1 - (band_width * 0.5), rect.top(), x1 + (band_width * 0.5), rect.bottom())
            sheen2.setColorAt(0.0, QColor(255, 255, 255, 0))
            sheen2.setColorAt(0.5, QColor(255, 255, 255, int(18 * pulse)))
            sheen2.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, sheen2)

            top_gloss = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.top() + rect.height() * 0.38)
            top_gloss.setColorAt(0.0, QColor(255, 255, 255, int(44 * pulse)))
            top_gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, top_gloss)

    class ShimmerBackgroundRoot(QWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._shimmer_progress = -1.2
            self._bg_anim = QPropertyAnimation(self, b'shimmerProgress', self)
            self._bg_anim.setDuration(9800)
            self._bg_anim.setStartValue(-1.2)
            self._bg_anim.setEndValue(2.2)
            self._bg_anim.setLoopCount(-1)
            self._bg_anim.setEasingCurve(QEasingCurve.InOutSine)
            self._bg_anim.start()
            self._shimmer_phase = (id(self) % 977) / 977.0 * math.tau

        def get_shimmer_progress(self):
            return self._shimmer_progress

        def set_shimmer_progress(self, value):
            self._shimmer_progress = value
            self.update()

        shimmerProgress = pyqtProperty(float, fget=get_shimmer_progress, fset=set_shimmer_progress)

        def paintEvent(self, event):
            super().paintEvent(event)
            if getattr(self.window(), 'reduced_effects_mode', False):
                return
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(Qt.NoPen)

            rect = self.rect()
            if getattr(self.window(), 'akka_mode', False):
                painter.fillRect(rect, QColor(0, 0, 0))
                return
            if getattr(self.window(), 'noctua_mode', False):
                base = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
                base.setColorAt(0.0, QColor('#E7CEB5'))
                base.setColorAt(1.0, QColor('#dcc2a7'))
                painter.fillRect(rect, base)
                warm_sheen = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
                warm_sheen.setColorAt(0.0, QColor(101, 48, 36, 16))
                warm_sheen.setColorAt(1.0, QColor(101, 48, 36, 0))
                painter.fillRect(rect, warm_sheen)
                return

            band_width = max(140.0, rect.width() * 0.20)
            x0 = rect.left() + rect.width() * self._shimmer_progress
            pulse = 0.75 + 0.25 * math.sin((self._shimmer_progress * math.tau * 0.9) + self._shimmer_phase)
            sheen = QLinearGradient(x0 - band_width, rect.top(), x0 + band_width, rect.bottom())
            sheen.setColorAt(0.0, QColor(255, 255, 255, 0))
            sheen.setColorAt(0.5, QColor(255, 255, 255, int(20 * pulse)))
            sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, sheen)

            x1 = rect.left() + rect.width() * (self._shimmer_progress - 0.52)
            sheen2 = QLinearGradient(x1 - (band_width * 0.45), rect.top(), x1 + (band_width * 0.45), rect.bottom())
            sheen2.setColorAt(0.0, QColor(255, 255, 255, 0))
            sheen2.setColorAt(0.5, QColor(255, 255, 255, int(8 * pulse)))
            sheen2.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(rect, sheen2)

    class StreamLabel(QLabel):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setFocusPolicy(Qt.StrongFocus)
        def keyPressEvent(self, event):
            if hasattr(self.parent(), 'handle_key_press'):
                self.parent().handle_key_press(event)
        def keyReleaseEvent(self, event):
            if hasattr(self.parent(), 'handle_key_release'):
                self.parent().handle_key_release(event)
    # Removed custom eventFilter and keyPressEvent override. Keyboard events handled by stream_label only.
    def send_key(self):
        key = self.key_input.text().strip()
        if not key:
            self.show_warning('Key input is empty.')
            return
        if not self.selected_sender:
            self.show_warning('Select a sender before sending key.')
            return
        payload = {
            'type': 'remote-control',
            'action': 'key-press',
            'key': key,
            'machineId': self.selected_sender
        }
        asyncio.ensure_future(self.send_ws(payload))
        self.key_input.clear()
        self.show_warning('Key sent.')
    def send_chat_message(self):
        message = self.chat_input.text().strip()
        if not message:
            self.show_warning('Chat message is empty.')
            return
        if not self.selected_sender:
            self.show_warning('Select a sender before sending chat.')
            return
        payload = {
            'type': 'chat',
            'user': 'viewer',
            'message': message,
            'machineId': self.selected_sender
        }
        asyncio.ensure_future(self.send_ws(payload))
        self.chat_log.addItem(f"viewer: {message}")
        self.chat_input.clear()
        self.show_warning('Chat message sent.')
    def __init__(self):
        super().__init__()
        self._restart_in_progress = False
        self.reduced_effects_mode = False
        self._depth_effect_specs = []
        self._next_stream_frame_log_ts = 0.0
        self.rgb_mode = False
        self.akka_mode = False
        self.noctua_mode = False
        self.taskbar_left_mode = False
        # Compatibility layer: register widgets once and keep them consistent
        # across all mode combinations (normal/rgb/akka + dock variants).
        self._mode_aware_widgets = set()
        self._mode_icon_buttons = []
        self._last_mode_icon_tint_state = None
        self._shimmer_widgets_cache = None
        self._saved_left_dock_mode = False
        self._rgb_hue = 0
        self.rgb_timer = QTimer(self)
        self.rgb_timer.timeout.connect(self._update_rgb_cycle)
        # Keep stream focus with low-frequency checks to avoid constant UI churn.
        self.focus_timer = QTimer(self)
        self.focus_timer.timeout.connect(self._maintain_stream_focus)
        self.focus_timer.start(1500)
        # Initialize all UI widgets
        self.clipboard_input = QLineEdit()
        self.clipboard_send_btn = QPushButton('Send Clipboard')
        self.clipboard_send_btn.clicked.connect(self.send_clipboard_text)
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText('Select file to send...')
        self.file_select_btn = QPushButton('Browse')
        self.dest_input = QLineEdit()
        self.dest_input.setPlaceholderText('Destination path on sender (optional)')
        self.dest_select_btn = QPushButton('Choose Destination')
        self.file_send_btn = QPushButton('Send File')
        self.file_select_btn.clicked.connect(self.select_file)
        # Install event filter for key events
        self.installEventFilter(self)
        self.setFocus()
        print("[DEBUG] ViewerWindow __init__ focus set.")
        self.dest_select_btn.clicked.connect(self.choose_dest)
        self.file_send_btn.clicked.connect(self.send_file)
        self.selected_file_path = ''

        # Initialize widgets referenced in setup_ui and other methods
        from PyQt5.QtWidgets import QComboBox, QLabel, QTextEdit, QListWidget
        self.sender_list = QComboBox()
        self.selected_sender_label = QLabel('No sender selected')
        self.status_label = QLabel('Disconnected')
        self.chat_log = QListWidget()
        self.chat_input = QLineEdit()
        self.chat_send = QPushButton('Send')
        self.remote_panel = self.create_remote_panel()
        self.telemetry_panel = QTextEdit()
        self.telemetry_panel.setReadOnly(True)
        self.stream_label = StreamLabel(self)
        self.stream_label.setText('Waiting for stream...')
        self.stream_label.setAlignment(Qt.AlignCenter)

        # Initialize connection settings
        self.ws_url = 'ws://vnc.jake.cash:3000'  # Default server address
        self.room_id = 'ops-room'
        self.secret = 'boi123'
        self.target_machine_id = ''
        self._load_persisted_ui_settings()
        self.ws = None
        self.loop = asyncio.get_event_loop()

        # File manager widgets (populated into the File Manager control page in setup_ui)
        self._fm_local_path = QLineEdit()
        self._fm_local_path.setPlaceholderText('Local path')
        self._fm_local_list = QListWidget()
        self._fm_remote_path = QLineEdit()
        self._fm_remote_path.setPlaceholderText('Remote path')
        self._fm_remote_list = QListWidget()
        self._fm_local_refresh_btn = QPushButton('↺')
        self._fm_local_refresh_btn.setFixedWidth(26)
        self._fm_local_up_btn = QPushButton('↑')
        self._fm_local_up_btn.setFixedWidth(26)
        self._fm_remote_refresh_btn = QPushButton('↺')
        self._fm_remote_refresh_btn.setFixedWidth(26)
        self._fm_remote_up_btn = QPushButton('↑')
        self._fm_remote_up_btn.setFixedWidth(26)
        self._fm_upload_btn = QPushButton('Upload ↑')
        self._fm_download_btn = QPushButton('Download ↓')
        self._fm_pending_download_path = None
        self._fm_local_path.setText(os.path.expanduser('~'))
        self._fm_remote_path.setText('C:\\')
        self._fm_local_list.itemDoubleClicked.connect(self._fm_handle_local_double_click)
        self._fm_local_refresh_btn.clicked.connect(self._fm_refresh_local)
        self._fm_local_up_btn.clicked.connect(self._fm_local_up)
        self._fm_remote_list.itemDoubleClicked.connect(self._fm_handle_remote_double_click)
        self._fm_remote_refresh_btn.clicked.connect(self._fm_refresh_remote)
        self._fm_remote_up_btn.clicked.connect(self._fm_remote_up)
        self._fm_upload_btn.clicked.connect(self._fm_upload)
        self._fm_download_btn.clicked.connect(self._fm_download)
        self._fm_remote_path.editingFinished.connect(self._fm_remote_path_changed)
        self._fm_refresh_local()

        self.setup_ui()
        self._tune_button_responsiveness()
        self.switch_to_dark_mode()
        if getattr(self, '_saved_left_dock_mode', False):
            # Defer dock restore until startup layout/style passes finish.
            QTimer.singleShot(0, self._restore_saved_dock_mode)
        self.enable_remote_control()
        self.connect_task = self.loop.create_task(self.connect_to_server())
        self.sender_list.currentIndexChanged.connect(self.handle_sender_select)
        self.chat_send.clicked.connect(self.send_chat_message)
        self.mouse_center_btn.clicked.connect(lambda: self.send_remote_command('mouse_center'))
        self.mouse_left_btn.clicked.connect(lambda: self.send_remote_command('mouse_left'))
        self.mouse_right_btn.clicked.connect(lambda: self.send_remote_command('mouse_right'))
        self.key_send_btn.clicked.connect(self.send_key)
        self.kill_pid_btn.clicked.connect(self.send_kill_pid)
        self.selected_sender = None

    def _restore_saved_dock_mode(self):
        if not getattr(self, '_saved_left_dock_mode', False):
            return
        if not hasattr(self, 'left_dock_toggle_btn'):
            return
        self.left_dock_toggle_btn.blockSignals(True)
        self.left_dock_toggle_btn.setChecked(True)
        self.left_dock_toggle_btn.blockSignals(False)
        self._set_taskbar_left_mode(True)

    def _tune_button_responsiveness(self):
        for btn in self.findChildren(QPushButton):
            btn.setAutoDefault(False)
            btn.setDefault(False)
            btn.setFocusPolicy(Qt.NoFocus)

        for btn in self.findChildren(QToolButton):
            btn.setFocusPolicy(Qt.NoFocus)

    def _set_depth_effects_enabled(self, enabled):
        for widget, alpha, blur, y_offset in self._depth_effect_specs:
            if widget is None:
                continue
            if enabled:
                shadow = QGraphicsDropShadowEffect(widget)
                shadow.setBlurRadius(blur)
                shadow.setXOffset(0)
                shadow.setYOffset(y_offset)
                shadow.setColor(QColor(0, 0, 0, alpha))
                widget.setGraphicsEffect(shadow)
            else:
                widget.setGraphicsEffect(None)

    def _set_reduced_effects_mode(self, enabled):
        self.reduced_effects_mode = bool(enabled)
        if hasattr(self, 'minimal_ui_btn'):
            self.minimal_ui_btn.blockSignals(True)
            self.minimal_ui_btn.setChecked(self.reduced_effects_mode)
            self.minimal_ui_btn.setText('Disable Minimal UI' if self.reduced_effects_mode else 'Enable Minimal UI')
            self.minimal_ui_btn.blockSignals(False)

        if self.reduced_effects_mode and hasattr(self, 'rgb_mode_checkbox') and self.rgb_mode_checkbox.isChecked():
            self.rgb_mode_checkbox.setChecked(False)

        for attr in ['_nav_shimmer_anim']:
            anim = getattr(self, attr, None)
            if isinstance(anim, QPropertyAnimation):
                if self.reduced_effects_mode:
                    anim.stop()
                else:
                    anim.start()

        if hasattr(self, 'rgb_timer'):
            if self.reduced_effects_mode:
                self.rgb_timer.stop()
            elif getattr(self, 'rgb_mode', False):
                self.rgb_timer.start(200)

        for widget in self.findChildren(QWidget):
            for anim_attr in ['_shimmer_anim', '_bar_shimmer_anim', '_panel_shimmer_anim', '_bg_anim', '_jump_anim', '_lift_anim', '_active_line_anim']:
                anim = getattr(widget, anim_attr, None)
                if isinstance(anim, QPropertyAnimation):
                    if self.reduced_effects_mode:
                        anim.stop()
                    elif anim_attr in ['_shimmer_anim', '_bar_shimmer_anim', '_panel_shimmer_anim', '_bg_anim']:
                        anim.start()
            widget.update()

        self._set_depth_effects_enabled(not self.reduced_effects_mode)

    def _register_mode_widget(self, widget):
        if widget is None:
            return
        self._mode_aware_widgets.add(widget)

    def _register_mode_icon_button(self, button):
        if button is None:
            return
        self._register_mode_widget(button)
        if not hasattr(button, '_default_icon'):
            button._default_icon = QIcon(button.icon())
        if button not in self._mode_icon_buttons:
            self._mode_icon_buttons.append(button)

    def _tint_icon(self, icon, size, color_hex):
        if icon is None:
            return QIcon()
        base = icon.pixmap(size, size)
        if base.isNull():
            return icon
        recolored = QPixmap(base.size())
        recolored.fill(Qt.transparent)
        painter = QPainter(recolored)
        painter.drawPixmap(0, 0, base)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(recolored.rect(), QColor(color_hex))
        painter.end()
        return QIcon(recolored)

    def _apply_mode_compatibility(self):
        mode_akka_value = 'true' if self.akka_mode else 'false'
        mode_rgb_value = 'true' if self.rgb_mode else 'false'
        dock_left_value = 'true' if self.taskbar_left_mode else 'false'

        for widget in list(self._mode_aware_widgets):
            if widget is None:
                continue
            if isinstance(widget, QPushButton):
                if widget.autoDefault():
                    widget.setAutoDefault(False)
                if widget.isDefault():
                    widget.setDefault(False)
                if widget.focusPolicy() != Qt.NoFocus:
                    widget.setFocusPolicy(Qt.NoFocus)
            elif isinstance(widget, QToolButton):
                if widget.focusPolicy() != Qt.NoFocus:
                    widget.setFocusPolicy(Qt.NoFocus)

            needs_restyle = False
            if widget.property('modeAkka') != mode_akka_value:
                widget.setProperty('modeAkka', mode_akka_value)
                needs_restyle = True
            if widget.property('modeRgb') != mode_rgb_value:
                widget.setProperty('modeRgb', mode_rgb_value)
                needs_restyle = True
            if widget.property('dockLeft') != dock_left_value:
                widget.setProperty('dockLeft', dock_left_value)
                needs_restyle = True

            if needs_restyle:
                widget.style().unpolish(widget)
                widget.style().polish(widget)

        # Tint/un-tint only when AKKA state changes to avoid repeated icon work.
        if self._last_mode_icon_tint_state != self.akka_mode:
            for btn in list(self._mode_icon_buttons):
                if btn is None:
                    continue
                if not hasattr(btn, '_default_icon'):
                    btn._default_icon = QIcon(btn.icon())
                if self.akka_mode:
                    icon_px = btn.iconSize().width() if btn.iconSize().width() > 0 else 16
                    btn.setIcon(self._tint_icon(btn._default_icon, icon_px, '#39FF14'))
                else:
                    btn.setIcon(btn._default_icon)
            self._last_mode_icon_tint_state = self.akka_mode

    def create_mode_button(self, text, on_click=None, tooltip=None):
        btn = QPushButton(text)
        btn.setObjectName('whiteTextButton')
        btn.setAutoDefault(False)
        btn.setDefault(False)
        btn.setFocusPolicy(Qt.NoFocus)
        if tooltip:
            btn.setToolTip(tooltip)
        if on_click is not None:
            btn.clicked.connect(on_click)
        self._register_mode_widget(btn)
        return btn

    def _maintain_stream_focus(self):
        if not hasattr(self, 'stream_label'):
            return
        if self._is_user_interacting_with_ui():
            return
        if self._is_text_input_focused():
            return
        if self.isActiveWindow() and not self.stream_label.hasFocus() and not self._panel_has_focus_child():
            self.stream_label.setFocus()

    def _is_text_input_focused(self):
        fw = QApplication.focusWidget()
        while fw is not None:
            if isinstance(fw, (QLineEdit, QTextEdit, QComboBox)):
                return True
            if fw is getattr(self, 'stream_label', None):
                return False
            fw = fw.parentWidget()
        return False

    def _is_user_interacting_with_ui(self):
        # Don't steal focus while the user is actively working with controls.
        if QApplication.mouseButtons() != Qt.NoButton:
            return True

        hovered = QApplication.widgetAt(QCursor.pos())
        if hovered is None:
            return False
        if hasattr(self, 'stream_label') and (hovered is self.stream_label or self.stream_label.isAncestorOf(hovered)):
            return False
        if hasattr(self, 'bubble_bar') and (hovered is self.bubble_bar or self.bubble_bar.isAncestorOf(hovered)):
            return True
        if hasattr(self, 'control_panel_container') and self.control_panel_container.isVisible():
            if hovered is self.control_panel_container or self.control_panel_container.isAncestorOf(hovered):
                return True

        return isinstance(hovered, (QPushButton, QToolButton, QLineEdit, QComboBox, QTextEdit, QListWidget))

    def choose_dest(self):
        folder_dialog = QFileDialog()
        folder_dialog.setFileMode(QFileDialog.Directory)
        folder_dialog.setOption(QFileDialog.ShowDirsOnly, True)
        dest_path = folder_dialog.getExistingDirectory(self, "Select Destination Folder")
        if dest_path:
            self.dest_input.setText(dest_path)

    def select_file(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Select File", "", "All Files (*.*)")
        if file_path:
            self.selected_file_path = file_path
            self.file_input.setText(file_path)

    def _ui_settings_path(self):
        return os.path.join(os.path.dirname(__file__), 'viewer_settings.json')

    def _load_persisted_ui_settings(self):
        self._saved_left_dock_mode = False
        settings_path = self._ui_settings_path()
        if not os.path.exists(settings_path):
            return
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._saved_left_dock_mode = bool(data.get('left_dock_mode', False))
        except Exception as e:
            print(f"[DEBUG] Failed to load UI settings: {e}")

    def _save_persisted_ui_settings(self):
        settings_path = self._ui_settings_path()
        data = {
            'left_dock_mode': bool(getattr(self, 'taskbar_left_mode', False)),
        }
        try:
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[DEBUG] Failed to save UI settings: {e}")

    def update_left_banner(self):
        banner_dir = os.path.dirname(__file__)
        preferred_candidates = [
            'left-banner.png',
            'left-banner.jpg',
            'left-banner.jpeg',
            'left-banner.webp',
            'left-banner.png.jpg',
        ]
        banner_path = ''
        for candidate in preferred_candidates:
            candidate_path = os.path.join(banner_dir, candidate)
            if os.path.exists(candidate_path):
                banner_path = candidate_path
                break

        if not banner_path:
            dynamic_candidates = []
            for name in os.listdir(banner_dir):
                lower_name = name.lower()
                if lower_name.startswith('left-banner') and lower_name.endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp')):
                    dynamic_candidates.append(name)
            if dynamic_candidates:
                dynamic_candidates.sort()
                banner_path = os.path.join(banner_dir, dynamic_candidates[0])

        banner_pixmap = QPixmap(banner_path) if banner_path else QPixmap()
        if not banner_pixmap.isNull():
            target_w = max(1, self.left_banner.width() - 8)
            target_h = max(1, self.left_banner.height() - 8)
            stretched = banner_pixmap.scaled(
                target_w,
                target_h,
                Qt.IgnoreAspectRatio,
                Qt.SmoothTransformation,
            )
            self.left_banner.setPixmap(stretched)
            self.left_banner.setText('')
        else:
            self.left_banner.setPixmap(QPixmap())
            self.left_banner.setText('Add left-banner.png or left-banner.jpg')

    def _show_control_panel(self):
        if not hasattr(self, 'control_panel_container') or not hasattr(self, '_panel_anim'):
            return
        if getattr(self, 'taskbar_left_mode', False):
            self.control_panel_container.show()
            return
        self._update_responsive_ui()
        self._panel_is_hidden = False
        if not self.control_panel_container.isVisible():
            self.control_panel_container.show()
        self._position_control_panel(getattr(self, '_panel_anchor_widget', None))
        self._panel_anim.stop()
        self._panel_anim.setStartValue(self.control_panel_container.height())
        self._panel_anim.setEndValue(self._bottom_panel_target_height())
        self._panel_anim.start()

    def _hide_control_panel(self):
        if not hasattr(self, 'control_panel_container') or not hasattr(self, '_panel_anim'):
            return
        if getattr(self, 'taskbar_left_mode', False):
            return
        if self._is_cursor_over_panel_region() or self._panel_has_focus_child():
            # Recheck shortly while user is still hovering/interacting.
            self._schedule_panel_hide(delay_ms=320)
            return
        self._panel_is_hidden = True
        self._panel_anim.stop()
        self._panel_anim.setStartValue(self.control_panel_container.height())
        self._panel_anim.setEndValue(0)
        self._panel_anim.start()

    def _force_hide_control_panel(self):
        if not hasattr(self, 'control_panel_container') or not hasattr(self, '_panel_anim'):
            return
        if getattr(self, 'taskbar_left_mode', False):
            return
        if hasattr(self, '_panel_hide_timer'):
            self._panel_hide_timer.stop()
        self._panel_is_hidden = True
        self._panel_anim.stop()
        self._panel_anim.setStartValue(self.control_panel_container.height())
        self._panel_anim.setEndValue(0)
        self._panel_anim.start()

    def _schedule_panel_hide(self, delay_ms=None):
        if getattr(self, 'taskbar_left_mode', False):
            return
        if hasattr(self, '_panel_hide_timer'):
            self._panel_hide_timer.start(self._panel_hide_delay_ms if delay_ms is None else max(120, int(delay_ms)))

    def _is_cursor_over_panel_region(self):
        hovered = QApplication.widgetAt(QCursor.pos())
        if hovered is None:
            return False

        for widget in [
            getattr(self, 'control_panel_container', None),
            getattr(self, 'bubble_bar', None),
        ]:
            if widget is None:
                continue
            if hovered is widget or widget.isAncestorOf(hovered):
                return True
        return False

    def _panel_has_focus_child(self):
        fw = QApplication.focusWidget()
        if fw is None:
            return False

        # Floating panel focus (normal bottom mode)
        if hasattr(self, 'control_panel_container'):
            if fw is self.control_panel_container or self.control_panel_container.isAncestorOf(fw):
                return True

        # Inline left-dock menu focus
        if hasattr(self, 'taskbar_program_container'):
            if fw is self.taskbar_program_container or self.taskbar_program_container.isAncestorOf(fw):
                return True

        # Some complex widgets focus internal children; keep typing-safe by checking ancestry both ways.
        if hasattr(self, 'control_panel_container') and hasattr(fw, 'isAncestorOf') and fw.isAncestorOf(self.control_panel_container):
            return True
        if hasattr(self, 'taskbar_program_container') and hasattr(fw, 'isAncestorOf') and fw.isAncestorOf(self.taskbar_program_container):
            return True
        return False

    def _position_control_panel(self, anchor_widget=None):
        if getattr(self, 'taskbar_left_mode', False):
            return
        if not hasattr(self, 'monitor_wall_widget') or not hasattr(self, 'bubble_bar'):
            return
        panel_w = self.control_panel_container.width()
        panel_h = max(1, self.control_panel_container.height())
        bounds = self.monitor_wall_widget.rect()

        if anchor_widget is not None and anchor_widget.isVisible():
            anchor_center_global = anchor_widget.mapToGlobal(anchor_widget.rect().center())
            anchor_center = self.monitor_wall_widget.mapFromGlobal(anchor_center_global)
            x = anchor_center.x() - (panel_w // 2)
        else:
            x = (bounds.width() - panel_w) // 2

        x = max(8, min(x, bounds.width() - panel_w - 8))
        if self.bubble_bar.parentWidget() is self.monitor_wall_widget:
            bubble_top = self.bubble_bar.geometry().top()
        else:
            bubble_top_global = self.bubble_bar.mapToGlobal(self.bubble_bar.rect().topLeft())
            bubble_top = self.monitor_wall_widget.mapFromGlobal(bubble_top_global).y()

        y = bubble_top - panel_h - 8
        y = max(8, min(y, bounds.height() - panel_h - 8))
        self.control_panel_container.move(x, y)

    def _on_panel_anim_value(self, value):
        height = max(0, int(value))
        self.control_panel_container.setFixedHeight(height)
        self._position_control_panel(getattr(self, '_panel_anchor_widget', None))

    def _on_panel_anim_finished(self):
        if getattr(self, '_panel_is_hidden', False):
            self.control_panel_container.hide()

    def _bottom_panel_min_width(self):
        # File Transfer needs more horizontal room for inputs/buttons.
        if hasattr(self, 'control_stack') and self.control_stack.currentIndex() == 3:
            return 320
        return 190

    def _bottom_panel_target_height(self):
        # File Transfer has more controls and needs extra height to avoid clipping.
        if hasattr(self, 'control_stack') and self.control_stack.currentIndex() == 3:
            return 220
        return self._panel_expanded_height

    def _update_responsive_ui(self):
        if not hasattr(self, 'bubble_bar'):
            return

        # Scale the popup panel to the available monitor page width.
        if hasattr(self, 'monitor_wall_widget') and hasattr(self, 'control_panel_container'):
            base_w = self.monitor_wall_widget.width() if self.monitor_wall_widget.width() > 0 else self.width()
            panel_w = int(base_w * 0.30)
            panel_w = max(self._bottom_panel_min_width(), min(360, panel_w))
            if self.control_panel_container.width() != panel_w:
                self.control_panel_container.setFixedWidth(panel_w)

            if hasattr(self, 'control_stack'):
                target_h = self._bottom_panel_target_height()
                min_h = max(130, target_h - 50)
                if self.control_stack.minimumHeight() != min_h:
                    self.control_stack.setMinimumHeight(min_h)
                if self.control_stack.maximumHeight() != target_h:
                    self.control_stack.setMaximumHeight(target_h)

            if hasattr(self, 'left_banner'):
                banner_w = max(220, min(336, panel_w - 24))
                if self.left_banner.width() != banner_w:
                    self.left_banner.setFixedWidth(banner_w)
                    self.update_left_banner()

        # Keep taskbar program buttons balanced on narrow and wide windows.
        if getattr(self, 'is_dark_mode', False) and hasattr(self, 'program_layout') and self.nav_buttons:
            if getattr(self, 'taskbar_left_mode', False):
                menu_w = self._left_menu_item_width()
                menu_inner_w = max(120, menu_w - 10)
                for btn in self.nav_buttons:
                    btn.setFixedSize(menu_inner_w, 22)
                    btn._base_icon_size = 16
                    btn.setIconSize(QSize(0, 0))
                self.bubble_bar.setFixedWidth(self._left_sidebar_width())
                if hasattr(self, 'taskbar_separator'):
                    self.taskbar_separator.setFixedWidth(self._left_sidebar_width())
                if hasattr(self, 'inline_dropdown_panels'):
                    for panel in self.inline_dropdown_panels:
                        panel.setFixedWidth(menu_inner_w)
                if hasattr(self, 'control_panel_container') and self.control_panel_container.parentWidget() is self.bubble_bar:
                    self.control_panel_container.setFixedWidth(menu_w)
                if hasattr(self, 'control_panel_container') and self.control_panel_container.isVisible():
                    self._position_control_panel(getattr(self, '_panel_anchor_widget', None))
                return
            count = len(self.nav_buttons)
            spacing = self.program_layout.spacing()
            margins = self.program_layout.contentsMargins()
            viewport_w = 0
            if hasattr(self, 'taskbar_program_scroll') and self.taskbar_program_scroll.viewport() is not None:
                viewport_w = self.taskbar_program_scroll.viewport().width()
            if viewport_w <= 0 and hasattr(self, 'center_taskbar_side'):
                viewport_w = self.center_taskbar_side.width()
            if viewport_w <= 0:
                viewport_w = self.bubble_bar.width() if self.bubble_bar.width() > 0 else self.width()

            usable_w = max(1, viewport_w - margins.left() - margins.right() - (spacing * max(0, count - 1)))
            slot_w = usable_w // max(1, count)
            # Keep labels readable in normal mode while avoiding right-edge clipping.
            if count >= 6:
                # More buttons (e.g. added File Manager) need narrower slots to avoid clipping.
                slot_w = max(102, min(122, slot_w))
                icon_px = 12 if slot_w < 110 else 13
            else:
                slot_w = max(120, min(132, slot_w))
                icon_px = 14 if slot_w < 114 else 16

            for btn in self.nav_buttons:
                btn.setFixedSize(slot_w, 32)
                btn._base_icon_size = icon_px
                btn.setIconSize(QSize(icon_px, icon_px))

        if hasattr(self, 'control_panel_container') and self.control_panel_container.isVisible():
            self._position_control_panel(getattr(self, '_panel_anchor_widget', None))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_responsive_ui()
        self.set_nav_shimmer_progress(getattr(self, '_nav_shimmer_progress', 0.0))

    def showEvent(self, event):
        super().showEvent(event)
        # Ensure taskbar button sizing runs after the first real layout pass.
        QTimer.singleShot(0, self._update_responsive_ui)
        QTimer.singleShot(60, self._update_responsive_ui)

    def _update_taskbar_clock(self):
        if hasattr(self, 'taskbar_clock_label'):
            if getattr(self, 'taskbar_left_mode', False):
                self.taskbar_clock_label.setText(QTime.currentTime().toString('h:mm AP'))
            else:
                self.taskbar_clock_label.setText(QTime.currentTime().toString('h:mm AP'))

    def _left_sidebar_width(self):
        base_w = self.width() if self.width() > 0 else 1280
        return max(200, min(300, int(base_w * 0.20)))

    def _left_menu_item_width(self):
        return max(165, self._left_sidebar_width() - 14)

    def get_nav_shimmer_progress(self):
        return getattr(self, '_nav_shimmer_progress', 0.0)

    def set_nav_shimmer_progress(self, value):
        self._nav_shimmer_progress = max(0.0, min(1.0, float(value)))
        if not hasattr(self, 'nav_buttons') or not self.nav_buttons:
            return
        if not hasattr(self, 'taskbar_program_container'):
            return

        container_w = max(1, self.taskbar_program_container.width())
        max_btn_w = max(btn.width() for btn in self.nav_buttons)
        sweep_span = container_w + (max_btn_w * 2)
        sweep_x = -max_btn_w + (self._nav_shimmer_progress * sweep_span)

        for btn in self.nav_buttons:
            local_progress = (sweep_x - btn.x()) / max(1.0, float(btn.width()))
            btn.shimmerProgress = local_progress 

    navShimmerProgress = pyqtProperty(float, fget=get_nav_shimmer_progress, fset=set_nav_shimmer_progress)

    def _set_dark_taskbar_mode(self, enabled):
        if not hasattr(self, 'bubble_bar'):
            return
        self._dark_taskbar_profile = bool(enabled)

        if hasattr(self, 'start_orb_btn'):
            self.start_orb_btn.setVisible(enabled)
        if hasattr(self, 'taskbar_separator'):
            self.taskbar_separator.setVisible(enabled)
        if hasattr(self, 'taskbar_tray_container'):
            self.taskbar_tray_container.setVisible(enabled)
        if hasattr(self, 'taskbar_clock_label'):
            self.taskbar_clock_label.setVisible(enabled)

        if enabled:
            self.bubble_layout.setContentsMargins(8, 0, 8, 0)
            self.bubble_layout.setSpacing(0)
            self.bubble_bar.setFixedHeight(40)
            for btn in self.nav_buttons:
                btn.setFixedSize(136, 32)
                btn.setIconSize(QSize(16, 16))
                btn._base_icon_size = 16
                btn._jump_offset = 0
            self._update_taskbar_clock()
            if hasattr(self, 'taskbar_clock_timer'):
                self.taskbar_clock_timer.start(1000)
        else:
            self.bubble_layout.setContentsMargins(16, 24, 16, 8)
            self.bubble_layout.setSpacing(2)
            self.bubble_bar.setMinimumHeight(0)
            self.bubble_bar.setMaximumHeight(16777215)
            for btn in self.nav_buttons:
                btn.setFixedSize(84, 84)
                btn.setIconSize(QSize(34, 34))
                btn._base_icon_size = 34
                btn._jump_offset = 12
            if hasattr(self, 'taskbar_clock_timer'):
                self.taskbar_clock_timer.stop()

        self._update_responsive_ui()

    def _set_taskbar_left_mode(self, enabled, persist=True):
        if not hasattr(self, 'bubble_bar'):
            return
        self.taskbar_left_mode = bool(enabled)
        self._sync_taskbar_container_dock_property()
        if hasattr(self, 'left_dock_toggle_btn'):
            self.left_dock_toggle_btn.blockSignals(True)
            self.left_dock_toggle_btn.setChecked(self.taskbar_left_mode)
            self.left_dock_toggle_btn.setProperty('active', 'true' if self.taskbar_left_mode else 'false')
            self.left_dock_toggle_btn.style().unpolish(self.left_dock_toggle_btn)
            self.left_dock_toggle_btn.style().polish(self.left_dock_toggle_btn)
            self.left_dock_toggle_btn.blockSignals(False)

        if self.taskbar_left_mode:
            menu_w = self._left_menu_item_width()
            if hasattr(self, 'central_layout'):
                self.central_layout.removeWidget(self.bubble_bar)
                self.central_layout.removeWidget(self.main_pages)
                self.central_layout.setDirection(QBoxLayout.LeftToRight)
                self.central_layout.addWidget(self.bubble_bar, 0)
                self.central_layout.addWidget(self.main_pages, 1)

            if hasattr(self, '_panel_hide_timer'):
                self._panel_hide_timer.stop()
            if hasattr(self, 'control_panel_container') and hasattr(self, 'monitor_wall_widget'):
                self.control_panel_container.hide()
                self.control_panel_container.setParent(self.monitor_wall_widget)
                self.control_panel_container.setFixedSize(460, 0)

            if hasattr(self, 'inline_dropdown_panels'):
                for i, page in enumerate(self.control_pages):
                    panel = self.inline_dropdown_panels[i]
                    panel_layout = panel.layout()
                    self.control_stack.removeWidget(page)
                    panel_layout.addWidget(page)
                    page.show()
                    self.program_layout.removeWidget(panel)
                    panel.setFixedWidth(max(120, menu_w - 10))
                    panel.setMinimumHeight(0)
                    panel.setMaximumHeight(16777215)
                    panel.show()
                    self.nav_buttons[i].setProperty('active', 'false')
                    self.nav_buttons[i].set_active(False)
                    self.nav_buttons[i].setProperty('leftHeader', 'true')
                    self.nav_buttons[i].setCheckable(False)
                    self.nav_buttons[i].style().unpolish(self.nav_buttons[i])
                    self.nav_buttons[i].style().polish(self.nav_buttons[i])

            # Rebuild left stack as permanent header + panel sections.
            if hasattr(self, 'inline_dropdown_panels'):
                for panel in self.inline_dropdown_panels:
                    self.program_layout.removeWidget(panel)
            while self.program_layout.count():
                self.program_layout.takeAt(0)
            for i, btn in enumerate(self.nav_buttons):
                self.program_layout.addWidget(btn, 0, Qt.AlignLeft)
                self.program_layout.addWidget(self.inline_dropdown_panels[i], 0, Qt.AlignLeft)

            # Move clock under the orb and let it occupy remaining vertical space.
            if hasattr(self, 'right_taskbar_layout') and hasattr(self, 'left_taskbar_layout'):
                # Rebuild top-left stack in a strict order.
                self.left_taskbar_layout.removeWidget(self.start_orb_btn)
                self.left_taskbar_layout.removeWidget(self.taskbar_tray_container)
                self.left_taskbar_layout.removeWidget(self.taskbar_separator)
                self.left_taskbar_layout.removeWidget(self.taskbar_clock_label)
                if hasattr(self, 'left_top_row'):
                    self.left_taskbar_layout.removeWidget(self.left_top_row)
                self.right_taskbar_layout.removeWidget(self.taskbar_clock_label)
                self.right_taskbar_layout.removeWidget(self.taskbar_separator)
                self.right_taskbar_layout.removeWidget(self.taskbar_tray_container)
                self.left_taskbar_layout.setDirection(QBoxLayout.TopToBottom)
                self.left_taskbar_layout.setSpacing(6)
                self.left_taskbar_layout.setContentsMargins(0, 0, 0, 0)

                if not hasattr(self, 'left_top_row'):
                    self.left_top_row = QWidget(self.left_taskbar_side)
                    self.left_top_row_layout = QHBoxLayout()
                    self.left_top_row_layout.setContentsMargins(0, 0, 0, 0)
                    self.left_top_row_layout.setSpacing(4)
                    self.left_top_row.setLayout(self.left_top_row_layout)

                while self.left_top_row_layout.count():
                    item = self.left_top_row_layout.takeAt(0)
                    if item.widget() is not None:
                        item.widget().setParent(None)
                self.left_top_row_layout.addWidget(self.taskbar_tray_container, 0, Qt.AlignLeft | Qt.AlignTop)
                self.left_top_row_layout.addStretch(1)
                self.left_top_row_layout.addWidget(self.taskbar_clock_label, 0, Qt.AlignRight | Qt.AlignTop)
                self.left_top_row.show()

                self.left_taskbar_layout.insertWidget(0, self.left_top_row, 0, Qt.AlignTop)
                self.left_taskbar_layout.insertWidget(1, self.start_orb_btn, 0, Qt.AlignHCenter | Qt.AlignTop)
                self.left_taskbar_layout.insertWidget(2, self.taskbar_separator, 0, Qt.AlignLeft | Qt.AlignTop)
                self.left_taskbar_side.setMinimumHeight(0)
                self.left_taskbar_side.setMaximumHeight(16777215)
                self.right_taskbar_side.hide()

            self.left_taskbar_side.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            self.bubble_layout.setAlignment(self.left_taskbar_side, Qt.AlignTop)
            self.bubble_layout.setAlignment(self.center_taskbar_side, Qt.AlignTop)
            self.bubble_layout.setAlignment(self.right_taskbar_side, Qt.AlignTop)
            self.bubble_layout.setStretch(0, 0)
            self.bubble_layout.setStretch(1, 1)
            self.bubble_layout.setStretch(2, 0)

            self.bubble_layout.setDirection(QBoxLayout.TopToBottom)
            self.program_layout.setDirection(QBoxLayout.TopToBottom)
            # This wrapper has side stretches for horizontal centering.
            # Keeping it horizontal avoids a large vertical gap around buttons.
            self.center_taskbar_layout.setDirection(QBoxLayout.LeftToRight)
            self.center_taskbar_layout.setAlignment(self.taskbar_program_scroll, Qt.AlignHCenter)
            self.right_taskbar_layout.setDirection(QBoxLayout.TopToBottom)
            self.tray_layout.setDirection(QBoxLayout.LeftToRight)

            # Keep the center wrapper removed in left mode; menu stack now lives under clock in left section.
            self.center_taskbar_layout.removeWidget(self.taskbar_program_scroll)
            self.bubble_layout.removeWidget(self.center_taskbar_side)
            self.center_taskbar_side.hide()
            self.bubble_layout.removeWidget(self.taskbar_program_scroll)
            self.bubble_layout.insertWidget(1, self.taskbar_program_scroll, 1)

            self.bubble_layout.setContentsMargins(6, 0, 6, 0)
            self.bubble_layout.setSpacing(0)
            self.program_layout.setContentsMargins(0, 0, 0, 0)
            self.program_layout.setSpacing(0)
            self.right_taskbar_layout.setSpacing(6)
            self.tray_layout.setSpacing(4)
            self.taskbar_program_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            self.taskbar_program_scroll.setMinimumHeight(0)
            self.taskbar_program_container.setMinimumWidth(0)
            self.taskbar_program_container.setMaximumWidth(16777215)
            self.taskbar_program_scroll.setWidgetResizable(True)
            self.taskbar_program_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.taskbar_program_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            self.bubble_bar.setFixedWidth(self._left_sidebar_width())
            self.bubble_bar.setMinimumHeight(0)
            self.bubble_bar.setMaximumHeight(16777215)
            self.bubble_bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

            self.taskbar_separator.setFrameShape(QFrame.HLine)
            self.taskbar_separator.setFixedHeight(2)
            self.taskbar_separator.setFixedWidth(self._left_sidebar_width())

            for btn in self.nav_buttons:
                btn.setFixedSize(max(120, menu_w - 10), 20)
                btn.setIcon(QIcon())
                btn.setIconSize(QSize(0, 0))

        else:
            if hasattr(self, 'central_layout'):
                self.central_layout.removeWidget(self.bubble_bar)
                self.central_layout.removeWidget(self.main_pages)
                self.central_layout.setDirection(QBoxLayout.TopToBottom)
                self.central_layout.addWidget(self.main_pages, 1)
                self.central_layout.addWidget(self.bubble_bar, 0, Qt.AlignBottom)

            if hasattr(self, 'control_panel_container') and hasattr(self, 'monitor_wall_widget'):
                self.program_layout.removeWidget(self.control_panel_container)
                self.bubble_layout.removeWidget(self.control_panel_container)
                self.control_panel_container.hide()
                self.control_panel_container.setParent(self.monitor_wall_widget)
                self.control_panel_container.setFixedSize(460, 0)
                self.control_panel_container.hide()

            if hasattr(self, 'inline_dropdown_panels'):
                for i, page in enumerate(self.control_pages):
                    panel = self.inline_dropdown_panels[i]
                    self.program_layout.removeWidget(panel)
                    panel.hide()
                    panel.layout().removeWidget(page)
                    self.control_stack.insertWidget(i, page)
                self.control_stack.setCurrentIndex(0)

            if hasattr(self, 'right_taskbar_layout') and hasattr(self, 'left_taskbar_layout'):
                self.left_taskbar_layout.removeWidget(self.taskbar_clock_label)
                self.right_taskbar_layout.removeWidget(self.taskbar_clock_label)
                self.left_taskbar_layout.removeWidget(self.taskbar_separator)
                self.left_taskbar_layout.removeWidget(self.taskbar_tray_container)
                self.left_taskbar_layout.removeWidget(self.start_orb_btn)
                if hasattr(self, 'left_top_row'):
                    self.left_taskbar_layout.removeWidget(self.left_top_row)
                    self.left_top_row_layout.removeWidget(self.taskbar_tray_container)
                    self.left_top_row_layout.removeWidget(self.taskbar_clock_label)
                    self.left_top_row.hide()
                self.left_taskbar_layout.setDirection(QBoxLayout.LeftToRight)
                self.left_taskbar_layout.setSpacing(0)
                self.left_taskbar_layout.addWidget(self.start_orb_btn, 0, Qt.AlignVCenter)
                self.right_taskbar_layout.insertWidget(0, self.taskbar_separator, 0, Qt.AlignVCenter)
                self.right_taskbar_layout.insertWidget(1, self.taskbar_tray_container, 0, Qt.AlignVCenter)
                self.right_taskbar_layout.addWidget(self.taskbar_clock_label, 0, Qt.AlignVCenter)
                self.taskbar_clock_label.setMinimumHeight(0)
                self.taskbar_clock_label.setMaximumHeight(16777215)
                self.taskbar_clock_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                self.taskbar_clock_label.setStyleSheet('')
                self.left_taskbar_side.setMinimumHeight(0)
                self.left_taskbar_side.setMaximumHeight(16777215)
                self.right_taskbar_side.show()

            self.bubble_bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

            self.bubble_layout.setAlignment(self.left_taskbar_side, Qt.AlignVCenter)
            self.bubble_layout.setAlignment(self.center_taskbar_side, Qt.AlignVCenter)
            self.bubble_layout.setAlignment(self.right_taskbar_side, Qt.AlignVCenter)
            self.bubble_layout.setStretch(0, 0)
            self.bubble_layout.setStretch(1, 1)
            self.bubble_layout.setStretch(2, 0)

            self.bubble_layout.setDirection(QBoxLayout.LeftToRight)
            self.program_layout.setDirection(QBoxLayout.LeftToRight)
            self.center_taskbar_layout.setDirection(QBoxLayout.LeftToRight)
            self.center_taskbar_layout.setAlignment(self.taskbar_program_scroll, Qt.AlignCenter)
            self.right_taskbar_layout.setDirection(QBoxLayout.LeftToRight)
            self.tray_layout.setDirection(QBoxLayout.LeftToRight)

            # Restore original center wrapper placement in bottom mode.
            self.bubble_layout.removeWidget(self.taskbar_program_scroll)
            self.center_taskbar_layout.insertWidget(1, self.taskbar_program_scroll, 0, Qt.AlignCenter)
            self.bubble_layout.removeWidget(self.center_taskbar_side)
            self.bubble_layout.insertWidget(1, self.center_taskbar_side, 1, Qt.AlignVCenter)
            self.center_taskbar_side.show()

            for btn in self.nav_buttons:
                btn.setProperty('leftHeader', 'false')
                btn.setCheckable(True)
                if hasattr(btn, '_default_icon'):
                    btn.setIcon(btn._default_icon)
                btn.setFixedSize(136, 32)
                btn._base_icon_size = 16
                btn.setIconSize(QSize(16, 16))
                btn.show()
                btn.style().unpolish(btn)
                btn.style().polish(btn)

            self.bubble_layout.setContentsMargins(8, 0, 8, 0)
            self.bubble_layout.setSpacing(0)
            self.program_layout.setContentsMargins(0, 0, 0, 0)
            self.program_layout.setSpacing(2)
            self.right_taskbar_layout.setSpacing(8)
            self.tray_layout.setSpacing(6)
            self.taskbar_program_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            self.taskbar_program_container.setMinimumWidth(0)
            self.taskbar_program_container.setMaximumWidth(16777215)
            self.taskbar_program_scroll.setWidgetResizable(True)
            self.taskbar_program_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.taskbar_program_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            self.bubble_bar.setMinimumWidth(0)
            self.bubble_bar.setMaximumWidth(16777215)
            self.bubble_bar.setFixedHeight(40)

            self.taskbar_separator.setFrameShape(QFrame.VLine)
            self.taskbar_separator.setFixedHeight(26)
            self.taskbar_separator.setFixedWidth(2)


        if persist:
            self._save_persisted_ui_settings()
        if self.rgb_mode:
            self.rgb_timer.start(200)
        self._set_left_dock_boxy_properties(self.taskbar_left_mode)
        self._apply_mode_compatibility()
        self._update_responsive_ui()
        self._position_control_panel(getattr(self, '_panel_anchor_widget', None))

    def _sync_taskbar_container_dock_property(self):
        dock_value = 'true' if getattr(self, 'taskbar_left_mode', False) else 'false'
        for container in [
            getattr(self, 'bubble_bar', None),
            getattr(self, 'taskbar_tray_container', None),
            getattr(self, 'taskbar_program_container', None),
            getattr(self, 'taskbar_program_scroll', None),
            getattr(self, 'taskbar_separator', None),
        ]:
            if container is None:
                continue
            if container.property('dockLeft') != dock_value:
                container.setProperty('dockLeft', dock_value)
                container.style().unpolish(container)
                container.style().polish(container)

    def _set_left_dock_boxy_properties(self, enabled):
        boxy_value = 'true' if enabled else 'false'
        for widget in self.findChildren((QPushButton, QToolButton, QLineEdit, QTextEdit, QComboBox, QListWidget, QFrame)):
            if isinstance(widget, QPushButton) and widget.objectName() == 'startOrbButton':
                continue
            if isinstance(widget, QFrame) and widget.objectName() != 'inlineDropdownPanel':
                continue
            if widget.property('leftBoxy') != boxy_value:
                widget.setProperty('leftBoxy', boxy_value)
                widget.style().unpolish(widget)
                widget.style().polish(widget)

        # Force the menu page containers to match squared left-dock panels.
        extra_widgets = []
        if hasattr(self, 'control_pages'):
            extra_widgets.extend(self.control_pages)
        if hasattr(self, 'control_stack'):
            extra_widgets.append(self.control_stack)
        if hasattr(self, 'control_panel_container'):
            extra_widgets.append(self.control_panel_container)
        for widget in extra_widgets:
            if widget is None:
                continue
            if widget.property('leftBoxy') != boxy_value:
                widget.setProperty('leftBoxy', boxy_value)
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    def eventFilter(self, watched, event):
        if hasattr(self, 'taskbar_tray_buttons'):
            tray_hover_widgets = list(self.taskbar_tray_buttons)
            if hasattr(self, 'left_dock_toggle_btn'):
                tray_hover_widgets.append(self.left_dock_toggle_btn)
            if watched in tray_hover_widgets:
                if event.type() == QEvent.Enter:
                    tooltip_text = watched.toolTip().strip() if hasattr(watched, 'toolTip') else ''
                    if tooltip_text:
                        QToolTip.showText(QCursor.pos(), tooltip_text, watched)
                elif event.type() == QEvent.Leave:
                    QToolTip.hideText()

        if hasattr(self, 'taskbar_program_scroll'):
            is_taskbar_scroll_obj = watched is self.taskbar_program_scroll
            is_taskbar_viewport = watched is self.taskbar_program_scroll.viewport()
            if (is_taskbar_scroll_obj or is_taskbar_viewport) and event.type() == QEvent.Wheel:
                if not getattr(self, 'taskbar_left_mode', False):
                    return True

        if hasattr(self, 'stream_label') and watched is self.stream_label:
            event_type = event.type()
            if event_type == QEvent.Enter:
                if hasattr(self, '_panel_hide_timer'):
                    self._panel_hide_timer.stop()
                self._force_hide_control_panel()
            elif event_type == QEvent.Leave:
                self._schedule_panel_hide()
            return super().eventFilter(watched, event)

        if hasattr(self, '_panel_watch_widgets') and watched in self._panel_watch_widgets:
            event_type = event.type()
            if watched in getattr(self, 'nav_buttons', []):
                if event_type in (QEvent.Leave, QEvent.FocusOut):
                    self._schedule_panel_hide()
            elif event_type in (QEvent.Enter, QEvent.FocusIn, QEvent.MouseButtonPress):
                self._show_control_panel()
                self._schedule_panel_hide()
            elif event_type in (QEvent.Leave, QEvent.FocusOut):
                self._schedule_panel_hide()
        elif hasattr(self, '_panel_input_widgets') and watched in self._panel_input_widgets:
            event_type = event.type()
            if event_type in (QEvent.Enter, QEvent.FocusIn, QEvent.MouseButtonPress, QEvent.KeyPress):
                if hasattr(self, '_panel_hide_timer'):
                    self._panel_hide_timer.stop()
            elif event_type in (QEvent.Leave, QEvent.FocusOut):
                self._schedule_panel_hide()
        return super().eventFilter(watched, event)

    def _apply_dark_mode_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #020202,
                    stop: 0.5 #0a0a0a,
                    stop: 1 #151515
                );
            }

            QWidget {
                color: #d5dbe6;
                font-family: "Palatino Linotype";
                font-size: 10.5pt;
            }

            QWidget#glassRoot {
                background: transparent;
            }

            QWidget#glassPanel,
            QWidget#glassPage,
            QStackedWidget#glassPanel,
            QWidget#controlPanelContainer,
            QTabWidget::pane {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(32, 32, 32, 0.93),
                    stop: 1 rgba(14, 14, 14, 0.95)
                );
                border: 1px solid rgba(166, 166, 166, 0.25);
                border-radius: 12px;
            }

            QWidget#bubbleBar {
                min-height: 40px;
                max-height: 40px;
                border-radius: 10px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(62, 62, 62, 0.58),
                    stop: 1 rgba(18, 18, 18, 0.84)
                );
                border: 1px solid rgba(174, 174, 174, 0.30);
            }

            QPushButton#startOrbButton {
                border-radius: 18px;
                border: 1px solid rgba(242, 248, 255, 0.98);
                background: qradialgradient(
                    cx: 0.33, cy: 0.24, radius: 1.02, fx: 0.32, fy: 0.23,
                    stop: 0 rgba(255, 255, 255, 252),
                    stop: 0.10 rgba(242, 250, 255, 248),
                    stop: 0.26 rgba(208, 232, 248, 238),
                    stop: 0.46 rgba(138, 186, 224, 232),
                    stop: 0.66 rgba(86, 136, 184, 240),
                    stop: 0.84 rgba(50, 84, 132, 246),
                    stop: 1 rgba(22, 40, 72, 252)
                );
            }

            QPushButton#startOrbButton:hover {
                background: qradialgradient(
                    cx: 0.31, cy: 0.22, radius: 1.03, fx: 0.30, fy: 0.21,
                    stop: 0 rgba(255, 255, 255, 255),
                    stop: 0.10 rgba(248, 253, 255, 252),
                    stop: 0.28 rgba(220, 240, 252, 246),
                    stop: 0.46 rgba(166, 206, 234, 242),
                    stop: 0.64 rgba(118, 166, 208, 246),
                    stop: 0.82 rgba(74, 116, 170, 250),
                    stop: 1 rgba(38, 66, 118, 252)
                );
            }

            QPushButton#startOrbButton:pressed {
                padding-top: 1px;
            }

            QWidget#taskbarProgramContainer {
                background: transparent;
                border: none;
            }

            QWidget#controlPanelContainer {
                border-radius: 10px;
            }

            QTabBar::tab {
                color: #dbe4f1;
                padding: 8px 14px;
                margin-right: 4px;
                border-radius: 8px;
                border: 1px solid rgba(146, 146, 146, 0.34);
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #363636,
                    stop: 1 #212121
                );
            }

            QTabBar::tab:selected {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #4a4a4a,
                    stop: 1 #2b2b2b
                );
                border: 1px solid rgba(188, 188, 188, 0.48);
            }

            QLabel#leftBanner,
            QLabel#streamSurface,
            QListWidget#glassInput,
            QTextEdit#glassInput,
            QLineEdit#glassInput,
            QComboBox#glassInput {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(34, 34, 34, 0.94),
                    stop: 0.22 rgba(24, 24, 24, 0.95),
                    stop: 0.7 rgba(14, 14, 14, 0.97),
                    stop: 1 rgba(8, 8, 8, 0.98)
                );
                border: 1px solid rgba(144, 144, 144, 0.36);
                border-radius: 10px;
                padding: 6px;
                color: #d6dde8;
                selection-background-color: #4b4b4b;
                selection-color: #ffffff;
            }

            QLabel {
                color: #d3dae6;
                background: transparent;
            }

            QPushButton {
                color: #e3e9f1;
                border-radius: 10px;
                border: 1px solid rgba(142, 142, 142, 0.36);
                padding: 8px 12px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #3a3a3a,
                    stop: 0.42 #272727,
                    stop: 1 #191919
                );
            }

            QPushButton:hover {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #4a4a4a,
                    stop: 0.42 #353535,
                    stop: 1 #232323
                );
            }

            QPushButton#bubbleNavButton {
                color: #f1f4f9;
                border-radius: 3px;
                border: 1px solid rgba(164, 164, 164, 0.42);
                padding: 0 10px 0 8px;
                text-align: left;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(60, 60, 60, 0.78),
                    stop: 1 rgba(26, 26, 26, 0.84)
                );
            }

            /* Bottom taskbar buttons need tighter content spacing when many items are present. */
            QPushButton#bubbleNavButton[dockLeft="false"] {
                padding: 0 6px 0 5px;
                font-size: 9.5pt;
            }

            QPushButton#bubbleNavButton:hover {
                border: 1px solid rgba(200, 200, 200, 0.72);
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(78, 78, 78, 0.84),
                    stop: 1 rgba(38, 38, 38, 0.86)
                );
            }

            QPushButton#bubbleNavButton[active="true"] {
                border: 1px solid rgba(174, 204, 240, 0.86);
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(72, 92, 120, 0.88),
                    stop: 1 rgba(42, 58, 78, 0.90)
                );
            }

            QPushButton#bubbleNavButton:pressed {
                padding-top: 1px;
                padding-bottom: 0px;
            }

            QPushButton#bubbleNavButton[leftHeader="true"] {
                border: none;
                border-radius: 0;
                padding: 4px 2px 2px 2px;
                text-align: left;
                color: #d9e6fb;
                font-size: 12px;
                font-weight: 600;
                background: transparent;
            }

            QPushButton#bubbleNavButton[leftHeader="true"]:hover,
            QPushButton#bubbleNavButton[leftHeader="true"]:pressed,
            QPushButton#bubbleNavButton[leftHeader="true"][active="true"] {
                border: none;
                background: transparent;
            }

            QFrame#inlineDropdownPanel {
                margin-top: -1px;
                border-top: none;
                border-left: 1px solid rgba(164, 164, 164, 0.42);
                border-right: 1px solid rgba(164, 164, 164, 0.42);
                border-bottom: 1px solid rgba(164, 164, 164, 0.42);
                border-bottom-left-radius: 7px;
                border-bottom-right-radius: 7px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(46, 46, 46, 0.82),
                    stop: 1 rgba(22, 22, 22, 0.86)
                );
            }

            QPushButton#whiteTextButton {
                color: #ffffff;
            }

            QFrame#uiSettingsBox {
                border: 1px solid rgba(176, 186, 204, 0.40);
                border-radius: 10px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(40, 40, 40, 0.70),
                    stop: 1 rgba(18, 18, 18, 0.78)
                );
                padding: 8px;
            }

            QFrame#connectionDetailsBox {
                border: 1px solid rgba(176, 186, 204, 0.40);
                border-radius: 10px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(40, 40, 40, 0.70),
                    stop: 1 rgba(18, 18, 18, 0.78)
                );
                padding: 8px;
            }

            QLabel#uiSettingsHeader {
                color: #e3ebf9;
                font-size: 10pt;
                font-weight: 700;
                letter-spacing: 0.4px;
                background: transparent;
                border: none;
                padding-bottom: 4px;
            }

            QLabel#connectionDetailsHeader {
                color: #e3ebf9;
                font-size: 10pt;
                font-weight: 700;
                letter-spacing: 0.4px;
                background: transparent;
                border: none;
                padding-bottom: 4px;
            }

            QPushButton#rgbModeToggleButton {
                color: #f4f8ff;
                border: 1px solid rgba(156, 200, 255, 0.62);
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(210, 80, 80, 0.80),
                    stop: 0.33 rgba(196, 158, 74, 0.82),
                    stop: 0.66 rgba(74, 158, 210, 0.82),
                    stop: 1 rgba(138, 90, 198, 0.84)
                );
            }

            QPushButton#rgbModeToggleButton:hover {
                border: 1px solid rgba(210, 230, 255, 0.90);
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(230, 100, 100, 0.88),
                    stop: 0.33 rgba(214, 178, 92, 0.90),
                    stop: 0.66 rgba(92, 176, 228, 0.90),
                    stop: 1 rgba(158, 110, 216, 0.92)
                );
            }

            QPushButton#rgbModeToggleButton:checked {
                border: 1px solid rgba(232, 246, 255, 0.98);
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(255, 124, 124, 0.94),
                    stop: 0.33 rgba(248, 204, 112, 0.95),
                    stop: 0.66 rgba(116, 208, 255, 0.95),
                    stop: 1 rgba(184, 140, 255, 0.96)
                );
            }

            QPushButton#akkaModeToggleButton {
                color: #39FF14;
                border: 1px solid #FFFFFF;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(18, 18, 18, 0.94),
                    stop: 1 rgba(0, 0, 0, 0.98)
                );
            }

            QPushButton#akkaModeToggleButton:hover,
            QPushButton#akkaModeToggleButton:checked {
                color: #7bff61;
                border: 1px solid #FFFFFF;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(24, 42, 24, 0.96),
                    stop: 1 rgba(0, 0, 0, 0.99)
                );
            }

            QPushButton#noctuaModeToggleButton {
                color: #2f1a13;
                border: 1px solid #653024;
                background: #dec3a6;
            }

            QPushButton#noctuaModeToggleButton:hover,
            QPushButton#noctuaModeToggleButton:checked {
                color: #f6eadf;
                border: 1px solid #653024;
                background: #653024;
            }

            QFrame#taskbarTraySeparator {
                background: rgba(188, 188, 188, 0.62);
                min-width: 2px;
                max-width: 2px;
            }

            QWidget#taskbarTrayContainer {
                background: transparent;
                border: none;
            }

            QScrollArea#taskbarProgramScroll {
                background: transparent;
                border: none;
            }

            QScrollArea#taskbarProgramScroll QScrollBar:vertical {
                background: rgba(18, 18, 18, 0.72);
                width: 5px;
                margin: 2px 0 2px 0;
                border: 1px solid rgba(148, 148, 148, 0.22);
                border-radius: 2px;
            }

            QScrollArea#taskbarProgramScroll QScrollBar::handle:vertical {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 rgba(162, 182, 208, 0.82),
                    stop: 1 rgba(118, 136, 162, 0.86)
                );
                min-height: 28px;
                border: 1px solid rgba(208, 220, 238, 0.44);
                border-radius: 2px;
            }

            QScrollArea#taskbarProgramScroll QScrollBar::handle:vertical:hover {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 rgba(186, 204, 226, 0.90),
                    stop: 1 rgba(132, 150, 178, 0.92)
                );
                border: 1px solid rgba(224, 236, 252, 0.66);
            }

            QScrollArea#taskbarProgramScroll QScrollBar::add-line:vertical,
            QScrollArea#taskbarProgramScroll QScrollBar::sub-line:vertical,
            QScrollArea#taskbarProgramScroll QScrollBar::add-page:vertical,
            QScrollArea#taskbarProgramScroll QScrollBar::sub-page:vertical {
                background: transparent;
                border: none;
                height: 0px;
            }

            QWidget#taskbarProgramViewport {
                background: transparent;
                border: none;
            }

            QWidget#taskbarProgramContainer {
                background: transparent;
                border: none;
            }

            QToolButton#trayIconButton {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(58, 58, 58, 0.72),
                    stop: 1 rgba(24, 24, 24, 0.80)
                );
                border: 1px solid rgba(150, 150, 150, 0.46);
                border-radius: 6px;
            }

            QToolButton#trayIconButton[active="true"] {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(95, 178, 255, 0.64),
                    stop: 1 rgba(38, 120, 214, 0.62)
                );
                border: 1px solid rgba(175, 223, 255, 0.86);
            }

            QLabel#taskbarClockLabel {
                color: #edf2f9;
                padding-left: 8px;
                padding-right: 2px;
                font-family: "Palatino Linotype";
                font-size: 9.5pt;
                background: transparent;
            }

            QLineEdit[leftBoxy="true"],
            QLineEdit#glassInput[leftBoxy="true"],
            QTextEdit[leftBoxy="true"],
            QTextEdit#glassInput[leftBoxy="true"],
            QComboBox[leftBoxy="true"],
            QComboBox#glassInput[leftBoxy="true"],
            QListWidget[leftBoxy="true"],
            QListWidget#glassInput[leftBoxy="true"],
            QWidget#glassPage[leftBoxy="true"],
            QWidget#glassPanel[leftBoxy="true"],
            QWidget#controlPanelContainer[leftBoxy="true"],
            QStackedWidget#glassPanel[leftBoxy="true"],
            QPushButton[leftBoxy="true"],
            QPushButton#whiteTextButton[leftBoxy="true"],
            QPushButton#bubbleNavButton[leftBoxy="true"],
            QToolButton#trayIconButton[leftBoxy="true"],
            QFrame#inlineDropdownPanel[leftBoxy="true"] {
                border-radius: 1px;
            }

            QPushButton#startOrbButton[leftBoxy="true"] {
                border-radius: 18px;
            }

            QFrame#inlineDropdownPanel[leftBoxy="true"] {
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }
        """)

    def _apply_rgb_overlay_stylesheet(self):
        hue = int(self._rgb_hue % 360)
        # Keep RGB mode colorful but less aggressive on brightness and saturation.
        accent = QColor.fromHsv(hue, 120, 210).name()
        accent_soft = QColor.fromHsv((hue + 24) % 360, 90, 190).name()
        accent_mid = QColor.fromHsv((hue + 72) % 360, 110, 170).name()
        accent_dark = QColor.fromHsv((hue + 128) % 360, 120, 95).name()
        text_color = QColor.fromHsv((hue + 180) % 360, 28, 232).name()

        left_mode = bool(getattr(self, 'taskbar_left_mode', False))
        if left_mode:
            # In left-dock mode, keep RGB away from taskbar/nav widgets to
            # avoid style-driven relayout and overlap.
            rgb_qss = """
                QWidget#glassPanel,
                QWidget#glassPage,
                QStackedWidget#glassPanel,
                QWidget#controlPanelContainer,
                QLabel#streamSurface,
                QLabel#leftBanner,
                QListWidget#glassInput,
                QTextEdit#glassInput,
                QLineEdit#glassInput,
                QComboBox#glassInput {{
                    color: {text_color};
                    border: 1px solid {accent};
                    background: qlineargradient(
                        x1: 0, y1: 0, x2: 1, y2: 1,
                        stop: 0 {accent_dark},
                        stop: 0.45 {accent_mid},
                        stop: 1 {accent_soft}
                    );
                }}

                QComboBox,
                QLineEdit,
                QTextEdit,
                QListWidget,
                QPushButton#whiteTextButton {{
                    border: 1px solid {accent};
                    color: {text_color};
                    background: qlineargradient(
                        x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 {accent_soft},
                        stop: 1 {accent_mid}
                    );
                }}

                QPushButton#startOrbButton {{
                    border: 1px solid {accent};
                    color: {text_color};
                    background: qradialgradient(
                        cx: 0.5, cy: 0.5, radius: 1.0,
                        stop: 0 {accent},
                        stop: 1 {accent_dark}
                    );
                }}

                QPushButton#startOrbButton:hover {{
                    background: qradialgradient(
                        cx: 0.48, cy: 0.48, radius: 1.0,
                        stop: 0 {accent_soft},
                        stop: 1 {accent_mid}
                    );
                }}

                QFrame#taskbarTraySeparator {{
                    background: rgba(188, 188, 188, 0.62);
                }}
            """.format(
                text_color=text_color,
                accent=accent,
                accent_soft=accent_soft,
                accent_mid=accent_mid,
                accent_dark=accent_dark,
            )
            self.setStyleSheet(self.styleSheet() + rgb_qss)
            return

        rgb_container_selector = """
            QWidget#glassPanel,
            QWidget#glassPage,
            QStackedWidget#glassPanel,
            QWidget#controlPanelContainer,
            QLabel#streamSurface,
            QLabel#leftBanner,
            QListWidget#glassInput,
            QTextEdit#glassInput,
            QLineEdit#glassInput,
            QComboBox#glassInput
        """
        if not left_mode:
            rgb_container_selector += ",\n            QWidget#bubbleBar,\n            QWidget#taskbarTrayContainer"

        rgb_control_selector = "QComboBox,\n            QLineEdit,\n            QTextEdit,\n            QListWidget"
        if not left_mode:
            rgb_control_selector = "QPushButton,\n            QToolButton,\n            " + rgb_control_selector

        rgb_nav_block = """
            {rgb_nav_selector} {{
                border: 1px solid {accent};
                background: qradialgradient(
                    cx: 0.5, cy: 0.5, radius: 1.0,
                    stop: 0 {accent},
                    stop: 1 {accent_dark}
                );
            }}
        """.format(
            rgb_nav_selector="QPushButton#bubbleNavButton,\n            QToolButton#trayIconButton,\n            QPushButton#startOrbButton",
            accent=accent,
            accent_dark=accent_dark,
        ) if not left_mode else ""

        left_header_guard = """
            QPushButton#bubbleNavButton[leftHeader="true"] {{
                border: none;
                background: transparent;
                color: {text_color};
            }}

            QPushButton#bubbleNavButton[leftHeader="true"]:hover,
            QPushButton#bubbleNavButton[leftHeader="true"]:pressed,
            QPushButton#bubbleNavButton[leftHeader="true"][active="true"] {{
                border: none;
                background: transparent;
            }}

            QWidget#taskbarProgramContainer {{
                border: none;
                background: transparent;
            }}

            QWidget#taskbarTrayContainer,
            QWidget#bubbleBar,
            QScrollArea#taskbarProgramScroll,
            QWidget#taskbarProgramViewport {{
                border: none;
                background: transparent;
            }}

            QLabel#taskbarClockLabel {{
                background: transparent;
            }}

            QFrame#inlineDropdownPanel {{
                border: 1px solid rgba(164, 164, 164, 0.42);
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(46, 46, 46, 0.82),
                    stop: 1 rgba(22, 22, 22, 0.86)
                );
            }}
        """ if left_mode else ""

        rgb_qss = """
            QWidget {{
                color: {text_color};
            }}

            {rgb_container_selector} {{
                border: 1px solid {accent};
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 {accent_dark},
                    stop: 0.45 {accent_mid},
                    stop: 1 {accent_soft}
                );
            }}

            {rgb_control_selector} {{
                border: 1px solid {accent};
                color: {text_color};
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 {accent_soft},
                    stop: 1 {accent_mid}
                );
            }}

            {rgb_nav_block}

            {left_header_guard}

            QFrame#taskbarTraySeparator {{
                background: {accent};
            }}
        """.format(
            text_color=text_color,
            accent=accent,
            accent_soft=accent_soft,
            accent_mid=accent_mid,
            accent_dark=accent_dark,
            rgb_container_selector=rgb_container_selector,
            rgb_control_selector=rgb_control_selector,
            rgb_nav_block=rgb_nav_block,
            left_header_guard=left_header_guard,
        )

        self.setStyleSheet(self.styleSheet() + rgb_qss)

    def _apply_akka_overlay_stylesheet(self):
        akka_qss = """
            * {
                color: #39FF14;
                background-color: #000000;
                border: none;
                selection-color: #000000;
                selection-background-color: #39FF14;
            }

            QWidget,
            QFrame,
            QGroupBox,
            QStackedWidget,
            QListWidget,
            QTextEdit,
            QLineEdit,
            QComboBox,
            QPushButton,
            QToolButton,
            QLabel,
            QCheckBox {
                background-color: #000000;
                color: #39FF14;
                border: none;
            }

            QLabel,
            QCheckBox,
            QWidget#taskbarTrayContainer,
            QWidget#taskbarProgramContainer,
            QWidget#bubbleBar,
            QLabel#taskbarClockLabel,
            QWidget#taskbarProgramViewport,
            QScrollArea#taskbarProgramScroll,
            QToolButton#trayIconButton {
                border: none;
            }

            QWidget#glassPanel,
            QWidget#glassPage,
            QStackedWidget#glassPanel,
            QWidget#controlPanelContainer,
            QFrame#connectionDetailsBox,
            QFrame#uiSettingsBox,
            QLabel#streamSurface,
            QFrame#inlineDropdownPanel,
            QLineEdit,
            QLineEdit#glassInput,
            QTextEdit,
            QTextEdit#glassInput,
            QComboBox,
            QComboBox#glassInput,
            QListWidget,
            QListWidget#glassInput,
            QPushButton#whiteTextButton,
            QPushButton,
            QPushButton#bubbleNavButton,
            QPushButton#startOrbButton {
                background: #000000;
                background-color: #000000;
                color: #39FF14;
                border: 1px solid #FFFFFF;
            }

            QWidget#glassPanel,
            QWidget#glassPage,
            QStackedWidget#glassPanel,
            QWidget#controlPanelContainer,
            QFrame#inlineDropdownPanel,
            QMenu,
            QAbstractItemView,
            QComboBox QAbstractItemView {
                background: #000000;
                background-color: #000000;
                color: #39FF14;
            }

            QAbstractItemView::item,
            QMenu::item {
                background: #000000;
                color: #39FF14;
            }

            QAbstractItemView::item:selected,
            QMenu::item:selected {
                background: #103010;
                color: #39FF14;
            }

            QPushButton:hover,
            QPushButton#whiteTextButton:hover,
            QPushButton#bubbleNavButton:hover,
            QToolButton:hover,
            QComboBox:hover,
            QComboBox#glassInput:hover,
            QLineEdit:hover,
            QLineEdit#glassInput:hover,
            QTextEdit:hover,
            QTextEdit#glassInput:hover,
            QListWidget:hover {
                background: #081808;
                background-color: #081808;
                border: 1px solid #FFFFFF;
            }

            QToolButton#trayIconButton,
            QToolButton#trayIconButton:hover,
            QToolButton#trayIconButton:pressed,
            QToolButton#trayIconButton[active="true"] {
                background: #000000;
                background-color: #000000;
                color: #39FF14;
                border: none;
            }

            QPushButton:pressed,
            QPushButton#whiteTextButton:pressed,
            QPushButton#bubbleNavButton:pressed,
            QToolButton:pressed {
                background: #103010;
                background-color: #103010;
            }

            QComboBox::drop-down {
                border-left: 1px solid #FFFFFF;
                background-color: #000000;
            }

            QComboBox QAbstractItemView,
            QListWidget {
                background-color: #000000;
                color: #39FF14;
                border: 1px solid #FFFFFF;
            }

            QScrollBar:vertical,
            QScrollBar:horizontal {
                background: #000000;
                border: 1px solid #FFFFFF;
            }

            QScrollBar::handle:vertical,
            QScrollBar::handle:horizontal {
                background: #39FF14;
                border: 1px solid #FFFFFF;
            }

            QCheckBox::indicator {
                width: 12px;
                height: 12px;
                background-color: #000000;
                border: 1px solid #FFFFFF;
            }

            QCheckBox::indicator:checked {
                background-color: #39FF14;
                border: 1px solid #FFFFFF;
            }

            QFrame#taskbarTraySeparator {
                background: #FFFFFF;
                border: none;
            }

            QPushButton#startOrbButton,
            QPushButton#startOrbButton:hover,
            QPushButton#startOrbButton:pressed {
                background: #39FF14;
                background-color: #39FF14;
                color: #000000;
                border: 1px solid #FFFFFF;
                border-radius: 18px;
                padding: 0px;
                margin: 0px;
                outline: none;
            }
        """
        self.setStyleSheet(self.styleSheet() + akka_qss)

    def _apply_left_dock_boxy_overlay_stylesheet(self):
        if not getattr(self, 'taskbar_left_mode', False):
            return

        boxy_qss = """
            QWidget#glassPanel,
            QWidget#glassPage,
            QStackedWidget#glassPanel,
            QWidget#controlPanelContainer,
            QFrame#inlineDropdownPanel,
            QLineEdit,
            QLineEdit#glassInput,
            QTextEdit,
            QTextEdit#glassInput,
            QComboBox,
            QComboBox#glassInput,
            QListWidget,
            QListWidget#glassInput,
            QPushButton,
            QPushButton#whiteTextButton,
            QPushButton#bubbleNavButton,
            QToolButton#trayIconButton {
                border-radius: 1px;
            }

            QPushButton#startOrbButton {
                border-radius: 18px;
            }

            QFrame#inlineDropdownPanel {
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }
        """
        self.setStyleSheet(self.styleSheet() + boxy_qss)

    def _apply_current_stylesheet(self):
        self._apply_dark_mode_stylesheet()
        if self.akka_mode:
            self._apply_akka_overlay_stylesheet()
        elif self.rgb_mode:
            self._apply_rgb_overlay_stylesheet()
        elif self.noctua_mode:
            self._apply_noctua_overlay_stylesheet()
        self._apply_left_dock_boxy_overlay_stylesheet()

    def _apply_noctua_overlay_stylesheet(self):
        noctua_qss = """
            QMainWindow {
                background: #E7CEB5;
            }

            QWidget,
            QFrame,
            QGroupBox,
            QStackedWidget,
            QListWidget,
            QTextEdit,
            QLineEdit,
            QComboBox,
            QPushButton,
            QToolButton,
            QLabel,
            QCheckBox {
                color: #2f1a13;
            }

            QWidget#glassRoot,
            QWidget#glassPanel,
            QWidget#glassPage,
            QStackedWidget#glassPanel,
            QWidget#controlPanelContainer,
            QLabel#streamSurface,
            QLabel#leftBanner,
            QFrame#inlineDropdownPanel,
            QWidget#connectionDetailsBox,
            QWidget#uiSettingsBox,
            QFrame#connectionDetailsBox,
            QFrame#uiSettingsBox,
            QTabWidget::pane {
                background: #E7CEB5;
                background-color: #E7CEB5;
                border: 1px solid #653024;
            }

            QLineEdit,
            QLineEdit#glassInput,
            QTextEdit,
            QTextEdit#glassInput,
            QComboBox,
            QComboBox#glassInput,
            QListWidget,
            QListWidget#glassInput {
                background: #f0ddcb;
                color: #2f1a13;
                border: 1px solid #653024;
            }

            QPushButton,
            QPushButton#whiteTextButton,
            QPushButton#bubbleNavButton,
            QToolButton#trayIconButton {
                background: #dec3a6;
                color: #2f1a13;
                border: 1px solid #653024;
            }

            QPushButton:hover,
            QPushButton#whiteTextButton:hover,
            QPushButton#bubbleNavButton:hover,
            QToolButton#trayIconButton:hover {
                background: #d4b392;
                border: 1px solid #653024;
            }

            QPushButton#bubbleNavButton[active="true"],
            QToolButton#trayIconButton[active="true"],
            QPushButton#startOrbButton,
            QPushButton#startOrbButton:hover {
                background: #653024;
                color: #f6eadf;
                border: 1px solid #653024;
            }

            QFrame#taskbarTraySeparator {
                background: #653024;
                border: none;
            }

            QLabel#taskbarClockLabel,
            QLabel#connectionDetailsHeader,
            QLabel#uiSettingsHeader {
                color: #653024;
            }

            QLabel#streamSurface {
                color: #653024;
            }

            QPushButton#bubbleNavButton[leftHeader="true"],
            QPushButton#bubbleNavButton[leftHeader="true"]:hover,
            QPushButton#bubbleNavButton[leftHeader="true"]:pressed,
            QPushButton#bubbleNavButton[leftHeader="true"][active="true"] {
                color: #653024;
                background: transparent;
                border: none;
            }

            /* Left-docked NOCTUA taskbar: prevent doubled parent borders/edge lines. */
            QWidget#bubbleBar[dockLeft="true"],
            QWidget#taskbarTrayContainer[dockLeft="true"],
            QWidget#taskbarProgramContainer[dockLeft="true"],
            QScrollArea#taskbarProgramScroll[dockLeft="true"],
            QWidget#taskbarProgramViewport {
                background: transparent;
                background-color: transparent;
                border: none;
            }

            /* Bottom taskbar in NOCTUA: remove large parent container boxes. */
            QWidget#bubbleBar[dockLeft="false"],
            QWidget#taskbarTrayContainer[dockLeft="false"],
            QWidget#taskbarProgramContainer[dockLeft="false"],
            QScrollArea#taskbarProgramScroll[dockLeft="false"],
            QWidget#taskbarProgramViewport,
            QFrame#taskbarTraySeparator[dockLeft="false"] {
                background: transparent;
                background-color: transparent;
                border: none;
            }
        """
        self.setStyleSheet(self.styleSheet() + noctua_qss)

    def _set_rgb_mode(self, enabled):
        self.rgb_mode = bool(enabled)
        if self.rgb_mode:
            if getattr(self, 'akka_mode', False):
                self.akka_mode = False
                if hasattr(self, 'akka_mode_checkbox'):
                    self.akka_mode_checkbox.blockSignals(True)
                    self.akka_mode_checkbox.setChecked(False)
                    self.akka_mode_checkbox.blockSignals(False)
            if getattr(self, 'noctua_mode', False):
                self.noctua_mode = False
                if hasattr(self, 'noctua_mode_checkbox'):
                    self.noctua_mode_checkbox.blockSignals(True)
                    self.noctua_mode_checkbox.setChecked(False)
                    self.noctua_mode_checkbox.blockSignals(False)
            self._rgb_hue = (self._rgb_hue + 24) % 360
            self.rgb_timer.start(200)
        else:
            self.rgb_timer.stop()

        self._update_mode_toggle_button_labels()
        self._sync_mode_pipeline(reflow_left_dock=True)

    def _refresh_akka_surfaces(self):
        if self._shimmer_widgets_cache is None:
            self._shimmer_widgets_cache = list(
                self.findChildren((self.ShimmerTaskbar, self.ShimmerGlassPanel, self.ShimmerBackgroundRoot))
            )
        for widget in self._shimmer_widgets_cache:
            if widget is not None:
                widget.update()

    def _apply_akka_stream_overrides(self, enabled):
        row_qss = 'background: #000000; border: none;' if enabled else ''
        container_qss = 'background: #000000; border: 1px solid #FFFFFF; border-radius: 10px;' if enabled else ''
        label_qss = 'background: #000000; color: #39FF14; border: 1px solid #FFFFFF; border-radius: 8px; padding: 0px;' if enabled else ''
        if hasattr(self, 'stream_row_widget'):
            if self.stream_row_widget.styleSheet() != row_qss:
                self.stream_row_widget.setStyleSheet(row_qss)
        if hasattr(self, 'stream_container'):
            if self.stream_container.styleSheet() != container_qss:
                self.stream_container.setStyleSheet(container_qss)
        if hasattr(self, 'stream_label'):
            if self.stream_label.styleSheet() != label_qss:
                self.stream_label.setStyleSheet(label_qss)
        if hasattr(self, 'stream_layout'):
            self.stream_layout.setContentsMargins(0, 0, 0, 0) if enabled else self.stream_layout.setContentsMargins(10, 10, 10, 10)
        if hasattr(self, 'start_orb_btn'):
            if self.start_orb_btn.styleSheet():
                self.start_orb_btn.setStyleSheet('')
            effect = self.start_orb_btn.graphicsEffect()
            if isinstance(effect, QGraphicsDropShadowEffect):
                # Keep orb shadow stable across mode switches.
                effect.setBlurRadius(12)
                effect.setXOffset(0)
                effect.setYOffset(1)
                effect.setColor(QColor(18, 26, 38, 165))

    def _sync_mode_pipeline(self, reflow_left_dock=False):
        # Single compatibility pipeline used by all mode toggles.
        self._apply_current_stylesheet()
        if reflow_left_dock and getattr(self, 'taskbar_left_mode', False):
            self._set_taskbar_left_mode(True, persist=False)
        self._apply_akka_stream_overrides(self.akka_mode)
        self._apply_mode_compatibility()
        self._refresh_akka_surfaces()

    def _set_akka_mode(self, enabled):
        self.akka_mode = bool(enabled)
        if self.akka_mode and self.rgb_mode:
            self.rgb_mode = False
            self.rgb_timer.stop()
            if hasattr(self, 'rgb_mode_checkbox'):
                self.rgb_mode_checkbox.blockSignals(True)
                self.rgb_mode_checkbox.setChecked(False)
                self.rgb_mode_checkbox.blockSignals(False)
        if self.akka_mode and getattr(self, 'noctua_mode', False):
            self.noctua_mode = False
            if hasattr(self, 'noctua_mode_checkbox'):
                self.noctua_mode_checkbox.blockSignals(True)
                self.noctua_mode_checkbox.setChecked(False)
                self.noctua_mode_checkbox.blockSignals(False)

        self._update_mode_toggle_button_labels()
        self._sync_mode_pipeline(reflow_left_dock=True)

    def _set_noctua_mode(self, enabled):
        self.noctua_mode = bool(enabled)
        if self.noctua_mode and self.rgb_mode:
            self.rgb_mode = False
            self.rgb_timer.stop()
            if hasattr(self, 'rgb_mode_checkbox'):
                self.rgb_mode_checkbox.blockSignals(True)
                self.rgb_mode_checkbox.setChecked(False)
                self.rgb_mode_checkbox.blockSignals(False)
        if self.noctua_mode and self.akka_mode:
            self.akka_mode = False
            if hasattr(self, 'akka_mode_checkbox'):
                self.akka_mode_checkbox.blockSignals(True)
                self.akka_mode_checkbox.setChecked(False)
                self.akka_mode_checkbox.blockSignals(False)

        self._update_mode_toggle_button_labels()
        self._sync_mode_pipeline(reflow_left_dock=True)

    def _update_mode_toggle_button_labels(self):
        if hasattr(self, 'rgb_mode_checkbox'):
            rgb_label = 'Disable RGB Mode' if self.rgb_mode else 'Enable RGB Mode'
            if self.rgb_mode_checkbox.text() != rgb_label:
                self.rgb_mode_checkbox.setText(rgb_label)
        if hasattr(self, 'akka_mode_checkbox'):
            akka_label = 'Disable AKKA Mode' if self.akka_mode else 'Enable AKKA Mode'
            if self.akka_mode_checkbox.text() != akka_label:
                self.akka_mode_checkbox.setText(akka_label)
        if hasattr(self, 'noctua_mode_checkbox'):
            noctua_label = 'Disable NOCTUA Mode' if self.noctua_mode else 'Enable NOCTUA Mode'
            if self.noctua_mode_checkbox.text() != noctua_label:
                self.noctua_mode_checkbox.setText(noctua_label)

    def _update_rgb_cycle(self):
        if not self.rgb_mode:
            return
        self._rgb_hue = (self._rgb_hue + 5) % 360
        self._apply_current_stylesheet()
        if getattr(self, 'taskbar_left_mode', False) and hasattr(self, 'taskbar_program_scroll'):
            scroll_bar = self.taskbar_program_scroll.verticalScrollBar()
            prev_value = scroll_bar.value() if scroll_bar is not None else 0
            self.taskbar_program_scroll.setUpdatesEnabled(False)
            self._set_taskbar_left_mode(True, persist=False)
            if scroll_bar is not None:
                scroll_bar.setValue(min(prev_value, scroll_bar.maximum()))
            self.taskbar_program_scroll.setUpdatesEnabled(True)

    def switch_to_dark_mode(self):
        if getattr(self, 'is_dark_mode', False):
            return
        self._apply_current_stylesheet()
        self._set_dark_taskbar_mode(True)
        if hasattr(self, 'left_banner'):
            self.left_banner.setPixmap(QPixmap())
            self.left_banner.setText('')
            self.left_banner.setVisible(False)
        self.is_dark_mode = True

    def handle_sender_select(self, index):
        print(f"[DEBUG] handle_sender_select called with index={index}")
        if index >= 0:
            self.selected_sender = self.sender_list.itemText(index)
            self.selected_sender_label.setText(f"Current sender: {self.selected_sender}")
            print(f"[DEBUG] Sender selected: {self.selected_sender}")
            asyncio.ensure_future(self.send_ws({'type': 'select_sender', 'sender': self.selected_sender}))
        else:
            self.selected_sender = None
            self.selected_sender_label.setText('No sender selected')
            print("[DEBUG] No sender selected")

    def update_selected_sender(self):
        index = self.sender_list.currentIndex()
        if index >= 0:
            self.selected_sender = self.sender_list.itemText(index)
            self.selected_sender_label.setText(f"Current sender: {self.selected_sender}")
        else:
            self.selected_sender = None
            self.selected_sender_label.setText('No sender selected')

    def handle_server_message(self, msg):
        print(f"[DEBUG] handle_server_message called with msg={msg[:100]}...")
        try:
            data = json.loads(msg)
            print(f"[DEBUG] Parsed JSON: {data}")
        except Exception as e:
            print(f"[DEBUG] JSON decode failed: {e}")
            return
        msg_type = data.get('type')
        print(f"[DEBUG] msg_type={msg_type}")
        if msg_type == 'sender_list':
            self.sender_list.clear()
            senders = data.get('senders', [])
            print(f"[DEBUG] Received sender_list: {senders}")
            self.sender_list.addItems(senders)
            print(f"[DEBUG] Sender dropdown populated with {self.sender_list.count()} items.")
            # Auto-select first sender if available
            if senders:
                self.sender_list.setCurrentIndex(0)
                self.selected_sender = self.sender_list.itemText(0)
                print(f"[DEBUG] Auto-selected sender: {self.selected_sender}")
        elif msg_type == 'active-machines':
            self.sender_list.clear()
            machines = data.get('machines', [])
            print(f"[DEBUG] Received active-machines: {machines}")
            self.sender_list.addItems(machines)
            print(f"[DEBUG] Sender dropdown populated with {self.sender_list.count()} items.")
            # Auto-select first machine if available
            if machines:
                self.sender_list.setCurrentIndex(0)
                self.selected_sender = self.sender_list.itemText(0)
                print(f"[DEBUG] Auto-selected sender: {self.selected_sender}")
        elif msg_type == 'system-info':
            info = data.get('info')
            print(f"[DEBUG] system-info payload: {json.dumps(info, indent=2)}")
            if info and info.get('summary'):
                # Show the formatted summary from sender
                self.telemetry_panel.setPlainText(info['summary'])
            elif info:
                self.telemetry_panel.setHtml('<span style="color:#888">No summary available.</span>')
            else:
                self.telemetry_panel.setHtml('<span style="color:#888">No telemetry info received.</span>')
    def show_warning(self, message):
        self.status_label.setText(message)
        self.status_label.setStyleSheet('color: #ff5555;')
        QTimer.singleShot(3000, lambda: self.status_label.setStyleSheet('color: #e0e0e0;'))
    def enable_remote_control(self):
        # Enable mouse and keyboard events on stream_label
        self.stream_label.setMouseTracking(True)
        self.stream_label.setFocusPolicy(Qt.StrongFocus)
        self.stream_label.mousePressEvent = self.handle_mouse_press
        self.stream_label.mouseReleaseEvent = self.handle_mouse_release
        self.stream_label.mouseMoveEvent = self.handle_mouse_move
        self.stream_label.wheelEvent = self.handle_mouse_wheel
        self.stream_label.keyPressEvent = self.handle_key_press
        self.stream_label.keyReleaseEvent = self.handle_key_release
        self.selected_sender = None
        self.stream_label.enterEvent = self.handle_stream_enter
       # self.stream_label.focusOutEvent = self.handle_stream_focus_out
    def handle_stream_focus_out(self, event):
        self.show_warning('Stream area lost focus. Click to re-enable keyboard control.')
        event.accept()

    def handle_stream_enter(self, event):
        event.accept()


    # Removed broken update_selected_sender (QComboBox has no .selectedItems()). Only handle_sender_select is used.

    def handle_mouse_press(self, event):
        label = self.get_active_stream_label()
        if not label.hasFocus():
            self.show_warning('Click the stream area to enable control.')
            return
        if not self.selected_sender:
            self.show_warning('Select a sender before controlling.')
            return
        pixmap = label.pixmap()
        if pixmap:
            pw = pixmap.width()
            ph = pixmap.height()
            lw = label.width()
            lh = label.height()
            x_offset = (lw - pw) // 2 if lw > pw else 0
            y_offset = (lh - ph) // 2 if lh > ph else 0
            x = event.x() - x_offset
            y = event.y() - y_offset
            xNorm = min(max(x / max(1, pw), 0), 1)
            yNorm = min(max(y / max(1, ph), 0), 1)
        else:
            xNorm = min(max(event.x() / max(1, label.width()), 0), 1)
            yNorm = min(max(event.y() / max(1, label.height()), 0), 1)
        button = self.qt_button_to_str(event.button())
        asyncio.ensure_future(self.send_ws({
            'type': 'remote-control',
            'action': 'mouse-down',
            'xNorm': xNorm,
            'yNorm': yNorm,
            'button': button,
            'machineId': self.selected_sender
        }))

    def handle_mouse_release(self, event):
        label = self.get_active_stream_label()
        if not label.hasFocus():
            self.show_warning('Click the stream area to enable control.')
            return
        if not self.selected_sender:
            self.show_warning('Select a sender before controlling.')
            return
        pixmap = label.pixmap()
        if pixmap:
            pw = pixmap.width()
            ph = pixmap.height()
            lw = label.width()
            lh = label.height()
            x_offset = (lw - pw) // 2 if lw > pw else 0
            y_offset = (lh - ph) // 2 if lh > ph else 0
            x = event.x() - x_offset
            y = event.y() - y_offset
            xNorm = min(max(x / max(1, pw), 0), 1)
            yNorm = min(max(y / max(1, ph), 0), 1)
        else:
            xNorm = min(max(event.x() / max(1, label.width()), 0), 1)
            yNorm = min(max(event.y() / max(1, label.height()), 0), 1)
        button = self.qt_button_to_str(event.button())
        asyncio.ensure_future(self.send_ws({
            'type': 'remote-control',
            'action': 'mouse-up',
            'xNorm': xNorm,
            'yNorm': yNorm,
            'button': button,
            'machineId': self.selected_sender
        }))

    def handle_mouse_move(self, event):
        label = self.get_active_stream_label()
        if not label.hasFocus():
            return
        if not self.selected_sender:
            return
        pixmap = label.pixmap()
        if pixmap:
            pw = pixmap.width()
            ph = pixmap.height()
            lw = label.width()
            lh = label.height()
            x_offset = (lw - pw) // 2 if lw > pw else 0
            y_offset = (lh - ph) // 2 if lh > ph else 0
            x = event.x() - x_offset
            y = event.y() - y_offset
            xNorm = min(max(x / max(1, pw), 0), 1)
            yNorm = min(max(y / max(1, ph), 0), 1)
        else:
            xNorm = min(max(event.x() / max(1, label.width()), 0), 1)
            yNorm = min(max(event.y() / max(1, label.height()), 0), 1)
        now = time.time()
        if not hasattr(self, '_mouse_move_pending'):
            self._mouse_move_pending = False
        if not hasattr(self, '_last_mouse_move'):
            self._last_mouse_move = 0
        self._pending_xNorm = xNorm
        self._pending_yNorm = yNorm
        def send_latest():
            self._mouse_move_pending = False
            print(f"[DEBUG] Mouse move: sender={self.selected_sender}, xNorm={self._pending_xNorm:.4f}, yNorm={self._pending_yNorm:.4f}")
            asyncio.ensure_future(self.send_ws({
                'type': 'remote-control',
                'action': 'mouse-move',
                'xNorm': self._pending_xNorm,
                'yNorm': self._pending_yNorm,
                'machineId': self.selected_sender
            }))
            self._last_mouse_move = time.time()
        if now - self._last_mouse_move > 0.01:
            send_latest()
        elif not self._mouse_move_pending:
            self._mouse_move_pending = True
            QTimer.singleShot(10, send_latest)

    def reconnect(self):
        async def cleanup():
            if self.connect_task:
                self.connect_task.cancel()
                try:
                    await self.connect_task
                except Exception:
                    pass
            if self.ws:
                try:
                    await self.ws.close()
                except Exception:
                    pass
                self.ws = None
        async def do_reconnect():
            await cleanup()
            self.connect_task = self.loop.create_task(self.connect_to_server())
        self.loop.create_task(do_reconnect())

    def restart_application(self):
        if self._restart_in_progress:
            return
        self._restart_in_progress = True

        executable = sys.executable
        script_path = os.path.abspath(sys.argv[0]) if sys.argv else ''
        arguments = [script_path] + sys.argv[1:] if script_path else sys.argv[:]
        working_dir = os.path.dirname(script_path) if script_path else os.getcwd()

        restarted = QProcess.startDetached(executable, arguments, working_dir)
        if restarted:
            QApplication.instance().quit()
        else:
            self._restart_in_progress = False
            self.show_warning('Failed to restart application.')

    def handle_mouse_wheel(self, event):
        label = self.get_active_stream_label()
        if not label.hasFocus():
            self.show_warning('Click the stream area to enable control.')
            return
        if not self.selected_sender:
            self.show_warning('Select a sender before controlling.')
            return
        xNorm = min(max(event.x() / max(1, label.width()), 0), 1)
        yNorm = min(max(event.y() / max(1, label.height()), 0), 1)
        delta = event.angleDelta().y()
        asyncio.ensure_future(self.send_ws({
            'type': 'remote-control',
            'action': 'mouse-wheel',
            'xNorm': xNorm,
            'yNorm': yNorm,
            'delta': delta,
            'machineId': self.selected_sender
        }))

    def handle_key_press(self, event):
        label = self.get_active_stream_label()
        if not label.hasFocus():
            self.show_warning('Click the stream area to enable control.')
            return
        if not self.selected_sender:
            self.show_warning('Select a sender before controlling.')
            return
        key = event.text()
        keyCode = event.key()
        # Only clear key for control keys, not punctuation
        if keyCode in [Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab, Qt.Key_Escape] or (Qt.Key_F1 <= keyCode <= Qt.Key_F35):
            key = ''
        try:
            asyncio.ensure_future(self.send_ws({
                'type': 'remote-control',
                'action': 'key-press',
                'key': key,
                'keyCode': keyCode,
                'machineId': self.selected_sender
            }))
        except Exception as e:
            self.show_warning(f'Failed to send key-press: {e}')

    def handle_key_release(self, event):
        label = self.get_active_stream_label()
        if not label.hasFocus():
            self.show_warning('Click the stream area to enable control.')
            return
        if not self.selected_sender:
            self.show_warning('Select a sender before controlling.')
            return
        key = event.text()
        keyCode = event.key()
        if keyCode in [Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab, Qt.Key_Escape] or (Qt.Key_F1 <= keyCode <= Qt.Key_F35):
            key = ''
        try:
            asyncio.ensure_future(self.send_ws({
                'type': 'remote-control',
                'action': 'key-release',
                'key': key,
                'keyCode': keyCode,
                'machineId': self.selected_sender
            }))
        except Exception as e:
            self.show_warning(f'Failed to send key-release: {e}')

    def qt_button_to_str(self, button):
        if button == Qt.LeftButton:
            return 'left'
        elif button == Qt.RightButton:
            return 'right'
        elif button == Qt.MiddleButton:
            return 'middle'
        return 'unknown'

    # Removed duplicate __init__
        self.kill_pid_btn.clicked.connect(self.send_kill_pid)

    # ...existing code...

    async def connect_to_server(self):
        try:
            print(f"[DEBUG] connect_to_server called with ws_url={self.ws_url}")
            self.status_label.setText('Connecting...')
            print(f"[DEBUG] Attempting websockets.connect({self.ws_url})")
            self.ws = await websockets.connect(self.ws_url)
            print(f"[DEBUG] WebSocket connection established: {self.ws}")
            # Send join message
            join_msg = {
                'type': 'join',
                'role': 'receiver',
                'roomId': self.room_id,
                'secret': self.secret,
                'targetMachineId': self.target_machine_id
            }
            print(f"[DEBUG] Sending join message: {join_msg}")
            await self.ws.send(json.dumps(join_msg))
            print(f"[DEBUG] Join message sent, starting listen_server")
            await self.listen_server()
        except Exception as e:
            print(f"[DEBUG] Connection failed: {e}")
            self.status_label.setText(f'Connection failed: {e}')

    async def listen_server(self):
        try:
            async for message in self.ws:
                # Handle binary messages as images
                if isinstance(message, bytes):
                    now = time.monotonic()
                    should_log_frame = now >= self._next_stream_frame_log_ts
                    if should_log_frame:
                        print(f"[DEBUG] Received binary message of length {len(message)}. Attempting to display as image.")
                        self._next_stream_frame_log_ts = now + 5.0
                    try:
                        image = QImage.fromData(message)
                        if not image.isNull():
                            pixmap = QPixmap.fromImage(image)
                            self.stream_label.setPixmap(pixmap)
                            self.stream_label.setText("")
                            if should_log_frame:
                                print("[DEBUG] Stream image displayed.")
                        else:
                            self.stream_label.setText("Failed to decode stream image.")
                            print("[DEBUG] Failed to decode stream image.")
                    except Exception as e:
                        self.stream_label.setText("Error displaying stream image.")
                        print(f"[DEBUG] Error displaying stream image: {e}")
                    continue
                try:
                    data = json.loads(message)
                except Exception as e:
                    print(f"[DEBUG] Failed to parse server message: {e}")
                    continue
                msg_type = data.get('type')
                print(f"[DEBUG] Received message type: {msg_type}")
                print(f"[DEBUG] Full payload: {json.dumps(data, indent=2)}")
                if msg_type == 'active-machines':
                    self.sender_list.clear()
                    machines = data.get('machines', [])
                    print(f"[DEBUG] Received active-machines: {machines}")
                    self.sender_list.addItems(machines)
                    print(f"[DEBUG] Sender dropdown populated with {self.sender_list.count()} items.")
                    # Auto-select first machine if available
                    if machines:
                        self.sender_list.setCurrentIndex(0)
                        self.selected_sender = self.sender_list.itemText(0)
                        print(f"[DEBUG] Auto-selected sender: {self.selected_sender}")
                elif msg_type == 'system-info':
                    info = data.get('info')
                    print(f"[DEBUG] system-info payload: {json.dumps(info, indent=2)}")
                    if info and info.get('summary'):
                        # Show the formatted summary from sender
                        self.telemetry_panel.setPlainText(info['summary'])
                    elif info:
                        self.telemetry_panel.setHtml('<span style="color:#888">No summary available.</span>')
                    else:
                        self.telemetry_panel.setHtml('<span style="color:#888">No telemetry info received.</span>')
                elif msg_type == 'sender-online':
                    machine_id = data.get('machineId')
                    print(f"[DEBUG] sender-online: machine_id={machine_id}")
                    current_senders = [self.sender_list.itemText(i) for i in range(self.sender_list.count())]
                    print(f"[DEBUG] Current senders: {current_senders}")
                    if machine_id and machine_id not in current_senders:
                        self.sender_list.addItem(machine_id)
                        print(f"[DEBUG] Added sender {machine_id}")
                elif msg_type == 'chat':
                    print(f"[DEBUG] chat: {data}")
                    self.chat_log.addItem(f"{data.get('user')}: {data.get('message')}")
                elif msg_type == 'telemetry':
                    print(f"[DEBUG] telemetry: {data}")
                    self.telemetry_panel.setPlainText(data.get('content', ''))
                elif msg_type == 'stream':
                    print(f"[DEBUG] stream: {data}")
                    img_data = data.get('image')
                    # Placeholder: handle stream image
                    self.stream_label.setText('Stream received (implement image display)')
                elif msg_type == 'file-list':
                    print(f"[DEBUG] file-list: {data}")
                    QTimer.singleShot(0, lambda d=data: self._fm_update_remote_list(d))
                elif msg_type == 'file-data':
                    print(f"[DEBUG] file-data received")
                    QTimer.singleShot(0, lambda d=data: self._fm_receive_download(d))
                # Add more handlers as needed
                self.key_input.clear()
        except Exception as e:
            print(f"[DEBUG] Outer listen_server error: {e}")

    def send_kill_pid(self):
        pid = self.kill_pid_input.text()
        if pid:
            asyncio.ensure_future(self.send_ws({'type': 'remote-control', 'action': 'process-kill', 'pid': pid, 'machineId': self.selected_sender}))
            self.kill_pid_input.clear()

    def send_clipboard_text(self):
        text = self.clipboard_input.text()
        if not text:
            self.show_warning('Clipboard text is empty.')
            return
        if not self.selected_sender:
            self.show_warning('Select a sender before sending clipboard.')
            return
        asyncio.ensure_future(self.send_ws({
            'type': 'remote-control',
            'action': 'clipboard-text',
            'text': text,
            'machineId': self.selected_sender
        }))
        self.clipboard_input.clear()
        self.show_warning('Clipboard text sent.')

    def send_file(self):
        file_path = self.selected_file_path or self.file_input.text()
        dest_path = self.dest_input.text().strip()
        if not file_path:
            self.show_warning('No file selected.')
            return
        if not self.selected_sender:
            self.show_warning('Select a sender before sending file.')
            return
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            import base64
            encoded = base64.b64encode(data).decode('utf-8')
            payload = {
                'type': 'remote-control',
                'action': 'file-transfer',
                'filename': file_path.split('/')[-1],
                'data': encoded,
                'machineId': self.selected_sender
            }
            if dest_path:
                payload['destPath'] = dest_path
            asyncio.ensure_future(self.send_ws(payload))
            self.show_warning('File sent.')
            self.file_input.clear()
            self.dest_input.clear()
            self.selected_file_path = ''
        except Exception as e:
            self.show_warning(f'Failed to send file: {e}')

    async def send_ws(self, data):
        import json
        if self.ws:
            try:
                print(f"[DEBUG] send_ws sending: {data}")
                await self.ws.send(json.dumps(data))
                print(f"[DEBUG] send_ws sent successfully.")
            except Exception as e:
                print(f"[DEBUG] send_ws failed: {e}")
                self.status_label.setText('Send failed')

    def setup_ui(self):
        self.is_dark_mode = False
        # Monitor Wall: stream view + switchable functional panes + bottom bubble taskbar.
        self.left_banner = QLabel()
        self.left_banner.setObjectName('leftBanner')
        self.left_banner.setAlignment(Qt.AlignCenter)
        self.left_banner.setFixedHeight(110)
        self.left_banner.setMinimumWidth(220)
        self.left_banner.setMaximumWidth(720)
        self.left_banner.setScaledContents(False)
        self.update_left_banner()

        monitor_wall_layout = QVBoxLayout()
        self.monitor_wall_layout = monitor_wall_layout
        monitor_wall_layout.setContentsMargins(12, 12, 12, 0)
        monitor_wall_layout.setSpacing(10)

        stream_container = self.ShimmerGlassPanel()
        self.stream_container = stream_container
        stream_container.setObjectName('glassPanel')
        stream_layout = QVBoxLayout()
        self.stream_layout = stream_layout
        stream_layout.setContentsMargins(10, 10, 10, 10)
        stream_layout.addWidget(self.stream_label, 1)
        stream_container.setLayout(stream_layout)
        self.stream_row_widget = QWidget()
        self.stream_row_layout = QHBoxLayout()
        self.stream_row_layout.setContentsMargins(0, 0, 0, 0)
        self.stream_row_layout.setSpacing(10)
        self.stream_row_layout.addWidget(stream_container, 1)
        self.stream_row_widget.setLayout(self.stream_row_layout)
        monitor_wall_layout.addWidget(self.stream_row_widget, 1)

        self.control_stack = QStackedWidget()
        self.control_stack.setObjectName('glassPanel')
        self.control_stack.setMinimumHeight(130)
        self.control_stack.setMaximumHeight(170)

        self.control_panel_container = self.ShimmerGlassPanel()
        self.control_panel_container.setObjectName('controlPanelContainer')
        control_panel_layout = QVBoxLayout()
        control_panel_layout.setContentsMargins(0, 0, 0, 0)
        control_panel_layout.setSpacing(0)
        control_panel_layout.addWidget(self.control_stack)
        self.control_panel_container.setLayout(control_panel_layout)
        self._panel_expanded_height = 170
        self.control_panel_container.setFixedSize(230, 0)

        senders_page = QWidget()
        senders_page.setObjectName('glassPage')
        senders_layout = QVBoxLayout()
        senders_layout.setContentsMargins(12, 10, 12, 10)
        senders_layout.setSpacing(6)
        senders_layout.addWidget(self.left_banner, 0, Qt.AlignLeft)
        senders_layout.addWidget(self.sender_list)
        senders_layout.addWidget(self.selected_sender_label)
        senders_layout.addWidget(self.status_label)
        senders_page.setLayout(senders_layout)

        chat_page = QWidget()
        chat_page.setObjectName('glassPage')
        chat_layout = QVBoxLayout()
        chat_layout.setContentsMargins(12, 10, 12, 10)
        chat_layout.setSpacing(6)
        chat_layout.addWidget(self.chat_log, 1)
        chat_layout.addWidget(self.chat_input)
        chat_layout.addWidget(self.chat_send)
        chat_page.setLayout(chat_layout)

        clipboard_page = QWidget()
        clipboard_page.setObjectName('glassPage')
        clipboard_layout = QVBoxLayout()
        clipboard_layout.setContentsMargins(12, 10, 12, 10)
        clipboard_layout.setSpacing(6)
        clipboard_layout.addWidget(self.clipboard_input)
        clipboard_layout.addWidget(self.clipboard_send_btn)
        clipboard_layout.addStretch(1)
        clipboard_page.setLayout(clipboard_layout)

        file_page = QWidget()
        file_page.setObjectName('glassPage')
        file_layout = QVBoxLayout()
        file_layout.setContentsMargins(12, 10, 12, 10)
        file_layout.setSpacing(6)
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(self.file_select_btn)
        file_layout.addWidget(self.dest_input)
        file_layout.addWidget(self.dest_select_btn)
        file_layout.addWidget(self.file_send_btn)
        file_layout.addStretch(1)
        file_page.setLayout(file_layout)

        fun_page = QWidget()
        fun_page.setObjectName('glassPage')
        fun_layout = QVBoxLayout()
        fun_layout.setContentsMargins(12, 10, 12, 10)
        fun_layout.setSpacing(6)
        fun_placeholder = QLabel('Blank slate for new menu items.')
        fun_placeholder.setAlignment(Qt.AlignCenter)
        fun_layout.addWidget(fun_placeholder, 1)
        fun_page.setLayout(fun_layout)

        file_manager_page = QWidget()
        file_manager_page.setObjectName('glassPage')
        file_manager_layout = QVBoxLayout()
        file_manager_layout.setContentsMargins(12, 10, 12, 10)
        file_manager_layout.setSpacing(4)

        fm_tabs = QTabWidget()
        fm_tabs.setObjectName('glassInput')

        local_tab = QWidget()
        local_tab_layout = QVBoxLayout()
        local_tab_layout.setContentsMargins(2, 2, 2, 2)
        local_tab_layout.setSpacing(2)
        lpath_row = QHBoxLayout()
        lpath_row.setSpacing(2)
        lpath_row.addWidget(self._fm_local_path, 1)
        lpath_row.addWidget(self._fm_local_up_btn)
        lpath_row.addWidget(self._fm_local_refresh_btn)
        local_tab_layout.addLayout(lpath_row)
        local_tab_layout.addWidget(self._fm_local_list, 1)
        local_tab.setLayout(local_tab_layout)

        remote_tab = QWidget()
        remote_tab_layout = QVBoxLayout()
        remote_tab_layout.setContentsMargins(2, 2, 2, 2)
        remote_tab_layout.setSpacing(2)
        rpath_row = QHBoxLayout()
        rpath_row.setSpacing(2)
        rpath_row.addWidget(self._fm_remote_path, 1)
        rpath_row.addWidget(self._fm_remote_up_btn)
        rpath_row.addWidget(self._fm_remote_refresh_btn)
        remote_tab_layout.addLayout(rpath_row)
        remote_tab_layout.addWidget(self._fm_remote_list, 1)
        remote_tab.setLayout(remote_tab_layout)

        fm_tabs.addTab(local_tab, 'Local')
        fm_tabs.addTab(remote_tab, 'Remote')
        file_manager_layout.addWidget(fm_tabs, 1)

        fm_btn_row = QHBoxLayout()
        fm_btn_row.setSpacing(4)
        fm_btn_row.addWidget(self._fm_upload_btn)
        fm_btn_row.addWidget(self._fm_download_btn)
        file_manager_layout.addLayout(fm_btn_row)

        file_manager_page.setLayout(file_manager_layout)

        self.control_pages = [senders_page, chat_page, clipboard_page, file_page, file_manager_page, fun_page]
        for page in self.control_pages:
            self.control_stack.addWidget(page)

        bubble_bar = self.ShimmerTaskbar()
        bubble_bar.setObjectName('bubbleBar')
        bubble_bar.setFixedHeight(40)
        self.bubble_bar = bubble_bar
        bubble_layout = QHBoxLayout()
        self.bubble_layout = bubble_layout
        bubble_layout.setContentsMargins(8, 0, 8, 0)
        bubble_layout.setSpacing(0)

        self.start_orb_btn = self.BubbleOrbButton('')
        self.start_orb_btn.setObjectName('startOrbButton')
        self.start_orb_btn.setFixedSize(36, 36)
        self.start_orb_btn.setCursor(Qt.PointingHandCursor)
        self.start_orb_btn.setAutoDefault(False)
        self.start_orb_btn.setDefault(False)
        self.start_orb_btn.setFocusPolicy(Qt.NoFocus)
        self._register_mode_widget(self.start_orb_btn)
        start_orb_shadow = QGraphicsDropShadowEffect(self.start_orb_btn)
        start_orb_shadow.setBlurRadius(12)
        start_orb_shadow.setXOffset(0)
        start_orb_shadow.setYOffset(1)
        start_orb_shadow.setColor(QColor(18, 26, 38, 165))
        self.start_orb_btn.setGraphicsEffect(start_orb_shadow)

        left_taskbar_side = QWidget()
        self.left_taskbar_side = left_taskbar_side
        left_taskbar_layout = QHBoxLayout()
        self.left_taskbar_layout = left_taskbar_layout
        left_taskbar_layout.setContentsMargins(0, 0, 0, 0)
        left_taskbar_layout.setSpacing(0)
        left_taskbar_layout.addWidget(self.start_orb_btn, 0, Qt.AlignVCenter)
        left_taskbar_side.setLayout(left_taskbar_layout)
        bubble_layout.addWidget(left_taskbar_side, 0, Qt.AlignVCenter)

        self.taskbar_program_container = QWidget()
        self.taskbar_program_container.setObjectName('taskbarProgramContainer')
        program_layout = QHBoxLayout()
        program_layout.setContentsMargins(0, 0, 2, 0)
        program_layout.setSpacing(2)
        self.program_layout = program_layout
        self.taskbar_program_container.setLayout(program_layout)

        self.taskbar_program_scroll = QScrollArea()
        self.taskbar_program_scroll.setObjectName('taskbarProgramScroll')
        self.taskbar_program_scroll.setFrameShape(QFrame.NoFrame)
        self.taskbar_program_scroll.setWidgetResizable(True)
        self.taskbar_program_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.taskbar_program_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.taskbar_program_scroll.viewport().setObjectName('taskbarProgramViewport')
        self.taskbar_program_scroll.viewport().setAutoFillBackground(False)
        self.taskbar_program_scroll.installEventFilter(self)
        self.taskbar_program_scroll.viewport().installEventFilter(self)
        self.taskbar_program_scroll.setWidget(self.taskbar_program_container)

        self.nav_buttons = []
        nav_items = [
            ('Senders', QStyle.SP_ComputerIcon),
            ('Chat', QStyle.SP_MessageBoxInformation),
            ('Clipboard', QStyle.SP_FileDialogDetailedView),
            ('File Transfer', QStyle.SP_DirIcon),
            ('File Manager', QStyle.SP_DirHomeIcon),
            ('Fun', QStyle.SP_MediaPlay),
        ]

        def set_active_nav(index, anchor_button=None, show_panel=True):
            # Big taskbar buttons always target Monitor Wall.
            if hasattr(self, 'main_pages') and self.main_pages.currentIndex() != 0:
                self.main_pages.setCurrentIndex(0)
                if hasattr(self, 'taskbar_tray_buttons'):
                    for i, tray_btn in enumerate(self.taskbar_tray_buttons[:3]):
                        tray_btn.setProperty('active', 'true' if i == 0 else 'false')
                        tray_btn.style().unpolish(tray_btn)
                        tray_btn.style().polish(tray_btn)

            if getattr(self, 'taskbar_left_mode', False):
                # Left-docked mode uses permanent section headers with always-open panels.
                panel = self.inline_dropdown_panels[index] if index < len(self.inline_dropdown_panels) else None
                if panel is not None:
                    panel.setMinimumHeight(0)
                    if self.program_layout.indexOf(panel) == -1:
                        btn_index = self.program_layout.indexOf(self.nav_buttons[index])
                        self.program_layout.insertWidget(btn_index + 1, panel, 0)
                    panel.setMaximumHeight(16777215)
                    panel.show()
                    if index < len(self.control_pages):
                        self.control_pages[index].show()
                    btn = self.nav_buttons[index]
                    btn.setProperty('active', 'false')
                    btn.set_active(False)
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)

                if index == 1 and panel is not None and panel.isVisible():
                    QTimer.singleShot(0, self.chat_input.setFocus)
                elif index == 2 and panel is not None and panel.isVisible():
                    QTimer.singleShot(0, self.clipboard_input.setFocus)
                elif index == 3 and panel is not None and panel.isVisible():
                    QTimer.singleShot(0, self.file_input.setFocus)
                return

            for i, btn in enumerate(self.nav_buttons):
                btn.setProperty('active', 'true' if i == index else 'false')
                btn.set_active(i == index)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            self.control_stack.setCurrentIndex(index)
            self._panel_anchor_widget = anchor_button
            if show_panel:
                self._show_control_panel()
                self._schedule_panel_hide()
                if index == 1:
                    QTimer.singleShot(0, self.chat_input.setFocus)
                elif index == 2:
                    QTimer.singleShot(0, self.clipboard_input.setFocus)
                elif index == 3:
                    QTimer.singleShot(0, self.file_input.setFocus)

        for index, (label, icon_type) in enumerate(nav_items):
            btn = self.BubbleNavButton(label)
            btn.setObjectName('bubbleNavButton')
            btn.setCheckable(True)
            btn.setFixedSize(136, 32)
            btn._default_icon = self.style().standardIcon(icon_type)
            btn.setIcon(btn._default_icon)
            btn.setIconSize(QSize(16, 16))
            btn._base_icon_size = 16
            btn._jump_offset = 0
            btn.setToolTip(label)
            btn.pressed.connect(lambda i=index, b=btn: set_active_nav(i, b, True))
            self.nav_buttons.append(btn)
            self._register_mode_icon_button(btn)
            program_layout.addWidget(btn)

        self.inline_dropdown_panels = []
        for _ in self.control_pages:
            dropdown = QFrame()
            dropdown.setObjectName('inlineDropdownPanel')
            dropdown_layout = QVBoxLayout()
            dropdown_layout.setContentsMargins(0, 0, 0, 0)
            dropdown_layout.setSpacing(0)
            dropdown.setLayout(dropdown_layout)
            dropdown.hide()
            self.inline_dropdown_panels.append(dropdown)

        self._nav_shimmer_progress = 0.0
        self._nav_shimmer_anim = QPropertyAnimation(self, b'navShimmerProgress', self)
        self._nav_shimmer_anim.setDuration(4200)
        self._nav_shimmer_anim.setStartValue(0.0)
        self._nav_shimmer_anim.setEndValue(1.0)
        self._nav_shimmer_anim.setLoopCount(-1)
        self._nav_shimmer_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._nav_shimmer_anim.start()

        center_taskbar_side = QWidget()
        self.center_taskbar_side = center_taskbar_side
        center_taskbar_layout = QHBoxLayout()
        self.center_taskbar_layout = center_taskbar_layout
        center_taskbar_layout.setContentsMargins(0, 0, 0, 0)
        center_taskbar_layout.addStretch(1)
        center_taskbar_layout.addWidget(self.taskbar_program_scroll, 0, Qt.AlignCenter)
        center_taskbar_layout.addStretch(1)
        center_taskbar_side.setLayout(center_taskbar_layout)
        bubble_layout.addWidget(center_taskbar_side, 1, Qt.AlignVCenter)

        right_taskbar_side = QWidget()
        self.right_taskbar_side = right_taskbar_side
        right_taskbar_layout = QHBoxLayout()
        self.right_taskbar_layout = right_taskbar_layout
        right_taskbar_layout.setContentsMargins(0, 0, 0, 0)
        right_taskbar_layout.setSpacing(8)

        self.taskbar_separator = QFrame()
        self.taskbar_separator.setObjectName('taskbarTraySeparator')
        self.taskbar_separator.setFrameShape(QFrame.VLine)
        self.taskbar_separator.setFrameShadow(QFrame.Plain)
        self.taskbar_separator.setFixedHeight(26)
        right_taskbar_layout.addWidget(self.taskbar_separator, 0, Qt.AlignVCenter)

        self.taskbar_tray_container = QWidget()
        self.taskbar_tray_container.setObjectName('taskbarTrayContainer')
        tray_layout = QHBoxLayout()
        self.tray_layout = tray_layout
        tray_layout.setContentsMargins(0, 0, 0, 0)
        tray_layout.setSpacing(6)
        self.taskbar_tray_buttons = []
        tray_items = [
            ('Monitor Wall', QStyle.SP_DesktopIcon),
            ('Machine Detail', QStyle.SP_FileDialogInfoView),
            ('Settings', QStyle.SP_FileDialogDetailedView),
        ]
        for tray_label, tray_icon in tray_items:
            tray_btn = QToolButton()
            tray_btn.setObjectName('trayIconButton')
            tray_btn.setIcon(self.style().standardIcon(tray_icon))
            tray_btn.setIconSize(QSize(16, 16))
            tray_btn.setFixedSize(24, 24)
            tray_btn.setToolTip(tray_label)
            tray_btn.setToolTipDuration(2500)
            tray_btn.installEventFilter(self)
            self._register_mode_icon_button(tray_btn)
            tray_layout.addWidget(tray_btn)
            self.taskbar_tray_buttons.append(tray_btn)

        self.left_dock_toggle_btn = QToolButton()
        self.left_dock_toggle_btn.setObjectName('trayIconButton')
        self.left_dock_toggle_btn.setIcon(self.style().standardIcon(QStyle.SP_ArrowLeft))
        self.left_dock_toggle_btn.setIconSize(QSize(16, 16))
        self.left_dock_toggle_btn.setFixedSize(24, 24)
        self.left_dock_toggle_btn.setCheckable(True)
        self.left_dock_toggle_btn.setToolTip('Toggle left-docked taskbar')
        self.left_dock_toggle_btn.setToolTipDuration(2500)
        self.left_dock_toggle_btn.installEventFilter(self)
        self.left_dock_toggle_btn.setProperty('active', 'false')
        self._register_mode_icon_button(self.left_dock_toggle_btn)
        tray_layout.addWidget(self.left_dock_toggle_btn)
        self.taskbar_tray_container.setLayout(tray_layout)
        right_taskbar_layout.addWidget(self.taskbar_tray_container, 0, Qt.AlignVCenter)

        self.taskbar_clock_label = QLabel('')
        self.taskbar_clock_label.setObjectName('taskbarClockLabel')
        self.taskbar_clock_label.setAlignment(Qt.AlignCenter)
        right_taskbar_layout.addWidget(self.taskbar_clock_label, 0, Qt.AlignVCenter)

        right_taskbar_side.setLayout(right_taskbar_layout)
        bubble_layout.addWidget(right_taskbar_side, 0, Qt.AlignVCenter)

        self.taskbar_clock_timer = QTimer(self)
        self.taskbar_clock_timer.timeout.connect(self._update_taskbar_clock)

        bubble_bar.setLayout(bubble_layout)

        monitor_wall_widget = QWidget()
        monitor_wall_widget.setObjectName('glassRoot')
        monitor_wall_widget.setLayout(monitor_wall_layout)
        self.monitor_wall_widget = monitor_wall_widget
        self.control_panel_container.setParent(monitor_wall_widget)
        self.control_panel_container.hide()

        self._panel_anim = QPropertyAnimation(self.control_panel_container, b'maximumHeight', self)
        self._panel_anim.setDuration(260)
        self._panel_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._panel_anim.valueChanged.connect(self._on_panel_anim_value)
        self._panel_anim.finished.connect(self._on_panel_anim_finished)
        self._panel_hide_timer = QTimer(self)
        self._panel_hide_timer.setSingleShot(True)
        self._panel_hide_delay_ms = 1100
        self._panel_hide_timer.timeout.connect(self._hide_control_panel)
        self._panel_watch_widgets = [self.control_panel_container, self.control_stack, self.bubble_bar]
        for nav_btn in self.nav_buttons:
            self._panel_watch_widgets.append(nav_btn)
        for watched_widget in self._panel_watch_widgets:
            watched_widget.installEventFilter(self)
        self._panel_input_widgets = [
            self.chat_input,
            self.clipboard_input,
            self.file_input,
            self.dest_input,
        ]
        for input_widget in self._panel_input_widgets:
            input_widget.installEventFilter(self)
        self.stream_label.installEventFilter(self)
        self._panel_anchor_widget = None
        set_active_nav(0, None, False)
        self.start_orb_btn.pressed.connect(self.restart_application)
        self._set_dark_taskbar_mode(True)

        # Machine Detail tab placeholder
        machine_detail_widget = self.ShimmerGlassPanel()
        machine_detail_widget.setObjectName('glassPanel')
        machine_detail_layout = QVBoxLayout()
        machine_detail_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        machine_detail_layout.addWidget(QLabel('Telemetry'))
        machine_detail_layout.addWidget(self.telemetry_panel, 1)
        machine_detail_widget.setLayout(machine_detail_layout)

        # Settings tab
        settings_widget = self.ShimmerGlassPanel()
        settings_widget.setObjectName('glassPanel')
        settings_layout = QVBoxLayout()
        settings_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        connection_details_box = QFrame()
        connection_details_box.setObjectName('connectionDetailsBox')
        connection_details_layout = QVBoxLayout()
        connection_details_layout.setContentsMargins(8, 8, 8, 8)
        connection_details_layout.setSpacing(6)
        self.connection_details_header = QLabel('Connection Details')
        self.connection_details_header.setObjectName('connectionDetailsHeader')
        connection_details_layout.addWidget(self.connection_details_header)

        connection_details_layout.addWidget(QLabel('WebSocket Server Address:'))
        self.ws_url_input = QLineEdit(self.ws_url)
        connection_details_layout.addWidget(self.ws_url_input)
        connection_details_layout.addWidget(QLabel('Room ID:'))
        self.room_id_input = QLineEdit(self.room_id)
        connection_details_layout.addWidget(self.room_id_input)
        connection_details_layout.addWidget(QLabel('Secret:'))
        self.secret_input = QLineEdit(self.secret)
        self.secret_input.setEchoMode(QLineEdit.Password)
        connection_details_layout.addWidget(self.secret_input)
        connection_details_layout.addWidget(QLabel('Target Machine ID:'))
        self.target_machine_id_input = QLineEdit(self.target_machine_id)
        connection_details_layout.addWidget(self.target_machine_id_input)

        self.ws_connect_btn = QPushButton('Connect')
        connection_details_layout.addWidget(self.ws_connect_btn)

        connection_details_box.setLayout(connection_details_layout)
        settings_layout.addWidget(connection_details_box)

        ui_settings_box = QFrame()
        ui_settings_box.setObjectName('uiSettingsBox')
        ui_settings_box_layout = QVBoxLayout()
        ui_settings_box_layout.setContentsMargins(8, 8, 8, 8)
        ui_settings_box_layout.setSpacing(6)

        self.ui_settings_header = QLabel('UI SETTINGS')
        self.ui_settings_header.setObjectName('uiSettingsHeader')
        ui_settings_box_layout.addWidget(self.ui_settings_header)
        self.rgb_mode_checkbox = QPushButton('Enable RGB Mode')
        self.rgb_mode_checkbox.setCheckable(True)
        self.rgb_mode_checkbox.setChecked(False)
        ui_settings_box_layout.addWidget(self.rgb_mode_checkbox)
        self.akka_mode_checkbox = QPushButton('Enable AKKA Mode')
        self.akka_mode_checkbox.setCheckable(True)
        self.akka_mode_checkbox.setChecked(False)
        ui_settings_box_layout.addWidget(self.akka_mode_checkbox)
        self.noctua_mode_checkbox = QPushButton('Enable NOCTUA Mode')
        self.noctua_mode_checkbox.setCheckable(True)
        self.noctua_mode_checkbox.setChecked(False)
        ui_settings_box_layout.addWidget(self.noctua_mode_checkbox)
        self.minimal_ui_btn = QPushButton('Enable Minimal UI')
        self.minimal_ui_btn.setCheckable(True)
        ui_settings_box_layout.addWidget(self.minimal_ui_btn)

        ui_settings_box.setLayout(ui_settings_box_layout)
        settings_layout.addWidget(ui_settings_box)
        settings_widget.setLayout(settings_layout)

        self.chat_send.setObjectName('whiteTextButton')
        self.clipboard_send_btn.setObjectName('whiteTextButton')
        self.file_select_btn.setObjectName('whiteTextButton')
        self.dest_select_btn.setObjectName('whiteTextButton')
        self.file_send_btn.setObjectName('whiteTextButton')
        self.ws_connect_btn.setObjectName('whiteTextButton')
        self.rgb_mode_checkbox.setObjectName('rgbModeToggleButton')
        self.akka_mode_checkbox.setObjectName('akkaModeToggleButton')
        self.noctua_mode_checkbox.setObjectName('noctuaModeToggleButton')
        self.minimal_ui_btn.setObjectName('whiteTextButton')

        for mode_widget in [
            self.chat_send,
            self.clipboard_send_btn,
            self.file_select_btn,
            self.dest_select_btn,
            self.file_send_btn,
            self.ws_connect_btn,
            self.rgb_mode_checkbox,
            self.akka_mode_checkbox,
            self.noctua_mode_checkbox,
            self.chat_input,
            self.clipboard_input,
            self.file_input,
            self.dest_input,
            self.ws_url_input,
            self.room_id_input,
            self.secret_input,
            self.target_machine_id_input,
            self.sender_list,
            self.chat_log,
            self.telemetry_panel,
        ]:
            self._register_mode_widget(mode_widget)

        # App pages (replaces top tabs so taskbar remains visible globally).
        self.main_pages = QStackedWidget()
        self.main_pages.addWidget(monitor_wall_widget)
        self.main_pages.addWidget(machine_detail_widget)
        self.main_pages.addWidget(settings_widget)

        def switch_main_page(index):
            self.main_pages.setCurrentIndex(index)
            for i, tray_btn in enumerate(self.taskbar_tray_buttons[:3]):
                tray_btn.setProperty('active', 'true' if i == index else 'false')
                tray_btn.style().unpolish(tray_btn)
                tray_btn.style().polish(tray_btn)
            if index != 0:
                self._hide_control_panel()

        # Move former top-tab navigation into tray icons next to the clock.
        if len(self.taskbar_tray_buttons) >= 3:
            self.taskbar_tray_buttons[0].clicked.connect(lambda: switch_main_page(0))
            self.taskbar_tray_buttons[1].clicked.connect(lambda: switch_main_page(1))
            self.taskbar_tray_buttons[2].clicked.connect(lambda: switch_main_page(2))
            switch_main_page(0)

        # Central widget
        central_widget = self.ShimmerBackgroundRoot()
        central_widget.setObjectName('glassRoot')
        central_layout = QVBoxLayout()
        self.central_layout = central_layout
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.main_pages, 1)
        central_layout.addWidget(bubble_bar, 0, Qt.AlignBottom)
        central_widget.setLayout(central_layout)
        self.setCentralWidget(central_widget)

        self.stream_label.setObjectName('streamSurface')
        self.chat_log.setObjectName('glassInput')
        self.telemetry_panel.setObjectName('glassInput')
        self.sender_list.setObjectName('glassInput')
        self.chat_input.setObjectName('glassInput')
        self.clipboard_input.setObjectName('glassInput')
        self.file_input.setObjectName('glassInput')
        self.dest_input.setObjectName('glassInput')
        self.ws_url_input.setObjectName('glassInput')
        self.room_id_input.setObjectName('glassInput')
        self.secret_input.setObjectName('glassInput')
        self.target_machine_id_input.setObjectName('glassInput')

        # Connect settings button
        self.ws_connect_btn.clicked.connect(self.change_ws_settings)
        self.rgb_mode_checkbox.toggled.connect(self._set_rgb_mode)
        self.akka_mode_checkbox.toggled.connect(self._set_akka_mode)
        self.noctua_mode_checkbox.toggled.connect(self._set_noctua_mode)
        self._update_mode_toggle_button_labels()
        self.left_dock_toggle_btn.toggled.connect(self._set_taskbar_left_mode)
        self.minimal_ui_btn.toggled.connect(self._set_reduced_effects_mode)
        self._apply_mode_compatibility()

        # Dark-only styling baseline (light stylesheet removed).
        self._apply_current_stylesheet()

        # Track depth effects so Minimal UI mode can turn them off and restore them.
        self._depth_effect_specs = [
            (stream_container, 124, 18, 4),
            (self.control_panel_container, 124, 18, 4),
            (bubble_bar, 124, 18, 4),
            (self.stream_label, 124, 18, 4),
            (self.left_banner, 124, 18, 4),
            (machine_detail_widget, 124, 18, 4),
            (settings_widget, 124, 18, 4),
            (self.chat_send, 108, 12, 3),
            (self.clipboard_send_btn, 108, 12, 3),
            (self.file_select_btn, 108, 12, 3),
            (self.dest_select_btn, 108, 12, 3),
            (self.file_send_btn, 108, 12, 3),
            (self.ws_connect_btn, 108, 12, 3),
            (self.noctua_mode_checkbox, 108, 12, 3),
            (self.minimal_ui_btn, 108, 12, 3),
            (self.mouse_center_btn, 108, 12, 3),
            (self.mouse_left_btn, 108, 12, 3),
            (self.mouse_right_btn, 108, 12, 3),
            (self.key_send_btn, 108, 12, 3),
            (self.kill_pid_btn, 108, 12, 3),
        ]
        for nav_btn in self.nav_buttons:
            self._depth_effect_specs.append((nav_btn, 138, 20, 5))
        self._set_depth_effects_enabled(True)

        QTimer.singleShot(0, self._update_responsive_ui)
        QTimer.singleShot(0, lambda: self.set_nav_shimmer_progress(self._nav_shimmer_progress))

    # ---- File Manager methods ----

    def _fm_refresh_local(self):
        path = self._fm_local_path.text()
        self._fm_local_list.clear()
        try:
            for item in sorted(os.listdir(path)):
                self._fm_local_list.addItem(item)
        except Exception as e:
            self._fm_local_list.addItem(f'Error: {e}')

    def _fm_local_up(self):
        path = self._fm_local_path.text()
        parent = os.path.dirname(path)
        if parent and parent != path:
            self._fm_local_path.setText(parent)
            self._fm_refresh_local()

    def _fm_handle_local_double_click(self, item):
        full_path = os.path.join(self._fm_local_path.text(), item.text())
        if os.path.isdir(full_path):
            self._fm_local_path.setText(full_path)
            self._fm_refresh_local()

    def _fm_refresh_remote(self):
        path = self._fm_remote_path.text()
        if not path or not path.strip():
            path = 'C:\\'
            self._fm_remote_path.setText(path)
        if not self.selected_sender:
            self.show_warning('Select a sender before browsing remote files.')
            return
        if not self.ws:
            self.show_warning('Not connected to server.')
            return
        asyncio.ensure_future(self.send_ws({
            'type': 'remote-control',
            'action': 'file-list',
            'machineId': self.selected_sender,
            'path': path,
        }))

    def _fm_remote_up(self):
        path = self._fm_remote_path.text()
        parent = os.path.dirname(path)
        if parent and parent != path:
            self._fm_remote_path.setText(parent)
            self._fm_refresh_remote()

    def _fm_handle_remote_double_click(self, item):
        if item.data(Qt.UserRole) == 'dir':
            new_path = os.path.join(self._fm_remote_path.text(), item.data(Qt.UserRole + 1))
            self._fm_remote_path.setText(new_path)
            self._fm_refresh_remote()

    def _fm_remote_path_changed(self):
        path = self._fm_remote_path.text()
        if not path or not self.selected_sender or not self.ws:
            return
        asyncio.ensure_future(self.send_ws({
            'type': 'remote-control', 'action': 'set-directory',
            'machineId': self.selected_sender, 'path': path,
        }))
        self._fm_refresh_remote()

    def _fm_update_remote_list(self, data):
        path = data.get('path', '')
        files = data.get('files', [])
        directories = data.get('directories', [])
        requested = self._fm_remote_path.text()
        if path and os.path.normpath(path) == os.path.normpath(requested):
            self._fm_remote_path.setText(path)
        self._fm_remote_list.clear()
        if not files and not directories:
            self._fm_remote_list.addItem('No files or directories found.')
        else:
            for dname in directories:
                li = QListWidgetItem(f'[DIR] {dname}')
                li.setData(Qt.UserRole, 'dir')
                li.setData(Qt.UserRole + 1, dname)
                self._fm_remote_list.addItem(li)
            for fname in files:
                li = QListWidgetItem(fname)
                li.setData(Qt.UserRole, 'file')
                li.setData(Qt.UserRole + 1, fname)
                self._fm_remote_list.addItem(li)
        self._fm_remote_list.repaint()

    def _fm_upload(self):
        if not self.selected_sender:
            self.show_warning('Select a sender before uploading.')
            return
        selected = self._fm_local_list.selectedItems()
        if selected:
            local_file = os.path.join(self._fm_local_path.text(), selected[0].text())
            if os.path.isdir(local_file):
                self.show_warning('Cannot upload a directory.')
                return
        else:
            local_file, _ = QFileDialog.getOpenFileName(self, 'Select file to upload')
            if not local_file:
                return
        remote_dir = self._fm_remote_path.text().rstrip('\\').rstrip('/') or 'C:'
        file_name = os.path.basename(local_file)
        remote_path = remote_dir + '\\' + file_name
        try:
            with open(local_file, 'rb') as fh:
                encoded = base64.b64encode(fh.read()).decode('utf-8')
        except Exception as e:
            self.show_warning(f'Failed to read file: {e}')
            return
        asyncio.ensure_future(self.send_ws({
            'type': 'remote-control',
            'action': 'file-upload',
            'machineId': self.selected_sender,
            'remotePath': remote_path,
            'fileName': file_name,
            'data': encoded,
        }))
        self.show_warning(f'Uploading {file_name}...')

    def _fm_download(self):
        if not self.selected_sender:
            self.show_warning('Select a sender before downloading.')
            return
        selected = self._fm_remote_list.selectedItems()
        if not selected:
            self.show_warning('Select a remote file to download.')
            return
        item = selected[0]
        if item.data(Qt.UserRole) == 'dir':
            self.show_warning('Cannot download a directory.')
            return
        item_name = item.data(Qt.UserRole + 1)
        remote_dir = self._fm_remote_path.text().rstrip('\\').rstrip('/') or 'C:'
        remote_path = remote_dir + '\\' + item_name
        save_path, _ = QFileDialog.getSaveFileName(
            self, 'Save downloaded file as',
            os.path.join(self._fm_local_path.text(), item_name)
        )
        if not save_path:
            return
        self._fm_pending_download_path = save_path
        self._fm_pending_request_id = str(uuid.uuid4())
        asyncio.ensure_future(self.send_ws({
            'type': 'remote-control',
            'action': 'file-download',
            'machineId': self.selected_sender,
            'path': remote_path,
            'fileName': item_name,
            'requestId': self._fm_pending_request_id,
        }))
        self.show_warning(f'Downloading {item_name}...')

    def _fm_receive_download(self, data):
        file_name = data.get('fileName', 'download')
        file_data_b64 = data.get('data', '')
        save_path = self._fm_pending_download_path
        if not save_path:
            save_path, _ = QFileDialog.getSaveFileName(
                self, 'Save downloaded file as',
                os.path.join(self._fm_local_path.text(), file_name)
            )
        if not save_path:
            return
        try:
            with open(save_path, 'wb') as fh:
                fh.write(base64.b64decode(file_data_b64))
            self._fm_pending_download_path = None
            self.show_warning(f'Downloaded: {os.path.basename(save_path)}')
            self._fm_refresh_local()
        except Exception as e:
            self.show_warning(f'Failed to save file: {e}')

    def change_ws_settings(self):
        new_url = self.ws_url_input.text()
        new_room = self.room_id_input.text()
        new_secret = self.secret_input.text()
        new_target = self.target_machine_id_input.text()
        changed = False
        if new_url and new_url != self.ws_url:
            self.ws_url = new_url
            changed = True
        if new_room and new_room != self.room_id:
            self.room_id = new_room
            changed = True
        if new_secret and new_secret != self.secret:
            self.secret = new_secret
            changed = True
        if new_target != self.target_machine_id:
            self.target_machine_id = new_target
            changed = True
        if changed:
            self.status_label.setText('Reconnecting...')
            self.reconnect()

    def create_remote_panel(self):
        group = QGroupBox()
        layout = QFormLayout()
        self.mouse_center_btn = QPushButton('Move Mouse Center')
        self.mouse_left_btn = QPushButton('Left Click')
        self.mouse_right_btn = QPushButton('Right Click')
        self.key_input = QLineEdit()
        self.key_send_btn = QPushButton('Send Key')
        self.kill_pid_input = QLineEdit()
        self.kill_pid_btn = QPushButton('Kill Process')
        layout.addRow(self.mouse_center_btn)
        layout.addRow(self.mouse_left_btn)
        layout.addRow(self.mouse_right_btn)
        layout.addRow('Key:', self.key_input)
        layout.addRow(self.key_send_btn)
        layout.addRow('PID:', self.kill_pid_input)
        layout.addRow(self.kill_pid_btn)
        group.setLayout(layout)
        return group

def main():
    print("[DEBUG] main() called, starting QAsyncApplication and QEventLoop")
    app = QAsyncApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = ViewerWindow()
    window.show()
    print("[DEBUG] Entering QEventLoop.run_forever()")
    with loop:
        loop.run_forever()

if __name__ == '__main__':
    main()
