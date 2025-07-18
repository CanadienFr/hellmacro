import sys
import json
import threading
import time
import logging
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QGridLayout, QTextEdit,
    QStyledItemDelegate, QMessageBox, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QStandardItemModel, QStandardItem, QColor, QPalette
from pynput.keyboard import Controller as KeyboardController, Key, Listener as KeyboardListener
from pynput import mouse as pynput_mouse
from pynput.mouse import Controller as MouseController, Button

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

# Define support stratagems
SUPPORT_STRATAGEMS = {
    "Reinforce": ["up", "down", "right", "left", "up"],
    "Resupply": ["down", "down", "up", "right"],
    "SEAF Artillery": ["right", "up", "up", "down"],
    "Hellbomb": ["down", "up", "left", "down", "up", "right", "down", "up"],
    "Eagle Rearm": ["up", "up", "left", "up", "right"]
}

# Initialize globals as empty
STRATAGEM_DATA = {}
PROFILES = {}
LAST_PROFILE = "Default"

keyboard = KeyboardController()
mouse = MouseController()
mouse_listener = None
keyboard_listener = None

class SignalHandler(QObject):
    show_warning = Signal(str)
    log_message = Signal(str)
    blink = Signal()

class ColorDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        color = index.data(Qt.UserRole)
        if color:
            option.palette.setColor(QPalette.Text, QColor(color))

class MacroApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Helldivers 2 Macro")
        self.setMinimumSize(800, 600)

        self.load_data_files()

        self.active_keybind = None
        self.running_macro = False
        self.railgun_safety = False
        self.left_click_active = False
        self.left_click_time = 0
        self.railgun_timeout = 2.95
        self.railgun_debounce = 0.2
        self.last_railgun_release = 0
        self.arc_thrower_rapidfire = False
        self.arc_thrower_delay = 1.05
        self.arc_thrower_thread = None
        self.macro_thread = None
        self.railgun_timer = None
        self.railgun_keybind = ""
        self.arc_thrower_keybind = ""
        self.last_toggle_time = {"railgun": 0, "arc_thrower": 0}
        self.toggle_debounce = 0.2
        self.railgun_use_keyboard_fallback = False
        self.macro_delay = 0.05

        self.signal_handler = SignalHandler()
        self.signal_handler.show_warning.connect(self.show_warning_message)
        self.signal_handler.log_message.connect(self.append_log)
        self.signal_handler.blink.connect(self.blink_indicator)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)

        self.setStyleSheet("""
            QMainWindow { background-color: #263238; color: #ECEFF1; }
            QTabWidget::pane { border: 1px solid #455A64; background: #37474F; }
            QTabBar::tab { 
                background: #455A64; 
                color: #ECEFF1; 
                padding: 8px 16px; 
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected { 
                background: #37474F; 
                border-bottom: 2px solid #4FC3F7;
                color: #E1F5FE;
            }
            QLabel { color: #ECEFF1; font-size: 14px; }
            QPushButton { 
                background-color: #546E7A; 
                color: #ECEFF1; 
                padding: 3px 8px; 
                border: none;
                border-radius: 4px;
                font-size: 11px;
                min-height: 24px;
                white-space: nowrap;
            }
            QPushButton:hover { background-color: #78909C; }
            QPushButton:pressed { background-color: #455A64; }
            QPushButton[clear="true"] { 
                background-color: #EF5350; 
                color: #FFFFFF; 
                padding: 3px 8px; 
                border-radius: 4px;
                min-height: 24px;
                white-space: nowrap;
            }
            QComboBox { 
                background-color: #546E7A; 
                color: #ECEFF1; 
                border: none;
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 11px;
                min-height: 24px;
                white-space: nowrap;
            }
            QComboBox::drop-down { 
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #37474F;
                color: #ECEFF1;
                selection-background-color: #4FC3F7;
            }
            QLineEdit { 
                background-color: #546E7A; 
                color: #ECEFF1; 
                border: none;
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 11px;
                min-height: 24px;
            }
            QTextEdit {
                background-color: #1E272C;
                color: #ECEFF1;
                border: 1px solid #455A64;
                padding: 5px;
                font-family: Consolas, "Courier New", monospace;
                font-size: 12px;
            }
            QCheckBox { 
                color: #ECEFF1; 
                font-size: 12px;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                background-color: #546E7A;
                border: 1px solid #455A64;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #4CAF50;
                border: 1px solid #455A64;
            }
        """)

        self.tab_widget = QTabWidget()
        self.main_layout.addWidget(self.tab_widget)

        self.stratagems_tab = QWidget()
        self.weapons_tab = QWidget()
        self.support_tab = QWidget()
        self.logs_tab = QWidget()
        self.tab_widget.addTab(self.stratagems_tab, "Stratagems")
        self.tab_widget.addTab(self.weapons_tab, "Weapons")
        self.tab_widget.addTab(self.support_tab, "Support")
        self.tab_widget.addTab(self.logs_tab, "Logs")

        self.keybind_vars = [""] * 5
        self.support_keybind_vars = [""] * len(SUPPORT_STRATAGEMS)
        self.keybind_buttons = []
        self.stratagem_combos = []
        self.stratagem_outputs = []
        self.delete_keybind_buttons = []
        self.support_keybind_buttons = []
        self.support_outputs = []
        self.support_delete_keybind_buttons = []
        self.support_test_buttons = []

        self.create_stratagems_tab()
        self.create_weapons_tab()
        self.create_support_tab()
        self.create_logs_tab()
        self.create_profile_section()

        toggle_hbox = QHBoxLayout()
        toggle_hbox.addStretch()
        self.toggle_button = QPushButton("▶ Start")
        self.toggle_button.setToolTip("Start or stop the macro system")
        self.toggle_button.setStyleSheet("background-color: #4CAF50; color: #FFFFFF; padding: 3px 8px; border-radius: 4px; min-height: 24px;")
        self.toggle_button.clicked.connect(self.toggle_macro)
        toggle_hbox.addWidget(self.toggle_button)
        self.macro_indicator = QLabel()
        self.macro_indicator.setFixedSize(20, 20)
        self.macro_indicator.setStyleSheet("background-color: red; border-radius: 10px;")
        toggle_hbox.addWidget(self.macro_indicator)
        toggle_hbox.addStretch()
        self.main_layout.addLayout(toggle_hbox)

        QMessageBox.warning(self, "Important Notice", "This tool is for personal use only. Please check Helldivers 2 Terms of Service regarding macros.")

        self.load_profile(LAST_PROFILE)
        self.start_listeners()

    def load_data_files(self):
        global STRATAGEM_DATA, PROFILES, LAST_PROFILE

        # Load stratagems.json
        try:
            with open("stratagems.json", "r") as f:
                STRATAGEM_DATA = json.load(f)
        except FileNotFoundError:
            QMessageBox.warning(self, "Warning", "stratagems.json not found, creating basic file.")
            basic_stratagems = {
                "Machine Gun": {
                    "sequence": ["down", "left", "down", "up", "right"],
                    "color": "#FF0000"
                },
                "Anti-Materiel Rifle": {
                    "sequence": ["down", "left", "right", "up", "down"],
                    "color": "#00FF00"
                },
                "Eagle Airstrike": {
                    "sequence": ["up", "right", "down", "right"],
                    "color": "#FF4500"
                },
                "Orbital Precision Strike": {
                    "sequence": ["right", "right", "up"],
                    "color": "#FFA500"
                },
            }
            with open("stratagems.json", "w") as f:
                json.dump(basic_stratagems, f, indent=4)
            STRATAGEM_DATA = basic_stratagems
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding stratagems.json: {e}")
            STRATAGEM_DATA = {}

        # Load profiles.json
        try:
            with open("profiles.json", "r") as f:
                PROFILES = json.load(f)
        except FileNotFoundError:
            PROFILES = {
                "Default": {
                    "keybinds": [""] * 5,
                    "stratagems": ["Select Stratagem"] * 5,
                    "support_keybinds": [""] * len(SUPPORT_STRATAGEMS),
                    "railgun_timeout": 2.95,
                    "arc_thrower_delay": 1.05,
                    "railgun_keybind": "",
                    "arc_thrower_keybind": "",
                    "railgun_use_keyboard_fallback": False,
                    "macro_delay": 0.05
                }
            }
            try:
                with open("profiles.json", "w") as f_out:
                    json.dump(PROFILES, f_out, indent=4)
            except Exception as e:
                logging.error(f"Error creating profiles.json: {e}")
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding profiles.json: {e}")
            PROFILES = {}

        # Load last_profile.json
        try:
            with open("last_profile.json", "r") as f:
                LAST_PROFILE = json.load(f).get("last_profile", "Default")
        except FileNotFoundError:
            LAST_PROFILE = "Default"

    def create_stratagems_tab(self):
        layout = QGridLayout(self.stratagems_tab)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        label = QLabel("Assign Stratagems")
        label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(label, 0, 0, 1, 3)

        reload_button = QPushButton("Reload Stratagems")
        reload_button.setToolTip("Reload stratagems from stratagems.json without restarting")
        reload_button.clicked.connect(self.reload_stratagems)
        layout.addWidget(reload_button, 0, 2, 1, 1, alignment=Qt.AlignRight)

        strat_labels = ["Stratagem 1", "Stratagem 2", "Stratagem 3", "Stratagem 4", "EXTRA 5"]
        all_stratagems = list(STRATAGEM_DATA.keys())

        for i, strat_label in enumerate(strat_labels):
            frame = QWidget()
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(0, 4, 0, 4)
            frame_layout.setSpacing(4)

            label = QLabel(strat_label)
            label.setStyleSheet("font-size: 16px; font-weight: bold;")
            frame_layout.addWidget(label)

            button_combo_frame = QWidget()
            button_combo_layout = QHBoxLayout(button_combo_frame)
            button_combo_layout.setContentsMargins(0, 0, 0, 0)
            button_combo_layout.setSpacing(8)

            keybind_button = QPushButton("Set Keybind")
            keybind_button.setFixedWidth(120)
            keybind_button.setToolTip("Assign a key or mouse button for this stratagem")
            keybind_button.clicked.connect(lambda checked, idx=i: self.set_keybind(idx))
            button_combo_layout.addWidget(keybind_button)
            self.keybind_buttons.append(keybind_button)

            del_button = QPushButton("Clear")
            del_button.setFixedWidth(60)
            del_button.setProperty("clear", True)
            del_button.clicked.connect(lambda checked, idx=i: self.delete_keybind(idx))
            button_combo_layout.addWidget(del_button)
            self.delete_keybind_buttons.append(del_button)

            combo = QComboBox()
            combo.setFixedWidth(250)
            model = QStandardItemModel()
            item = QStandardItem("Select Stratagem")
            item.setForeground(QColor("#ECEFF1"))
            item.setData("#ECEFF1", Qt.UserRole)
            model.appendRow(item)
            for strat in all_stratagems:
                item = QStandardItem(strat)
                color = STRATAGEM_DATA[strat].get("color", "#ECEFF1") if isinstance(STRATAGEM_DATA[strat], dict) else "#ECEFF1"
                item.setForeground(QColor(color))
                item.setData(color, Qt.UserRole)
                model.appendRow(item)
            combo.setModel(model)
            combo.setItemDelegate(ColorDelegate())
            combo.view().setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            combo.currentTextChanged.connect(lambda value, idx=i: self.update_stratagem_output(idx))
            button_combo_layout.addWidget(combo)
            self.stratagem_combos.append(combo)

            test_button = QPushButton("Test")
            test_button.setFixedWidth(60)
            test_button.setToolTip("Test this stratagem sequence")
            test_button.clicked.connect(lambda checked, idx=i: self.test_stratagem(idx))
            button_combo_layout.addWidget(test_button)

            button_combo_layout.addStretch()
            frame_layout.addWidget(button_combo_frame)

            output_frame = QWidget()
            output_layout = QHBoxLayout(output_frame)
            output_layout.setContentsMargins(0, 0, 0, 0)
            output_layout.setSpacing(8)

            output_label = QLabel("")
            output_layout.addWidget(output_label)
            self.stratagem_outputs.append(output_label)
            output_layout.addStretch()

            frame_layout.addWidget(output_frame)
            layout.addWidget(frame, i + 1, 0, 1, 3)

        layout.setRowStretch(i + 2, 1)

    def reload_stratagems(self):
        global STRATAGEM_DATA
        try:
            with open("stratagems.json", "r") as f:
                STRATAGEM_DATA = json.load(f)
            self.signal_handler.log_message.emit("Stratagems reloaded from file")
        except Exception as e:
            self.signal_handler.show_warning.emit(f"Failed to reload stratagems: {e}")
            self.signal_handler.log_message.emit(f"Failed to reload stratagems: {e}")
            return

        all_stratagems = list(STRATAGEM_DATA.keys())
        for combo in self.stratagem_combos:
            current_text = combo.currentText()
            model = QStandardItemModel()
            item = QStandardItem("Select Stratagem")
            item.setForeground(QColor("#ECEFF1"))
            item.setData("#ECEFF1", Qt.UserRole)
            model.appendRow(item)
            for strat in all_stratagems:
                item = QStandardItem(strat)
                color = STRATAGEM_DATA[strat].get("color", "#ECEFF1") if isinstance(STRATAGEM_DATA[strat], dict) else "#ECEFF1"
                item.setForeground(QColor(color))
                item.setData(color, Qt.UserRole)
                model.appendRow(item)
            combo.setModel(model)
            combo.setCurrentText(current_text)  # Preserve selection if possible

    def create_weapons_tab(self):
        layout = QVBoxLayout(self.weapons_tab)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        label = QLabel("Weapons Configuration")
        label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(label)

        # Railgun/Epoch Section
        railgun_frame = QWidget()
        railgun_layout = QVBoxLayout(railgun_frame)
        railgun_layout.setSpacing(4)
        railgun_layout.setContentsMargins(0, 0, 0, 0)

        railgun_button_frame = QWidget()
        railgun_button_layout = QHBoxLayout(railgun_button_frame)
        railgun_button_layout.setSpacing(8)
        railgun_button_layout.setContentsMargins(0, 0, 0, 0)

        self.railgun_button = QPushButton("Railgun/Epoch Safety: OFF")
        self.railgun_button.setStyleSheet(
            "background-color: #EF5350; color: #FFFFFF; padding: 3px 8px; border-radius: 4px; min-height: 24px;"
        )
        self.railgun_button.clicked.connect(self.toggle_railgun_safety)
        railgun_button_layout.addWidget(self.railgun_button)

        self.railgun_keybind_button = QPushButton("Set Keybind")
        self.railgun_keybind_button.setFixedWidth(120)
        self.railgun_keybind_button.setToolTip("Assign a key to toggle railgun/epoch safety")
        self.railgun_keybind_button.clicked.connect(self.set_railgun_keybind)
        railgun_button_layout.addWidget(self.railgun_keybind_button)

        self.railgun_keybind_delete_button = QPushButton("Clear")
        self.railgun_keybind_delete_button.setFixedWidth(60)
        self.railgun_keybind_delete_button.setProperty("clear", True)
        self.railgun_keybind_delete_button.clicked.connect(self.delete_railgun_keybind)
        railgun_button_layout.addWidget(self.railgun_keybind_delete_button)

        railgun_button_layout.addStretch()
        railgun_layout.addWidget(railgun_button_frame)

        railgun_info = QLabel("Railgun/Epoch safety releases left click or switches weapon if held too long.")
        railgun_info.setStyleSheet("font-size: 12px; color: #B0BEC5;")
        railgun_layout.addWidget(railgun_info)

        self.railgun_fallback_checkbox = QCheckBox("Use keyboard fallback (press '1' to interrupt)")
        self.railgun_fallback_checkbox.setChecked(self.railgun_use_keyboard_fallback)
        self.railgun_fallback_checkbox.stateChanged.connect(self.update_railgun_fallback)
        railgun_layout.addWidget(self.railgun_fallback_checkbox)

        layout.addWidget(railgun_frame)

        # Arc Thrower Section
        arc_thrower_frame = QWidget()
        arc_thrower_layout = QVBoxLayout(arc_thrower_frame)
        arc_thrower_layout.setSpacing(4)
        arc_thrower_layout.setContentsMargins(0, 0, 0, 0)

        arc_thrower_button_frame = QWidget()
        arc_thrower_button_layout = QHBoxLayout(arc_thrower_button_frame)
        arc_thrower_button_layout.setSpacing(8)
        arc_thrower_button_layout.setContentsMargins(0, 0, 0, 0)

        self.arc_thrower_button = QPushButton("Arc Thrower Rapidfire: OFF")
        self.arc_thrower_button.setStyleSheet(
            "background-color: #EF5350; color: #FFFFFF; padding: 3px 8px; border-radius: 4px; min-height: 24px;"
        )
        self.arc_thrower_button.clicked.connect(self.toggle_arc_thrower_rapidfire)
        arc_thrower_button_layout.addWidget(self.arc_thrower_button)

        self.arc_thrower_keybind_button = QPushButton("Set Keybind")
        self.arc_thrower_keybind_button.setFixedWidth(120)
        self.arc_thrower_keybind_button.setToolTip("Assign a key to toggle arc thrower rapidfire")
        self.arc_thrower_keybind_button.clicked.connect(self.set_arc_thrower_keybind)
        arc_thrower_button_layout.addWidget(self.arc_thrower_keybind_button)

        self.arc_thrower_keybind_delete_button = QPushButton("Clear")
        self.arc_thrower_keybind_delete_button.setFixedWidth(60)
        self.arc_thrower_keybind_delete_button.setProperty("clear", True)
        self.arc_thrower_keybind_delete_button.clicked.connect(self.delete_arc_thrower_keybind)
        arc_thrower_button_layout.addWidget(self.arc_thrower_keybind_delete_button)

        arc_thrower_button_layout.addStretch()
        arc_thrower_layout.addWidget(arc_thrower_button_frame)

        self.arc_thrower_info = QLabel(f"Arc Thrower rapidfire releases and represses left click every {self.arc_thrower_delay}s when held.")
        self.arc_thrower_info.setStyleSheet("font-size: 12px; color: #B0BEC5;")
        arc_thrower_layout.addWidget(self.arc_thrower_info)
        layout.addWidget(arc_thrower_frame)

        arc_thrower_delay_frame = QHBoxLayout()
        arc_thrower_delay_label = QLabel("Arc Thrower Delay (seconds):")
        arc_thrower_delay_frame.addWidget(arc_thrower_delay_label)

        self.arc_thrower_delay_entry = QLineEdit(str(self.arc_thrower_delay))
        self.arc_thrower_delay_entry.setFixedWidth(60)
        self.arc_thrower_delay_entry.setToolTip("Enter value > 0.15 and <= 10 for rapidfire delay")
        arc_thrower_delay_frame.addWidget(self.arc_thrower_delay_entry)

        arc_thrower_update_button = QPushButton("Update")
        arc_thrower_update_button.setFixedWidth(80)
        arc_thrower_update_button.clicked.connect(self.update_arc_thrower_delay)
        arc_thrower_delay_frame.addWidget(arc_thrower_update_button)
        arc_thrower_delay_frame.addStretch()

        layout.addLayout(arc_thrower_delay_frame)

        timeout_frame = QHBoxLayout()
        timeout_label = QLabel("Railgun/Epoch Safety Timeout (seconds):")
        timeout_frame.addWidget(timeout_label)

        self.timeout_entry = QLineEdit(str(self.railgun_timeout))
        self.timeout_entry.setFixedWidth(60)
        self.timeout_entry.setToolTip("Enter positive value <= 10 for safety timeout")
        timeout_frame.addWidget(self.timeout_entry)

        update_button = QPushButton("Update")
        update_button.setFixedWidth(80)
        update_button.clicked.connect(self.update_railgun_timeout)
        timeout_frame.addWidget(update_button)
        timeout_frame.addStretch()

        layout.addLayout(timeout_frame)
        layout.addStretch()

    def create_support_tab(self):
        layout = QGridLayout(self.support_tab)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        label = QLabel("Support Stratagems")
        label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(label, 0, 0, 1, 5)  # Adjusted for test button

        support_stratagems = list(SUPPORT_STRATAGEMS.keys())

        for i, strat_name in enumerate(support_stratagems):
            frame = QWidget()
            frame_layout = QHBoxLayout(frame)
            frame_layout.setContentsMargins(0, 6, 0, 6)
            frame_layout.setSpacing(8)

            label = QLabel(strat_name)
            label.setFixedWidth(120)
            frame_layout.addWidget(label)

            keybind_button = QPushButton("Set Keybind")
            keybind_button.setFixedWidth(120)
            keybind_button.setToolTip("Assign a key or mouse button for this support stratagem")
            keybind_button.clicked.connect(lambda checked, idx=i: self.set_support_keybind(idx))
            frame_layout.addWidget(keybind_button)
            self.support_keybind_buttons.append(keybind_button)

            del_button = QPushButton("Clear")
            del_button.setFixedWidth(60)
            del_button.setProperty("clear", True)
            del_button.clicked.connect(lambda checked, idx=i: self.delete_support_keybind(idx))
            frame_layout.addWidget(del_button)
            self.support_delete_keybind_buttons.append(del_button)

            test_button = QPushButton("Test")
            test_button.setFixedWidth(60)
            test_button.setToolTip("Test this support stratagem sequence")
            test_button.clicked.connect(lambda checked, idx=i: self.test_support_stratagem(idx))
            frame_layout.addWidget(test_button)
            self.support_test_buttons.append(test_button)

            sequence = SUPPORT_STRATAGEMS.get(strat_name, [])
            output_label = QLabel(" → ".join(sequence))
            frame_layout.addWidget(output_label)
            self.support_outputs.append(output_label)

            layout.addWidget(frame, i + 1, 0, 1, 5)

        layout.setRowStretch(i + 2, 1)

    def create_logs_tab(self):
        layout = QVBoxLayout(self.logs_tab)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        label = QLabel("Logs")
        label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1E272C;
                color: #ECEFF1;
                border: 1px solid #455A64;
                padding: 5px;
                font-family: Consolas, "Courier New", monospace;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.log_text)

        clear_button = QPushButton("Clear Logs")
        clear_button.setFixedWidth(100)
        clear_button.setProperty("clear", True)
        clear_button.clicked.connect(self.clear_logs)
        layout.addWidget(clear_button)

        layout.addStretch()

    def create_profile_section(self):
        profile_frame = QWidget()
        profile_layout = QHBoxLayout(profile_frame)
        profile_layout.setContentsMargins(0, 5, 0, 5)
        profile_layout.setSpacing(8)

        label = QLabel("Profile Management")
        label.setStyleSheet("font-size: 16px; font-weight: bold;")
        profile_layout.addWidget(label)

        self.profile_combo = QComboBox()
        self.profile_combo.setFixedWidth(150)
        self.profile_combo.addItems(list(PROFILES.keys()))
        self.profile_combo.currentTextChanged.connect(self.load_profile)
        profile_layout.addWidget(self.profile_combo)

        self.profile_name_entry = QLineEdit()
        self.profile_name_entry.setFixedWidth(150)
        self.profile_name_entry.setPlaceholderText("Enter profile name")
        profile_layout.addWidget(self.profile_name_entry)

        create_button = QPushButton("Create Profile")
        create_button.setFixedWidth(100)
        create_button.setToolTip("Create a new profile with current configuration")
        create_button.clicked.connect(self.create_new_profile)
        profile_layout.addWidget(create_button)

        save_button = QPushButton("Save Profile")
        save_button.setFixedWidth(100)
        save_button.setToolTip("Save the current configuration to the selected profile")
        save_button.clicked.connect(self.save_profile)
        profile_layout.addWidget(save_button)

        rename_button = QPushButton("Rename Profile")
        rename_button.setFixedWidth(100)
        rename_button.setToolTip("Rename the selected profile")
        rename_button.clicked.connect(self.rename_profile)
        profile_layout.addWidget(rename_button)

        del_button = QPushButton("Delete")
        del_button.setFixedWidth(80)
        del_button.setProperty("clear", True)
        del_button.setToolTip("Delete the selected profile")
        del_button.clicked.connect(self.confirm_delete_profile)
        profile_layout.addWidget(del_button)

        profile_layout.addStretch()
        self.main_layout.addWidget(profile_frame)

    def append_log(self, message):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def clear_logs(self):
        self.log_text.clear()

    def blink_indicator(self):
        def blink_cycle(count):
            if count % 2 == 0:
                self.macro_indicator.setStyleSheet("background-color: yellow; border-radius: 10px;")
            else:
                self.macro_indicator.setStyleSheet(f"background-color: {'green' if self.running_macro else 'red'}; border-radius: 10px;")
            if count > 0:
                QTimer.singleShot(100, lambda: blink_cycle(count - 1))
        blink_cycle(3)

    def perform_mouse_release(self):
        try:
            if not (self.left_click_active and self.railgun_safety and self.running_macro):
                return
            current_time = time.time()
            if current_time - self.last_railgun_release < self.railgun_debounce:
                return
            self.last_railgun_release = current_time
            if self.railgun_use_keyboard_fallback:
                keyboard.press('1')
                time.sleep(0.01)
                keyboard.release('1')
                self.signal_handler.log_message.emit(f"Railgun/Epoch safety: Switched weapon at {current_time - self.left_click_time:.2f}s")
            else:
                time.sleep(0.005)
                mouse.release(Button.left)
                self.signal_handler.log_message.emit(f"Railgun/Epoch safety: Released left click at {current_time - self.left_click_time:.2f}s")
            self.left_click_active = False
        except Exception as e:
            self.signal_handler.log_message.emit(f"Error in railgun/epoch safety: {e}")
            logging.error(f"Error in railgun/epoch safety: {e}")

    def arc_thrower_rapidfire_func(self):
        self.signal_handler.log_message.emit("Arc Thrower thread started")
        while self.running_macro and self.arc_thrower_rapidfire:
            try:
                if not self.left_click_active:
                    time.sleep(0.2)
                    continue
                # Maintien pour le délai complet (hold time) avant tout relâchement
                time.sleep(self.arc_thrower_delay)
                if not (self.arc_thrower_rapidfire and self.left_click_active):
                    continue
                self.signal_handler.log_message.emit("Arc Thrower: Releasing and repressing left click")
                mouse.release(Button.left)
                time.sleep(0.03)
                mouse.press(Button.left)
            except Exception as e:
                self.signal_handler.log_message.emit(f"Error in arc thrower rapidfire: {e}")
                logging.error(f"Error in arc thrower rapidfire: {e}")
                break
        self.signal_handler.log_message.emit("Arc Thrower thread stopped")

    def toggle_arc_thrower_rapidfire(self):
        current_time = time.time()
        if current_time - self.last_toggle_time["arc_thrower"] < self.toggle_debounce:
            self.signal_handler.log_message.emit("Arc Thrower toggle ignored (debounce)")
            return
        self.last_toggle_time["arc_thrower"] = current_time

        new_state = not self.arc_thrower_rapidfire
        if new_state and self.railgun_safety:
            # Mutually exclusive: turn off railgun if turning on arc thrower
            self.railgun_safety = False
            self.railgun_button.setText("Railgun/Epoch Safety: OFF")
            self.railgun_button.setStyleSheet(
                "background-color: #EF5350; color: #FFFFFF; padding: 3px 8px; border-radius: 4px; min-height: 24px;"
            )
            self.signal_handler.log_message.emit("Railgun/Epoch safety disabled (mutual exclusion with Arc Thrower)")
            if self.railgun_timer is not None:
                self.railgun_timer.cancel()
                self.railgun_timer = None
                self.signal_handler.log_message.emit("Railgun/Epoch timer cancelled")

        self.arc_thrower_rapidfire = new_state
        color = "#4CAF50" if self.arc_thrower_rapidfire else "#EF5350"
        text = "Arc Thrower Rapidfire: ON" if self.arc_thrower_rapidfire else "Arc Thrower Rapidfire: OFF"
        self.arc_thrower_button.setText(text)
        self.arc_thrower_button.setStyleSheet(
            f"background-color: {color}; color: #FFFFFF; padding: 3px 8px; border-radius: 4px; min-height: 24px;"
        )
        self.arc_thrower_info.setText(f"Arc Thrower rapidfire releases and represses left click every {self.arc_thrower_delay}s when held.")
        self.signal_handler.log_message.emit(f"Arc Thrower rapidfire {'enabled' if self.arc_thrower_rapidfire else 'disabled'}")

        if self.arc_thrower_rapidfire and self.running_macro:
            if self.arc_thrower_thread is None or not self.arc_thrower_thread.is_alive():
                self.arc_thrower_thread = threading.Thread(target=self.arc_thrower_rapidfire_func, daemon=True)
                self.arc_thrower_thread.start()
        elif not self.arc_thrower_rapidfire:
            if self.arc_thrower_thread is not None:
                self.arc_thrower_thread.join(timeout=1)
            mouse.release(Button.left)

    def toggle_railgun_safety(self):
        current_time = time.time()
        if current_time - self.last_toggle_time["railgun"] < self.toggle_debounce:
            self.signal_handler.log_message.emit("Railgun/Epoch toggle ignored (debounce)")
            return
        self.last_toggle_time["railgun"] = current_time

        new_state = not self.railgun_safety
        if new_state and self.arc_thrower_rapidfire:
            # Mutually exclusive: turn off arc thrower if turning on railgun
            self.arc_thrower_rapidfire = False
            self.arc_thrower_button.setText("Arc Thrower Rapidfire: OFF")
            self.arc_thrower_button.setStyleSheet(
                "background-color: #EF5350; color: #FFFFFF; padding: 3px 8px; border-radius: 4px; min-height: 24px;"
            )
            self.signal_handler.log_message.emit("Arc Thrower rapidfire disabled (mutual exclusion with Railgun/Epoch)")
            if self.arc_thrower_thread is not None:
                self.arc_thrower_thread.join(timeout=1)
            mouse.release(Button.left)

        self.railgun_safety = new_state
        color = "#4CAF50" if self.railgun_safety else "#EF5350"
        text = "Railgun/Epoch Safety: ON" if self.railgun_safety else "Railgun/Epoch Safety: OFF"
        self.railgun_button.setText(text)
        self.railgun_button.setStyleSheet(
            f"background-color: {color}; color: #FFFFFF; padding: 3px 8px; border-radius: 4px; min-height: 24px;"
        )
        self.signal_handler.log_message.emit(f"Railgun/Epoch safety {'enabled' if self.railgun_safety else 'disabled'}")

        if not self.railgun_safety and self.railgun_timer is not None:
            self.railgun_timer.cancel()
            self.railgun_timer = None
            self.signal_handler.log_message.emit("Railgun/Epoch timer cancelled")

    def update_railgun_fallback(self, state):
        self.railgun_use_keyboard_fallback = state == Qt.Checked
        self.signal_handler.log_message.emit(f"Railgun/Epoch keyboard fallback {'enabled' if self.railgun_use_keyboard_fallback else 'disabled'}")

    def update_arc_thrower_delay(self):
        try:
            new_delay = float(self.arc_thrower_delay_entry.text())
            if new_delay <= 0.15 or new_delay > 10:
                self.signal_handler.show_warning.emit("Delay must be between 0.15 and 10 seconds.")
                self.signal_handler.log_message.emit("Failed to update Arc Thrower delay: Invalid range")
                return
            self.arc_thrower_delay = new_delay
            self.arc_thrower_info.setText(f"Arc Thrower rapidfire releases and represses left click every {self.arc_thrower_delay}s when held.")
            self.signal_handler.log_message.emit(f"Updated Arc Thrower delay to {self.arc_thrower_delay}s")
        except ValueError:
            self.signal_handler.show_warning.emit("Please enter a valid number for delay.")
            self.signal_handler.log_message.emit("Failed to update Arc Thrower delay: Invalid number entered")

    def update_railgun_timeout(self):
        try:
            new_timeout = float(self.timeout_entry.text())
            if new_timeout <= 0 or new_timeout > 10:
                self.signal_handler.show_warning.emit("Timeout must be positive and <= 10 seconds.")
                self.signal_handler.log_message.emit("Failed to update Railgun/Epoch timeout: Invalid range")
                return
            self.railgun_timeout = new_timeout
            self.signal_handler.log_message.emit(f"Updated Railgun/Epoch timeout to {self.railgun_timeout}s")
        except ValueError:
            self.signal_handler.show_warning.emit("Please enter a valid number for timeout.")
            self.signal_handler.log_message.emit("Failed to update Railgun/Epoch timeout: Invalid number entered")

    def set_railgun_keybind(self):
        self.active_keybind = "railgun"
        self.railgun_keybind_button.setText("Press a key or side mouse button...")
        self.signal_handler.log_message.emit("Setting Railgun/Epoch keybind...")

    def set_arc_thrower_keybind(self):
        self.active_keybind = "arc_thrower"
        self.arc_thrower_keybind_button.setText("Press a key or side mouse button...")
        self.signal_handler.log_message.emit("Setting Arc Thrower keybind...")

    def delete_railgun_keybind(self):
        self.railgun_keybind = ""
        self.railgun_keybind_button.setText("Set Keybind")
        self.signal_handler.log_message.emit("Cleared Railgun/Epoch keybind")

    def delete_arc_thrower_keybind(self):
        self.arc_thrower_keybind = ""
        self.arc_thrower_keybind_button.setText("Set Keybind")
        self.signal_handler.log_message.emit("Cleared Arc Thrower keybind")

    def set_keybind(self, index):
        self.active_keybind = index
        self.keybind_buttons[index].setText("Press a key or side mouse button...")
        self.signal_handler.log_message.emit(f"Setting keybind for Stratagem {index+1}...")

    def set_support_keybind(self, index):
        self.active_keybind = index + len(self.keybind_buttons)
        self.support_keybind_buttons[index].setText("Press a key or side mouse button...")
        self.signal_handler.log_message.emit(f"Setting keybind for Support Stratagem {list(SUPPORT_STRATAGEMS.keys())[index]}...")

    def delete_keybind(self, index):
        self.keybind_vars[index] = ""
        self.keybind_buttons[index].setText("Set Keybind")
        self.signal_handler.log_message.emit(f"Cleared keybind for Stratagem {index+1}")

    def delete_support_keybind(self, index):
        self.support_keybind_vars[index] = ""
        self.support_keybind_buttons[index].setText("Set Keybind")
        self.signal_handler.log_message.emit(f"Cleared keybind for Support Stratagem {list(SUPPORT_STRATAGEMS.keys())[index]}")

    def check_keybind_conflict(self, key_str, exclude_index=None):
        for i, key_var in enumerate(self.keybind_vars):
            if i != exclude_index and key_var == key_str and i < len(self.keybind_buttons):
                return f"Keybind '{key_str}' is already assigned to Stratagem {i+1}"
        for i, key_var in enumerate(self.support_keybind_vars):
            if (exclude_index is None or i + len(self.keybind_buttons) != exclude_index) and key_var == key_str:
                return f"Keybind '{key_str}' is already assigned to {list(SUPPORT_STRATAGEMS.keys())[i]}"
        if exclude_index != "railgun" and self.railgun_keybind == key_str:
            return f"Keybind '{key_str}' is already assigned to Railgun/Epoch Safety"
        if exclude_index != "arc_thrower" and self.arc_thrower_keybind == key_str:
            return f"Keybind '{key_str}' is already assigned to Arc Thrower Rapidfire"
        return None

    def show_warning_message(self, message):
        QMessageBox.warning(self, "Warning", message)

    def create_new_profile(self):
        profile_name = self.profile_name_entry.text().strip()
        if not profile_name:
            self.signal_handler.show_warning.emit("Please enter a profile name.")
            self.signal_handler.log_message.emit("Failed to create profile: No profile name entered")
            return

        if profile_name in PROFILES:
            self.signal_handler.show_warning.emit("Profile name already exists.")
            self.signal_handler.log_message.emit("Failed to create profile: Profile name already exists")
            return

        profile_data = {
            "keybinds": self.keybind_vars[:],
            "stratagems": [combo.currentText() for combo in self.stratagem_combos],
            "support_keybinds": self.support_keybind_vars[:],
            "railgun_timeout": self.railgun_timeout,
            "arc_thrower_delay": self.arc_thrower_delay,
            "railgun_keybind": self.railgun_keybind,
            "arc_thrower_keybind": self.arc_thrower_keybind,
            "railgun_use_keyboard_fallback": self.railgun_use_keyboard_fallback,
            "macro_delay": self.macro_delay
        }

        PROFILES[profile_name] = profile_data
        try:
            with open("profiles.json", "w") as f:
                json.dump(PROFILES, f, indent=4)
            self.profile_combo.addItem(profile_name)
            self.profile_combo.setCurrentText(profile_name)
            self.profile_name_entry.clear()
            self.save_last_profile(profile_name)
            self.signal_handler.log_message.emit(f"Created new profile: {profile_name}")
        except Exception as e:
            self.signal_handler.show_warning.emit(f"Failed to create profile: {e}")
            self.signal_handler.log_message.emit(f"Failed to create profile: {e}")

    def save_profile(self):
        profile_name = self.profile_combo.currentText()
        if not profile_name:
            self.signal_handler.show_warning.emit("Please select a profile to save.")
            self.signal_handler.log_message.emit("Failed to save profile: No profile selected")
            return

        reply = QMessageBox.question(self, "Confirmation", f"Are you sure you want to overwrite '{profile_name}'?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            return

        profile_data = {
            "keybinds": self.keybind_vars[:],
            "stratagems": [combo.currentText() for combo in self.stratagem_combos],
            "support_keybinds": self.support_keybind_vars[:],
            "railgun_timeout": self.railgun_timeout,
            "arc_thrower_delay": self.arc_thrower_delay,
            "railgun_keybind": self.railgun_keybind,
            "arc_thrower_keybind": self.arc_thrower_keybind,
            "railgun_use_keyboard_fallback": self.railgun_use_keyboard_fallback,
            "macro_delay": self.macro_delay
        }

        PROFILES[profile_name] = profile_data
        try:
            with open("profiles.json", "w") as f:
                json.dump(PROFILES, f, indent=4)
            self.signal_handler.log_message.emit(f"Saved profile: {profile_name}")
            self.save_last_profile(profile_name)
        except Exception as e:
            self.signal_handler.show_warning.emit(f"Failed to save profile: {e}")
            self.signal_handler.log_message.emit(f"Failed to save profile: {e}")

    def load_profile(self, profile_name):
        if not profile_name or profile_name not in PROFILES:
            self.signal_handler.show_warning.emit("Invalid profile selected.")
            self.signal_handler.log_message.emit("Failed to load profile: Invalid profile selected")
            return

        try:
            profile_data = PROFILES[profile_name]
            self.keybind_vars = profile_data.get("keybinds", [""] * 5)
            self.support_keybind_vars = profile_data.get("support_keybinds", [""] * len(SUPPORT_STRATAGEMS))

            for i in range(len(self.keybind_buttons)):
                self.keybind_buttons[i].setText(self.keybind_vars[i] if self.keybind_vars[i] else "Set Keybind")

            for i in range(len(self.stratagem_combos)):
                self.stratagem_combos[i].setCurrentText(profile_data.get("stratagems", ["Select Stratagem"] * 5)[i])
                self.update_stratagem_output(i)

            for i in range(len(self.support_keybind_buttons)):
                self.support_keybind_buttons[i].setText(self.support_keybind_vars[i] if self.support_keybind_vars[i] else "Set Keybind")

            self.railgun_timeout = profile_data.get("railgun_timeout", 2.95)
            self.timeout_entry.setText(str(self.railgun_timeout))
            self.arc_thrower_delay = profile_data.get("arc_thrower_delay", 1.05)
            self.arc_thrower_delay_entry.setText(str(self.arc_thrower_delay))
            self.arc_thrower_info.setText(f"Arc Thrower rapidfire releases and represses left click every {self.arc_thrower_delay}s when held.")
            self.railgun_keybind = profile_data.get("railgun_keybind", "")
            self.railgun_keybind_button.setText(self.railgun_keybind if self.railgun_keybind else "Set Keybind")
            self.arc_thrower_keybind = profile_data.get("arc_thrower_keybind", "")
            self.arc_thrower_keybind_button.setText(self.arc_thrower_keybind if self.arc_thrower_keybind else "Set Keybind")
            self.railgun_use_keyboard_fallback = profile_data.get("railgun_use_keyboard_fallback", False)
            self.railgun_fallback_checkbox.setChecked(self.railgun_use_keyboard_fallback)
            self.macro_delay = profile_data.get("macro_delay", 0.05)
            self.profile_name_entry.setText(profile_name)
            self.signal_handler.log_message.emit(f"Loaded profile: {profile_name}")
            self.save_last_profile(profile_name)
        except Exception as e:
            self.signal_handler.show_warning.emit(f"Failed to load profile: {e}")
            self.signal_handler.log_message.emit(f"Failed to load profile: {e}")

    def rename_profile(self):
        old_name = self.profile_combo.currentText()
        new_name = self.profile_name_entry.text().strip()
        if not old_name or not new_name:
            self.signal_handler.show_warning.emit("Please select a profile and enter a new name.")
            self.signal_handler.log_message.emit("Failed to rename profile: Missing profile or new name")
            return
        if new_name in PROFILES:
            self.signal_handler.show_warning.emit("Profile name already exists.")
            self.signal_handler.log_message.emit("Failed to rename profile: Profile name already exists")
            return

        try:
            PROFILES[new_name] = PROFILES.pop(old_name)
            with open("profiles.json", "w") as f:
                json.dump(PROFILES, f, indent=4)
            self.profile_combo.clear()
            self.profile_combo.addItems(list(PROFILES.keys()))
            self.profile_combo.setCurrentText(new_name)
            self.profile_name_entry.clear()
            self.signal_handler.log_message.emit(f"Renamed profile from {old_name} to {new_name}")
            self.save_last_profile(new_name)
        except Exception as e:
            self.signal_handler.show_warning.emit(f"Failed to rename profile: {e}")
            self.signal_handler.log_message.emit(f"Failed to rename profile: {e}")

    def confirm_delete_profile(self):
        profile_name = self.profile_combo.currentText()
        if not profile_name or profile_name not in PROFILES:
            self.signal_handler.show_warning.emit("No valid profile selected.")
            self.signal_handler.log_message.emit("Failed to delete profile: No valid profile selected")
            return
        if profile_name == "Default":
            self.signal_handler.show_warning.emit("Cannot delete the Default profile.")
            self.signal_handler.log_message.emit("Failed to delete profile: Cannot delete Default profile")
            return

        reply = QMessageBox.question(self, "Confirmation", f"Are you sure you want to delete the profile '{profile_name}'?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.delete_profile(profile_name)

    def delete_profile(self, profile_name):
        try:
            del PROFILES[profile_name]
            with open("profiles.json", "w") as f:
                json.dump(PROFILES, f, indent=4)
            self.profile_combo.clear()
            self.profile_combo.addItems(list(PROFILES.keys()))
            self.profile_combo.setCurrentText("Default")
            self.profile_name_entry.clear()
            self.load_profile("Default")
            self.signal_handler.log_message.emit(f"Deleted profile: {profile_name}")
        except Exception as e:
            self.signal_handler.show_warning.emit(f"Failed to delete profile: {e}")
            self.signal_handler.log_message.emit(f"Failed to delete profile: {e}")

    def toggle_macro(self):
        self.running_macro = not self.running_macro
        color = "#EF5350" if self.running_macro else "#4CAF50"
        text = "⏹ Stop" if self.running_macro else "▶ Start"
        self.toggle_button.setText(text)
        self.toggle_button.setStyleSheet(f"background-color: {color}; color: #FFFFFF; padding: 3px 8px; border-radius: 4px; min-height: 24px;")
        self.macro_indicator.setStyleSheet(f"background-color: {'green' if self.running_macro else 'red'}; border-radius: 10px;")
        self.signal_handler.log_message.emit(f"Macro system {'started' if self.running_macro else 'stopped'}")

        if not self.running_macro:
            self.arc_thrower_rapidfire = False
            self.railgun_safety = False
            self.stop_all_threads()
            self.arc_thrower_button.setText("Arc Thrower Rapidfire: OFF")
            self.arc_thrower_button.setStyleSheet(
                "background-color: #EF5350; color: #FFFFFF; padding: 3px 8px; border-radius: 4px; min-height: 24px;"
            )
            self.railgun_button.setText("Railgun/Epoch Safety: OFF")
            self.railgun_button.setStyleSheet(
                "background-color: #EF5350; color: #FFFFFF; padding: 3px 8px; border-radius: 4px; min-height: 24px;"
            )
            self.arc_thrower_info.setText(f"Arc Thrower rapidfire releases and represses left click every {self.arc_thrower_delay}s when held.")
        elif self.arc_thrower_rapidfire:
            if self.arc_thrower_thread is None or not self.arc_thrower_thread.is_alive():
                self.arc_thrower_thread = threading.Thread(target=self.arc_thrower_rapidfire_func, daemon=True)
                self.arc_thrower_thread.start()

    def run_macro_sequence(self, sequence, test_mode=False):
        if not test_mode and not self.running_macro:
            self.signal_handler.log_message.emit("Macro stopped, exiting sequence")
            return
        try:
            self.signal_handler.log_message.emit(f"Executing sequence: {sequence}")
            keyboard.press(Key.ctrl)
            time.sleep(0.05)
            start_time = time.time()
            for key in sequence:
                if not test_mode and not self.running_macro:
                    self.signal_handler.log_message.emit("Macro interrupted")
                    break
                key_map = {
                    "up": Key.up,
                    "down": Key.down,
                    "left": Key.left,
                    "right": Key.right
                }
                if key in key_map:
                    self.signal_handler.log_message.emit(f"Pressing {key} at {time.time() - start_time:.2f}s")
                    self.signal_handler.blink.emit()
                    keyboard.press(key_map[key])
                    time.sleep(self.macro_delay)
                    keyboard.release(key_map[key])
                    time.sleep(self.macro_delay)
            self.signal_handler.log_message.emit("Sequence completed")
        except Exception as e:
            self.signal_handler.log_message.emit(f"Error executing macro: {e}")
        finally:
            keyboard.release(Key.ctrl)
            self.signal_handler.log_message.emit("Ctrl released")

    def update_stratagem_output(self, idx):
        strat_name = self.stratagem_combos[idx].currentText()
        if strat_name in STRATAGEM_DATA and isinstance(STRATAGEM_DATA[strat_name], dict) and "sequence" in STRATAGEM_DATA[strat_name] and STRATAGEM_DATA[strat_name]["sequence"]:
            sequence = STRATAGEM_DATA[strat_name]["sequence"]
            color = STRATAGEM_DATA[strat_name].get("color", "#ECEFF1")
            self.stratagem_outputs[idx].setText(" → ".join(sequence))
            self.stratagem_outputs[idx].setStyleSheet(f"color: {color};")
            self.signal_handler.log_message.emit(f"Updated Stratagem {idx+1} to {strat_name}")
        else:
            self.stratagem_outputs[idx].setText("")
            self.stratagem_outputs[idx].setStyleSheet("color: #ECEFF1;")
            self.signal_handler.log_message.emit(f"Cleared Stratagem {idx+1} output")

    def start_listeners(self):
        def on_press(key):
            try:
                key_str = str(key).replace("Key.", "").replace("'", "").lower()
                self.signal_handler.log_message.emit(f"Key pressed: {key_str}")
                if self.active_keybind is not None:
                    if key_str in ["esc", "enter", "tab"]:
                        self.signal_handler.show_warning.emit(f"Key '{key_str}' cannot be used as a keybind.")
                        self.signal_handler.log_message.emit(f"Key '{key_str}' cannot be used as a keybind")
                        return
                    conflict_msg = self.check_keybind_conflict(key_str, self.active_keybind)
                    if conflict_msg:
                        self.signal_handler.show_warning.emit(conflict_msg)
                        self.signal_handler.log_message.emit(conflict_msg)
                        if isinstance(self.active_keybind, int) and self.active_keybind < len(self.keybind_buttons):
                            self.keybind_buttons[self.active_keybind].setText(
                                self.keybind_vars[self.active_keybind] if self.keybind_vars[self.active_keybind] else "Set Keybind"
                            )
                        elif isinstance(self.active_keybind, int):
                            support_idx = self.active_keybind - len(self.keybind_buttons)
                            self.support_keybind_buttons[support_idx].setText(
                                self.support_keybind_vars[support_idx] if self.support_keybind_vars[support_idx] else "Set Keybind"
                            )
                        elif self.active_keybind == "railgun":
                            self.railgun_keybind_button.setText(self.railgun_keybind if self.railgun_keybind else "Set Keybind")
                        elif self.active_keybind == "arc_thrower":
                            self.arc_thrower_keybind_button.setText(self.arc_thrower_keybind if self.arc_thrower_keybind else "Set Keybind")
                        self.active_keybind = None
                        return
                    if isinstance(self.active_keybind, int) and self.active_keybind < len(self.keybind_buttons):
                        self.keybind_vars[self.active_keybind] = key_str
                        self.keybind_buttons[self.active_keybind].setText(key_str)
                        self.signal_handler.log_message.emit(f"Set keybind for Stratagem {self.active_keybind+1} to {key_str}")
                    elif isinstance(self.active_keybind, int):
                        support_idx = self.active_keybind - len(self.keybind_buttons)
                        self.support_keybind_vars[support_idx] = key_str
                        self.support_keybind_buttons[support_idx].setText(key_str)
                        self.signal_handler.log_message.emit(f"Set keybind for Support Stratagem {list(SUPPORT_STRATAGEMS.keys())[support_idx]} to {key_str}")
                    elif self.active_keybind == "railgun":
                        self.railgun_keybind = key_str
                        self.railgun_keybind_button.setText(key_str)
                        self.signal_handler.log_message.emit(f"Set Railgun/Epoch keybind to {key_str}")
                    elif self.active_keybind == "arc_thrower":
                        self.arc_thrower_keybind = key_str
                        self.arc_thrower_keybind_button.setText(key_str)
                        self.signal_handler.log_message.emit(f"Set Arc Thrower keybind to {key_str}")
                    self.active_keybind = None
                elif self.running_macro:
                    if key_str == self.railgun_keybind:
                        self.toggle_railgun_safety()
                    elif key_str == self.arc_thrower_keybind:
                        self.toggle_arc_thrower_rapidfire()
                    for i, key_var in enumerate(self.keybind_vars):
                        if key_var == key_str and i < len(self.stratagem_combos):
                            strat_name = self.stratagem_combos[i].currentText()
                            if strat_name in STRATAGEM_DATA and isinstance(STRATAGEM_DATA[strat_name], dict) and "sequence" in STRATAGEM_DATA[strat_name] and STRATAGEM_DATA[strat_name]["sequence"]:
                                if self.macro_thread and self.macro_thread.is_alive():
                                    self.signal_handler.log_message.emit("Macro thread busy, skipping")
                                    continue
                                self.signal_handler.log_message.emit(f"Launching stratagem: {strat_name}")
                                self.macro_thread = threading.Thread(
                                    target=self.run_macro_sequence,
                                    args=(STRATAGEM_DATA[strat_name]["sequence"],),
                                    daemon=True
                                )
                                self.macro_thread.start()
                    for i, key_var in enumerate(self.support_keybind_vars):
                        if key_var == key_str:
                            strat_name = list(SUPPORT_STRATAGEMS.keys())[i]
                            if strat_name in SUPPORT_STRATAGEMS:
                                if self.macro_thread and self.macro_thread.is_alive():
                                    self.signal_handler.log_message.emit("Macro thread busy, skipping")
                                    continue
                                self.signal_handler.log_message.emit(f"Launching support stratagem: {strat_name}")
                                self.macro_thread = threading.Thread(
                                    target=self.run_macro_sequence,
                                    args=(SUPPORT_STRATAGEMS[strat_name],),
                                    daemon=True
                                )
                                self.macro_thread.start()
            except Exception as e:
                self.signal_handler.log_message.emit(f"Error in key press: {e}")

        def on_click(x, y, button, pressed):
            try:
                if button == Button.left:
                    self.left_click_active = pressed
                    self.left_click_time = time.time() if pressed else self.left_click_time
                    if pressed and self.railgun_safety and self.running_macro:
                        if self.railgun_timer is not None:
                            self.railgun_timer.cancel()
                        self.railgun_timer = threading.Timer(self.railgun_timeout - 0.05, self.perform_mouse_release)
                        self.railgun_timer.daemon = True
                        self.railgun_timer.start()
                        self.signal_handler.log_message.emit("Railgun timer started")
                    elif not pressed and self.railgun_timer is not None:
                        self.railgun_timer.cancel()
                        self.railgun_timer = None
                        self.signal_handler.log_message.emit("Railgun timer cancelled on release")
                if pressed and button in [Button.x1, Button.x2]:
                    button_str = str(button).replace("Button.", "").lower()
                    self.signal_handler.log_message.emit(f"Mouse button pressed: {button_str}")
                    if self.active_keybind is not None:
                        conflict_msg = self.check_keybind_conflict(button_str, self.active_keybind)
                        if conflict_msg:
                            self.signal_handler.show_warning.emit(conflict_msg)
                            self.signal_handler.log_message.emit(conflict_msg)
                            if isinstance(self.active_keybind, int) and self.active_keybind < len(self.keybind_buttons):
                                self.keybind_buttons[self.active_keybind].setText(
                                    self.keybind_vars[self.active_keybind] if self.keybind_vars[self.active_keybind] else "Set Keybind"
                                )
                            elif isinstance(self.active_keybind, int):
                                support_idx = self.active_keybind - len(self.keybind_buttons)
                                self.support_keybind_buttons[support_idx].setText(
                                    self.support_keybind_vars[support_idx] if self.support_keybind_vars[support_idx] else "Set Keybind"
                                )
                            elif self.active_keybind == "railgun":
                                self.railgun_keybind_button.setText(self.railgun_keybind if self.railgun_keybind else "Set Keybind")
                            elif self.active_keybind == "arc_thrower":
                                self.arc_thrower_keybind_button.setText(self.arc_thrower_keybind if self.arc_thrower_keybind else "Set Keybind")
                            self.active_keybind = None
                            return
                        if isinstance(self.active_keybind, int) and self.active_keybind < len(self.keybind_buttons):
                            self.keybind_vars[self.active_keybind] = button_str
                            self.keybind_buttons[self.active_keybind].setText(button_str)
                            self.signal_handler.log_message.emit(f"Set keybind for Stratagem {self.active_keybind+1} to {button_str}")
                        elif isinstance(self.active_keybind, int):
                            support_idx = self.active_keybind - len(self.keybind_buttons)
                            self.support_keybind_vars[support_idx] = button_str
                            self.support_keybind_buttons[support_idx].setText(button_str)
                            self.signal_handler.log_message.emit(f"Set keybind for Support Stratagem {list(SUPPORT_STRATAGEMS.keys())[support_idx]} to {button_str}")
                        elif self.active_keybind == "railgun":
                            self.railgun_keybind = button_str
                            self.railgun_keybind_button.setText(button_str)
                            self.signal_handler.log_message.emit(f"Set Railgun keybind to {button_str}")
                        elif self.active_keybind == "arc_thrower":
                            self.arc_thrower_keybind = button_str
                            self.arc_thrower_keybind_button.setText(button_str)
                            self.signal_handler.log_message.emit(f"Set Arc Thrower keybind to {button_str}")
                        self.active_keybind = None
                    elif self.running_macro:
                        if button_str == self.railgun_keybind:
                            self.toggle_railgun_safety()
                        elif button_str == self.arc_thrower_keybind:
                            self.toggle_arc_thrower_rapidfire()
                        for i, key_var in enumerate(self.keybind_vars):
                            if key_var == button_str and i < len(self.stratagem_combos):
                                strat_name = self.stratagem_combos[i].currentText()
                                if strat_name in STRATAGEM_DATA and isinstance(STRATAGEM_DATA[strat_name], dict) and "sequence" in STRATAGEM_DATA[strat_name] and STRATAGEM_DATA[strat_name]["sequence"]:
                                    if self.macro_thread and self.macro_thread.is_alive():
                                        self.signal_handler.log_message.emit("Macro thread busy, skipping")
                                        continue
                                    self.signal_handler.log_message.emit(f"Launching stratagem: {strat_name}")
                                    self.macro_thread = threading.Thread(
                                        target=self.run_macro_sequence,
                                        args=(STRATAGEM_DATA[strat_name]["sequence"],),
                                        daemon=True
                                    )
                                    self.macro_thread.start()
                        for i, key_var in enumerate(self.support_keybind_vars):
                            if key_var == button_str:
                                strat_name = list(SUPPORT_STRATAGEMS.keys())[i]
                                if strat_name in SUPPORT_STRATAGEMS:
                                    if self.macro_thread and self.macro_thread.is_alive():
                                        self.signal_handler.log_message.emit("Macro thread busy, skipping")
                                        continue
                                    self.signal_handler.log_message.emit(f"Launching support stratagem: {strat_name}")
                                    self.macro_thread = threading.Thread(
                                        target=self.run_macro_sequence,
                                        args=(SUPPORT_STRATAGEMS[strat_name],),
                                        daemon=True
                                    )
                                    self.macro_thread.start()
            except Exception as e:
                self.signal_handler.log_message.emit(f"Error in mouse click: {e}")

        global mouse_listener, keyboard_listener
        mouse_listener = pynput_mouse.Listener(on_click=on_click)
        keyboard_listener = KeyboardListener(on_press=on_press)
        mouse_listener.start()
        keyboard_listener.start()

    def stop_all_threads(self):
        if self.arc_thrower_thread and self.arc_thrower_thread.is_alive():
            self.arc_thrower_rapidfire = False
            self.arc_thrower_thread.join(timeout=1)
        if self.railgun_timer:
            self.railgun_timer.cancel()
        if self.macro_thread and self.macro_thread.is_alive():
            self.macro_thread.join(timeout=1)

    def test_stratagem(self, idx):
        strat_name = self.stratagem_combos[idx].currentText()
        if strat_name in STRATAGEM_DATA and isinstance(STRATAGEM_DATA[strat_name], dict) and "sequence" in STRATAGEM_DATA[strat_name]:
            self.signal_handler.log_message.emit(f"[TEST] Stratagem {strat_name}: {STRATAGEM_DATA[strat_name]['sequence']}")
            self.run_macro_sequence(STRATAGEM_DATA[strat_name]['sequence'], test_mode=True)
        else:
            self.signal_handler.log_message.emit("[TEST] No valid sequence for this stratagem.")

    def test_support_stratagem(self, idx):
        strat_name = list(SUPPORT_STRATAGEMS.keys())[idx]
        sequence = SUPPORT_STRATAGEMS.get(strat_name, [])
        if sequence:
            self.signal_handler.log_message.emit(f"[TEST] Support Stratagem {strat_name}: {sequence}")
            self.run_macro_sequence(sequence, test_mode=True)
        else:
            self.signal_handler.log_message.emit("[TEST] No valid sequence for this support stratagem.")

    def save_last_profile(self, profile_name):
        try:
            with open("last_profile.json", "w") as f:
                json.dump({"last_profile": profile_name}, f)
        except Exception as e:
            logging.error(f"Error saving last profile: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MacroApp()
    window.show()
    sys.exit(app.exec())