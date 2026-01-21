"""
Combined script for mapping and storing tender data.
Processes tenders one at a time: maps each tender, then immediately stores it to the database.
This eliminates the need to wait for all mapping to complete before starting database insertion.
"""

import json
import os
import tempfile
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

# Import mapping functions from map_tender_data.py
from map_tender_data import (
    map_shubham_to_db,
    extract_tender_id,
    sanitize_tender_id_for_filename,
    is_valid_s3url,
    convert_date_format
)

# Import storing functions from zstore_new_tender.py
from zstore_new_tender import (
    store_single_tender_with_documents,
    send_tender_to_api,
    send_document_to_api
)

# Import PDF conversion function
from html_to_pdf import convert_html_to_pdf


def setup_logging(input_file: str) -> str:
    """
    Set up logging configuration with both file and console handlers.
    Suppresses WebDriver manager logs to keep logs clean.
    
    Args:
        input_file: Path to input JSON file (used for log filename)
        
    Returns:
        Path to the log file created
    """
    # Create logs directory if it doesn't exist
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    
    # Create log filename with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    input_filename = os.path.basename(input_file).replace(".json", "")
    log_filename = f"map_n_store_tender_{input_filename}_{timestamp}.log"
    log_file_path = os.path.join(logs_dir, log_filename)
    
    # Configure logging format
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.FileHandler(log_file_path, encoding='utf-8'),
            logging.StreamHandler()  # Also output to console
        ],
        force=True  # Override any existing logging configuration
    )
    
    # Suppress WebDriver manager logs (from pyhtml2pdf/Selenium)
    # These logs are verbose and not needed for our purposes
    webdriver_loggers = [
        'WDM',  # WebDriver Manager
        'selenium',
        'urllib3.connectionpool',
        'webdriver_manager'
    ]
    
    for logger_name in webdriver_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.WARNING)  # Only show warnings and errors, not INFO
        logger.propagate = False  # Prevent propagation to root logger
    
    return log_file_path


def detect_input_type(tender_data: Dict[str, Any]) -> str:
    """
    Detect if the tender data is a tender or corrigendum.
    Checks if Content1 field exists (corrigendum has it, tender doesn't).
    
    Args:
        tender_data: Single tender record dictionary
        
    Returns:
        "tender" or "corrigendum"
    """
    if "Content1" in tender_data and tender_data.get("Content1"):
        return "corrigendum"
    else:
        return "tender"


def convert_single_tender_content_to_pdf(tender_data: Dict[str, Any], input_type: str) -> bool:
    """
    Convert HTML content from a single tender to PDF file(s).
    For tender: Converts Content to PDF and saves in tender_content_pdf folder.
    For corrigendum: Converts Content and Content1 to PDF and saves in corrigendum_content_pdf folder.
    
    Args:
        tender_data: Single tender record dictionary
        input_type: "tender" or "corrigendum"
        
    Returns:
        bool: True if at least one PDF was created, False otherwise
    """
    tender_id = extract_tender_id(tender_data.get("TenderId"))
    if not tender_id:
        return False
    
    sanitized_tender_id = sanitize_tender_id_for_filename(tender_id)
    pdf_created = False
    
    try:
        if input_type == "tender":
            # For tender: Convert Content to PDF
            content = tender_data.get("Content")
            if content and content.strip():
                # Create tender_content_pdf directory if it doesn't exist
                if not os.path.exists("tender_content_pdf"):
                    os.makedirs("tender_content_pdf")
                
                # Create temporary HTML file
                with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_html:
                    temp_html.write(content)
                    temp_html_path = temp_html.name
                
                # Create PDF file path
                pdf_path = os.path.join("tender_content_pdf", f"{sanitized_tender_id}.pdf")
                
                # Convert HTML to PDF
                try:
                    convert_html_to_pdf(temp_html_path, pdf_path)
                    pdf_created = True
                except Exception as e:
                    error_msg = f"Error converting HTML to PDF for tender {tender_id}: {e}"
                    print(f"    ⚠ {error_msg}")
                    logging.warning(error_msg)
                finally:
                    # Clean up temporary HTML file
                    if os.path.exists(temp_html_path):
                        os.remove(temp_html_path)
        
        elif input_type == "corrigendum":
            # For corrigendum: Convert Content and Content1 to PDF
            # Create corrigendum_content_pdf directory if it doesn't exist
            if not os.path.exists("corrigendum_content_pdf"):
                os.makedirs("corrigendum_content_pdf")
            
            # Process Content (first PDF)
            content = tender_data.get("Content")
            if content and content.strip():
                try:
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_html:
                        temp_html.write(content)
                        temp_html_path = temp_html.name
                    
                    pdf_path = os.path.join("corrigendum_content_pdf", f"{sanitized_tender_id}_1.pdf")
                    convert_html_to_pdf(temp_html_path, pdf_path)
                    pdf_created = True
                    
                    if os.path.exists(temp_html_path):
                        os.remove(temp_html_path)
                except Exception as e:
                    error_msg = f"Error converting Content to PDF for corrigendum {tender_id}: {e}"
                    print(f"    ⚠ {error_msg}")
                    logging.warning(error_msg)
            
            # Process Content1 (second PDF)
            content1 = tender_data.get("Content1")
            if content1 and content1.strip():
                try:
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_html:
                        temp_html.write(content1)
                        temp_html_path = temp_html.name
                    
                    pdf_path = os.path.join("corrigendum_content_pdf", f"{sanitized_tender_id}_2.pdf")
                    convert_html_to_pdf(temp_html_path, pdf_path)
                    pdf_created = True
                    
                    if os.path.exists(temp_html_path):
                        os.remove(temp_html_path)
                except Exception as e:
                    error_msg = f"Error converting Content1 to PDF for corrigendum {tender_id}: {e}"
                    print(f"    ⚠ {error_msg}")
                    logging.warning(error_msg)
    
    except Exception as e:
        error_msg = f"Error processing PDF conversion for tender {tender_id}: {e}"
        print(f"    ⚠ {error_msg}")
        logging.warning(error_msg)
    
    return pdf_created


def map_documents_for_single_tender(tender_data: Dict[str, Any], input_type: str) -> List[Dict[str, Any]]:
    """
    Map documents for a single tender record.
    Processes TenderFileName_1 through TenderFileName_N fields and creates document records.
    Also handles NIT documents from Content/Content1 fields.
    
    Args:
        tender_data: Single tender record dictionary
        input_type: "tender" or "corrigendum"
        
    Returns:
        List of mapped document records
    """
    document_records = []
    
    try:
        # Extract tender ID
        tender_id = extract_tender_id(tender_data.get("TenderId"))
        if not tender_id:
            return document_records
        
        # Check all TenderFileName_{n} fields dynamically
        file_index = 1
        while True:
            field_name = f"TenderFileName_{file_index}"
            s3url = tender_data.get(field_name)
            
            # If field doesn't exist, we've reached the end
            if field_name not in tender_data:
                break
            
            # Check if the value is valid (non-empty)
            if is_valid_s3url(s3url):
                # Create document record
                document_record = {
                    "tenderid": tender_id,
                    "doctype": "Tender Documents",
                    "s3url": s3url.strip(),
                    "docname": "Tender Documents"
                }
                document_records.append(document_record)
            
            file_index += 1
            
            # Safety limit: stop after checking up to 20 fields
            if file_index > 20:
                break
        
        # Add NIT documents from Content and Content1 fields
        content = tender_data.get("Content")
        content1 = tender_data.get("Content1")
        sanitized_tender_id = sanitize_tender_id_for_filename(tender_id)
        
        if input_type == "corrigendum":
            # For corrigendum: Check for PDFs in corrigendum_content_pdf folder
            # Add NIT document for Content (tenderid_1.pdf)
            if content and content.strip():
                pdf_path_1 = os.path.join("corrigendum_content_pdf", f"{sanitized_tender_id}_1.pdf")
                if os.path.exists(pdf_path_1):
                    document_record = {
                        "tenderid": tender_id,
                        "doctype": "NIT",
                        "s3url": "",  # Will be set after S3 upload
                        "docname": "NIT",
                        "local_pdf_path": pdf_path_1,
                        "sanitized_tender_id": sanitized_tender_id
                    }
                    document_records.append(document_record)
            
            # Add NIT document for Content1 (tenderid_2.pdf)
            if content1 and content1.strip():
                pdf_path_2 = os.path.join("corrigendum_content_pdf", f"{sanitized_tender_id}_2.pdf")
                if os.path.exists(pdf_path_2):
                    document_record = {
                        "tenderid": tender_id,
                        "doctype": "NIT",
                        "s3url": "",  # Will be set after S3 upload
                        "docname": "NIT",
                        "local_pdf_path": pdf_path_2,
                        "sanitized_tender_id": sanitized_tender_id
                    }
                    document_records.append(document_record)
        
        elif input_type == "tender":
            # For tender: Check for PDF in tender_content_pdf folder
            if content and content.strip():
                pdf_path = os.path.join("tender_content_pdf", f"{sanitized_tender_id}.pdf")
                # Also try with original tender_id (for backward compatibility)
                if not os.path.exists(pdf_path):
                    pdf_path = os.path.join("tender_content_pdf", f"{tender_id}.pdf")
                
                if os.path.exists(pdf_path):
                    document_record = {
                        "tenderid": tender_id,
                        "doctype": "NIT",
                        "s3url": "",  # Will be set after S3 upload
                        "docname": "NIT",
                        "local_pdf_path": pdf_path,
                        "sanitized_tender_id": sanitized_tender_id
                    }
                    document_records.append(document_record)
    
    except Exception as e:
        error_msg = f"Error mapping documents for tender {tender_data.get('TenderId', 'unknown')}: {e}"
        print(f"    ⚠ {error_msg}")
        logging.warning(error_msg)
    
    return document_records


def process_and_store_single_tender(tender_data: Dict[str, Any], index: int, total: int, input_type: Optional[str] = None) -> Dict[str, int]:
    """
    Process a single tender: map it, convert PDFs if needed, then immediately store it.
    
    Args:
        tender_data: Single tender record dictionary from original JSON
        index: Current tender index (1-based)
        total: Total number of tenders
        input_type: Optional input type ("tender" or "corrigendum"). If None, will auto-detect.
        
    Returns:
        Dictionary with statistics for this tender
    """
    # Auto-detect input type if not provided
    if input_type is None:
        input_type = detect_input_type(tender_data)
    
    tender_id = extract_tender_id(tender_data.get("TenderId", "Unknown"))
    
    stats = {
        "tender_success": 0,
        "tender_error": 0,
        "doc_success": 0,
        "doc_error": 0,
        "boq_file_success": 0,
        "boq_file_error": 0,
        "boq_data_success": 0,
        "boq_data_error": 0,
        "nit_success": 0,
        "nit_error": 0
    }
    
    try:
        # Suppress WebDriver manager logs before PDF conversion
        # This ensures clean logs even if logging was reconfigured
        webdriver_loggers = ['WDM', 'selenium', 'urllib3.connectionpool', 'webdriver_manager']
        for logger_name in webdriver_loggers:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.WARNING)
            logger.propagate = False
        
        # Step 1: Convert HTML content to PDF (if needed)
        log_msg = f"[{index}/{total}] Processing Tender: {tender_id}"
        print(f"\n{log_msg}")
        logging.info(log_msg)
        print("-" * 60)
        logging.info("Step 1: Converting content to PDF (if needed)...")
        print(f"  Step 1: Converting content to PDF (if needed)...")
        convert_single_tender_content_to_pdf(tender_data, input_type)
        
        # Step 2: Map tender data
        logging.info("Step 2: Mapping tender data...")
        print(f"  Step 2: Mapping tender data...")
        mapped_tender_data = map_shubham_to_db(tender_data)
        
        # Step 3: Map documents for this tender
        logging.info("Step 3: Mapping documents...")
        print(f"  Step 3: Mapping documents...")
        mapped_documents = map_documents_for_single_tender(tender_data, input_type)
        doc_count_msg = f"Found {len(mapped_documents)} document(s)"
        print(f"    {doc_count_msg}")
        logging.info(doc_count_msg)
        
        # Step 4: Get BOQ HTML data
        boq_html = tender_data.get("BOQ")
        if boq_html:
            boq_html = boq_html.replace("\n", "") if boq_html else None
        
        # Step 5: Store tender and documents immediately
        logging.info("Step 4: Storing tender and documents...")
        print(f"  Step 4: Storing tender and documents...")
        t_success, t_error, d_success, d_error, bf_success, bf_error, bd_success, bd_error, n_success, n_error = store_single_tender_with_documents(
            mapped_tender_data, mapped_documents, boq_html, index, total
        )
        
        stats["tender_success"] = t_success
        stats["tender_error"] = t_error
        stats["doc_success"] = d_success
        stats["doc_error"] = d_error
        stats["boq_file_success"] = bf_success
        stats["boq_file_error"] = bf_error
        stats["boq_data_success"] = bd_success
        stats["boq_data_error"] = bd_error
        stats["nit_success"] = n_success
        stats["nit_error"] = n_error
        
        # Clear mapped data from memory after storing (helps with memory management)
        del mapped_tender_data
        del mapped_documents
        if boq_html:
            del boq_html
        
        # Log summary for this tender
        if t_success:
            logging.info(f"✓ Successfully processed tender {tender_id}")
        else:
            logging.error(f"✗ Failed to process tender {tender_id}")
        
    except Exception as e:
        error_msg = f"Error processing tender {tender_id}: {e}"
        print(f"  ✗ {error_msg}")
        logging.error(error_msg, exc_info=True)
        stats["tender_error"] = 1
    
    return stats


def map_and_store_tenders(input_file: str, input_type: Optional[str] = None):
    """
    Main function to map and store tenders one at a time.
    Reads the original JSON file and processes each tender: maps it, then immediately stores it.
    
    Args:
        input_file: Path to input JSON file (e.g., "jharkhandtenders_gov_in.json")
        input_type: Optional input type ("tender" or "corrigendum"). If None, will auto-detect from first record.
    """
    # Set up logging
    log_file_path = setup_logging(input_file)
    start_time = datetime.now()
    
    header = "MAPPING AND STORING TENDERS (ONE AT A TIME)"
    print("=" * 60)
    print(header)
    print("=" * 60)
    logging.info("=" * 60)
    logging.info(header)
    logging.info("=" * 60)
    logging.info(f"Log file: {log_file_path}")
    logging.info(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Read input JSON file
    # NOTE: This loads the entire file into memory at once.
    # For very large files (>500MB), consider using ijson for streaming parsing.
    # For most files, this approach is acceptable and simpler.
    input_msg = f"Reading tender data from: {input_file}"
    print(input_msg)
    logging.info(input_msg)
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            tender_data_list = json.load(f)
    except FileNotFoundError:
        error_msg = f"File not found: {input_file}"
        print(f"✗ Error: {error_msg}")
        logging.error(error_msg)
        return
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in file: {e}"
        print(f"✗ Error: {error_msg}")
        logging.error(error_msg)
        return
    except Exception as e:
        error_msg = f"Error reading file: {e}"
        print(f"✗ Error: {error_msg}")
        logging.error(error_msg, exc_info=True)
        return
    
    total_tenders = len(tender_data_list)
    total_msg = f"Found {total_tenders} tenders to process"
    print(f"{total_msg}\n")
    logging.info(total_msg)
    
    # Auto-detect input type from first record if not provided
    if input_type is None and total_tenders > 0:
        input_type = detect_input_type(tender_data_list[0])
        type_msg = f"Auto-detected input type: {input_type}"
        print(f"{type_msg}\n")
        logging.info(type_msg)
    
    # Track overall statistics
    total_stats = {
        "tender_success": 0,
        "tender_error": 0,
        "doc_success": 0,
        "doc_error": 0,
        "boq_file_success": 0,
        "boq_file_error": 0,
        "boq_data_success": 0,
        "boq_data_error": 0,
        "nit_success": 0,
        "nit_error": 0
    }
    
    # Process each tender one at a time
    # Memory management: We load all tenders at once, but process and store them one by one.
    # After each tender is stored, we delete the mapped data to free memory.
    # The original tender_data_list stays in memory until all tenders are processed.
    for index, tender_data in enumerate(tender_data_list, 1):
        stats = process_and_store_single_tender(tender_data, index, total_tenders, input_type)
        
        # Accumulate statistics
        for key in total_stats:
            total_stats[key] += stats[key]
        
        # Clear memory: delete the processed tender data to free memory
        # Note: The tender_data object is removed from the loop, but the list still holds the reference.
        # Python's garbage collector will handle cleanup when the list is cleared.
        del tender_data
    
    # Clear the entire list from memory after processing all tenders
    del tender_data_list
    
    # Calculate end time and duration
    end_time = datetime.now()
    duration = end_time - start_time
    
    # Print and log summary
    summary_header = "SUMMARY"
    print("\n" + "=" * 60)
    print(summary_header)
    print("=" * 60)
    logging.info("")
    logging.info("=" * 60)
    logging.info(summary_header)
    logging.info("=" * 60)
    
    summary_lines = [
        f"Tender Data:",
        f"  Total tenders processed: {total_tenders}",
        f"  Successfully stored: {total_stats['tender_success']}",
        f"  Failed: {total_stats['tender_error']}",
        "",
        f"Tender Documents:",
        f"  Successfully stored: {total_stats['doc_success']}",
        f"  Failed: {total_stats['doc_error']}",
        "",
        f"BOQ Files (from zip extraction):",
        f"  Successfully stored: {total_stats['boq_file_success']}",
        f"  Failed: {total_stats['boq_file_error']}",
        "",
        f"BOQ Data (head + details from HTML):",
        f"  Successfully stored: {total_stats['boq_data_success']}",
        f"  Failed: {total_stats['boq_data_error']}",
        "",
        f"NIT Documents:",
        f"  Successfully stored: {total_stats['nit_success']}",
        f"  Failed: {total_stats['nit_error']}",
        "",
        f"Processing Duration: {duration}",
        f"End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60
    ]
    
    for line in summary_lines:
        print(line)
        logging.info(line)
    
    logging.info(f"Log file saved to: {log_file_path}")


if __name__ == "__main__":
    # Specify the input JSON file
    input_file = "Uploading_Tender_Json09012026/1/eproc_punjab_gov_in.json"
    
    # Optional: Specify input type ("tender" or "corrigendum")
    # If None, will auto-detect from the first record
    input_type = "tender"  # Change to "tender" or "corrigendum" if needed
    
    # Map and store tenders one at a time
    map_and_store_tenders(input_file, input_type)

