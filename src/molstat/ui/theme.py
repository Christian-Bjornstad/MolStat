from __future__ import annotations


COLORS = {
    "primary": "#F2C811",
    "background": "#FFF9E6",
    "muted": "#FFF3C4",
    "surface": "#FFFFFF",
    "foreground": "#2B2618",
    "muted_text": "#5C553D",
    "border": "#E6D17A",
    "focus": "#8A6A00",
    "success": "#1B7D3A",
    "warning": "#9A6A00",
    "danger": "#A4262C",
    "sidebar": "#3A321B",
}


def build_stylesheet() -> str:
    return f"""
    * {{
        font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
        font-size: 14px;
        color: {COLORS['foreground']};
    }}
    QMainWindow, QWidget#app-shell {{ background: {COLORS['background']}; }}
    QFrame#sidebar {{ background: {COLORS['sidebar']}; border: none; }}
    QLabel#brand {{ color: white; font-size: 27px; font-weight: 700; }}
    QLabel#brand-subtitle {{ color: #F5E8B0; font-size: 12px; }}
    QPushButton {{
        min-height: 44px;
        border-radius: 8px;
        padding: 0 16px;
        font-weight: 600;
        background: {COLORS['muted']};
        border: 1px solid {COLORS['border']};
    }}
    QPushButton:hover {{ background: #FBE69A; border-color: {COLORS['focus']}; }}
    QPushButton:pressed {{ background: #F6D85D; }}
    QPushButton:focus {{ border: 3px solid {COLORS['focus']}; }}
    QPushButton:disabled {{ color: #6B6657; background: #EEE9D8; border-color: #D8CFAC; }}
    QPushButton[primary="true"] {{
        color: {COLORS['foreground']};
        background: {COLORS['primary']};
        border-color: {COLORS['focus']};
    }}
    QPushButton[primary="true"]:hover {{ background: #DDB600; border-color: #6E5500; }}
    QPushButton[nav="true"] {{
        color: #FFF9E6;
        background: transparent;
        border: 1px solid transparent;
        text-align: left;
    }}
    QPushButton[nav="true"]:hover {{ background: #514622; border-color: #8A6A00; }}
    QPushButton[nav="true"][active="true"] {{
        color: white;
        background: #665718;
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
        background: #F7F3E7;
        border: 1px dashed #B8AA78;
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
    QLineEdit, QPlainTextEdit {{
        background: white;
        border: 1px solid #9B8C52;
        border-radius: 8px;
        padding: 10px 12px;
        selection-background-color: {COLORS['primary']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus {{ border: 3px solid {COLORS['focus']}; }}
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
