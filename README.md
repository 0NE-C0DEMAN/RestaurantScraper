# Restaurant Menu Scraper

A Python scraper to extract menu items (name, description, price) from restaurant websites. Handles HTML, PDF, and image-based menus using multiple extraction methods.

## Project Status

**Total Restaurants:** 120  
**Completed:** 106 (88.3%)  
**Remaining:** 14 (11.7%)

- ✅ **DONE:** 106 restaurants
- ⚠️ **NO MENU:** 6 restaurants
- ❌ **SITE UNAVAILABLE:** 7 restaurants
- 🚫 **SPAM:** 1 restaurant

See `scraping_summary.txt` for detailed statistics.

## Features

- Scrapes menu items from restaurant websites
- Extracts: item name, description, and price
- Associates each item with its restaurant
- Handles HTML, PDF, and image-based menus
- Supports multiple extraction methods (Gemini, PDF Plumber, HTML Parsing)
- Outputs to JSON format
- Handles multi-price, multi-size, and add-ons

## Requirements

- Python 3.8+
- Playwright browser automation (for dynamic content)
- Google Gemini API key (for PDF/image extraction)
- PDF processing libraries (pdf2image, pdfplumber)
- BeautifulSoup4 (for HTML parsing)

## Installation

1. Create a virtual environment:
```bash
python -m venv .venv
```

2. Activate the virtual environment:
   - **Windows (PowerShell):**
     ```bash
     .venv\Scripts\Activate.ps1
     ```
   - **Windows (Command Prompt):**
     ```bash
     .venv\Scripts\activate.bat
     ```
   - **macOS/Linux:**
     ```bash
     source .venv/bin/activate
     ```

3. Install `uv` (fast Python package installer):
```bash
pip install uv
```

4. Install project dependencies using `uv`:
```bash
uv pip install -r requirements.txt
```

5. Install Playwright browsers:
```bash
playwright install chromium
```

6. **Configure API Key:**
   - Copy `config.json.example` to `config.json` (if example exists) or create `config.json`
   - Open `config.json` and replace `YOUR_GEMINI_API_KEY` with your actual Google Gemini API key:
   ```json
   {
     "gemini_api_key": "YOUR_ACTUAL_GEMINI_API_KEY_HERE"
   }
   ```
   - **Important:** You must update `config.json` with your own Gemini API key before running scrapers that use Gemini Vision API
   - Get your API key from: https://makersuite.google.com/app/apikey

## Usage

### Scrape Individual Restaurant

Each restaurant has its own dedicated scraper file in the `scrapers/` directory. For example:

```bash
python scrapers/15churchrestaurant_com.py
```

The scraper will:
- Access the restaurant website (using requests or Playwright)
- Download menu files (PDFs, images, or HTML)
- Extract menu items using the appropriate method
- Save all items to a single JSON file in the `output/` directory

Each scraper automatically selects the best extraction method based on the menu format.

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

## Scraping Methods

The project uses three main extraction methods, selected based on the menu format:

### 1. Gemini Vision API (PDF/Image Extraction)

**When to use:**
- Menu is in PDF format (especially scanned/image-based PDFs)
- Menu is embedded as images
- Complex layouts that HTML parsing struggles with
- Multi-column layouts, handwritten menus, scanned documents

**How it works:**
- PDFs are converted to images using `pdf2image`
- Images are sent to Google Gemini Vision API
- Gemini extracts structured menu data (name, description, price, section)
- Handles complex formatting, multi-price items, and add-ons

**Examples:**
- `mazzonehospitality_com.py` - Multiple PDF menus from Issuu
- `saratoga_city_tavern_com.py` - PDF menu
- `kingstavern_ca.py` - Multiple PDF menus
- `scottystruckstop_com.py` - PDF menu
- `villagepizzeria_com.py` - Wine menu PDF, kids menu images
- `holidayinn_com.py` - PDF menu from hotel website

**Configuration:**
- Requires `GEMINI_API_KEY` in `config.json`
- Includes 5-second delays between API calls to respect rate limits

### 2. PDF Plumber (Structured PDF Extraction)

**When to use:**
- PDF has selectable text (not scanned images)
- PDF has consistent structure
- Text can be extracted programmatically
- Faster than Gemini for simple, well-structured PDFs

**How it works:**
- Uses `pdfplumber` to extract text directly from PDF
- Parses structured text to identify menu items
- Extracts prices, descriptions, and sections

**Examples:**
- `15churchrestaurant_com.py`
- `amigoscantina_net.py`
- `baileyscafe_com.py`
- `beneluxny_com.py`
- `saratogabreadbasket_com.py`

### 3. HTML Parsing (BeautifulSoup)

**When to use:**
- Menu is embedded in HTML
- Menu is available via API (JSON/XML)
- Simple structured HTML menus
- Menu data is in the page source

**How it works:**
- Uses `requests` to fetch HTML
- Parses HTML with `BeautifulSoup`
- Extracts menu items using CSS selectors or XPath
- Handles multiple pages, locations, and menu types

**Examples:**
- `thegalwaylocalny_com.py` - Multiple HTML pages (breakfast, lunch, drink, dessert)
- `wheatfields_com.py` - Multiple locations
- `uncommongrounds_com.py` - Multiple locations
- `westavepizza_com.py` - JSON API
- `villagepizzeria_com.py` - Main menu HTML
- `wishingwellrestaurant_com.py` - Wine, cocktails, specials HTML

### 4. Playwright (Browser Automation)

**When to use:**
- Content requires JavaScript to load
- Cloudflare or bot protection
- Dynamic content loading
- Need to interact with page (click buttons, download PDFs)
- Content is loaded asynchronously

**How it works:**
- Launches headless browser (Chromium)
- Waits for JavaScript to render content
- Can interact with page elements (click, fill forms)
- Bypasses Cloudflare challenges
- Downloads PDFs from protected sources (e.g., Issuu)

**Examples:**
- `thecoatroom_com.py` - Cloudflare-protected SpotOn ordering page
- `550waterfrontbydruthers_com.py` - Dynamic content loading
- `mazzonehospitality_com.py` - Downloads PDFs from Issuu
- `villagepizzeria_com.py` - Main menu page with dynamic loading

**Configuration:**
- Runs in headless mode by default
- Can switch to headful mode for debugging
- Handles cookies and session management

## Method Selection Guide

| Menu Format | Recommended Method |
|------------|-------------------|
| PDF (scanned/image) | Gemini Vision API |
| PDF (text-based, structured) | PDF Plumber |
| PDF (text-based, complex) | Gemini Vision API |
| HTML (static) | BeautifulSoup |
| HTML (dynamic/JavaScript) | Playwright + BeautifulSoup |
| Images | Gemini Vision API |
| JSON API | requests + json parsing |
| Cloudflare protected | Playwright (headless or headful) |

## Notes

- Each restaurant scraper is self-contained in a single file
- Some scrapers use multiple methods (e.g., HTML parsing + Gemini for PDFs)
- All scrapers handle multi-price, multi-size, and add-ons
- Each menu item includes: `name`, `description`, `price`, `restaurant_name`, `restaurant_url`, and optionally `menu_name`, `section`, `location`
- Output files are named based on the restaurant domain (e.g., `villagepizzeria_com.json`)

## Configuration

### API Key Setup

**IMPORTANT:** Before running any scrapers that use Gemini Vision API, you must configure your API key.

1. Create or edit `config.json` in the project root directory
2. Add your Google Gemini API key:
   ```json
   {
     "gemini_api_key": "YOUR_ACTUAL_GEMINI_API_KEY_HERE"
   }
   ```
3. Replace `YOUR_ACTUAL_GEMINI_API_KEY_HERE` with your actual API key
4. Get your API key from: https://makersuite.google.com/app/apikey

**Note:** Without a valid API key, scrapers that use Gemini Vision API (for PDF/image extraction) will fail. HTML parsing and PDF Plumber scrapers do not require the API key.

## Troubleshooting

If a restaurant fails to scrape:

1. **Check the console output** for error messages
2. **Gemini API issues:**
   - Ensure Gemini API key is set correctly in `config.json`
   - Check API rate limits (5-second delays are included)
   - Verify PDF/image is accessible
3. **PDF issues:**
   - PDF must be accessible via direct URL
   - For protected PDFs, use Playwright to download first
   - Scanned PDFs require Gemini, not PDF Plumber
4. **HTML/JavaScript issues:**
   - Some restaurants require JavaScript - use Playwright
   - Cloudflare protection requires Playwright (may need headful mode)
   - Check if menu is loaded dynamically
5. **Network issues:**
   - Some sites may block automated requests
   - Use Playwright with proper headers and user agent
   - Check for cookie requirements

