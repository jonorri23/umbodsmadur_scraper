#!/usr/bin/env python3
"""
Umboðsmaður Alþingis Scraper (Loop Edition)
Fast, robust, and modern async scraper that iterates through case IDs directly.
"""

import asyncio
import json
import re
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import httpx
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID

# Configuration
BASE_URL = "https://www.umbodsmadur.is/alit-og-bref/mal/nr/{id}/skoda/mal/"
OUTPUT_DIR = Path("output")
CONCURRENCY_LIMIT = 10  # Moderate concurrency to be respectful
MAX_RETRIES = 3

console = Console()

class Scraper:
    def __init__(self, start_id: int, count: int, output_file: str):
        self.start_id = start_id
        self.count = count # How many valid cases to try to find, or just ID range
        self.output_file = output_file
        self.results: List[Dict[str, Any]] = []
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Umbodsmadur Scraper/1.0"}
        )
        self.semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async def close(self):
        await self.client.aclose()

    def clean_text(self, text: Optional[str]) -> str:
        """Strip whitespace and normalize text."""
        if not text:
            return ""
        return " ".join(text.split())

    def extract_id_year(self, h4_text: str) -> str:
        """
        Extracts 'Number/Year' from string like '(Mál nr. F143/2023)'
        Returns 'F143/2023'
        """
        # Regex to match content inside parentheses after "Mál nr. " or just the number pattern
        # Look for pattern: <Something>/<Year>
        match = re.search(r'Mál nr\. (.+?)\)', h4_text)
        if match:
            return match.group(1).strip()
        
        # Fallback: simple slash search
        match_simple = re.search(r'([\w\d]+/\d{4})', h4_text)
        if match_simple:
            return match_simple.group(1)
            
        return "Unknown"

    async def scrape_id(self, case_id: int, progress: Progress, task_id: TaskID) -> Optional[Dict]:
        url = BASE_URL.format(id=case_id)
        
        async with self.semaphore:
            for attempt in range(MAX_RETRIES):
                try:
                    response = await self.client.get(url)
                    
                    if response.status_code == 404:
                        # Case does not exist (gap or end of list)
                        return None
                    
                    if response.status_code != 200:
                        if attempt == MAX_RETRIES - 1:
                            console.print(f"[red]Failed {case_id}: Status {response.status_code}[/red]")
                        await asyncio.sleep(1)
                        continue

                    # Parse HTML
                    soup = BeautifulSoup(response.text, "html.parser")
                    
                    # 1. Type
                    type_el = soup.select_one(".page-header h1")
                    case_type = self.clean_text(type_el.get_text()) if type_el else "Unknown"
                    if case_type not in ["Álit", "Bréf"]:
                        # Might be some other page type, skip if strict
                        pass

                    # 2. Case ID / Year
                    h4_el = soup.select_one("section.case h4")
                    h4_text = self.clean_text(h4_el.get_text()) if h4_el else ""
                    id_year = self.extract_id_year(h4_text)
                    
                    # 3. Formatted Title: [Type] UA [Number]/[Year]
                    formatted_title = f"{case_type} UA {id_year}"

                    # 4. Abstract (.reifun)
                    abstract_div = soup.select_one(".reifun")
                    abstract = ""
                    if abstract_div:
                        paras = [self.clean_text(p.get_text()) for p in abstract_div.find_all("p")]
                        abstract = "\n\n".join(filter(None, paras))

                    # 5. Body (.alit) OR Fallback to .div.alit if empty?
                    # Note: Sample HTML had .alit empty but content in .reifun? 
                    # Actually standard cases have body in .alit.
                    # The user assignment says: "The Abstract... usually found at the top... The Body... main content"
                    # In sample 11110: .reifun has content. .alit has content.
                    
                    body_div = soup.select_one(".alit")
                    content_list = []
                    
                    if body_div:
                        # Extract paragraphs with index
                        paras = body_div.find_all("p")
                        idx = 0
                        for p in paras:
                            txt = self.clean_text(p.get_text())
                            if txt:
                                content_list.append({
                                    "index": idx,
                                    "paragraphText": txt
                                })
                                idx += 1
                                
                    # Structure Output
                    item = {
                        "title": formatted_title,
                        "originalUrl": url,
                        "type": case_type,
                        "abstract": abstract,
                        "content": content_list
                    }
                    
                    progress.advance(task_id)
                    return item

                except Exception as e:
                    if attempt == MAX_RETRIES - 1:
                         console.print(f"[red]Error scraping {case_id}: {e}[/red]")
                    await asyncio.sleep(1)
            
            return None

    async def run(self):
        # Determine range (User wanted ~20 cases for testing)
        # We start from start_id and go DOWN.
        # Ideally we want valid cases. 
        
        # We process in batches to allow progress updates
        BATCH_SIZE = 50
        current_id = self.start_id
        valid_cases_found = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed} found"),
        ) as progress:
            task = progress.add_task("[cyan]Scraping cases...", total=None)
            
            while valid_cases_found < self.count:
                # Create batch of tasks
                tasks = []
                # Simple strategy: try next N IDs downwards
                ids_to_try = range(current_id, current_id - BATCH_SIZE, -1)
                current_id -= BATCH_SIZE
                
                if current_id < 0:
                    break

                for i in ids_to_try:
                    tasks.append(self.scrape_id(i, progress, task))
                
                batch_results = await asyncio.gather(*tasks)
                
                for res in batch_results:
                    if res:
                        self.results.append(res)
                        valid_cases_found += 1
                        
                if valid_cases_found >= self.count:
                    break

        # Save results
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
            
        console.print(f"[green]✅ Successfully scraped {len(self.results)} cases to {self.output_file}[/green]")

async def main():
    parser = argparse.ArgumentParser(description="Clean Async Scraper")
    parser.add_argument("--start-id", type=int, default=11150, help="ID to start scanning backwards from")
    parser.add_argument("--count", type=int, default=20, help="Number of valid cases to find")
    parser.add_argument("--output", type=str, default="output/cases.json")
    
    args = parser.parse_args()
    
    scraper = Scraper(args.start_id, args.count, args.output)
    try:
        await scraper.run()
    finally:
        await scraper.close()

if __name__ == "__main__":
    asyncio.run(main())
