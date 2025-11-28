# -*- coding: utf-8 -*-

class ModernTheme:
    @staticmethod
    def get_font_style():
        """Return a standard font string for the application."""
        return "font-family: 'Segoe UI', 'Microsoft YaHei', 'San Francisco', 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 10pt;"

    @staticmethod
    def dark_palette():
        return {
            "background": "#2b2d30",
            "surface": "#3c3f41",
            "header_footer": "#222426", # Slightly darker than background
            "primary": "#365880",
            "primary_hover": "#4b6e99",
            "accent": "#528bff",
            "text": "#bbbbbb",
            "text_bright": "#ffffff",
            "border": "#555555",
            "input_bg": "#ffffff",
            "input_text": "#000000",
            "success": "#6a8759",
            "error": "#bc3f3c",
            "warning": "#d19a66",
            "splitter": "#1e1e1e",
        }

    @staticmethod
    def light_palette():
        return {
            "background": "#f0f2f5",
            "surface": "#ffffff",
            "header_footer": "#e1e4e8", # Slightly darker than background
            "primary": "#0078d4",
            "primary_hover": "#1084d9",
            "accent": "#0064b0",
            "text": "#333333",
            "text_bright": "#000000",
            "border": "#d1d1d1",
            "input_bg": "#ffffff",
            "input_text": "#000000",
            "success": "#107c10",
            "error": "#a80000",
            "warning": "#d9a100",
            "splitter": "#e0e0e0",
        }

    @classmethod
    def get_qss(cls, theme="dark"):
        p = cls.dark_palette() if theme == "dark" else cls.light_palette()
        
        qss = f"""
        /* Global */
        QWidget {{
            background-color: {p['background']};
            color: {p['text']};
            {cls.get_font_style()}
        }}

        /* QMainWindow & Central Widget */
        QMainWindow {{
            background-color: {p['background']};
        }}

        /* GroupBox */
        QGroupBox {{
            border: 1px solid {p['border']};
            border-radius: 6px;
            margin-top: 12px;
            background-color: transparent;
            padding-top: 10px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0 5px;
            color: {p['accent']};
            font-weight: bold;
        }}

        /* Buttons */
        QPushButton {{
            background-color: {p['surface']};
            border: 1px solid {p['border']};
            border-radius: 4px;
            padding: 6px 16px;
            min-height: 20px;
        }}
        QPushButton:hover {{
            background-color: {p['primary']};
            color: {p['text_bright']};
            border-color: {p['primary']};
        }}
        QPushButton:pressed {{
            background-color: {p['primary_hover']};
        }}
        QPushButton:disabled {{
            background-color: {p['background']};
            color: {p['border']};
            border-color: {p['border']};
        }}
        
        /* RadioButton & CheckBox */
        QRadioButton, QCheckBox {{
            spacing: 5px;
            background-color: transparent;
        }}
        
        /* CheckBox Indicator - Fixed Size 10x10 */
        QCheckBox::indicator {{
            width: 10px;
            height: 10px;
            border: 1px solid {p['border']};
            border-radius: 2px;
            background-color: {p['input_bg']};
        }}
        
        QCheckBox::indicator:checked {{
            background-color: {p['accent']};
            border: 1px solid {p['accent']};
            image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2 5 L4 7 L8 2' stroke='white' stroke-width='2' fill='none'/></svg>");
        }}
        
        QCheckBox::indicator:hover {{
            border-color: {p['accent']};
        }}

        /* RadioButton Indicator - Fixed Size, No Growth */
        QRadioButton::indicator {{
            width: 8px; 
            height: 8px;
            border: 1px solid {p['border']};
            border-radius: 4px;
            background-color: {p['input_bg']};
        }}

        /* RadioButton Checked - Inner Dot Fill Only */
        QRadioButton::indicator:checked {{
            background-color: {p['accent']}; /* Blue fill */
            border: 1px solid {p['accent']}; /* Blue Outer Ring */
            image: none;
        }}
        
        QRadioButton::indicator:hover {{
            border-color: {p['accent']};
        }}

        /* Inputs */
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
            background-color: {p['input_bg']};
            color: {p['input_text']};
            border: 1px solid {p['border']};
            border-radius: 4px;
            padding: 4px 8px;
            selection-background-color: {p['accent']};
            selection-color: #ffffff;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1px solid {p['accent']};
        }}

        /* ComboBox */
        QComboBox {{
            background-color: {p['input_bg']};
            color: {p['input_text']};
            border: 1px solid {p['border']};
            border-radius: 4px;
            padding: 4px 8px;
            min-height: 20px;
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 20px;
            border-left-width: 0px;
            border-top-right-radius: 4px;
            border-bottom-right-radius: 4px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {p['surface']};
            color: {p['text']};
            border: 1px solid {p['border']};
            selection-background-color: {p['primary']};
            selection-color: {p['text_bright']};
        }}

        /* TabWidget */
        QTabWidget::pane {{
            border: 1px solid {p['border']};
            background-color: {p['surface']};
            border-radius: 4px;
        }}
        QTabBar::tab {{
            background: {p['background']};
            border: 1px solid {p['border']};
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }}
        QTabBar::tab:selected {{
            background: {p['primary']};
            border-bottom-color: {p['primary']};
            color: #ffffff;
            font-weight: bold;
        }}
        QTabBar::tab:hover {{
            background: {p['primary_hover']};
            color: #ffffff;
        }}

        /* Scrollbars */
        QScrollBar:vertical {{
            border: none;
            background: {p['background']};
            width: 10px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {p['border']};
            min-height: 20px;
            border-radius: 5px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar::horizontal {{
            border: none;
            background: {p['background']};
            height: 10px;
            margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: {p['border']};
            min-width: 20px;
            border-radius: 5px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}

        /* Splitter */
        QSplitter::handle {{
            background-color: {p['splitter']};
        }}
        
        /* List & Table */
        QListWidget, QTableWidget {{
            background-color: {p['input_bg']};
            color: {p['input_text']};
            border: 1px solid {p['border']};
            gridline-color: {p['border']};
        }}
        QHeaderView::section {{
            background-color: {p['surface']};
            padding: 4px;
            border: 1px solid {p['border']};
        }}
        QTableCornerButton::section {{
            background-color: {p['surface']};
            border: 1px solid {p['border']};
        }}

        /* Status Bar & Menu Bar - Darker Header/Footer */
        QStatusBar {{
            background: {p['header_footer']};
            border-top: 1px solid {p['border']};
            color: {p['text']};
        }}
        QMenuBar {{
            background-color: {p['header_footer']};
            border-bottom: 1px solid {p['border']};
        }}
        QMenuBar::item {{
            spacing: 3px; 
            padding: 6px 10px;
            background: transparent;
            border-radius: 4px;
        }}
        QMenuBar::item:selected {{ 
            background-color: {p['primary']};
            color: {p['text_bright']};
        }}
        QMenu {{
            background-color: {p['surface']};
            border: 1px solid {p['border']};
        }}
        QMenu::item {{
            padding: 6px 24px;
        }}
        QMenu::item:selected {{
            background-color: {p['primary']};
            color: {p['text_bright']};
        }}
        
        /* Dialogs */
        QDialog {{
            background-color: {p['background']};
        }}
        
        /* Status Labels via Property */
        QLabel[status="success"] {{
            color: {p['success']};
            font-weight: bold;
        }}
        QLabel[status="error"] {{
            color: {p['error']};
            font-weight: bold;
        }}
        QLabel[status="warning"] {{
            color: {p['warning']};
            font-weight: bold;
        }}
        """
        return qss
