# Restaurant Menu Scraper

A Python scraper to extract menu items (name, description, price) from restaurant websites. Handles both HTML and PDF menus.

## Features

- Scrapes menu items from restaurant websites
- Extracts: item name, description, and price
- Associates each item with its restaurant
- Handles both HTML and PDF menus
- Outputs to JSON and CSV formats
- Supports 135+ restaurant URLs

## Requirements

- Python 3.8+
- Playwright browser automation
- PDF processing libraries

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Install Playwright browsers:
```bash
playwright install chromium
```

## Usage

### Scrape Individual Restaurant

Each restaurant has its own dedicated scraper file in the `scrapers/` directory. For example:

```bash
python scrapers/15churchrestaurant_com.py
```

The scraper will:
- Find all menu PDFs on the website
- Download each PDF using requests
- Extract menu items using Gemini Vision API
- Save all items to a single JSON file in the `output/` directory

## Output Files

- `output/www_15churchrestaurant_com_.json` - Menu items in JSON format (filename based on restaurant URL)

## CSV Format

The output CSV contains the following columns:
- `restaurant_name` - Name of the restaurant
- `restaurant_url` - URL of the restaurant website
- `name` - Menu item name
- `description` - Menu item description
- `price` - Menu item price

## JSON Format

The JSON output is an array of menu items, each with:
```json
{
  "restaurant_name": "Restaurant Name",
  "restaurant_url": "https://example.com",
  "name": "Menu Item Name",
  "description": "Item description",
  "price": "$12.99"
}
```

## Notes

- Each restaurant scraper is self-contained in a single file
- Uses requests library for reliable PDF downloads with retries
- Uses Gemini Vision API for accurate menu extraction from PDFs
- Automatically finds and processes all available menus on the website
- Each menu item includes: name, description, price, restaurant_name, restaurant_url, and menu_type

## Troubleshooting

If a restaurant fails to scrape:
1. Check the console output for error messages
2. Ensure Gemini API key is set correctly in the scraper file
3. PDF menus require the PDF to be accessible via direct URL
4. Some restaurants may require JavaScript to load menu links - Playwright handles this

