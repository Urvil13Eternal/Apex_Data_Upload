"""
Batch storing script for multiple mapped tender JSON files.
Processes all mapped tender files in a directory and stores them in the database.
Includes documents, BOQ data, and NIT documents.
"""

import os
import sys
import glob
import json
import time
from typing import Dict, Any
from zstore_new_tender import (
    read_data,
    store_tenders_with_documents
)


def find_mapped_files(directory: str) -> list:
    """
    Find all mapped tender JSON files in the specified directory.
    Looks for files starting with 'mapped_' but not 'mapped_doc_'.
    
    Args:
        directory: Directory path to search for mapped files
        
    Returns:
        List of mapped tender file paths
    """
    if not os.path.exists(directory):
        print(f"✗ Error: Directory not found: {directory}")
        return []
    
    if not os.path.isdir(directory):
        print(f"✗ Error: Path is not a directory: {directory}")
        return []
    
    # Find all mapped tender files (not document files)
    mapped_files = []
    for file_path in glob.glob(os.path.join(directory, "mapped_*.json")):
        filename = os.path.basename(file_path)
        # Skip document files
        if filename.startswith("mapped_doc_"):
            continue
        mapped_files.append(file_path)
    
    return sorted(mapped_files)


def get_documents_file(mapped_tender_file: str) -> str:
    """
    Get the corresponding mapped documents file path for a mapped tender file.
    
    Args:
        mapped_tender_file: Path to mapped tender file (e.g., "mapped_file.json")
        
    Returns:
        Path to mapped documents file (e.g., "mapped_doc_file.json")
    """
    directory = os.path.dirname(mapped_tender_file)
    filename = os.path.basename(mapped_tender_file)
    
    # Replace "mapped_" with "mapped_doc_"
    if filename.startswith("mapped_"):
        doc_filename = filename.replace("mapped_", "mapped_doc_", 1)
    else:
        # Fallback: just prepend "mapped_doc_"
        doc_filename = f"mapped_doc_{filename}"
    
    return os.path.join(directory, doc_filename)


def get_original_file(mapped_tender_file: str) -> str:
    """
    Get the corresponding original JSON file path for a mapped tender file.
    Removes 'mapped_' prefix to get the original filename.
    
    Args:
        mapped_tender_file: Path to mapped tender file (e.g., "mapped_file.json")
        
    Returns:
        Path to original file (e.g., "file.json")
    """
    directory = os.path.dirname(mapped_tender_file)
    filename = os.path.basename(mapped_tender_file)
    
    # Remove "mapped_" prefix
    if filename.startswith("mapped_"):
        original_filename = filename.replace("mapped_", "", 1)
    else:
        # Fallback: use same filename
        original_filename = filename
    
    return os.path.join(directory, original_filename)


def process_single_mapped_file(mapped_tender_file: str) -> Dict[str, Any]:
    """
    Process a single mapped tender file and store data in the database.
    
    Args:
        mapped_tender_file: Path to mapped tender JSON file
        
    Returns:
        Dictionary with processing statistics
    """
    filename = os.path.basename(mapped_tender_file)
    stats = {
        "filename": filename,
        "success": False,
        "total_tenders": 0,
        "tender_success": 0,
        "tender_error": 0,
        "documents_total": 0,
        "documents_success": 0,
        "documents_error": 0,
        "boq_file_success": 0,
        "boq_file_error": 0,
        "boq_data_success": 0,
        "boq_data_error": 0,
        "nit_success": 0,
        "nit_error": 0,
        "error_message": None
    }
    
    try:
        # Get corresponding files
        mapped_documents_file = get_documents_file(mapped_tender_file)
        original_json_file = get_original_file(mapped_tender_file)
        
        # Check if files exist
        if not os.path.exists(mapped_tender_file):
            stats["error_message"] = f"Mapped tender file not found: {mapped_tender_file}"
            print(f"  ✗ {stats['error_message']}")
            return stats
        
        # Read mapped tender data to get count
        print(f"  Reading mapped tender data...")
        try:
            tender_data_list = read_data(mapped_tender_file)
            stats["total_tenders"] = len(tender_data_list)
            print(f"  Found {stats['total_tenders']} tender records")
            del tender_data_list  # Clear from memory
        except Exception as e:
            stats["error_message"] = f"Error reading mapped tender file: {str(e)}"
            print(f"  ✗ {stats['error_message']}")
            return stats
        
        # Check if documents file exists
        if not os.path.exists(mapped_documents_file):
            print(f"  ⚠ Warning: Documents file not found: {mapped_documents_file}")
            print(f"    Continuing without documents...")
        
        # Check if original JSON file exists
        if not os.path.exists(original_json_file):
            print(f"  ⚠ Warning: Original JSON file not found: {original_json_file}")
            print(f"    Continuing without BOQ HTML data...")
        
        # Store tenders with documents and BOQ data
        # This function handles all the processing internally and prints detailed statistics
        print(f"  Storing tenders with documents and BOQ data...")
        
        try:
            # Call the store function
            # Note: store_tenders_with_documents handles missing files gracefully with try-except blocks
            store_tenders_with_documents(
                mapped_tender_file,
                mapped_documents_file,
                original_json_file
            )
            
            # Since store_tenders_with_documents doesn't return stats,
            # we'll mark as success if no exception was raised
            stats["success"] = True
            print(f"  ✓ Successfully processed {filename}")
            
        except Exception as e:
            stats["error_message"] = f"Error storing tenders: {str(e)}"
            print(f"  ✗ {stats['error_message']}")
            stats["success"] = False
        
    except FileNotFoundError as e:
        stats["error_message"] = f"File not found: {str(e)}"
        print(f"  ✗ {stats['error_message']}")
    except json.JSONDecodeError as e:
        stats["error_message"] = f"Invalid JSON: {str(e)}"
        print(f"  ✗ {stats['error_message']}")
    except Exception as e:
        stats["error_message"] = f"Error: {str(e)}"
        print(f"  ✗ {stats['error_message']}")
    
    return stats


def batch_store_tenders(directory: str):
    """
    Process all mapped tender files in a directory and store them in the database.
    
    Args:
        directory: Directory containing mapped tender JSON files
    """
    print("=" * 60)
    print("BATCH STORING TENDER DATA")
    print("=" * 60)
    print(f"Input directory: {directory}")
    print()
    
    # Find all mapped tender files
    mapped_files = find_mapped_files(directory)
    
    if not mapped_files:
        print(f"⚠ No mapped tender files found in directory: {directory}")
        print("  (Looking for files starting with 'mapped_' but not 'mapped_doc_')")
        return
    
    print(f"Found {len(mapped_files)} mapped tender file(s) to process")
    print("=" * 60)
    print()
    
    # Record overall start time
    overall_start_time = time.time()
    
    # Track overall statistics
    total_files = len(mapped_files)
    successful_files = 0
    failed_files = 0
    total_tenders = 0
    errors = []
    
    # Process each file
    for index, mapped_file in enumerate(mapped_files, 1):
        filename = os.path.basename(mapped_file)
        print(f"[{index}/{total_files}] Processing: {filename}")
        print("-" * 60)
        
        # Record start time
        start_time = time.time()
        
        stats = process_single_mapped_file(mapped_file)
        
        # Calculate elapsed time
        end_time = time.time()
        elapsed_time = end_time - start_time
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        milliseconds = int((elapsed_time % 1) * 1000)
        
        # Update overall statistics
        total_tenders += stats["total_tenders"]
        
        # Format time display
        if minutes > 0:
            time_str = f"{minutes}m {seconds}s {milliseconds}ms"
        else:
            time_str = f"{seconds}s {milliseconds}ms"
        
        if stats["success"]:
            successful_files += 1
            print(f"  ✓ Successfully processed")
            print(f"    Summary:")
            print(f"      Tenders: {stats['total_tenders']} total")
            print(f"      Processing time: {time_str}")
        else:
            failed_files += 1
            errors.append(f"{filename}: {stats.get('error_message', 'Unknown error')}")
            print(f"  ✗ Failed to process")
            print(f"    Processing time: {time_str}")
        
        print()
    
    # Calculate overall elapsed time
    overall_end_time = time.time()
    overall_elapsed_time = overall_end_time - overall_start_time
    overall_minutes = int(overall_elapsed_time // 60)
    overall_seconds = int(overall_elapsed_time % 60)
    overall_milliseconds = int((overall_elapsed_time % 1) * 1000)
    
    # Format overall time display
    if overall_minutes > 0:
        overall_time_str = f"{overall_minutes}m {overall_seconds}s {overall_milliseconds}ms"
    else:
        overall_time_str = f"{overall_seconds}s {overall_milliseconds}ms"
    
    # Print summary
    print("=" * 60)
    print("BATCH STORING SUMMARY")
    print("=" * 60)
    print(f"Files:")
    print(f"  Total files processed: {total_files}")
    print(f"  Successfully processed: {successful_files}")
    print(f"  Failed: {failed_files}")
    print()
    print(f"Tender Data:")
    print(f"  Total tenders processed: {total_tenders}")
    print()
    print(f"Total Processing Time: {overall_time_str}")
    print()
    
    if errors:
        print("Errors encountered:")
        for error in errors:
            print(f"  - {error}")
        print()
    
    print("=" * 60)
    print("✓ Batch storing completed!")


if __name__ == "__main__":
    # Set your directory here
    input_directory = "."
    
    # Validate input directory
    if not input_directory:
        print("✗ Error: Please set input_directory in the script")
        sys.exit(1)
    
    if not os.path.exists(input_directory):
        print(f"✗ Error: Directory not found: {input_directory}")
        sys.exit(1)
    
    # Process all mapped files in the directory
    batch_store_tenders(input_directory)

