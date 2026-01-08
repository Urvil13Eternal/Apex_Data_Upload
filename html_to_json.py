#!/usr/bin/env python3
"""
HTML Table Parser using BeautifulSoup4
Extracts table data from HTML files and returns structured JSON format.
"""

from bs4 import BeautifulSoup
import json
import sys
from pathlib import Path


def parse_html_table(html_content):
    """
    Parse HTML content and extract table data.
    
    Args:
        html_content: HTML content as string or file path
        
    Returns:
        dict: Structured data containing table information
    """
    # If html_content is a file path, read the file
    # Check if it's HTML content (contains HTML tags) or a file path
    if isinstance(html_content, (str, Path)):
        # Check if it looks like HTML content (contains HTML tags)
        html_str = str(html_content)
        is_html_content = any(tag in html_str.lower() for tag in ['<html', '<table', '<!doctype', '<head', '<body'])
        
        # If it doesn't look like HTML and might be a file path, try to read it
        if not is_html_content:
            try:
                path = Path(html_content)
                if path.exists() and path.is_file():
                    with open(html_content, 'r', encoding='utf-8') as f:
                        html_content = f.read()
            except (OSError, ValueError):
                # If path is invalid or too long, treat as HTML content
                pass
    
    # Parse HTML with BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find all tables in the HTML
    tables = soup.find_all('table')
    
    if not tables:
        return {
            "error": "No tables found in HTML",
            "data": []
        }
    
    result = {
        "tables": []
    }
    
    # Process each table
    for table_idx, table in enumerate(tables):
        table_data = {
            "table_index": table_idx + 1,
            "headers": [],
            "rows": []
        }
        
        # Extract headers from thead or first row
        thead = table.find('thead')
        if thead:
            header_row = thead.find('tr')
            if header_row:
                headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
                table_data["headers"] = headers
        
        # If no thead, try to get headers from first row in tbody
        if not table_data["headers"]:
            tbody = table.find('tbody')
            if tbody:
                first_row = tbody.find('tr')
                if first_row:
                    headers = [th.get_text(strip=True) for th in first_row.find_all(['th', 'td'])]
                    table_data["headers"] = headers
        
        # Extract rows from tbody
        tbody = table.find('tbody')
        if tbody:
            rows = tbody.find_all('tr')
        else:
            # If no tbody, get all rows except header row
            rows = table.find_all('tr')[1:] if table_data["headers"] else table.find_all('tr')
        
        # Process each row
        for row in rows:
            cells = row.find_all(['td', 'th'])
            row_data = {}
            
            # Create dictionary with headers as keys
            for idx, cell in enumerate(cells):
                cell_text = cell.get_text(strip=True)
                if table_data["headers"] and idx < len(table_data["headers"]):
                    header = table_data["headers"][idx]
                    row_data[header] = cell_text
                else:
                    # If no headers or more cells than headers, use index
                    row_data[f"column_{idx + 1}"] = cell_text
            
            # Only add row if it has data (not all empty)
            if any(value for value in row_data.values()):
                table_data["rows"].append(row_data)
        
        result["tables"].append(table_data)
    
    return result


def extract_boq_data(html_content):
    """
    Extract BOQ (Bill of Quantities) data specifically.
    Returns a simplified structure focused on BOQ items.
    
    Args:
        html_content: HTML content as string or file path
        
    Returns:
        dict: BOQ data in structured format
    """
    parsed_data = parse_html_table(html_content)
    
    if "error" in parsed_data:
        return parsed_data
    
    # Extract the first table (assuming BOQ is in the first table)
    if parsed_data["tables"]:
        table = parsed_data["tables"][0]
        
        # Filter out summary rows (like "Total in Figures", "Quoted Rate", etc.)
        boq_items = []
        summary_data = {}
        
        for row in table["rows"]:
            # Check if this is a summary row
            first_col = list(row.values())[0] if row else ""
            if isinstance(first_col, str):
                first_col_lower = first_col.lower()
                if any(keyword in first_col_lower for keyword in ["total", "quoted rate", "grand total"]):
                    # Store summary information
                    summary_data[first_col] = row
                else:
                    # Regular BOQ item
                    boq_items.append(row)
        
        return {
            "boq_items": boq_items,
            "summary": summary_data,
            "total_items": len(boq_items)
        }
    
    return {"error": "No data extracted", "boq_items": []}



if __name__ == "__main__":

    html_file = "boq_html_data/2025_RDPR_297191_23.html"
    boq_data = extract_boq_data(html_file)
    print(boq_data)