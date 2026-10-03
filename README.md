# Family Bank App Template

A customizable, local Flask app for teaching kids about pretend money, checking, savings, chores, jobs, rent, a family store, and NFC-style account cards.

> This project is a family finance simulator. It does **not** connect to a real bank, debit network, credit card network, or payment processor.

## Features

- Multiple kid accounts
- Checking and savings balances
- Money transfers
- Parent PIN mode
- Parent deposits and charges
- Monthly rent charging
- Family store with editable items
- Chores and bigger paid jobs
- Parent approval before chore/job rewards are paid
- Transaction history
- NFC UID field and `/tap?uid=...` route ready for future reader integration
- Responsive phone/tablet-friendly interface

## Customize it first

Open `settings.py`.

Change:

```python
BANK_NAME = "Your Bank Name"
PARENT_PIN = "1234"
```

Then edit the starter kids:

```python
DEFAULT_KIDS = [
    {
        "name": "Kid 1",
        "animal": "dog",
        "theme": "sun",
        "message": "Keep going!"
    },
    ...
]
```

The included avatar choices are:

- `dog`
- `horse`
- `capybara`

The included color themes are:

- `sun`
- `lavender`
- `aqua`

You can also change:

```python
STARTING_CHECKING = 100.00
STARTING_SAVINGS = 0.00
MONTHLY_RENT = 10.00
```

### Important

Customize `settings.py` **before the first launch**.

The first launch creates `family_bank.db` and seeds the starter accounts. Later changes to `DEFAULT_KIDS` do not automatically rename accounts already stored in an existing database.

## Run on Windows

Open the project folder in VS Code and create the virtual environment:

```powershell
python -m venv .venv
```

Install Flask:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the app:

```powershell
.venv\Scripts\python.exe app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Chores & Jobs

The template starts with example chores such as cleaning a room, taking out trash, and cleaning the kitchen, plus larger jobs such as washing a car, bathing a dog, gardening, and yard work.

A kid marks a task complete, Parent Mode reviews it, and approval adds the reward to that kid's checking account.

All task names, rewards, assignments, and descriptions can be edited from Parent Mode.

## Store

Parent Mode can:

- add store items
- edit names, icons, and prices
- hide/show items
- delete items

Purchases come from the selected kid's checking account.

## NFC

The app stores an NFC UID for each kid account and includes a `/tap?uid=...` route.

The intended setup is a USB NFC reader plus your own NFC cards/tags. The balance remains in the SQLite database; the NFC card acts only as an identifier.

Do not use this project to copy, emulate, or store real payment-card credentials.

## Data privacy

`family_bank.db` is intentionally ignored by Git.

That keeps real family names, balances, transaction history, task history, and NFC UIDs out of a public repository.

If you make a backup, keep the database file private.

## Local-network use

By default the app runs with Flask on your computer. Other devices on the same trusted home network can connect using the computer's local IPv4 address while the Flask server is running.

Do not expose the Flask development server directly to the public internet.

## Upload to GitHub

Create a new empty GitHub repository, then from this project folder run:

```powershell
git init
git add .
git commit -m "Initial family bank template"
git branch -M main
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin main
```

Because `.gitignore` excludes `family_bank.db`, your family's local data should not be included.

## License

MIT License. See `LICENSE`.
