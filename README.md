# Routine Pro — Task Tracker & Pomodoro 

A modern, premium-looking desktop app to manage tasks and focus sessions with a floating Pomodoro timer. Built with Python + PyQt5, backed by SQLite, styled with a polished macOS-inspired dark theme.

## Highlights
- Attractive  UI: 
- Floating Pomodoro timer (always-on-top) that can attach to a selected task
- SQLite persistence with automatic local backup
- Import/Export tasks as CSV
- Study time tracking saved to JSON
- Statistics dialog: totals, completed today, pomodoros, latest session
- Recurring tasks (None, Daily, Weekly)
- System Tray controls (start/pause/reset Pomodoro, show window)
- Notification sound on session completion (MP3/WAV; fallback to beep)

---

## Table of Contents
- Getting Started
- Features
- How It Works
- Data Model
- Import/Export Format
- Theming and UI
- Build (Windows EXE)
- Configuration & Files
- Troubleshooting
- FAQ


---

## Getting Started

### Requirements
- Python 3.8+
- pip

### Install
```bash
pip install PyQt5
```

### Run
```bash
python main.py
```
Use "Launch Floating Pomodoro Timer" to open the floating widget.

---

## Features

### Tasks and Categories
- Add tasks with title, category, priority, tags, due date, and optional subtasks
- Complete/delete tasks; overdue tasks are highlighted automatically
- Search by title/tags

### Recurring Tasks
- Options: None, Daily, Weekly
- Completing a recurring task auto-creates the next occurrence

### Floating Pomodoro Timer
- Always-on-top, frameless glassy card with macOS look
- Left-click to start/pause; drag to move; right-click for phase/attach options
- Attach to selected task to increment its Pomodoro count
- Quick phase switching (Focus, Short Break, Long Break)
- Close (✕) button and refined header controls

### Study Time Tracker
- Focus time contributes to cumulative study time
- Saved in `study_time.json` and shown in UI

### Statistics
- Total tasks, completed tasks, done today
- Total pomodoros across tasks and the latest task receiving a pomodoro
- Total study time in a human-friendly format

### Import/Export
- Export all tasks to CSV
- Import from CSV to restore/bulk add tasks (format below)

### System Tray
- Show window, toggle Pomodoro, start/pause, reset, quit

### Notification Sounds
- Prefers `sounds/notify.mp3`, then `sounds/notify.wav`
- Falls back to system beep if audio fails

### Automatic Local Backup
- On app close, `tasks.db` is copied to `tasks_backup.db`

---

## How It Works

- UI: `TaskTracker` (main window) + `FloatingPomodoroWidget` (overlay)
- Persistence: SQLite (`tasks.db`); study time in JSON (`study_time.json`)
- Logic: `PomodoroManager` handles phases, countdown, and session saving
- Tray: `QSystemTrayIcon` binds timer controls and visibility

---

## Data Model

SQLite table `tasks` (created/migrated automatically):
```sql
id INTEGER PRIMARY KEY,
task TEXT,
category TEXT,
completed INTEGER,
duedate TEXT,
subtasks TEXT,
started_at TEXT,
completed_at TEXT,
priority TEXT DEFAULT 'Medium',
tags TEXT DEFAULT '',
recurring TEXT DEFAULT 'None',
pomodoros INTEGER DEFAULT 0,
last_pomodoro_at TEXT
```

---

## Import/Export Format

Header used for CSV:
```text
ID,Task,Category,Completed,DueDate,Subtasks,Started At,Completed At,Priority,Tags,Recurring,Pomodoros,Last Pomodoro At
```
- Import is resilient: missing values default; invalid lines are skipped
- Date/time fields use ISO strings (e.g., 2025-01-01T13:00:00)

---

## Theming and UI

- Buttons: accent gradients, pill radius, hover/pressed states, focus ring
- Lists: card-like items with subtle accent bar and refined selection
- Floating timer: translucent panel, rounded corners, compact header

Tip: Adjust durations and long-break cadence in Settings.

---

## Build (Windows EXE)

Install PyInstaller:
```bash
pip install pyinstaller
```

Build:
```bash
pyinstaller --noconfirm --windowed --onefile ^
  --icon study.ico ^
  --add-data "task.db;." ^
  --add-data "sounds;sounds" ^
  main.py
```
- Output: `dist/main.exe`
- Include sounds/icons with `--add-data` as needed
- A sample `main.spec` may already be present for customization

---

## Configuration & Files
- `tasks.db`: primary SQLite database
- `tasks_backup.db`: backup written on close
- `study_time.json`: cumulative study seconds
- `sounds/notify.mp3` or `sounds/notify.wav`: notification sound
- `study.ico`: application icon

---

## Troubleshooting
- No sound: ensure `sounds/notify.mp3` or `.wav` exists; otherwise a beep plays
- Fonts: app prefers SF Pro; falls back to Segoe UI/OS defaults
- Import errors: verify CSV header and ISO date strings; unsupported rows are skipped

---

## FAQ
- Q: Is internet required?
  - A: No. It’s an offline desktop app. `index.html` is optional showcase.
- Q: Where is my data?
  - A: In the app directory: `tasks.db`, `study_time.json`, `tasks_backup.db`.
- Q: Can I customize the Pomodoro durations?
  - A: Yes. Use Settings to adjust Focus, Short/Long Breaks, and cadence.

---


## Acknowledgements
- PyQt5 for the desktop toolkit
- Created with the support of AI agents, insights from YouTube tutorials, and a lot of personal effort.

