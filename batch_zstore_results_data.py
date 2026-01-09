"""
Batch storing script for multiple mapped result JSON files.
Processes all mapped result files in a directory and stores them in the database.
"""

import os
import sys
import glob
import json
import time
from zstore_results_data import (
    Read_Data, Send_Data_to_DB, Update_Result_Data, 
    send_result_document_to_api, extract_tender_id
)


def find_mapped_files(directory: str) -> list:
    """
    Find all mapped result JSON files in the specified directory.
    Looks for files starting with 'mapped_' but not 'mapped_doc_'.
    
    Args:
        directory: Directory path to search for mapped files
        
    Returns:
        List of mapped result file paths
    """
    if not os.path.exists(directory):
        print(f"✗ Error: Directory not found: {directory}")
        return []
    
    if not os.path.isdir(directory):
        print(f"✗ Error: Path is not a directory: {directory}")
        return []
    
    # Find all mapped result files (not document files)
    mapped_files = []
    for file_path in glob.glob(os.path.join(directory, "mapped_*.json")):
        filename = os.path.basename(file_path)
        # Skip document files
        if filename.startswith("mapped_doc_"):
            continue
        mapped_files.append(file_path)
    
    return sorted(mapped_files)


def get_documents_file(mapped_results_file: str) -> str:
    """
    Get the corresponding mapped documents file path for a mapped results file.
    
    Args:
        mapped_results_file: Path to mapped results file (e.g., "mapped_file.json")
        
    Returns:
        Path to mapped documents file (e.g., "mapped_doc_file.json")
    """
    directory = os.path.dirname(mapped_results_file)
    filename = os.path.basename(mapped_results_file)
    
    # Replace "mapped_" with "mapped_doc_"
    if filename.startswith("mapped_"):
        doc_filename = filename.replace("mapped_", "mapped_doc_", 1)
    else:
        # Fallback: just prepend "mapped_doc_"
        doc_filename = f"mapped_doc_{filename}"
    
    return os.path.join(directory, doc_filename)


def process_single_mapped_file(mapped_results_file: str) -> dict:
    """
    Process a single mapped results file and store data in the database.
    
    Args:
        mapped_results_file: Path to mapped results JSON file
        
    Returns:
        Dictionary with processing statistics
    """
    filename = os.path.basename(mapped_results_file)
    stats = {
        "filename": filename,
        "success": False,
        "total_records": 0,
        "technical_records": 0,
        "update_records": 0,
        "technical_success": 0,
        "technical_error": 0,
        "update_success": 0,
        "update_error": 0,
        "documents_total": 0,
        "documents_success": 0,
        "documents_error": 0,
        "error_message": None
    }
    
    try:
        # Read mapped result data
        print(f"  Reading mapped result data...")
        data = Read_Data(mapped_results_file)
        stats["total_records"] = len(data)
        
        # Count records by type first (without creating lists)
        technical_count = 0
        update_count = 0
        for item in data:
            aocstatus = item.get("aocstatus")
            if aocstatus == "Technical":
                technical_count += 1
            elif aocstatus in ["AOC", "Financial"]:
                update_count += 1
        
        stats["technical_records"] = technical_count
        stats["update_records"] = update_count
        
        print(f"  Total records: {len(data)}")
        print(f"  Technical records (POST): {technical_count}")
        print(f"  Update records (PATCH - AOC/Financial): {update_count}")
        
        # Track successfully processed tenders (to store documents only once per tender)
        successfully_processed_tenders = set()
        
        # Process Technical records with POST API - process immediately, don't keep in memory
        if technical_count > 0:
            print(f"  Processing Technical records (POST API)...")
            for item in data:
                aocstatus = item.get("aocstatus")
                if aocstatus == "Technical":
                    response = Send_Data_to_DB(item)
                    tender_id = extract_tender_id(response.get('tender_id'))
                    
                    if response.get("success"):
                        if tender_id:
                            successfully_processed_tenders.add(tender_id)
                        stats["technical_success"] += 1
                        print(f"    ✓ Tender: {response.get('tender_id')}, Bidder: {response.get('bidder_name')}")
                    else:
                        stats["technical_error"] += 1
                        print(f"    ✗ Tender: {response.get('tender_id')}, Bidder: {response.get('bidder_name')}")
                        # Print error details
                        if "error" in response:
                            print(f"      Error: {response.get('error')}")
                        elif "status_code" in response:
                            status_code = response.get("status_code")
                            response_data = response.get("response", {})
                            print(f"      Status Code: {status_code}")
                            if isinstance(response_data, dict):
                                # Print error message from API response
                                error_msg = response_data.get("detail") or response_data.get("message") or response_data.get("error") or str(response_data)
                                print(f"      API Error: {error_msg}")
                            else:
                                print(f"      API Response: {response_data}")
                    print()
        
        # Process AOC and Financial records with PATCH update API - process immediately, don't keep in memory
        if update_count > 0:
            print(f"  Processing AOC/Financial records (PATCH update API)...")
            for item in data:
                aocstatus = item.get("aocstatus")
                if aocstatus in ["AOC", "Financial"]:
                    response = Update_Result_Data(item)
                    tender_id = extract_tender_id(response.get('tender_id'))
                    
                    # If update returns 404 (record not found), create it with POST API
                    if response.get("status_code") == 404:
                        print(f"    → Record not found (404), creating with POST API...")
                        response = Send_Data_to_DB(item)
                        tender_id = extract_tender_id(response.get('tender_id'))
                        print(f"    → POST API Response: {response}")
                    
                    if response.get("success"):
                        if tender_id:
                            successfully_processed_tenders.add(tender_id)
                        stats["update_success"] += 1
                        print(f"    ✓ Tender: {response.get('tender_id')}, Bidder: {response.get('bidder_name')}")
                    else:
                        stats["update_error"] += 1
                        print(f"    ✗ Tender: {response.get('tender_id')}, Bidder: {response.get('bidder_name')}")
                        if "error" in response:
                            print(f"      Error: {response.get('error')}")
                    print()
        
        # Clear data from memory after processing all records
        del data
        
        # Get corresponding documents file
        mapped_documents_file = get_documents_file(mapped_results_file)
        
        # Read mapped result documents only when needed
        print(f"  Reading mapped result documents...")
        try:
            mapped_documents = Read_Data(mapped_documents_file)
            print(f"  Found {len(mapped_documents)} document records")
            stats["documents_total"] = len(mapped_documents)
            
            # Group documents by tender_id
            documents_by_tender = {}
            for document in mapped_documents:
                tender_id = document.get("tenderid")
                if tender_id:
                    if tender_id not in documents_by_tender:
                        documents_by_tender[tender_id] = []
                    documents_by_tender[tender_id].append(document)
        except FileNotFoundError:
            print(f"  ⚠ Documents file not found: {mapped_documents_file}")
            print(f"    Continuing without documents...")
            mapped_documents = []
            documents_by_tender = {}
            stats["documents_total"] = 0
        except Exception as e:
            print(f"  ⚠ Error reading documents file: {str(e)}")
            print(f"    Continuing without documents...")
            mapped_documents = []
            documents_by_tender = {}
            stats["documents_total"] = 0
        
        # Store result documents for successfully processed tenders
        if successfully_processed_tenders and documents_by_tender:
            print(f"  " + "=" * 56)
            print(f"  STORING RESULT DOCUMENTS")
            print(f"  " + "=" * 56)
            
            for tender_id in successfully_processed_tenders:
                documents_for_tender = documents_by_tender.get(tender_id, [])
                
                if documents_for_tender:
                    print(f"\n  Storing {len(documents_for_tender)} document(s) for tender: {tender_id}")
                    
                    for doc_index, document_data in enumerate(documents_for_tender, 1):
                        doc_result = send_result_document_to_api(document_data)
                        
                        if doc_result.get("success"):
                            stats["documents_success"] += 1
                            print(f"    ✓ [{doc_index}/{len(documents_for_tender)}] Document stored: {document_data.get('s3url', 'Unknown')}")
                        else:
                            stats["documents_error"] += 1
                            print(f"    ✗ [{doc_index}/{len(documents_for_tender)}] Failed to store document")
                            print(f"      S3URL: {document_data.get('s3url', 'Unknown')}")
                            if "error" in doc_result:
                                print(f"      Error: {doc_result['error']}")
        
        # Clear documents from memory after processing
        del mapped_documents
        del documents_by_tender
        
        stats["success"] = True
        
    except FileNotFoundError:
        stats["error_message"] = f"File not found: {mapped_results_file}"
        print(f"  ✗ {stats['error_message']}")
    except json.JSONDecodeError as e:
        stats["error_message"] = f"Invalid JSON: {str(e)}"
        print(f"  ✗ {stats['error_message']}")
    except Exception as e:
        stats["error_message"] = f"Error: {str(e)}"
        print(f"  ✗ {stats['error_message']}")
    
    return stats


def batch_store_results(directory: str):
    """
    Process all mapped result files in a directory and store them in the database.
    
    Args:
        directory: Directory containing mapped result JSON files
    """
    print("=" * 60)
    print("BATCH STORING RESULT DATA")
    print("=" * 60)
    print(f"Input directory: {directory}")
    print()
    
    # Find all mapped result files
    mapped_files = find_mapped_files(directory)
    
    if not mapped_files:
        print(f"⚠ No mapped result files found in directory: {directory}")
        print("  (Looking for files starting with 'mapped_' but not 'mapped_doc_')")
        return
    
    print(f"Found {len(mapped_files)} mapped result file(s) to process")
    print("=" * 60)
    print()
    
    # Record overall start time
    overall_start_time = time.time()
    
    # Track overall statistics
    total_files = len(mapped_files)
    successful_files = 0
    failed_files = 0
    total_records = 0
    total_technical_success = 0
    total_technical_error = 0
    total_update_success = 0
    total_update_error = 0
    total_documents_success = 0
    total_documents_error = 0
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
        total_records += stats["total_records"]
        total_technical_success += stats["technical_success"]
        total_technical_error += stats["technical_error"]
        total_update_success += stats["update_success"]
        total_update_error += stats["update_error"]
        total_documents_success += stats["documents_success"]
        total_documents_error += stats["documents_error"]
        
        # Format time display
        if minutes > 0:
            time_str = f"{minutes}m {seconds}s {milliseconds}ms"
        else:
            time_str = f"{seconds}s {milliseconds}ms"
        
        if stats["success"]:
            successful_files += 1
            print(f"  ✓ Successfully processed")
            print(f"    Summary:")
            print(f"      Records: {stats['total_records']} total, "
                  f"{stats['technical_records']} technical, {stats['update_records']} update")
            print(f"      Results: {stats['technical_success'] + stats['update_success']} success, "
                  f"{stats['technical_error'] + stats['update_error']} errors")
            print(f"      Documents: {stats['documents_success']} success, "
                  f"{stats['documents_error']} errors")
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
    print(f"Result Data:")
    print(f"  Total records processed: {total_records}")
    print(f"  Technical records - Success: {total_technical_success}, Errors: {total_technical_error}")
    print(f"  Update records - Success: {total_update_success}, Errors: {total_update_error}")
    print()
    print(f"Result Documents:")
    print(f"  Successfully stored: {total_documents_success}")
    print(f"  Failed: {total_documents_error}")
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
    input_directory = "Tech_Fin_AOC_Json/Technical_Json/Technical_Json_Mapped"
    
    # Validate input directory
    if not input_directory:
        print("✗ Error: Please set input_directory in the script")
        sys.exit(1)
    
    if not os.path.exists(input_directory):
        print(f"✗ Error: Directory not found: {input_directory}")
        sys.exit(1)
    
    # Process all mapped files in the directory
    batch_store_results(input_directory)

