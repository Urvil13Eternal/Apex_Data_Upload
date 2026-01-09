"""
Batch mapping script for multiple tender JSON files.
Processes all JSON files in a directory and creates mapped tender data and documents.
Includes BOQ data collection and PDF conversion.
"""

import os
import sys
import glob
import time
from map_tender_data import (
    Process_Tender_Data_JSON_File,
    map_tender_documents,
    collect_boq_data,
    convert_content_to_pdf
)


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
        print(f"✗ Error: Directory not found: {directory}")
        return []
    
    if not os.path.isdir(directory):
        print(f"✗ Error: Path is not a directory: {directory}")
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


def process_single_file(input_file: str, output_dir: str = None) -> tuple:
    """
    Process a single tender JSON file and create mapped outputs.
    Includes BOQ data collection and PDF conversion.
    
    Args:
        input_file: Path to input JSON file
        output_dir: Optional output directory (if None, uses same directory as input)
        
    Returns:
        Tuple of (success: bool, mapped_tenders_count: int, mapped_documents_count: int, error_message: str)
    """
    try:
        # Determine output directory
        if output_dir is None:
            output_dir = os.path.dirname(input_file)
        
        # Create output directory if it doesn't exist
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # Generate output file paths
        input_filename = os.path.basename(input_file)
        output_path = os.path.join(output_dir, f"mapped_{input_filename}")
        documents_output_path = os.path.join(output_dir, f"mapped_doc_{input_filename}")
        
        # Step 1: Collect and process BOQ data
        print(f"  Step 1: Collecting BOQ data...")
        try:
            collect_boq_data(input_file)
        except Exception as e:
            print(f"  ⚠ Warning: Error collecting BOQ data: {str(e)}")
            # Continue processing even if BOQ collection fails
        
        # Step 2: Convert HTML content to PDF
        print(f"  Step 2: Converting HTML content to PDF...")
        try:
            convert_content_to_pdf(input_file)
        except Exception as e:
            print(f"  ⚠ Warning: Error converting content to PDF: {str(e)}")
            # Continue processing even if PDF conversion fails
        
        # Step 3: Process tender data mapping
        print(f"  Step 3: Processing tender data mapping...")
        mapped_tenders = Process_Tender_Data_JSON_File(input_file, output_path)
        tenders_count = len(mapped_tenders) if mapped_tenders else 0
        # Clear from memory after getting count
        del mapped_tenders
        
        # Step 4: Process tender documents mapping
        print(f"  Step 4: Processing tender documents mapping...")
        mapped_documents = map_tender_documents(input_file, documents_output_path)
        documents_count = len(mapped_documents) if mapped_documents else 0
        # Clear from memory after getting count
        del mapped_documents
        
        return True, tenders_count, documents_count, None
        
    except Exception as e:
        error_msg = f"Error processing {input_file}: {str(e)}"
        print(f"  ✗ {error_msg}")
        return False, 0, 0, error_msg


def batch_map_tenders(directory: str, output_dir: str = None):
    """
    Process all JSON files in a directory and create mapped tender data and documents.
    
    Args:
        directory: Directory containing JSON files to process
        output_dir: Optional output directory (if None, uses same directory as input files)
    """
    print("=" * 60)
    print("BATCH MAPPING TENDER DATA")
    print("=" * 60)
    print(f"Input directory: {directory}")
    if output_dir:
        print(f"Output directory: {output_dir}")
    else:
        print(f"Output directory: Same as input directory")
    print()
    
    # Find all JSON files
    json_files = find_json_files(directory)
    
    if not json_files:
        print(f"⚠ No JSON files found in directory: {directory}")
        print("  (Excluding files that start with 'mapped_' or 'mapped_doc_')")
        return
    
    print(f"Found {len(json_files)} JSON file(s) to process")
    print("=" * 60)
    print()
    
    # Record overall start time
    overall_start_time = time.time()
    
    # Track statistics
    total_files = len(json_files)
    successful_files = 0
    failed_files = 0
    total_tenders = 0
    total_documents = 0
    errors = []
    
    # Process each file
    for index, input_file in enumerate(json_files, 1):
        filename = os.path.basename(input_file)
        print(f"[{index}/{total_files}] Processing: {filename}")
        print("-" * 60)
        
        # Record start time
        start_time = time.time()
        
        success, tenders_count, documents_count, error_msg = process_single_file(
            input_file, output_dir
        )
        
        # Calculate elapsed time
        end_time = time.time()
        elapsed_time = end_time - start_time
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        milliseconds = int((elapsed_time % 1) * 1000)
        
        # Format time display
        if minutes > 0:
            time_str = f"{minutes}m {seconds}s {milliseconds}ms"
        else:
            time_str = f"{seconds}s {milliseconds}ms"
        
        if success:
            successful_files += 1
            total_tenders += tenders_count
            total_documents += documents_count
            print(f"  ✓ Successfully mapped: {tenders_count} tenders, {documents_count} documents")
            print(f"  Processing time: {time_str}")
        else:
            failed_files += 1
            errors.append(f"{filename}: {error_msg}")
            print(f"  ✗ Failed to process")
            print(f"  Processing time: {time_str}")
        
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
    print("BATCH MAPPING SUMMARY")
    print("=" * 60)
    print(f"Total files processed: {total_files}")
    print(f"  Successfully processed: {successful_files}")
    print(f"  Failed: {failed_files}")
    print()
    print(f"Total tenders mapped: {total_tenders}")
    print(f"Total documents mapped: {total_documents}")
    print()
    print(f"Total Processing Time: {overall_time_str}")
    print()
    
    if errors:
        print("Errors encountered:")
        for error in errors:
            print(f"  - {error}")
        print()
    
    print("=" * 60)
    print("✓ Batch mapping completed!")


if __name__ == "__main__":
    # Set your directories here
    input_directory = "."
    output_directory = None  # Set to None to use same directory as input, or specify a path
    
    # Validate input directory
    if not input_directory:
        print("✗ Error: Please set input_directory in the script")
        sys.exit(1)
    
    if not os.path.exists(input_directory):
        print(f"✗ Error: Directory not found: {input_directory}")
        sys.exit(1)
    
    # Process all files in the directory
    batch_map_tenders(input_directory, output_directory if output_directory else None)

