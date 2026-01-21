"""
Batch script for mapping and storing tender data from multiple JSON files.
Processes all JSON files in a directory: maps each tender, then immediately stores it to the database.
Each file is processed completely before moving to the next file.
Includes file-wise logging for each input file plus a master batch log.
"""

import os
import sys
import glob
import json
import logging
import time
from datetime import datetime
from typing import Optional

# Import the main mapping and storing function
from map_n_store_tender import map_and_store_tenders, detect_input_type


def setup_batch_logging(directory: str) -> tuple:
    """
    Set up master batch logging configuration using a named logger.
    
    Args:
        directory: Input directory path (used for log filename)
        
    Returns:
        Tuple of (logger object, log_file_path)
    """
    # Create logs directory if it doesn't exist
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    
    # Create master log filename with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # Use directory name for log filename
    dir_name = os.path.basename(directory.rstrip('/\\')) or "batch"
    log_filename = f"batch_map_n_store_tender_{dir_name}_{timestamp}.log"
    log_file_path = os.path.join(logs_dir, log_filename)
    
    # Configure logging format
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # Create a named logger for batch processing (not root logger)
    batch_logger = logging.getLogger("batch_map_n_store")
    batch_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    batch_logger.handlers.clear()
    
    # Create file handler
    file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(log_format, datefmt=date_format)
    file_handler.setFormatter(file_formatter)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(log_format, datefmt=date_format)
    console_handler.setFormatter(console_formatter)
    
    # Add handlers to logger
    batch_logger.addHandler(file_handler)
    batch_logger.addHandler(console_handler)
    
    # Prevent propagation to root logger
    batch_logger.propagate = False
    
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
    
    return batch_logger, log_file_path


def find_json_files(directory: str) -> list:
    """
    Find all JSON files in the specified directory.
    Excludes already mapped files (files starting with 'mapped_' or 'mapped_doc_').
    
    Args:
        directory: Directory path to search for JSON files
        
    Returns:
        List of JSON file paths
    """
    if not os.path.exists(directory):
        error_msg = f"Directory not found: {directory}"
        print(f"✗ Error: {error_msg}")
        return []
    
    if not os.path.isdir(directory):
        error_msg = f"Path is not a directory: {directory}"
        print(f"✗ Error: {error_msg}")
        return []
    
    # Find all JSON files, excluding mapped files
    json_files = []
    for file_path in glob.glob(os.path.join(directory, "*.json")):
        filename = os.path.basename(file_path)
        # Skip already mapped files
        if filename.startswith("mapped_") or filename.startswith("mapped_doc_"):
            continue
        json_files.append(file_path)
    
    return sorted(json_files)


def process_single_file(input_file: str, input_type: Optional[str] = None, file_index: int = 0, total_files: int = 0, batch_logger: Optional[logging.Logger] = None) -> dict:
    """
    Process a single JSON file: map and store all tenders in it.
    
    Args:
        input_file: Path to input JSON file
        input_type: Optional input type ("tender" or "corrigendum"). If None, will auto-detect.
        file_index: Current file index (for logging)
        total_files: Total number of files (for logging)
        
    Returns:
        Dictionary with processing statistics
    """
    filename = os.path.basename(input_file)
    stats = {
        "success": False,
        "tender_success": 0,
        "tender_error": 0,
        "doc_success": 0,
        "doc_error": 0,
        "boq_file_success": 0,
        "boq_file_error": 0,
        "boq_data_success": 0,
        "boq_data_error": 0,
        "nit_success": 0,
        "nit_error": 0,
        "error_message": None,
        "processing_time": 0.0
    }
    
    start_time = time.time()
    
    try:
        log_msg = f"[{file_index}/{total_files}] Processing file: {filename}"
        print(f"\n{log_msg}")
        if batch_logger:
            batch_logger.info(log_msg)
        print("-" * 60)
        
        # Auto-detect input type if not provided
        # NOTE: This loads the file into memory temporarily just for detection.
        # The file will be loaded again by map_and_store_tenders, but this is minimal overhead.
        if input_type is None:
            try:
                with open(input_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    input_type = detect_input_type(data[0])
                    type_msg = f"Auto-detected input type: {input_type}"
                    print(f"  {type_msg}")
                    if batch_logger:
                        batch_logger.info(type_msg)
                    # Clear data from memory after detection
                    del data
            except Exception as e:
                warning_msg = f"Could not auto-detect input type: {e}. Using default 'tender'."
                if batch_logger:
                    batch_logger.warning(warning_msg)
                input_type = "tender"
        
        # Process the file (this will create its own log file per file)
        # The map_and_store_tenders function will set up its own logging for the root logger
        # Our batch logger is separate, so it won't conflict
        # NOTE: map_and_store_tenders loads the entire file into memory, processes tenders one by one,
        # and cleans up mapped data after each tender is stored.
        map_and_store_tenders(input_file, input_type)
        
        # Read the file to get statistics (if we can)
        # NOTE: This is a second read of the file, but it's minimal overhead for statistics.
        # We delete the data immediately after getting the count.
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                stats["tender_success"] = len(data)  # Assume all succeeded if no exception
            # Clear data from memory after getting count
            del data
        except:
            pass
        
        stats["success"] = True
        
    except FileNotFoundError:
        error_msg = f"File not found: {input_file}"
        print(f"  ✗ {error_msg}")
        if batch_logger:
            batch_logger.error(error_msg)
        stats["error_message"] = error_msg
        stats["success"] = False
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in file {filename}: {e}"
        print(f"  ✗ {error_msg}")
        if batch_logger:
            batch_logger.error(error_msg)
        stats["error_message"] = error_msg
        stats["success"] = False
    except Exception as e:
        error_msg = f"Error processing file {filename}: {str(e)}"
        print(f"  ✗ {error_msg}")
        if batch_logger:
            batch_logger.error(error_msg, exc_info=True)
        stats["error_message"] = error_msg
        stats["success"] = False
    
    end_time = time.time()
    stats["processing_time"] = end_time - start_time
    
    return stats


def batch_map_and_store_tenders(directory: str, default_input_type: Optional[str] = None):
    """
    Process all JSON files in a directory: map and store tenders from each file.
    Each file is processed completely (all tenders mapped and stored) before moving to the next file.
    
    Args:
        directory: Directory containing JSON files to process
        default_input_type: Optional default input type for all files ("tender" or "corrigendum").
                          If None, will auto-detect for each file.
    """
    # Set up master batch logging
    batch_logger, master_log_path = setup_batch_logging(directory)
    overall_start_time = datetime.now()
    
    header = "BATCH MAPPING AND STORING TENDERS"
    print("=" * 60)
    print(header)
    print("=" * 60)
    batch_logger.info("=" * 60)
    batch_logger.info(header)
    batch_logger.info("=" * 60)
    batch_logger.info(f"Master batch log file: {master_log_path}")
    batch_logger.info(f"Input directory: {directory}")
    batch_logger.info(f"Start time: {overall_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    if default_input_type:
        batch_logger.info(f"Default input type: {default_input_type}")
    else:
        batch_logger.info("Input type: Auto-detect for each file")
    
    # Find all JSON files
    # NOTE: This only stores file paths (strings), not file contents, so memory usage is minimal.
    json_files = find_json_files(directory)
    
    if not json_files:
        warning_msg = f"No JSON files found in directory: {directory}"
        print(f"⚠ {warning_msg}")
        print("  (Excluding files that start with 'mapped_' or 'mapped_doc_')")
        batch_logger.warning(warning_msg)
        return
    
    total_files = len(json_files)
    files_msg = f"Found {total_files} JSON file(s) to process"
    print(files_msg)
    batch_logger.info(files_msg)
    print("=" * 60)
    print()
    
    # Track overall statistics
    successful_files = 0
    failed_files = 0
    total_tender_success = 0
    total_tender_error = 0
    total_doc_success = 0
    total_doc_error = 0
    total_boq_file_success = 0
    total_boq_file_error = 0
    total_boq_data_success = 0
    total_boq_data_error = 0
    total_nit_success = 0
    total_nit_error = 0
    errors = []
    
    # Process each file
    # Memory management: Each file is processed completely before moving to the next.
    # The map_and_store_tenders function handles memory cleanup for each file internally.
    for index, input_file in enumerate(json_files, 1):
        filename = os.path.basename(input_file)
        
        stats = process_single_file(input_file, default_input_type, index, total_files, batch_logger)
        
        # Accumulate statistics
        if stats["success"]:
            successful_files += 1
            total_tender_success += stats["tender_success"]
            total_tender_error += stats["tender_error"]
            total_doc_success += stats["doc_success"]
            total_doc_error += stats["doc_error"]
            total_boq_file_success += stats["boq_file_success"]
            total_boq_file_error += stats["boq_file_error"]
            total_boq_data_success += stats["boq_data_success"]
            total_boq_data_error += stats["boq_data_error"]
            total_nit_success += stats["nit_success"]
            total_nit_error += stats["nit_error"]
            
            # Format processing time
            processing_time = stats["processing_time"]
            minutes = int(processing_time // 60)
            seconds = int(processing_time % 60)
            if minutes > 0:
                time_str = f"{minutes}m {seconds}s"
            else:
                time_str = f"{seconds}s"
            
            success_msg = f"✓ Successfully processed {filename} (Time: {time_str})"
            print(f"  {success_msg}")
            batch_logger.info(success_msg)
        else:
            failed_files += 1
            error_msg = f"{filename}: {stats['error_message'] or 'Unknown error'}"
            errors.append(error_msg)
            print(f"  ✗ Failed to process {filename}")
            batch_logger.error(f"Failed to process {filename}: {stats['error_message']}")
        
        # Clear stats from memory after processing (helps with memory management)
        del stats
        print()
    
    # Clear the json_files list from memory after processing all files
    del json_files
    
    # Calculate overall elapsed time
    overall_end_time = datetime.now()
    overall_duration = overall_end_time - overall_start_time
    
    # Print and log summary
    summary_header = "BATCH PROCESSING SUMMARY"
    print("=" * 60)
    print(summary_header)
    print("=" * 60)
    batch_logger.info("")
    batch_logger.info("=" * 60)
    batch_logger.info(summary_header)
    batch_logger.info("=" * 60)
    
    summary_lines = [
        f"Files Processed:",
        f"  Total files: {total_files}",
        f"  Successfully processed: {successful_files}",
        f"  Failed: {failed_files}",
        "",
        f"Tender Data:",
        f"  Successfully stored: {total_tender_success}",
        f"  Failed: {total_tender_error}",
        "",
        f"Tender Documents:",
        f"  Successfully stored: {total_doc_success}",
        f"  Failed: {total_doc_error}",
        "",
        f"BOQ Files (from zip extraction):",
        f"  Successfully stored: {total_boq_file_success}",
        f"  Failed: {total_boq_file_error}",
        "",
        f"BOQ Data (head + details from HTML):",
        f"  Successfully stored: {total_boq_data_success}",
        f"  Failed: {total_boq_data_error}",
        "",
        f"NIT Documents:",
        f"  Successfully stored: {total_nit_success}",
        f"  Failed: {total_nit_error}",
        "",
        f"Processing Duration: {overall_duration}",
        f"End time: {overall_end_time.strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    
    if errors:
        summary_lines.append("")
        summary_lines.append("Errors encountered:")
        for error in errors:
            summary_lines.append(f"  - {error}")
    
    summary_lines.append("=" * 60)
    summary_lines.append(f"Master batch log saved to: {master_log_path}")
    summary_lines.append("Note: Each file also has its own detailed log file in logs/ directory")
    
    for line in summary_lines:
        print(line)
        batch_logger.info(line)


if __name__ == "__main__":
    # Set your directory here
    input_directory = "Uploading_Tender_Json09012026/4"
    
    # Set default input type for all files (optional)
    # Options: "tender", "corrigendum", or None (auto-detect for each file)
    default_input_type = "tender"  # Change to "tender" or "corrigendum" if all files are the same type
    
    # Validate input directory
    if not input_directory:
        print("✗ Error: Please set input_directory in the script")
        sys.exit(1)
    
    if not os.path.exists(input_directory):
        print(f"✗ Error: Directory not found: {input_directory}")
        sys.exit(1)
    
    # Process all files in the directory
    batch_map_and_store_tenders(input_directory, default_input_type)

