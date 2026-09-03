from __future__ import annotations


COLORS = {
    "primary": "#0284C7",
    "secondary": "#0891B2",
    "accent": "#16A34A",
    "background": "#F0F9FF",
    "surface": "#FFFFFF",
    "foreground": "#0C4A6E",
    "muted": "#E8F2F8",
    "border": "#BAE6FD",
    "danger": "#DC2626",
    "sidebar": "#082F49",
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
    QLabel#brand-subtitle {{ color: #BAE6FD; font-size: 12px; }}
    QPushButton {{
        min-height: 44px;
        border-radius: 8px;
        padding: 0 16px;
        font-weight: 600;
        background: {COLORS['muted']};
        border: 1px solid {COLORS['border']};
    }}
    QPushButton:hover {{ background: #D9F0FA; border-color: {COLORS['primary']}; }}
    QPushButton:pressed {{ background: #C7E7F5; }}
    QPushButton:focus {{ border: 3px solid {COLORS['primary']}; }}
    QPushButton:disabled {{ color: #64748B; background: #E2E8F0; border-color: #CBD5E1; }}
    QPushButton[primary="true"] {{
        color: white;
        background: {COLORS['accent']};
        border-color: {COLORS['accent']};
    }}
    QPushButton[primary="true"]:hover {{ background: #15803D; border-color: #15803D; }}
    QPushButton[nav="true"] {{
        color: #E0F2FE;
        background: transparent;
        border: 1px solid transparent;
        text-align: left;
    }}
    QPushButton[nav="true"]:hover {{ background: #0C4A6E; border-color: #0E7490; }}
    QPushButton[nav="true"][active="true"] {{
        color: white;
        background: #075985;
        border-color: #38BDF8;
    }}
    QLabel#page-title {{ font-size: 26px; font-weight: 700; }}
    QLabel#page-intro {{ color: #475569; font-size: 15px; }}
    QFrame#status-card {{
        background: white;
        border: 1px solid {COLORS['border']};
        border-radius: 12px;
    }}
    QLabel[cardTitle="true"] {{ color: #475569; font-weight: 600; }}
    QLabel[cardState="true"] {{ font-size: 20px; font-weight: 700; }}
    QLabel[cardDetail="true"] {{ color: #475569; }}
    QLineEdit, QPlainTextEdit {{
        background: white;
        border: 1px solid #94A3B8;
        border-radius: 8px;
        padding: 10px 12px;
        selection-background-color: {COLORS['primary']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus {{ border: 3px solid {COLORS['primary']}; }}
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
