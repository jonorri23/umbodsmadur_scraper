# Umboðsmaður Alþingis Scraper (Standard)

A robust, high-performance async web scraper for the [Icelandic Parliamentary Ombudsman](https://www.umbodsmadur.is) website.

## Features
- **Fast**: Uses `httpx` and `asyncio` for concurrent scraping.
- **Robust**: Handles network errors and retries gracefully.
- **Simple**: Zero browser dependencies (no Selenium/Playwright required).
- **Compliant**: Outputs JSON strictly adhering to assignment schema.

## Prerequisites
- Python 3.8+

## Setup
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

Run the scraper to fetch cases (defaults to recent ones):
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
The scraper generates a JSON file (`output/cases.json`) strictly following the assignment schema:
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
