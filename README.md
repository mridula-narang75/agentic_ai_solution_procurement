# Procurement Agent System

An AI-powered, multi-agent procurement automation system built with **Google ADK (Agent Development Kit)**. It automates the full procurement lifecycle — from sourcing suppliers, to collecting quotes, to negotiating and awarding a contract — with minimal human input.

## What This Project Does

You tell the system what you want to buy (category, quantity, and how fast you need it), and it does the rest automatically:

1. **Buyer Agent** — Asks you for your requirement and shows you a comparison of 5 suppliers based on real historical performance data (price, speed, quality, etc.), then publishes the request.
2. **Supplier Agent** — Automatically reaches out to the top 3 suppliers and collects price quotes.
3. **Negotiation Agent** — Compares the 3 quotes, negotiates one round of counter-offers if needed, and picks a winner.
4. **Final Award** — You get a full procurement award document showing who won, the final price, and the delivery terms.

No back-and-forth needed after you submit your request — the agents handle sourcing, quoting, and negotiating on their own.

## How It Works (Architecture)

- **Framework:** Google ADK
- **Language:** Python 3.12+
- **AI Model:** Google Gemini 2.5 Flash Lite
- **Database:** SQLite (3 local database files, included in the project)
- **Data:** Historical supplier performance data + negotiation rules per product category

The system covers 5 product categories: Electronics, MRO, Office Supplies, Raw Materials, and Packaging.

## Project Structure

```
procurement_agent/
├── buyer_agent/          # Collects your request, shows supplier comparison
├── supplier_agent/       # Contacts suppliers, collects quotes
├── negotiation_agent/    # Negotiates and issues the final award
├── data/
│   ├── negotiation.db    # Negotiation rules per category
│   ├── suppliers.db      # Supplier catalog and capacity info
│   └── procurement.db    # Historical order data (used for KPI scoring)
├── .env                  # Your API keys go here (see below)
└── requirements.txt      # Python packages needed to run the project
```

---

## How to Run This Project 

### Step 1: Install Python

You need Python 3.12 or newer installed on your computer.

- Go to [python.org/downloads](https://www.python.org/downloads/)
- Download and install the latest version
- **Important (Windows users):** during installation, check the box that says "Add Python to PATH" before clicking Install

To check it worked, open a terminal (on Mac: **Terminal** app, on Windows: **Command Prompt**) and type:

```
python --version
```

You should see something like `Python 3.12.x`.

### Step 2: Download This Project

If you have the project as a ZIP file, unzip it anywhere on your computer (e.g., your Desktop).

If you're getting it from GitHub instead, click the green **Code** button on the repository page, choose **Download ZIP**, and unzip it.

### Step 3: Open a Terminal in the Project Folder

- **Mac:** Right-click the project folder → "New Terminal at Folder" (or open Terminal and type `cd` followed by a space, then drag the folder into the window, then press Enter)
- **Windows:** Open the project folder in File Explorer, click on the address bar, type `cmd`, and press Enter

### Step 4: Install the Required Packages

In the terminal, type this command and press Enter:

```
pip install -r requirements.txt
```

This installs everything the project needs to run. It may take a minute or two.

### Step 5: Get Your Google API Key

This project uses Google's Gemini AI model, so you need a free API key from Google:

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Sign in with your Google account
3. Click **Create API Key**
4. Copy the key that's generated (it's a long string of letters and numbers)

Create separate keys for each agent (recommended if you plan to use this a lot, since it avoids hitting usage limits).

### Step 6: Add Your API Key to the `.env` File

The project uses a file called `.env` to store your secret API key safely (this file is never shared or uploaded anywhere).

1. In the main project folder, find the file named `.env` (or create a new file named exactly `.env` if it doesn't exist)
2. Open it with any text editor (Notepad on Windows, TextEdit on Mac)
3. Paste in the following, replacing `your_key_here` with the key you copied in Step 5:

```env
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=your_key_here

BUYER_AGENT_API_KEY=your_key_here
SUPPLIER_AGENT_API_KEY=your_key_here
NEGOTIATION_AGENT_API_KEY=your_key_here
```

4. Save the file. Make sure it's named exactly `.env` (not `.env.txt`).

> **Note:** If you're running an individual agent on its own (for example, just the negotiation agent), that agent's folder may need its own `.env` file with just `GOOGLE_API_KEY` and that agent's specific key.

### Step 7: Run the Project

In the same terminal window, type:

```
adk web
```

This starts the system and opens a chat interface in your web browser (usually at `http://localhost:8000`). From there, select the agent you want to start with (typically the **Buyer Agent** or the **Coordinator Agent**) and start chatting — for example:

```
I need 500 units of Electronics delivered within 10 days
```

The system will take it from there: showing you supplier options, collecting quotes, negotiating, and giving you a final award.

### Step 8: Stopping the Project

When you're done, go back to the terminal window and press `Ctrl + C` (Windows/Linux) or `Cmd + C` (Mac) to stop it.

---

## Troubleshooting

- **"command not found: python"** → Python isn't installed correctly, or wasn't added to PATH. Reinstall and make sure to check that box during setup.
- **"command not found: adk"** → Run `pip install google-adk` manually, then try again.
- **API errors / "invalid API key"** → Double check you copied the full key into the `.env` file with no extra spaces, and that the file is named exactly `.env`.
- **Nothing happens in the browser** → Check the terminal for a URL (usually `http://localhost:8000`) and open it manually.

---

## How the System Makes Decisions

### Choosing a Supplier (Sourcing Phase)
Each supplier is scored using historical data: **50% price, 30% delivery speed, 20% discount history.** The best-scoring supplier is recommended, but you can pick a different one if you prefer.

### Negotiating Quotes
Once 3 quotes are collected, each is scored on price, delivery, and quantity fulfilled. Based on the score:
- A great quote is **auto-awarded** immediately
- An overpriced quote may trigger a **walkaway** (rejecting all quotes)
- Otherwise, the system sends **one round of counter-offers** to try to get a better price before awarding

### Negotiation Rules by Category
Each product category (Electronics, MRO, Office Supplies, Raw Materials, Packaging) has its own target discount, acceptable price range, and scoring weights, since priorities differ (e.g., Electronics is more price-sensitive, Packaging is more delivery-sensitive).

---

## Key Design Decisions

- **One negotiation round only** — keeps the process fast and predictable
- **Fully autonomous between phases** — no manual approval needed once you submit your request
- **Top 3 suppliers contacted** — balances getting good options with not overwhelming suppliers
- **Separate API keys per agent** — prevents hitting Google's rate limits when multiple agents run at once

## Known Limitations

- Only one round of negotiation (by design)
- Always works with exactly 3 suppliers per request
- Limited to 5 predefined product categories
- Negotiation rules are fixed, not learned from outcomes over time

## Possible Future Improvements

- Support for multiple negotiation rounds
- Smarter, dynamic supplier selection
- Splitting large orders across multiple suppliers
- Learning better negotiation strategies from past outcomes over time

---

**System:** Google ADK Procurement Agent v2
