# Techno Vender

A virtual vending machine for our BMTA group project. Customers pick a product, choose a member and a saved payment method, and vend. Members get their plan's discount automatically. Payments are simulated: no real money moves and no real card numbers are stored.

Everything here is free. **If any website asks for a credit card or an upgrade, stop. You don't need one.**

## What's in this folder

| File | What it does | Where it goes |
|---|---|---|
| `schema.sql` | Creates the 5 tables, their rules, and sample data | Neon (paste into the SQL Editor) |
| `app.py` | The website's logic, with every database query written in plain SQL | GitHub |
| `templates/` | The pages: machine, purchases, members, payment methods | GitHub |
| `static/style.css` | The look of the site | GitHub |
| `requirements.txt` | The three Python packages Render installs | GitHub |
| `README.md` | This guide | GitHub |

## Setup: about 20 minutes, done by one group member

One person owns all three accounts. Render's free plan allows only one member per workspace, and inviting a second person costs money, so don't invite teammates on Render. Teammates join on GitHub instead, which is free.

### 1. GitHub: store the code

1. Create a free account at github.com.
2. Click **New repository**. Name it `techno-vender`. Private is fine. Click **Create repository**.
3. Click **uploading an existing file**.
4. Unzip `techno-vender.zip` on your computer. Open the `techno-vender` folder, select everything inside it (the files *and* the `templates` and `static` folders), and drag it onto the GitHub page. Don't drag the zip itself.
5. Click **Commit changes**.
6. Optional: under **Settings → Collaborators**, add your groupmates.

### 2. Neon: the database

1. Sign up at neon.com with **Continue with GitHub**.
2. Create a project named `techno-vender`. Pick the region closest to you.
3. Open the **SQL Editor**, paste the whole of `schema.sql`, and click **Run**. The last result should list the 5 tables with 3, 4, 5, 9 and 5 rows.
4. Click **Connect** on the project dashboard and copy the **connection string**. It starts with `postgresql://`. It contains your database password, so keep it private and never paste it into a chat or a file.

### 3. Render: the public website

1. Sign up at render.com with **GitHub**. Stay on the free **Hobby** workspace.
2. Click **New → Web Service** and pick your `techno-vender` repository. Allow Render to see it if asked.
3. Fill in:
   - **Language:** Python 3
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn app:app`
   - **Instance type:** Free
4. Under **Environment variables**, add two:
   - `DATABASE_URL`: paste the Neon connection string.
   - `SECRET_KEY`: click **Generate**.
5. Click **Deploy web service**. After a few minutes the page shows **Live** and a link like `https://techno-vender.onrender.com`. That's your public URL.

From now on, any change saved to GitHub redeploys the site automatically.

## Before you present or submit

- Both services sleep when no one uses them. Render takes up to a minute to wake up, so **open the site 2 minutes before your demo**.
- Add a line to your submission: "The site is on a free host and may take up to a minute to load the first time."
- To reset all data back to the samples, run `schema.sql` in Neon again. This erases everything else.
- To add or change products, use **Tables** in Neon and edit the `products` table directly.

## How the site follows the database rules

- **Vending** takes stock out of the machine and copies today's price and the member's discount into the purchase, so later price changes don't rewrite old receipts.
- **Editing a purchase** recalculates its total and moves stock in or out. Refunded and cancelled purchases don't hold stock.
- **Deleting a purchase** puts completed items back in the machine.
- **A member with purchases can't be deleted.** Set their status to Cancelled instead. A member without purchases is deleted along with their payment methods.
- **Deleting a payment method** keeps the purchases made with it. They show "Removed" in the Paid with column.
- **Each member has at most one default** payment method. Choosing a new default clears the old one.
