# Archive Folder

This folder contains test/comparison scripts and alternative scraper implementations that were used during development but are no longer needed for production.

## Files

- **30parkcp_com_gemini.py** - Initial attempt to use Gemini Vision API with screenshots (had connection issues)
- **30parkcp_com_gemini_html.py** - Alternative scraper using Gemini Text API with HTML as markdown input (for comparison)
- **check_prices.py** - Script to verify and compare prices between BeautifulSoup and Gemini scrapers
- **compare_scrapers.py** - Script to compare output from BeautifulSoup and Gemini HTML scrapers

## Note

The final production scraper is `scrapers/30parkcp_com.py` which uses BeautifulSoup and extracts all menu items correctly.

