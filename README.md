# Helldivers 2 Macro Tool

A simple Python application to automate stratagem inputs and weapon controls for *Helldivers 2*. Customize stratagems, set keybinds, and manage profiles with an easy-to-use interface.

## Features

- **Custom Stratagems**: Edit `stratagems.json` to create your own stratagems and colors, e.g.:
  ```
  {
      "Custom Nuke": {
          "sequence": ["up", "down", "left", "right"],
          "color": "#FF0000"
      }
  }
  ```
- **Keybinds**: Assign keys or mouse buttons to stratagems like Reinforce or Eagle Airstrike.
- **Weapons**: Railgun safety prevents overcharging; Arc Thrower rapidfire auto-clicks with adjustable delays.
- **Profiles**: Save and switch setups in `profiles.json`.
- **User Interface**: Dark-themed with Stratagems, Weapons, Support, and Logs tabs.

## Setup

1. **Install**: Ensure Python 3.8+ is installed, then run:
   ```
   pip install PySide6 pynput
   ```
2. **Download**: Clone or download this repository, including `hellmacro.py`, `stratagems.json`, and `profiles.json`.
3. **Run**: Launch the app with:
   ```
   python hellmacro.py
   ```
4. **Edit**: Customize stratagems in `stratagems.json`.
5. **Use**: Set keybinds, test sequences, and save profiles.

## Usage

- Edit `stratagems.json` to define custom stratagems and reload them in the app.
- Assign keybinds in the Stratagems or Support tabs.
- Configure weapon settings (e.g., Railgun safety timeout) in the Weapons tab.
- Start the macro system and press assigned keys to execute sequences.

## Notes

- **Customization**: Experiment with `stratagems.json` to create unique loadouts.

## Last Updated
10:58 AM EDT, Friday, July 18, 2025
