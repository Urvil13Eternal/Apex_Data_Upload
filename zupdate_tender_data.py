import json
import os
import requests
from typing import Optional, Dict, Any, List


def Read_Data(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return data

def Send_Data_to_DB(data):
    """Update tender data in DB. Returns (response_data, success_flag)
    The API endpoint handles both:
    - Updating tenders2 table
    - Storing CorrigendumTitle in corrigendum_details table
    """
    PUT_API = f"http://13.202.159.122:8000/tenders/{data['TenderID']}"
    headers = {
        "Content-Type": "application/json"
    }
    try:
        response = requests.put(PUT_API, headers=headers, json=data, timeout=30)
        response_data = response.json()
        # Consider 200 (OK) and 204 (No Content) as success
        success = response.status_code in [200, 204]
        return response_data, success
    except requests.exceptions.RequestException as e:
        print(f"  ✗ Error updating tender: {str(e)}")
        return {"error": str(e)}, False

def extract_filename(file_path: Optional[str]) -> Optional[str]:
    """Extract just the filename from a full file path"""
    if not file_path or file_path == "":
        return None
    # Normalize path separators (handle Windows paths on Unix systems)
    normalized_path = file_path.replace("\\", "/")
    # Split by forward slash and take the last part (filename)
    parts = normalized_path.split("/")
    filename = parts[-1] if parts else None
    return filename.strip() if filename else None

def get_s3_object_key(file_path: str) -> str:
    """
    Convert file path to S3 object key for corrigendum documents
    Example: s3/jharkhandtenders.gov.inpy/Files/file.pdf -> PythonDocumentCorrigendum/jharkhandtenders.gov.inpy/Files/file.pdf
    """
    # Normalize path
    normalized = file_path.replace("\\", "/")
    
    # Remove s3/ prefix if present
    if normalized.startswith("s3/"):
        normalized = normalized[3:]  # Remove "s3/" prefix
    
    # Extract filename and construct S3 key with PythonDocumentCorrigendum prefix
    filename = extract_filename(normalized)
    if filename:
        # Construct S3 key: PythonDocumentCorrigendum/jharkhandtenders.gov.inpy/Files/{filename}
        return f"PythonDocumentCorrigendum/jharkhandtenders.gov.inpy/Files/{filename}"
    
    # If we can't extract filename, try to preserve the path structure
    if "PythonDocumentCorrigendum" not in normalized:
        return f"PythonDocumentCorrigendum/{normalized}"
    
    return normalized

def get_s3_object_url(s3_key: str, bucket_name: str, aws_access_key: str, aws_secret_key: str, region: str = "ap-south-1") -> Optional[str]:
    """
    Get S3 object URL (direct object URL)
    Returns the S3 object URL in format: https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}
    """
    try:
        # Construct direct S3 object URL
        # Format: https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}
        url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}"
        return url
    except Exception as e:
        print(f"    ✗ Error constructing S3 URL for {s3_key}: {str(e)}")
        return None

def upload_single_corrigendum_document(document_data: Dict[str, Any], api_url: str) -> tuple:
    """
    Upload a single corrigendum document to the API
    Uses the document data from mapped_doc file which already has S3 URLs
    
    Args:
        document_data: Dictionary with keys: tenderid, doctype, s3url, docname
        api_url: API endpoint URL
    
    Returns:
        (success_count, error_count)
    """
    success_count = 0
    error_count = 0
    
    # Prepare API payload
    # Use doctype and docname from mapped file (which will be "CTC" if CTC=1, otherwise "Corrigendum" or "Tender Documents")
    # If not present in mapped file, default to "Corrigendum"
    doctype = document_data.get("doctype", "Corrigendum")
    docname = document_data.get("docname", "Corrigendum")
    
    payload = {
        "tenderid": document_data.get("tenderid"),
        "doctype": doctype,  # Use doctype from mapped file (CTC if CTC=1, otherwise Corrigendum)
        "s3url": document_data.get("s3url"),
        "docname": docname  # Use docname from mapped file
    }
    
    # Call API
    try:
        response = requests.post(api_url, json=payload, timeout=30)
        if response.status_code in [200, 201]:
            success_count += 1
            print(f"  ✓ Uploaded corrigendum document: {document_data.get('s3url', 'Unknown')}")
        else:
            error_count += 1
            print(f"  ✗ Failed to upload corrigendum document - Status: {response.status_code}")
            try:
                error_detail = response.json()
                print(f"    Error detail: {error_detail}")
            except:
                print(f"    Error text: {response.text[:200]}")
    except requests.exceptions.RequestException as e:
        error_count += 1
        print(f"  ✗ Error uploading corrigendum document - Error: {str(e)}")
    
    return success_count, error_count

def upload_corrigendum_documents_for_tender(tender_id: str, documents_list: List[Dict[str, Any]]):
    """
    Upload corrigendum documents to the API for a single tender
    Uses the mapped documents file which already has S3 URLs
    
    Args:
        tender_id: Tender ID
        documents_list: List of document records from mapped_doc file
    
    Returns:
        (success_count, error_count)
    """
    api_url = "http://13.202.159.122:8000/tender-documents/"
    total_success = 0
    total_error = 0
    
    # Filter documents for this tender
    tender_documents = [doc for doc in documents_list if doc.get("tenderid") == tender_id]
    
    if not tender_documents:
        print(f"  ⚠ No corrigendum documents found for tender {tender_id}")
        return total_success, total_error
    
    print(f"  Found {len(tender_documents)} corrigendum document(s) for tender {tender_id}")
    
    # Upload each document
    for doc in tender_documents:
        success, error = upload_single_corrigendum_document(doc, api_url)
        total_success += success
        total_error += error
    
    return total_success, total_error


if __name__ == "__main__":
    # File names - Update these to match your actual file names
    input_file = "Test_Corr.json"
    mapped_corrigendum_file = f"mapped_{input_file}"
    mapped_corrigendum_documents_file = f"mapped_doc_{input_file}"
    
    # Read mapped corrigendum data for updating tenders
    print(f"Reading mapped corrigendum data from: {mapped_corrigendum_file}")
    try:
        mapped_data = Read_Data(mapped_corrigendum_file)
    except FileNotFoundError:
        print(f"✗ Error: File not found: {mapped_corrigendum_file}")
        print("  Please update the file name in the script to match your actual file.")
        exit(1)
    
    # Read mapped corrigendum documents (which already have S3 URLs)
    print(f"Reading mapped corrigendum documents from: {mapped_corrigendum_documents_file}")
    try:
        mapped_documents = Read_Data(mapped_corrigendum_documents_file)
    except FileNotFoundError:
        print(f"⚠ Warning: File not found: {mapped_corrigendum_documents_file}")
        print("  Continuing without documents...")
        mapped_documents = []
    
    print(f"\nFound {len(mapped_data)} corrigendum records and {len(mapped_documents)} document records")
    print("=" * 60)
    
    # Process each mapped corrigendum
    total_tenders_updated = 0
    total_tenders_failed = 0
    total_docs_uploaded = 0
    total_docs_failed = 0
    
    for mapped_item in mapped_data:
        tender_id = mapped_item.get("TenderID")
        
        # Update tender data in DB
        # The API endpoint handles both:
        # - Updating tenders2 table with all fields except CorrigendumTitle
        # - Storing CorrigendumTitle in corrigendum_details table
        print(f"\nProcessing corrigendum for tender: {tender_id}")
        response, update_success = Send_Data_to_DB(mapped_item)
        
        if update_success:
            total_tenders_updated += 1
            print(f"  ✓ Tender updated successfully")
            if mapped_item.get("CorrigendumTitle"):
                print(f"  ✓ CorrigendumTitle stored in corrigendum_details: {mapped_item.get('CorrigendumTitle')}")
        else:
            total_tenders_failed += 1
            print(f"  ✗ Tender update failed")
            print(f"    Response: {response}")
            continue
        
        # Only upload corrigendum documents if tender update was successful
        if update_success:
            print(f"  Uploading corrigendum documents...")
            success, error = upload_corrigendum_documents_for_tender(tender_id, mapped_documents)
            total_docs_uploaded += success
            total_docs_failed += error
            print(f"  Documents: {success} uploaded, {error} errors")
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Tender Updates:")
    print(f"  Successfully updated: {total_tenders_updated}")
    print(f"  Failed: {total_tenders_failed}")
    print()
    print(f"Corrigendum Documents:")
    print(f"  Successfully uploaded: {total_docs_uploaded}")
    print(f"  Failed: {total_docs_failed}")
    print("=" * 60)
    print("\n✓ All corrigendums processed!")