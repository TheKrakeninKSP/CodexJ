from enum import Enum


class ColorTheme(str, Enum):
    """Status of import processing. Values match the enum member name."""

    light = "light"
    midnight = "midnight"
    solarized_dark = "solarized dark"
