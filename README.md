# Talbeena – Pure Barley Wellness

A modern, fast, and modular e-commerce engine built with Python (Flask) and SQLite. This backend has been meticulously designed to provide a completely generic, robust e-commerce structure alongside a beautiful, Next.js-inspired Admin Dashboard.

## Features

- **Generic E-commerce Core**: Support for Categories, Brands, Products, Variations (SKUs), and a dynamic Attribute system (e.g., Size, Flavor, Weight) that can be managed entirely from the Admin interface.
- **Modern Admin Dashboard**: A premium, responsive interface to manage Orders, Customers, Products, Reviews, Coupons, and Store Settings.
- **Cart & Checkout Engine**: Full cart management with session persistence, coupon logic, and checkout flows.
- **User Authentication**: Secure user registration, login, and profile management with distinct roles (`admin`, `customer`).
- **Cloudinary Integration**: Built-in support for uploading and serving optimized product imagery via Cloudinary.
- **Zero-Configuration Database**: Uses SQLite for an immediate, portable setup. Database tables and schema migrations are handled automatically.

## Technology Stack

- **Backend**: Python 3, Flask, SQLite3
- **Frontend**: HTML5, Jinja2 Templating, Vanilla CSS (Flexbox/Grid)
- **Security**: WTForms (CSRF Protection), Flask-Limiter, bcrypt

## Project Structure

```text
Talbeena/
├── apps/
│   ├── app.py             # Flask application factory
│   ├── db.py              # SQLite connection and automatic schema migrations
│   ├── helpers.py         # Utilities (Slugification, Cloudinary uploads, HTML parsing)
│   ├── routes/            # Blueprint routing (auth, admin, public, cart, checkout)
│   ├── static/            # Static assets (css/Talbeena.css, css/admin.css)
│   └── templates/         # Jinja2 templates (admin UI, storefront, errors)
│       ├── admin/         # Admin Dashboard views
│       ├── partials/      # Reusable UI components (_navbar, _footer)
│       └── ...            # User-facing pages (index, login, register, etc.)
├── seed_admin.py          # CLI script to easily create or promote an admin account
└── requirements.txt       # Python dependencies
```

## Setup & Installation

### 1. Environment Preparation
Ensure you have Python installed. It is highly recommended to use a virtual environment.
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 2. Install Dependencies
```bash
cd apps
pip install -r requirements.txt
```

### 3. Environment Variables
In the `apps/` directory, create a `.env` file containing your secret keys and Cloudinary configuration:
```env
SECRET_KEY=your_secure_secret_key_here
PORT=5001
FLASK_ENV=development

# Cloudinary Configuration (Format: cloudinary://API_KEY:API_SECRET@CLOUD_NAME)
CLOUDINARY_URL=cloudinary://your_api_key:your_api_secret@your_cloud_name
```

### 4. Start the Application
Run the Flask application. Upon the first run, the system will automatically create `apps/talbeena.db` and run all necessary database migrations.
```bash
cd apps
python app.py
```
The storefront will be available at `http://127.0.0.1:5001`.

### 5. Create an Admin Account
To access the Admin Dashboard, you need an account with the `admin` role. Open a new terminal (with your virtual environment active) and run the provided seed script from the root directory:
```bash
python seed_admin.py
```
Follow the prompts to create your admin credentials. Once created, visit `http://127.0.0.1:5001/login` and log in to be automatically redirected to the dashboard.

## Frontend Customization
The storefront interface is built heavily relying on Jinja2 inheritance. 
- **Global Styles**: Typography, CSS variables, and layout resets are defined in `apps/static/css/Talbeena.css`.
- **Base Layout**: `apps/templates/user_base.html` serves as the master template. All new user-facing pages should begin with `{% extends 'user_base.html' %}`.

## Database Management
The application is designed to be highly resilient. If you ever need to completely wipe the store and start fresh:
1. Stop the Flask server.
2. Delete the `apps/talbeena.db` file.
3. Restart the Flask server. A brand new, clean database with the full schema will be regenerated instantly.
