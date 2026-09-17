from __future__ import annotations


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
    QLabel#page-title {{ font-size: 26px; font-weight: 700; }}
    QLabel#page-intro {{ color: {COLORS['muted_text']}; font-size: 15px; }}
    QFrame#status-card {{
        background: white;
        border: 1px solid {COLORS['border']};
        border-radius: 12px;
    }}
    QFrame[unitStatus="active"] {{
        background: {COLORS['surface']};
        border: 1px solid {COLORS['border']};
        border-radius: 12px;
    }}
    QFrame[unitStatus="coming"] {{
        background: #EFF3F8;
        border: 1px dashed #AAB8CD;
        border-radius: 12px;
    }}
    QLabel[unitTitle="true"] {{ font-size: 19px; font-weight: 700; }}
    QLabel[unitBadge="active"] {{
        color: {COLORS['success']};
        font-weight: 700;
    }}
    QLabel[unitBadge="coming"] {{
        color: {COLORS['muted_text']};
        font-weight: 700;
    }}
    QLabel[unitRunState="true"] {{ color: {COLORS['foreground']}; }}
    QLabel[cardTitle="true"] {{ color: {COLORS['muted_text']}; font-weight: 600; }}
    QLabel[cardState="true"] {{ font-size: 20px; font-weight: 700; }}
    QLabel[cardDetail="true"] {{ color: {COLORS['muted_text']}; }}
    QLineEdit, QPlainTextEdit, QSpinBox {{
        background: white;
        border: 1px solid #8293AB;
        border-radius: 8px;
        padding: 10px 12px;
        selection-background-color: {COLORS['primary']};
        selection-color: white;
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{ border: 3px solid {COLORS['focus']}; }}
    QGroupBox {{
        background: white;
        border: 1px solid {COLORS['border']};
        border-radius: 12px;
        margin-top: 14px;
        padding: 18px;
        font-weight: 700;
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 16px; padding: 0 6px; }}
    QStatusBar {{ background: white; border-top: 1px solid {COLORS['border']}; }}
    """
