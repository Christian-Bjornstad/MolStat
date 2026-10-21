from __future__ import annotations

from pathlib import Path


COLORS = {
    "primary": "#2457C5",
    "background": "#F4F7FB",
    "muted": "#EDF2FA",
    "surface": "#FFFFFF",
    "foreground": "#172033",
    "muted_text": "#526176",
    "border": "#D6DFEB",
    "focus": "#2457C5",
    "success": "#18734A",
    "warning": "#8A5800",
    "danger": "#B42332",
    "sidebar": "#18263D",
}


def build_stylesheet() -> str:
    chevron = (Path(__file__).resolve().parents[1] / "assets" / "chevron-down.svg").as_posix()
    return f"""
    * {{
        font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
        font-size: 14px;
        color: {COLORS['foreground']};
    }}
    QWidget#qt_scrollarea_viewport, QScrollArea {{ background: {COLORS['background']}; border: none; }}
    QMainWindow, QWidget#app-shell, QWidget#page-content {{ background: {COLORS['background']}; }}
    QFrame#sidebar {{ background: {COLORS['sidebar']}; border: none; }}
    QLabel#brand {{ color: white; font-size: 27px; font-weight: 700; }}
    QLabel#brand-subtitle {{ color: #C5D4EB; font-size: 12px; }}
    QPushButton {{
        min-height: 44px;
        border-radius: 8px;
        padding: 0 16px;
        font-weight: 600;
        background: {COLORS['muted']};
        border: 1px solid {COLORS['border']};
    }}
    QPushButton:hover {{ background: #DFE8F7; border-color: {COLORS['focus']}; }}
    QPushButton:pressed {{ background: #CFDDF4; }}
    QPushButton:focus {{ border: 3px solid {COLORS['focus']}; }}
    QPushButton:disabled {{ color: #64748B; background: #E8EDF4; border-color: #D6DFEB; }}
    QPushButton[primary="true"] {{
        color: white;
        background: {COLORS['primary']};
        border-color: {COLORS['focus']};
    }}
    QPushButton[primary="true"]:hover {{ background: #1D46A0; border-color: #173980; }}
    QPushButton[nav="true"] {{
        color: #F4F7FB;
        background: transparent;
        border: 1px solid transparent;
        text-align: left;
    }}
    QPushButton[nav="true"]:hover {{ background: #263B5A; border-color: #2457C5; }}
    QPushButton[nav="true"][active="true"] {{
        color: white;
        background: #284A7A;
        border-color: {COLORS['primary']};
    }}
    QLabel#page-title {{ font-size: 28px; font-weight: 700; }}
    QLabel#page-intro {{ color: {COLORS['muted_text']}; font-size: 15px; }}
    QLabel[sectionTitle="true"] {{ font-size: 17px; font-weight: 700; }}
    QLabel[badge="true"] {{
        font-size: 12px;
        font-weight: 600;
        border-radius: 6px;
        padding: 4px 8px;
        background: {COLORS['muted']};
        color: {COLORS['muted_text']};
    }}
    QLabel[badge="true"][tone="success"] {{ background: #E9F4EE; color: {COLORS['success']}; }}
    QLabel[tone="success"] {{ color: {COLORS['success']}; }}
    QLabel[tone="danger"] {{ color: {COLORS['danger']}; }}
    QLabel[tone="warning"] {{ color: {COLORS['warning']}; }}
    QLabel[tone="working"] {{ color: {COLORS['primary']}; }}
    QLabel[capabilityStatus="true"] {{ font-size: 12px; }}
    QFrame#run-progress-panel {{
        background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 8px;
    }}
    QProgressBar {{ border: none; background: {COLORS['muted']}; border-radius: 4px; }}
    QProgressBar::chunk {{ background: {COLORS['primary']}; border-radius: 4px; }}
    QFrame#status-card {{
        background: white;
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
    }}
    QFrame[unitStatus="active"] {{
        background: {COLORS['surface']};
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
    }}
    QLabel[unitTitle="true"] {{ font-size: 18px; font-weight: 700; }}
    QLabel[unitBadge="active"] {{
        color: {COLORS['success']};
        font-weight: 700;
    }}
    QLabel[unitRunState="true"] {{ color: {COLORS['foreground']}; }}
    QLabel[cardTitle="true"] {{ color: {COLORS['muted_text']}; font-weight: 600; }}
    QLabel[cardState="true"] {{ font-size: 17px; font-weight: 700; }}
    QLabel[cardDetail="true"] {{ color: {COLORS['muted_text']}; }}
    QLineEdit, QPlainTextEdit, QSpinBox, QComboBox, QDateEdit {{
        background: white;
        border: 1px solid #8293AB;
        border-radius: 8px;
        padding: 10px 12px;
        selection-background-color: {COLORS['primary']};
        selection-color: white;
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus, QDateEdit:focus {{ border: 3px solid {COLORS['focus']}; }}
    QLineEdit[tone="danger"] {{ border-color: {COLORS['danger']}; }}
    QComboBox, QDateEdit, QSpinBox {{ padding-right: 24px; }}
    QComboBox::drop-down, QDateEdit::drop-down {{ width: 24px; border: none; }}
    QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url("{chevron}"); width: 12px; height: 12px; }}
    QComboBox QAbstractItemView {{ background: white; selection-background-color: {COLORS['primary']}; selection-color: white; }}
    QPushButton[quiet="true"] {{ background: transparent; border-color: {COLORS['border']}; color: {COLORS['muted_text']}; }}
    QPushButton[quiet="true"]:hover {{ background: {COLORS['muted']}; border-color: {COLORS['focus']}; color: {COLORS['foreground']}; }}
    QTabWidget::pane {{ background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 8px; }}
    QTabBar::tab {{
        min-height: 44px;
        padding: 0 16px;
        color: {COLORS['muted_text']};
        background: transparent;
        border: 1px solid transparent;
        border-bottom: 3px solid transparent;
        font-weight: 600;
    }}
    QTabBar::tab:selected {{ color: {COLORS['primary']}; border-bottom-color: {COLORS['primary']}; background: {COLORS['surface']}; }}
    QTabBar::tab:hover {{ background: {COLORS['muted']}; }}
    QTabBar::tab:focus {{ border: 3px solid {COLORS['focus']}; }}
    QWidget#settings-tab-content, QWidget#unit-settings-stack {{ background: {COLORS['surface']}; }}
    QListWidget {{ background: {COLORS['background']}; border: 1px solid {COLORS['border']}; border-radius: 8px; padding: 4px; }}
    QListWidget::item {{ padding: 8px; border-radius: 6px; }}
    QListWidget::item:selected {{ color: white; background: {COLORS['primary']}; }}
    QListWidget::item:hover:!selected {{ background: {COLORS['muted']}; }}
    QListWidget:focus {{ border: 3px solid {COLORS['focus']}; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox:focus {{ outline: 2px solid {COLORS['focus']}; }}
    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: #AAB8CD; border-radius: 4px; min-height: 32px; margin: 2px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    QGroupBox {{
        background: white;
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        margin-top: 14px;
        padding: 18px;
        font-weight: 700;
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 16px; padding: 0 6px; }}
    QLabel[tone="success"] {{ color: {COLORS['success']}; }}
    QLabel[tone="danger"] {{ color: {COLORS['danger']}; }}
    QLabel[tone="warning"] {{ color: {COLORS['warning']}; }}
    QLabel[tone="working"] {{ color: {COLORS['primary']}; }}
    QStatusBar {{ background: white; border-top: 1px solid {COLORS['border']}; }}
    QWidget#import-footer {{ background: {COLORS['surface']}; border-top: 1px solid {COLORS['border']}; }}
    """
