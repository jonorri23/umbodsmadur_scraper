#!/usr/bin/env python3
"""
Umboðsmaður Alþingis Scraper (Loop Edition)
Fast, robust, and modern async scraper that iterates through case IDs directly.
"""

import asyncio
import json
import re
import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import httpx
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID
from supabase import create_client, Client

# --- Supabase Configuration ---
SUPABASE_URL = "https://bvxgxpququhxrnrzcjcb.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ2eGd4cHF1cXVoeHJucnpjamNiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njg4MjYyNzUsImV4cCI6MjA4NDQwMjI3NX0.3tIBAVfhBz2_ZiwRP5D_rcUKjibcKMrW9OkA_QBNzsM"

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
            timeout=10.0, # Changed from 30.0
            follow_redirects=True,
            headers={"User-Agent": "Umbodsmadur Scraper/1.0"}
        )
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.console = Console()
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
                    # Extract case_number and year from id_year (e.g., "F143/2023")
                    case_number_match = re.match(r'(.+)/(\d{4})', id_year)
                    case_number = case_number_match.group(1) if case_number_match else id_year
                    year = int(case_number_match.group(2)) if case_number_match else None

                    full_text = f"{formatted_title}\n\n{abstract}\n\n" + "\n".join(p['paragraphText'] for p in content_list)

                    case_data = {
                        "case_number": case_number,
                        "year": year,
                        "title": formatted_title,
                        "type": case_type,
                        "original_url": url,
                        "abstract": abstract.strip(),
                        "content": content_list,
                        "full_text": full_text
                    }
                    
                    progress.advance(task_id)
                    return case_data

                except Exception as e:
                    if attempt == MAX_RETRIES - 1:
                         console.print(f"[red]Error scraping {case_id}: {e}[/red]")
                    await asyncio.sleep(1)
            
            return None

    async def save_to_supabase(self, cases: List[Dict]):
        if not cases:
            return
        
        try:
            # Prepare data for Supabase (matching schema keys)
            # Our case_data keys already match the SQL schema columns
            response = self.supabase.table("cases").upsert(cases, on_conflict="case_number").execute()
            self.console.print(f"[green]Successfully synced {len(cases)} cases to Supabase.[/green]")
        except Exception as e:
            self.console.print(f"[bold red]Supabase Sync Error:[/bold red] {e}")

    async def run(self):
        """Main execution loop."""
        self.console.print(f"[bold blue]Starting scraper from ID {self.start_id} looking for {self.count} cases...[/bold blue]")

        found_cases = []
        # Create a range of IDs to scan. 
        # We'll generate batches of IDs to scan in parallel.
        # We allow scanning significantly more IDs than 'count' because of gaps.
        
        # Generator for IDs downwards
        current_id = self.start_id
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed} found"),
        ) as progress:
            task = progress.add_task("[cyan]Scraping cases...", total=None)
            
            while len(found_cases) < self.count:
                # Create a batch of IDs
                # Simple strategy: try next N IDs downwards
                BATCH_SIZE = 50 # Using the existing BATCH_SIZE from original code
                ids_to_try = range(current_id, current_id - BATCH_SIZE, -1)
                current_id -= BATCH_SIZE
                
                if current_id < 0:
                    break

                # Create tasks
                tasks = [self.scrape_id(cid, progress, task) for cid in ids_to_try]
                results = await asyncio.gather(*tasks)
                
                # Filter valid results
                valid_results = [r for r in results if r is not None]
                
                if valid_results:
                    found_cases.extend(valid_results)
                    progress.update(task, completed=len(found_cases))
                    
                    # Sync batch to Supabase immediately (optional, but good for progress)
                    await self.save_to_supabase(valid_results)

                # Safety break if we go too far back (just to prevent infinite loops in dev)
                if current_id < 0:
                    break

        # Trim to requested count
        found_cases = found_cases[:self.count]
        
        # Save to JSON
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(found_cases, f, ensure_ascii=False, indent=2)
            
        self.console.print(f"[bold green]Done! Found {len(found_cases)} cases. Saved to {self.output_file}[/bold green]")

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
