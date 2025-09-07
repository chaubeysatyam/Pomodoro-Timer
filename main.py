import sys
import os
import csv
import shutil
import sqlite3
import json
from datetime import datetime, timedelta

from PyQt5.QtCore import QTimer, Qt, QPoint, QDateTime, QUrl
from PyQt5.QtGui import QFont, QIcon, QPalette, QColor
from PyQt5.QtMultimedia import QSound, QMediaPlayer, QMediaContent
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QLabel, QLineEdit, QMessageBox, QComboBox,
    QSystemTrayIcon, QFileDialog, QDialog, QDialogButtonBox, QFormLayout, QDateTimeEdit,
    QCheckBox, QMenu, QAction, QTextEdit, QSpinBox, QStyle, QGraphicsDropShadowEffect,
    QScrollArea
)

DB_PATH = 'tasks.db'
BACKUP_PATH = 'tasks_backup.db'
STUDY_TIME_FILE = 'study_time.json'

# -------- Helper: resource path for PyInstaller (onefile/onedir) --------
def resource_path(relative_path: str) -> str:
    try:
        base_path = getattr(sys, '_MEIPASS', None)
        if base_path:
            return os.path.join(base_path, relative_path)
    except Exception:
        pass
    return os.path.join(os.path.abspath('.'), relative_path)

def load_study_time():
    """Return total study time in seconds. Handles legacy minutes and string values."""
    try:
        if os.path.exists(STUDY_TIME_FILE):
            with open(STUDY_TIME_FILE, 'r') as f:
                data = json.load(f) or {}
                # Prefer seconds; coerce to int
                if 'total_seconds' in data:
                    try:
                        secs = int(float(data.get('total_seconds') or 0))
                    except Exception:
                        secs = 0
                    return max(0, secs)
                # Legacy minutes support
                if 'total_minutes' in data:
                    try:
                        mins = int(float(data.get('total_minutes') or 0))
                    except Exception:
                        mins = 0
                    secs = max(0, mins) * 60
                    # Migrate file to seconds format
                    try:
                        save_study_time(secs)
                    except Exception:
                        pass
                    return secs
    except Exception:
        pass
    return 0

def save_study_time(seconds):
    try:
        secs = int(float(seconds or 0))
        data = {'total_seconds': max(0, secs)}
        with open(STUDY_TIME_FILE, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass

def add_study_time(seconds):
    current = load_study_time()
    new_total = current + seconds
    save_study_time(new_total)
    return new_total

def format_study_time(seconds):
    if seconds < 60:
        return f"{seconds} seconds"
    elif seconds < 3600:  # 1 hour
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    elif seconds < 86400:  # 24 hours
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    elif seconds < 31536000:  # 365 days
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h"
    else:
        years = seconds // 31536000
        days = (seconds % 31536000) // 86400
        return f"{years}y {days}d"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
                 id INTEGER PRIMARY KEY,
                 task TEXT,
                 category TEXT,
                 completed INTEGER,
                 duedate TEXT,
                 subtasks TEXT,
                 started_at TEXT,
                 completed_at TEXT
                 )""")
    conn.commit()

    cols = {row[1] for row in c.execute("PRAGMA table_info(tasks)").fetchall()}
    to_add = []
    if 'priority' not in cols:
        to_add.append(("ALTER TABLE tasks ADD COLUMN priority TEXT DEFAULT 'Medium'",))
    if 'tags' not in cols:
        to_add.append(("ALTER TABLE tasks ADD COLUMN tags TEXT DEFAULT ''",))
    if 'recurring' not in cols:
        to_add.append(("ALTER TABLE tasks ADD COLUMN recurring TEXT DEFAULT 'None'",))
    if 'pomodoros' not in cols:
        to_add.append(("ALTER TABLE tasks ADD COLUMN pomodoros INTEGER DEFAULT 0",))
    if 'last_pomodoro_at' not in cols:
        to_add.append(("ALTER TABLE tasks ADD COLUMN last_pomodoro_at TEXT",))

    for (stmt,) in to_add:
        c.execute(stmt)
        conn.commit()

    conn.close()

def backup_db():
    try:
        if os.path.exists(DB_PATH):
            shutil.copyfile(DB_PATH, BACKUP_PATH)
    except Exception:
        pass

def add_task(task, category, duedate=None, subtasks="", priority="Medium", tags="", recurring="None"):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT INTO tasks
            (task, category, completed, duedate, subtasks, started_at, completed_at, priority, tags, recurring, pomodoros, last_pomodoro_at)
            VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, ?, 0, NULL)""",
            (task, category, duedate, subtasks, datetime.now().isoformat(), None, priority, tags, recurring))
        conn.commit()
    except sqlite3.Error as e:
        QMessageBox.critical(None, "Database Error", f"Failed to add task: {str(e)}")
    finally:
        conn.close()

def get_tasks():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # Show pending tasks first, and within each group show newest first
        c.execute("SELECT * FROM tasks ORDER BY completed ASC, id DESC")
        tasks = c.fetchall()
        conn.close()
        return tasks
    except sqlite3.Error as e:
        QMessageBox.critical(None, "Database Error", f"Failed to retrieve tasks: {str(e)}")
        return []

def complete_task_db(task_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE tasks SET completed = 1, completed_at = ? WHERE id = ?", (datetime.now().isoformat(), task_id))
        conn.commit()
    except sqlite3.Error as e:
        QMessageBox.critical(None, "Database Error", f"Failed to complete task: {str(e)}")
    finally:
        conn.close()

def delete_task_db(task_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
    except sqlite3.Error as e:
        QMessageBox.critical(None, "Database Error", f"Failed to delete task: {str(e)}")
    finally:
        conn.close()

def increment_pomodoro(task_id):
    if not task_id:
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE tasks SET pomodoros = IFNULL(pomodoros,0)+1, last_pomodoro_at = ? WHERE id = ?", (datetime.now().isoformat(), task_id))
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        conn.close()

class SettingsManager:
    def __init__(self):
        self.focus_secs = 25 * 60
        self.short_break_secs = 5 * 60
        self.long_break_secs = 15 * 60
        self.long_break_every = 4

    def set_from_minutes(self, focus_m, short_m, long_m, every_n):
        self.focus_secs = max(1, int(focus_m)) * 60
        self.short_break_secs = max(1, int(short_m)) * 60
        self.long_break_secs = max(1, int(long_m)) * 60
        self.long_break_every = max(1, int(every_n))

    def get_focus(self):
        return self.focus_secs

    def get_short(self):
        return self.short_break_secs

    def get_long(self):
        return self.long_break_secs

    def get_every(self):
        return self.long_break_every

settings_manager = SettingsManager()

def apply_global_theme(app: QApplication):
    # Premium macOS-inspired dark theme
    try:
        app.setFont(QFont("SF Pro Text", 12))
    except Exception:
        app.setFont(QFont("Segoe UI", 12))

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(18, 18, 22))
    palette.setColor(QPalette.WindowText, QColor(242, 242, 247))
    palette.setColor(QPalette.Base, QColor(20, 20, 26))
    palette.setColor(QPalette.AlternateBase, QColor(30, 30, 36))
    palette.setColor(QPalette.Text, QColor(235, 235, 240))
    palette.setColor(QPalette.Button, QColor(36, 36, 44))
    palette.setColor(QPalette.ButtonText, QColor(245, 245, 250))
    palette.setColor(QPalette.Highlight, QColor(10, 132, 255))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ToolTipBase, QColor(50, 50, 65))
    palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.PlaceholderText, QColor(180, 180, 195))
    app.setPalette(palette)

    app.setStyleSheet(
        """
        QWidget {
            color: #f5f6f8;
            font-family: -apple-system, 'SF Pro Text', 'Segoe UI', Arial, sans-serif;
            font-size: 13px;
        }

        QToolTip {
            background-color: rgba(40, 40, 55, 0.95);
            color: #ffffff;
            border: 1px solid rgba(255,255,255,0.12);
            padding: 6px 8px;
            border-radius: 8px;
        }

        QPushButton {
            background: #0a84ff;
            border: none;
            border-radius: 14px;
            padding: 10px 18px;
            color: #ffffff;
            font-weight: 600;
            letter-spacing: 0.2px;
            min-height: 28px;
        }
        QPushButton:hover { background: #0a74e6; }
        QPushButton:pressed { background: #085fb8; }
        QPushButton:disabled {
            background: #3a3f55;
            color: rgba(255,255,255,0.5);
        }

        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox {
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 12px;
            padding: 10px 12px;
            selection-background-color: #0a84ff;
            selection-color: white;
        }
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {
            border: 1px solid #0a84ff;
            background: rgba(255, 255, 255, 0.10);
        }

        QComboBox {
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 12px;
            padding: 8px 12px;
            min-height: 28px;
        }
        QComboBox:hover { border: 1px solid rgba(255, 255, 255, 0.18); }
        QComboBox:focus { border: 1px solid #0a84ff; }
        QComboBox QAbstractItemView {
            background: #24283b;
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 12px;
            selection-background-color: #0a84ff;
            color: white;
        }

        QListWidget, QTreeView, QTableView {
            background: rgba(255, 255, 255, 0.035);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 6px;
        }
        QListWidget::item {
            background: rgba(255, 255, 255, 0.045);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            margin: 4px;
            padding: 12px;
        }
        QListWidget::item:hover {
            background: rgba(255, 255, 255, 0.09);
        }
        QListWidget::item:selected {
            background: #0a84ff;
            border: 1px solid rgba(255,255,255,0.2);
        }

        QMenu {
            background: rgba(36, 40, 59, 0.92);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 10px;
            padding: 6px;
        }
        QMenu::item {
            padding: 8px 12px;
            border-radius: 6px;
        }
        QMenu::item:selected { background: rgba(102,126,234,0.25); }
        QMenu::separator { height: 1px; background: rgba(255,255,255,0.08); margin: 6px 8px; }

        QDialog {
            background: rgba(255,255,255,0.03);
            color: white;
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 14px;
        }

        QScrollBar:vertical {
            background: transparent;
            width: 12px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: rgba(255, 255, 255, 0.25);
            min-height: 24px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 0.4); }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """
    )

def play_notification_sound():
    mp3_path = resource_path(os.path.join('sounds', 'notify.mp3'))
    wav_path = resource_path(os.path.join('sounds', 'notify.wav'))
    try:
        if os.path.exists(mp3_path):
            player = QMediaPlayer()
            media = QMediaContent(QUrl.fromLocalFile(mp3_path))
            player.setMedia(media)
            player.setVolume(70)
            player.play()
            QApplication.instance()._last_media_player = player  # keep ref
            return
        if os.path.exists(wav_path):
            QSound.play(wav_path)
            return
    except Exception:
        pass
    try:
        QApplication.beep()
    except Exception:
        pass

class PomodoroManager:
    """
    Handles cycle logic and emits callbacks for UI to update.
    Phases: 'Focus', 'Short Break', 'Long Break'
    """
    def __init__(self, on_phase_change=None, on_tick=None, on_complete_cycle=None):
        self.on_phase_change = on_phase_change
        self.on_tick = on_tick
        self.on_complete_cycle = on_complete_cycle

        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)

        self.phase = 'Focus'
        self.remaining = settings_manager.get_focus()
        self.is_running = False
        self.completed_focus_count = 0  # since last long break
        self.attached_task_id = None
        self.session_start_time = None
        self.total_session_time = 0  # seconds completed in this session

    def attach_task(self, task_id: int):
        self.attached_task_id = task_id

    def save_current_session(self):
        """Save current session time immediately"""
        if self.phase == 'Focus' and self.session_start_time:
            elapsed = datetime.now() - self.session_start_time
            self.total_session_time += elapsed.total_seconds()
            self.session_start_time = None
            if self.total_session_time > 0:
                add_study_time(int(self.total_session_time))
                self.total_session_time = 0

    def start(self):
        if not self.is_running:
            if self.remaining <= 0:
                self._reset_phase_duration()
            self.timer.start(1000)
            self.is_running = True
            if self.phase == 'Focus' and not self.session_start_time:
                self.session_start_time = datetime.now()

    def pause(self):
        if self.is_running:
            self.timer.stop()
            self.is_running = False
            if self.phase == 'Focus' and self.session_start_time:
                elapsed = datetime.now() - self.session_start_time
                self.total_session_time += elapsed.total_seconds()
                self.session_start_time = None
                if self.total_session_time > 0:
                    add_study_time(int(self.total_session_time))
                    self.total_session_time = 0

    def reset(self):
        if self.phase == 'Focus' and self.session_start_time:
            elapsed = datetime.now() - self.session_start_time
            self.total_session_time += elapsed.total_seconds()
            self.session_start_time = None

        if self.total_session_time > 0:
            add_study_time(int(self.total_session_time))
            self.total_session_time = 0

        self.pause()
        self.phase = 'Focus'
        self.remaining = settings_manager.get_focus()
        self._notify_phase_change()

    def switch_phase(self, phase: str):
        if self.phase == 'Focus' and self.session_start_time:
            elapsed = datetime.now() - self.session_start_time
            self.total_session_time += elapsed.total_seconds()
            self.session_start_time = None
            if self.total_session_time > 0:
                add_study_time(int(self.total_session_time))
                self.total_session_time = 0

        self.phase = phase
        self._reset_phase_duration()
        self._notify_phase_change()

        if self.is_running:
            self.timer.start(1000)
            if self.phase == 'Focus':
                self.session_start_time = datetime.now()

    def _reset_phase_duration(self):
        if self.phase == 'Focus':
            self.remaining = settings_manager.get_focus()
        elif self.phase == 'Short Break':
            self.remaining = settings_manager.get_short()
        else:
            self.remaining = settings_manager.get_long()

    def _format(self, secs):
        m, s = divmod(max(0, int(secs)), 60)
        return f"{m:02}:{s:02}"

    def _tick(self):
        if self.remaining <= 0:
            self._handle_phase_end()
            return
        self.remaining -= 1
        if self.on_tick:
            self.on_tick(self.phase, self.remaining, self._format(self.remaining))

    def _handle_phase_end(self):
        play_notification_sound()

        if self.phase == 'Focus':
            self.completed_focus_count += 1
            if self.attached_task_id:
                increment_pomodoro(self.attached_task_id)

            if self.session_start_time:
                elapsed = datetime.now() - self.session_start_time
                self.total_session_time += elapsed.total_seconds()
                self.session_start_time = None
                add_study_time(int(self.total_session_time))
                self.total_session_time = 0

        if self.phase == 'Focus':
            if self.completed_focus_count % settings_manager.get_every() == 0:
                self.phase = 'Long Break'
            else:
                self.phase = 'Short Break'
        else:
            self.phase = 'Focus'

        self._reset_phase_duration()
        self._notify_phase_change()

        if self.on_complete_cycle:
            self.on_complete_cycle(self.phase)

    def _notify_phase_change(self):
        if self.on_phase_change:
            self.on_phase_change(self.phase, self.remaining, self._format(self.remaining))

class FloatingPomodoroWidget(QWidget):
    def __init__(self, parent=None, manager=None):
        super().__init__(None)
        self._owner = parent
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Pomodoro Timer")

        self.attached_task_title = None

        self.manager = manager or PomodoroManager()

        self._pressed = False
        self._moved = False
        self._press_pos = None

        self.setStyleSheet(
            """
            QWidget#FloatingPanel {
                background: rgba(25, 25, 32, 0.72);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 18px;
            }
            QLabel {
                color: #f5f6f8;
                font-family: -apple-system, 'SF Pro Text', 'Segoe UI', Arial, sans-serif;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a84ff, stop:1 #0a74e6);
                border: none;
                color: white;
                padding: 8px 14px;
                border-radius: 14px;
                font-weight: 600;
                font-size: 14px;
            }
            QPushButton:hover { background: #0a74e6; }
            QPushButton:pressed { background: #085fb8; }
            QPushButton#StartBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #34c759, stop:1 #2fb14f);
            }
            QPushButton#StartBtn:hover { background: #2fb14f; }
            QPushButton#StartBtn:pressed { background: #279745; }
            QPushButton#ResetBtn { background: #3a3a44; color: #e6e7ea; }
            QPushButton#ResetBtn:hover { background: #464654; }
            QPushButton#ResetBtn:pressed { background: #3b3b48; }
            QPushButton#CloseButton {
                background: rgba(255,255,255,0.08);
                color: #cfd2d8;
                border-radius: 12px;
                padding: 0px;
                font-size: 13px;
                min-width: 24px;
                min-height: 24px;
            }
            QPushButton#CloseButton:hover { background: rgba(255, 59, 48, 0.9); color: #ffffff; }
            QPushButton#CloseButton:pressed { background: rgba(220, 30, 20, 0.95); }
            """
        )

        panel = QWidget(self)
        panel.setObjectName("FloatingPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("Pomodoro")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #cfd2d8;")
        header.addWidget(title)
        header.addStretch()
        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("CloseButton")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.clicked.connect(self.close)
        header.addWidget(self.close_btn)
        layout.addLayout(header)

        self.label = QLabel("Pomodoro: 25:00")
        self.label.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #f5f6f8; padding: 10px;"
            "background: rgba(255, 255, 255, 0.06); border-radius: 14px;"
            "border: 1px solid rgba(255, 255, 255, 0.10);"
        )
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        self.study_time_label = QLabel("Study Time: 0s")
        self.study_time_label.setStyleSheet(
            "font-size: 13px; color: #2ecc71; font-weight: 600; padding: 8px;"
            "background: rgba(46, 204, 113, 0.12); border-radius: 12px;"
            "border: 1px solid rgba(46, 204, 113, 0.18);"
        )
        self.study_time_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.study_time_label)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.start_btn = QPushButton("▶ Start")
        self.start_btn.setObjectName("StartBtn")
        self.start_btn.clicked.connect(self._toggle)
        self.start_btn.setMinimumWidth(80)
        button_layout.addWidget(self.start_btn)

        self.reset_btn = QPushButton("⟳ Reset")
        self.reset_btn.setObjectName("ResetBtn")
        self.reset_btn.clicked.connect(self.manager.reset)
        self.reset_btn.setMinimumWidth(80)
        button_layout.addWidget(self.reset_btn)

        layout.addLayout(button_layout)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)
        self.setLayout(outer)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(Qt.black)
        panel.setGraphicsEffect(shadow)

        self.menu = QMenu(self)
        act_toggle = QAction("Start/Pause", self, triggered=self._toggle)
        act_reset = QAction("Reset", self, triggered=self._reset)
        act_attach = QAction("Attach Selected Task", self, triggered=self._attach_selected_task)
        phase_menu = QMenu("Switch Phase", self)
        phase_menu.addAction("Focus", lambda: self._switch('Focus'))
        phase_menu.addAction("Short Break", lambda: self._switch('Short Break'))
        phase_menu.addAction("Long Break", lambda: self._switch('Long Break'))
        self.menu.addAction(act_toggle)
        self.menu.addAction(act_reset)
        self.menu.addAction(act_attach)
        self.menu.addMenu(phase_menu)

        self.manager.on_tick = self._on_tick
        self.manager.on_phase_change = self._on_phase_change

        self._on_phase_change(self.manager.phase, self.manager.remaining, self._format(self.manager.remaining))

    def _format(self, seconds):
        m, s = divmod(seconds, 60)
        return f"{m:02}:{s:02}"

    def _title_text(self, phase, mmss):
        if self.attached_task_title:
            return f"{phase} {mmss} · {self.attached_task_title}"
        return f"{phase} {mmss}"

    def _on_phase_change(self, phase, remaining, mmss):
        color_map = {
            'Focus': '#58D68D',
            'Short Break': '#5DADE2',
            'Long Break': '#AF7AC5'
        }
        color = color_map.get(phase, 'white')
        self.label.setText(self._title_text(phase, mmss))
        self.label.setStyleSheet(f"font-size: 22px; font-weight: 600; color: {color};")

        total_study = load_study_time()
        self.study_time_label.setText(f"Study Time: {format_study_time(total_study)}")

    def _on_tick(self, phase, remaining, mmss):
        self.label.setText(self._title_text(phase, mmss))

        if phase == 'Focus' and self.manager.is_running:
            total_study = load_study_time()
            self.study_time_label.setText(f"Study Time: {format_study_time(total_study)}")

    def _on_cycle(self, next_phase):
        pass

    def _start(self):
        self.manager.start()

    def _pause(self):
        self.manager.pause()

    def _reset(self):
        self.manager.reset()
        self.attached_task_title = self.attached_task_title  # keep title

    def _switch(self, phase):
        self.manager.switch_phase(phase)

    def _toggle(self):
        if self.manager.is_running:
            self._pause()
        else:
            self._start()

    def _attach_selected_task(self):
        parent = self._owner
        if parent and isinstance(parent, TaskTracker):
            task = parent.get_selected_task_row()
            if task:
                task_id, title = task[0], task[1]
                self.manager.attach_task(int(task_id))
                self.attached_task_title = title
                self._on_phase_change(self.manager.phase, self.manager.remaining, self._format(self.manager.remaining))
                parent.toast("Pomodoro", f"Attached to task: {title}")
            else:
                parent.toast("Pomodoro", "No task selected to attach.")
        else:
            pass

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._moved = False
            self._press_pos = event.globalPos()
            event.accept()
        elif event.button() == Qt.RightButton:
            self.menu.popup(event.globalPos())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pressed and self._press_pos:
            delta = event.globalPos() - self._press_pos
            if delta.manhattanLength() > 6:
                self._moved = True
                self.move(self.x() + delta.x(), self.y() + delta.y())
                self._press_pos = event.globalPos()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pressed and event.button() == Qt.LeftButton:
            self._pressed = False
            if not self._moved:
                if self.manager.is_running:
                    self._pause()
                else:
                    self._start()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        event.accept()

    def closeEvent(self, event):
        if self.manager:
            self.manager.save_current_session()
        event.accept()

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super(SettingsDialog, self).__init__(parent)
        self.setWindowTitle('Routine  - Settings')
        self.setMinimumSize(500, 400)
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a1a2e, stop:1 #16213e);
                color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
            }

            QLabel {
                color: white;
                font-size: 13px;
                font-weight: 500;
            }

            QLabel#SectionTitle {
                font-size: 16px;
                font-weight: bold;
                color: #667eea;
                padding: 10px 0;
                border-bottom: 2px solid rgba(102, 126, 234, 0.3);
            }

            QLabel#StudyTimeDisplay {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2ecc71, stop:1 #27ae60);
                border-radius: 10px;
                padding: 15px;
                font-size: 18px;
                font-weight: bold;
                color: white;
                text-align: center;
            }

            QSpinBox {
                background: rgba(255, 255, 255, 0.1);
                border: 2px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                padding: 10px 15px;
                color: white;
                font-size: 14px;
                font-weight: 500;
                min-width: 100px;
            }
            QSpinBox:hover {
                border: 2px solid rgba(255, 255, 255, 0.3);
            }
            QSpinBox:focus {
                border: 2px solid #667eea;
                background: rgba(255, 255, 255, 0.15);
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 4px;
                width: 20px;
                height: 15px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: rgba(255, 255, 255, 0.2);
            }
            QSpinBox::up-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 6px solid white;
            }
            QSpinBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
            }

            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                color: white;
                font-weight: bold;
                font-size: 14px;
                min-width: 100px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5a6fd8, stop:1 #6a4190);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a5fc8, stop:1 #5a3180);
            }

            QPushButton#CancelBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e74c3c, stop:1 #c0392b);
            }
            QPushButton#CancelBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #c0392b, stop:1 #a93226);
            }
        """)

        self.form = QVBoxLayout(self)
        self.form.setSpacing(20)
        self.form.setContentsMargins(25, 25, 25, 25)

        header_label = QLabel("⚙️ Routine  Settings")
        header_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #667eea; text-align: center; padding: 10px;")
        self.form.addWidget(header_label)

        study_time_label = QLabel("📊 Total Study Time")
        study_time_label.setObjectName("SectionTitle")
        self.form.addWidget(study_time_label)

        self.study_time_value = QLabel(format_study_time(load_study_time()))
        self.study_time_value.setObjectName("StudyTimeDisplay")
        self.form.addWidget(self.study_time_value)

        pomodoro_label = QLabel("⏰ Pomodoro Timer Settings")
        pomodoro_label.setObjectName("SectionTitle")
        self.form.addWidget(pomodoro_label)

        settings_widget = QWidget()
        settings_layout = QFormLayout(settings_widget)
        settings_layout.setSpacing(15)
        settings_layout.setLabelAlignment(Qt.AlignRight)

        self.focus_m = QSpinBox(self)
        self.focus_m.setRange(1, 300)
        self.focus_m.setValue(settings_manager.get_focus() // 60)
        self.focus_m.setSuffix(" minutes")

        self.short_m = QSpinBox(self)
        self.short_m.setRange(1, 120)
        self.short_m.setValue(settings_manager.get_short() // 60)
        self.short_m.setSuffix(" minutes")

        self.long_m = QSpinBox(self)
        self.long_m.setRange(1, 240)
        self.long_m.setValue(settings_manager.get_long() // 60)
        self.long_m.setSuffix(" minutes")

        self.every_n = QSpinBox(self)
        self.every_n.setRange(1, 12)
        self.every_n.setValue(settings_manager.get_every())
        self.every_n.setSuffix(" sessions")

        settings_layout.addRow('Focus Duration:', self.focus_m)
        settings_layout.addRow('Short Break:', self.short_m)
        settings_layout.addRow('Long Break:', self.long_m)
        settings_layout.addRow('Long Break Every:', self.every_n)

        self.form.addWidget(settings_widget)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        for button in self.button_box.buttons():
            if self.button_box.buttonRole(button) == QDialogButtonBox.RejectRole:
                button.setObjectName("CancelBtn")

        button_layout.addStretch()
        button_layout.addWidget(self.button_box)
        self.form.addLayout(button_layout)

    def accept(self):
        settings_manager.set_from_minutes(self.focus_m.value(), self.short_m.value(), self.long_m.value(), self.every_n.value())
        super().accept()

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super(HelpDialog, self).__init__(parent)
        self.setWindowTitle('Help')
        self.setGeometry(400, 400, 440, 280)
        layout = QVBoxLayout(self)
        text = QLabel(
            "Task Tracker + Floating Pomodoro\n\n"
            "• Add tasks with priority, tags, recurring.\n"
            "• Start the Floating Pomodoro and attach it to a task.\n"
            "• Left-click to start/pause; drag to move; right-click for options.\n"
            "• Auto cycles focus/short/long breaks.\n"
            "• Stats shows your progress; Import/Export CSV for backup.\n"
            "• System Tray lets you quick-control the timer.\n"
        )
        text.setWordWrap(True)
        layout.addWidget(text)

class StatsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Statistics')
        self.setStyleSheet("""
            QDialog {
                background-color: #2c3e50;
                color: white;
            }
            QLabel {
                color: white;
                font-size: 12px;
            }
            QPushButton {
                background-color: #3498db;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)

        layout = QVBoxLayout(self)
        self.info = QLabel("", self)
        self.info.setWordWrap(True)
        self.info.setStyleSheet("font-size: 13px; line-height: 1.5; padding: 15px; background-color: #34495e; border-radius: 8px;")
        layout.addWidget(self.info)

        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            total = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            done = c.execute("SELECT COUNT(*) FROM tasks WHERE completed=1").fetchone()[0]
            today = datetime.now().date().isoformat()
            done_today = c.execute(
                "SELECT COUNT(*) FROM tasks WHERE completed=1 AND date(substr(completed_at,1,10))=?",
                (today,)
            ).fetchone()[0]
            total_pomos = c.execute("SELECT SUM(pomodoros) FROM tasks").fetchone()[0] or 0
            latest = c.execute("SELECT task, pomodoros FROM tasks ORDER BY last_pomodoro_at DESC LIMIT 1").fetchone()
            conn.close()
        except Exception:
            total = done = done_today = total_pomos = 0
            latest = None

        total_study_time = load_study_time()
        study_time_formatted = format_study_time(total_study_time)

        latest_txt = f"{latest[0]} (+{latest[1]} total)" if latest else "—"

        stats_text = f"""
📊 <b>Task Statistics:</b>
• Total tasks: <span style='color: #3498db;'>{total}</span>
• Completed tasks: <span style='color: #2ecc71;'>{done}</span>
• Completed today: <span style='color: #f39c12;'>{done_today}</span>
• Total Pomodoro sessions: <span style='color: #e74c3c;'>{total_pomos}</span>
• Most recent Pomodoro: <span style='color: #9b59b6;'>{latest_txt}</span>

⏰ <b>Study Time:</b>
• Total study time: <span style='color: #2ecc71; font-size: 16px; font-weight: bold;'>{study_time_formatted}</span>
        """

        self.info.setText(stats_text)

        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)

class TaskDialog(QDialog):
    def __init__(self, parent=None):
        super(TaskDialog, self).__init__(parent)
        self.setWindowTitle('Add/Edit Task')

        self.form = QFormLayout(self)

        self.task_title_edit = QLineEdit(self)
        self.form.addRow('Task Title:', self.task_title_edit)

        self.category_combobox = QComboBox(self)
        self.category_combobox.addItems(['Study', 'Homework'])
        self.form.addRow('Category:', self.category_combobox)

        self.priority_combo = QComboBox(self)
        self.priority_combo.addItems(['High', 'Medium', 'Low'])
        self.form.addRow('Priority:', self.priority_combo)

        self.tags_edit = QLineEdit(self)
        self.tags_edit.setPlaceholderText("comma, separated, tags")
        self.form.addRow('Tags:', self.tags_edit)

        self.recurring_combo = QComboBox(self)
        self.recurring_combo.addItems(['None', 'Daily', 'Weekly'])
        self.form.addRow('Recurring:', self.recurring_combo)

        self.duedate_edit = QDateTimeEdit(self)
        self.duedate_edit.setCalendarPopup(True)
        self.duedate_edit.setDateTime(QDateTime.currentDateTime())
        self.form.addRow('Due Date:', self.duedate_edit)

        self.subtasks_edit = QLineEdit(self)
        self.form.addRow('Subtasks (comma-separated):', self.subtasks_edit)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.form.addRow(self.button_box)

        self.setLayout(self.form)

    def get_task_details(self):
        return {
            'title': self.task_title_edit.text().strip(),
            'category': self.category_combobox.currentText(),
            'priority': self.priority_combo.currentText(),
            'tags': self.tags_edit.text().strip(),
            'recurring': self.recurring_combo.currentText(),
            'duedate': self.duedate_edit.dateTime().toString(Qt.ISODate),
            'subtasks': self.subtasks_edit.text().strip()
        }

    def set_task_details(self, details):
        self.task_title_edit.setText(details.get('title', ''))
        self.category_combobox.setCurrentText(details.get('category', 'Study'))
        self.priority_combo.setCurrentText(details.get('priority', 'Medium'))
        self.tags_edit.setText(details.get('tags', ''))
        self.recurring_combo.setCurrentText(details.get('recurring', 'None'))
        if details.get('duedate'):
            self.duedate_edit.setDateTime(QDateTime.fromString(details.get('duedate'), Qt.ISODate))
        self.subtasks_edit.setText(details.get('subtasks', ''))

class TaskTracker(QMainWindow):
    def __init__(self):
        super().__init__()
        self._floating = None
        self._tray = None
        self.init_ui()
        self.init_tray()

    def init_ui(self):
        self.setWindowTitle('Routine - Task Tracker & Pomodoro Timer')
        self.setGeometry(400, 120, 1200, 800)

        try:
            icon = QIcon(resource_path('study.ico'))
            if not icon.isNull():
                self.setWindowIcon(icon)
            else:
                self.setWindowIcon(QIcon.fromTheme("face-smile"))
        except:
            self.setWindowIcon(QIcon.fromTheme("face-smile"))

        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #14151b, stop:1 #0f1117);
                color: #ffffff;
            }
            QWidget {
                background: transparent;
                color: #ffffff;
                font-family: -apple-system, 'SF Pro Text', 'Segoe UI', Arial, sans-serif;
            }

            /* Header and Title Styling */
            QLabel#TitleLabel {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
                padding: 14px 16px;
                font-size: 18px;
                font-weight: 700;
                color: #f5f6f8;
            }

            /* Search Bar */
            QLineEdit#SearchBar {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 22px;
                padding: 12px 20px;
                color: white;
                font-size: 14px;
                font-weight: 500;
            }
            QLineEdit#SearchBar:focus {
                border: 1px solid #0a84ff;
                background: rgba(255, 255, 255, 0.12);
            }
            QLineEdit#SearchBar::placeholder {
                color: rgba(255, 255, 255, 0.6);
            }

            /* Quick Add Section */
            QWidget#QuickAddPanel {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                padding: 16px;
                backdrop-filter: blur(12px);
            }

            QLineEdit#QuickAddInput {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 12px;
                padding: 10px 15px;
                color: white;
                font-size: 13px;
            }
            QLineEdit#QuickAddInput:focus {
                border: 1px solid #0a84ff;
            }
            QLineEdit#QuickAddInput::placeholder {
                color: rgba(255, 255, 255, 0.5);
            }

            /* ComboBox Styling */
            QComboBox {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 12px;
                padding: 10px 15px;
                color: white;
                font-size: 13px;
                font-weight: 500;
                min-width: 120px;
            }
            QComboBox:hover {
                background: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(255, 255, 255, 0.18);
            }
            QComboBox:focus {
                border: 1px solid #0a84ff;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-top: 6px solid white;
                margin-right: 10px;
            }
            QComboBox QAbstractItemView {
                background: #2c3e50;
                border: 1px solid #34495e;
                border-radius: 8px;
                selection-background-color: #667eea;
                color: white;
                font-size: 13px;
            }

            /* Task List */
            QListWidget {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                color: white;
                font-size: 14px;
                padding: 8px;
                outline: none;
            }
            QListWidget::item {
                background: rgba(255, 255, 255, 0.045);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-left: 4px solid rgba(10,132,255,0.85);
                border-radius: 12px;
                padding: 16px 16px;
                margin: 4px;
                font-size: 13px;
                line-height: 1.4;
            }
            QListWidget::item:hover {
                background: rgba(255, 255, 255, 0.09);
                border: 1px solid rgba(255, 255, 255, 0.12);
            }
            QListWidget::item:selected {
                background: #0a84ff;
                border: 1px solid rgba(255, 255, 255, 0.18);
            }

            /* Button Styling */
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0a84ff, stop:1 #0a74e6);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px;
                padding: 12px 20px;
                color: #ffffff;
                font-weight: 700;
                font-size: 13px;
                min-height: 20px;
            }
            QPushButton:hover { background: #0a74e6; }
            QPushButton:pressed { background: #085fb8; }
            QPushButton:focus { border: 2px solid rgba(10,132,255,0.65); }

            /* Special Button Styles */
            QPushButton#QuickAddBtn { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #34c759, stop:1 #2fb14f); }
            QPushButton#QuickAddBtn:hover { background: #2fb14f; }

            QPushButton#PomodoroBtn { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff9f0a, stop:1 #e28c09); font-size: 16px; padding: 15px 30px; border-radius: 18px; }
            QPushButton#PomodoroBtn:hover { background: #e28c09; }

            QPushButton#CompleteBtn { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #34c759, stop:1 #2fb14f); }
            QPushButton#CompleteBtn:hover { background: #2fb14f; }

            QPushButton#DeleteBtn { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff453a, stop:1 #e03d33); }
            QPushButton#DeleteBtn:hover { background: #e03d33; }

            /* Scrollbar Styling */
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.1);
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.3);
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.5);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }

            /* Panel Styling */
            QWidget#LeftPanel {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 14px;
                padding: 16px;
            }

            QWidget#RightPanel {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                padding: 16px;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        left_panel = QWidget()
        left_panel.setObjectName("LeftPanel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(15)

        header_layout = QHBoxLayout()
        title_label = QLabel("📚 Routine")
        title_label.setObjectName("TitleLabel")
        title_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title_label)
        left_layout.addLayout(header_layout)

        search_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("SearchBar")
        self.search_bar.setPlaceholderText('🔍 Search tasks, tags, or categories...')
        self.search_bar.textChanged.connect(self.search_tasks)
        search_layout.addWidget(self.search_bar)
        left_layout.addLayout(search_layout)

        list_label = QLabel("📋 Your Tasks")
        list_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #667eea; margin-bottom: 5px;")
        left_layout.addWidget(list_label)

        self.task_listbox = QListWidget()
        self.task_listbox.setWordWrap(True)  # Enable word wrapping
        left_layout.addWidget(self.task_listbox)

        main_layout.addWidget(left_panel, 6)

        right_panel_container = QWidget()
        right_panel_container.setObjectName("RightPanel")
        right_layout = QVBoxLayout(right_panel_container)
        right_layout.setSpacing(20)

        quick_add_widget = QWidget()
        quick_add_widget.setObjectName("QuickAddPanel")
        quick_add_layout = QVBoxLayout(quick_add_widget)

        quick_add_title = QLabel("⚡ Quick Add Task")
        quick_add_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2ecc71; margin-bottom: 10px;")
        quick_add_layout.addWidget(quick_add_title)

        entry_layout = QVBoxLayout()
        self.task_entry = QLineEdit()
        self.task_entry.setObjectName("QuickAddInput")
        self.task_entry.setPlaceholderText("Enter task title...")
        entry_layout.addWidget(self.task_entry)

        combo_layout = QHBoxLayout()
        self.category_combobox = QComboBox()
        self.category_combobox.addItems(['📖 Study', '📝 Homework', '💼 Work', '🏠 Personal'])
        combo_layout.addWidget(self.category_combobox)

        self.priority_quick = QComboBox()
        self.priority_quick.addItems(['⚪ Medium', '🔴 High', '🟢 Low'])
        combo_layout.addWidget(self.priority_quick)
        entry_layout.addLayout(combo_layout)

        add_quick_btn = QPushButton('➕ Add Task')
        add_quick_btn.setObjectName("QuickAddBtn")
        add_quick_btn.clicked.connect(self.quick_add_task)
        entry_layout.addWidget(add_quick_btn)

        quick_add_layout.addLayout(entry_layout)
        right_layout.addWidget(quick_add_widget)

        pomodoro_label = QLabel("⏰ Focus Timer")
        pomodoro_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #e74c3c; margin: 5px 0; text-align: center;")
        right_layout.addWidget(pomodoro_label)

        self.float_timer_button = QPushButton('🚀 Launch Floating Pomodoro Timer')
        self.float_timer_button.setObjectName("PomodoroBtn")
        self.float_timer_button.clicked.connect(self.toggle_floating_pomodoro)
        right_layout.addWidget(self.float_timer_button)

        buttons_label = QLabel("🛠️ Task Management")
        buttons_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #667eea; margin: 10px 0;")
        right_layout.addWidget(buttons_label)

        task_buttons_layout = QVBoxLayout()
        task_buttons_layout.setSpacing(10)

        self.add_button = QPushButton('📋 Add Task...')
        self.add_button.clicked.connect(self.show_task_dialog)
        task_buttons_layout.addWidget(self.add_button)

        self.complete_button = QPushButton('✅ Complete Task')
        self.complete_button.setObjectName("CompleteBtn")
        self.complete_button.clicked.connect(self.complete_task)
        task_buttons_layout.addWidget(self.complete_button)

        self.delete_button = QPushButton('🗑️ Delete Task')
        self.delete_button.setObjectName("DeleteBtn")
        self.delete_button.clicked.connect(self.delete_task)
        task_buttons_layout.addWidget(self.delete_button)

        right_layout.addLayout(task_buttons_layout)

        utility_label = QLabel("⚙️ Tools & Settings")
        utility_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #667eea; margin: 10px 0;")
        right_layout.addWidget(utility_label)

        utility_layout = QVBoxLayout()
        utility_layout.setSpacing(10)

        self.settings_button = QPushButton('⚙️ Settings')
        self.settings_button.clicked.connect(self.open_settings)
        utility_layout.addWidget(self.settings_button)

        self.stats_button = QPushButton('📊 Statistics')
        self.stats_button.clicked.connect(self.show_stats)
        utility_layout.addWidget(self.stats_button)

        self.help_button = QPushButton('❓ Help')
        self.help_button.clicked.connect(self.show_help)
        utility_layout.addWidget(self.help_button)

        right_layout.addLayout(utility_layout)

        data_label = QLabel("💾 Data Management")
        data_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #667eea; margin: 10px 0;")
        right_layout.addWidget(data_label)

        data_layout = QVBoxLayout()
        data_layout.setSpacing(10)

        self.export_button = QPushButton('📤 Export Tasks')
        self.export_button.clicked.connect(self.export_tasks)
        data_layout.addWidget(self.export_button)

        self.import_button = QPushButton('📥 Import Tasks')
        self.import_button.clicked.connect(self.import_tasks)
        data_layout.addWidget(self.import_button)

        right_layout.addLayout(data_layout)

        right_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(right_panel_container)

        main_layout.addWidget(scroll, 4)

        central_widget.setLayout(main_layout)
        self.update_tasks()

    def init_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self)
        # Prefer bundled app icon if available
        icon = QIcon(resource_path('study.ico'))
        if icon.isNull():
            icon = QIcon.fromTheme("face-smile")
        if icon.isNull():
            try:
                icon = QApplication.style().standardIcon(QStyle.SP_ComputerIcon)
            except Exception:
                icon = QIcon()
        self._tray.setIcon(icon)
        menu = QMenu()

        act_show = QAction("Show Window", self, triggered=self.showNormal)
        act_toggle_pomo = QAction("Toggle Floating Pomodoro", self, triggered=self.toggle_floating_pomodoro)
        act_start = QAction("Start Pomodoro", self, triggered=lambda: self._floating and self._floating._start())
        act_pause = QAction("Pause Pomodoro", self, triggered=lambda: self._floating and self._floating._pause())
        act_reset = QAction("Reset Pomodoro", self, triggered=lambda: self._floating and self._floating._reset())
        act_quit = QAction("Quit", self, triggered=self.close)

        menu.addAction(act_show)
        menu.addSeparator()
        menu.addAction(act_toggle_pomo)
        menu.addAction(act_start)
        menu.addAction(act_pause)
        menu.addAction(act_reset)
        menu.addSeparator()
        menu.addAction(act_quit)

        self._tray.setContextMenu(menu)
        self._tray.setToolTip("Task Tracker & Pomodoro")
        self._tray.show()

    def toast(self, title, message):
        if self._tray:
            self._tray.showMessage(title, message, QSystemTrayIcon.Information, 4000)

    def quick_add_task(self):
        title = self.task_entry.text().strip()
        if not title:
            return
        add_task(
            task=title,
            category=self.category_combobox.currentText(),
            duedate=None,
            subtasks="",
            priority=self.priority_quick.currentText(),
            tags="",
            recurring="None"
        )
        self.task_entry.clear()
        self.update_tasks()
        self.toast("Task added", title)

    def show_task_dialog(self):
        dialog = TaskDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            d = dialog.get_task_details()
            if not d['title']:
                QMessageBox.warning(self, "Input", "Task title is required.")
                return
            add_task(d['title'], d['category'], d['duedate'], d['subtasks'], d['priority'], d['tags'], d['recurring'])
            self.update_tasks()

    def export_tasks(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV files (*.csv)")
        if path:
            try:
                with open(path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(["ID","Task","Category","Completed","DueDate","Subtasks","Started At","Completed At","Priority","Tags","Recurring","Pomodoros","Last Pomodoro At"])
                    for task in get_tasks():
                        writer.writerow(task)
                self.toast("Export", "Tasks exported successfully.")
            except IOError:
                QMessageBox.critical(self, "Error", "Could not save file.")

    def import_tasks(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open CSV", "", "CSV files (*.csv)")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as file:
                    reader = csv.reader(file)
                    header = next(reader, None)
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    for row in reader:
                        row = row + [None] * (13 - len(row))
                        (task_id, task_title, task_category, task_completed, task_duedate, task_subtasks,
                         started_at, completed_at, priority, tags, recurring, pomodoros, last_pomo_at) = row
                        try:
                            c.execute("""INSERT OR REPLACE INTO tasks
                            (id, task, category, completed, duedate, subtasks, started_at, completed_at, priority, tags, recurring, pomodoros, last_pomodoro_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                      (task_id, task_title, task_category, int(task_completed or 0), task_duedate or None,
                                       task_subtasks or "", started_at or None, completed_at or None,
                                       priority or "Medium", tags or "", recurring or "None",
                                       int(pomodoros or 0), last_pomo_at or None))
                        except Exception:
                            continue
                    conn.commit()
                    conn.close()
                self.update_tasks()
                self.toast("Import", "Tasks imported.")
            except IOError:
                QMessageBox.critical(self, "Error", "Could not open file.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Import failed: {str(e)}")

    def search_tasks(self):
        query = self.search_bar.text().lower().strip()
        self.task_listbox.clear()
        tasks = get_tasks()
        for task in tasks:
            task_id, title, category, completed, duedate, subtasks, started_at, completed_at, priority, tags, recurring, pomos, last_pomo = task
            hay = f"{title} {tags}".lower()
            if query in hay:
                self._add_task_list_item(task)

    def complete_task(self):
        selected = self.get_selected_task_row()
        if selected:
            task_id = selected[0]
            complete_task_db(task_id)
            self._handle_recurring(selected)
            self.update_tasks()

    def delete_task(self):
        selected = self.get_selected_task_row()
        if selected:
            task_id = selected[0]
            delete_task_db(task_id)
            self.update_tasks()

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec_()
        if self._floating:
            self._floating._reset()
            self._floating._on_phase_change(self._floating.manager.phase, self._floating.manager.remaining, self._floating._format(self._floating.manager.remaining))

    def show_help(self):
        HelpDialog(self).exec_()

    def show_stats(self):
        StatsDialog(self).exec_()

    def toggle_floating_pomodoro(self):
        if self._floating and self._floating.isVisible():
            self._floating.hide()
        else:
            if not self._floating:
                self._floating = FloatingPomodoroWidget(parent=self)
                screen = QApplication.primaryScreen().availableGeometry()
                x = screen.right() - 220
                y = screen.bottom() - 140
                self._floating.move(x, y)
            self._floating.show()
            self._floating.raise_()

    def _add_task_list_item(self, task_tuple):
        (task_id, title, category, completed, duedate, subtasks, started_at, completed_at,
         priority, tags, recurring, pomos, last_pomo) = task_tuple

        status = "✅ Done" if completed else "⏳ Pending"
        priority_icon = {"High": "🔴", "Medium": "⚪", "Low": "🟢"}.get(priority, "⚪")

        task_lines = []

        task_lines.append(f"{priority_icon} {title}")

        task_lines.append(f"Status: {status} | Category: {category}")

        task_lines.append(f"Priority: {priority} | Pomodoros: 🍅 {pomos or 0}")

        if duedate:
            try:
                dt = datetime.strptime(duedate.split('.')[0], '%Y-%m-%dT%H:%M:%S')
                task_lines.append(f"Due: 📅 {dt.strftime('%I:%M %p • %d %b %Y')}")
            except Exception:
                task_lines.append(f"Due: 📅 {duedate}")

        if tags:
            task_lines.append(f"Tags: 🏷️ {tags}")

        if subtasks:
            task_lines.append(f"Subtasks: 📋 {subtasks}")

        if started_at:
            try:
                started_time = datetime.strptime(started_at.split('.')[0], '%Y-%m-%dT%H:%M:%S').strftime('%I:%M %p • %d %b %Y')
                task_lines.append(f"Started: 🚀 {started_time}")
            except Exception:
                pass
        if completed_at:
            try:
                completed_time = datetime.strptime(completed_at.split('.')[0], '%Y-%m-%dT%H:%M:%S').strftime('%I:%M %p • %d %b %Y')
                task_lines.append(f"Completed: ✅ {completed_time}")
            except Exception:
                pass

        if recurring and recurring != 'None':
            task_lines.append(f"Recurring: 🔄 {recurring}")

        item_text = "\n".join(task_lines)

        list_item = QListWidgetItem()
        list_item.setText(item_text)
        # Store the task ID for reliable Complete/Delete operations
        try:
            list_item.setData(Qt.UserRole, int(task_id))
        except Exception:
            pass
        self.task_listbox.addItem(list_item)

        if duedate:
            try:
                due_dt = datetime.strptime(duedate.split('.')[0], "%Y-%m-%dT%H:%M:%S")
                if due_dt < datetime.now() and not completed:
                    list_item.setForeground(Qt.red)
                    urgent_text = item_text.replace("📅", "🚨 URGENT")
                    list_item.setText(urgent_text)
            except Exception:
                pass

        if priority == 'High':
            list_item.setBackground(Qt.darkRed)
        elif priority == 'Low':
            list_item.setBackground(Qt.darkGray)

    def update_tasks(self):
        self.task_listbox.clear()
        for t in get_tasks():
            self._add_task_list_item(t)

    def get_selected_task_row(self):
        idx = self.task_listbox.currentRow()
        if idx < 0:
            return None
        item = self.task_listbox.item(idx)
        if not item:
            return None
        task_id = item.data(Qt.UserRole)
        if task_id is None:
            return None
        for t in get_tasks():
            if t[0] == task_id:
                return t
        return None

    def _handle_recurring(self, task_row):
        (task_id, title, category, completed, duedate, subtasks, started_at, completed_at,
         priority, tags, recurring, pomos, last_pomo) = task_row
        if not recurring or recurring == 'None':
            return
        next_due = None
        try:
            if duedate:
                base = datetime.strptime(duedate.split('.')[0], '%Y-%m-%dT%H:%M:%S')
            else:
                base = datetime.now()
            if recurring == 'Daily':
                next_due = (base + timedelta(days=1)).isoformat()
            elif recurring == 'Weekly':
                next_due = (base + timedelta(weeks=1)).isoformat()
        except Exception:
            next_due = None

        add_task(task=title, category=category, duedate=next_due, subtasks=subtasks,
                 priority=priority, tags=tags, recurring=recurring)

    def closeEvent(self, event):
        try:
            if self._floating and self._floating.manager:
                self._floating.manager.save_current_session()
            backup_db()
        except Exception:
            pass
        event.accept()

if __name__ == "__main__":
    init_db()
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    apply_global_theme(app)
    window = TaskTracker()
    window.show()
    sys.exit(app.exec_())