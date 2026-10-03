"""
Customize this file before you start the app.

This project is a pretend-money family banking simulator.
It is not connected to a real bank or payment network.
"""

BANK_NAME = "Your Bank Name"
BANK_TAGLINE = "Family finance, made friendly."

# Change this before using Parent Mode.
PARENT_PIN = "1234"

# Change this to a long random string for your own installation.
SECRET_KEY = "change-this-secret-key"

# These are the starter accounts created the first time the app runs.
# Available animal icons included with this template:
# dog, horse, capybara
#
# Available themes:
# sun, lavender, aqua
DEFAULT_KIDS = [
    {
        "name": "Kid 1",
        "animal": "dog",
        "theme": "sun",
        "message": "Keep going!"
    },
    {
        "name": "Kid 2",
        "animal": "horse",
        "theme": "lavender",
        "message": "You’ve got this!"
    },
    {
        "name": "Kid 3",
        "animal": "capybara",
        "theme": "aqua",
        "message": "Nice saving!"
    },
]

STARTING_CHECKING = 100.00
STARTING_SAVINGS = 0.00
MONTHLY_RENT = 10.00
