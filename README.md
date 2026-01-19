# Umboðsmaður Alþingis Scraper

A robust, high-performance async web scraper for the [Icelandic Parliamentary Ombudsman](https://www.umbodsmadur.is) website.

## Features
- **Fast**: Uses `httpx` and `asyncio` for concurrent scraping.
- **Robust**: Handles network errors and retries gracefully.
- **Simple**: Zero browser dependencies (no Selenium/Playwright required).
- **Output**: Clean, structured JSON with metadata, abstract, and indexed content.

## Prerequisites
- Python 3.8+

## Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/jonorri23/umbodsmadur_scraper.git
   cd umbodsmadur_scraper
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the scraper with default settings (scans backwards from ID 11150):
```bash
python scraper.py
```

### Options
| Flag | Description | Default |
|------|-------------|---------|
| `--start-id` | Internal ID to start scanning backwards from. | `11150` |
| `--count` | Number of valid cases to find. | `20` |
| `--output` | Output JSON file path. | `output/cases.json` |

### Example
Scrape 50 cases starting from ID 12000:
```bash
python scraper.py --start-id 12000 --count 50
```

## Output Format
The scraper generates a JSON file containing an array of case objects:
```json
[
  {
    "title": "Álit UA 123/2024",
    "originalUrl": "https://...",
    "type": "Álit",
    "abstract": "...",
    "content": [
      {
        "index": 0,
        "paragraphText": "..."
      }
    ]
  }
]
```
