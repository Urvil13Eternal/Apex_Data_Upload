import json
import os
import io
import zipfile
import requests
import boto3
from urllib.parse import urlparse
from botocore.exceptions import ClientError
from botocore.config import Config
from typing import Dict, Any, Optional, List, Tuple

# API endpoints
TENDER_POST_API = "http://13.202.159.122:8000/tenders/"
TENDER_DOCUMENTS_API = "http://13.202.159.122:8000/tender-documents/"
BOQ_HEAD_API = "http://13.202.159.122:8000/boq/head/"
BOQ_DETAIL_API = "http://13.202.159.122:8000/boq/detail/"

# Import BOQ extraction function
from html_to_json import extract_boq_data

# AWS S3 Configuration
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "AKIAU2VF6N2ZLAEXHP5K")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "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")
BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "shubhum-object")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

def read_data(file_path: str) -> list:
    """Read JSON data from file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def send_tender_to_api(tender_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send tender data to the API
    
    Args:
        tender_data: Dictionary containing tender data to be sent
        
    Returns:
        Dictionary with response status and data
    """
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(TENDER_POST_API, headers=headers, json=tender_data, timeout=30)
        
        # Try to get JSON response
        try:
            response_data = response.json()
        except:
            response_data = {"message": response.text, "status_code": response.status_code}
        
        # Check if request was successful
        if response.status_code in [200, 201]:
            return {
                "success": True,
                "status_code": response.status_code,
                "response": response_data,
                "tender_id": tender_data.get("TenderID"),
                "tender_number": tender_data.get("TenderNumber")
            }
        else:
            return {
                "success": False,
                "status_code": response.status_code,
                "response": response_data,
                "tender_id": tender_data.get("TenderID"),
                "tender_number": tender_data.get("TenderNumber"),
                "error": f"API returned status code {response.status_code}"
            }
            
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e),
            "tender_id": tender_data.get("TenderID"),
            "tender_number": tender_data.get("TenderNumber")
        }

def extract_folder_path_from_s3_url(s3_url: str) -> Optional[str]:
    """
    Extract the folder path from a full S3 URL dynamically.
    
    Example:
        Input: https://shubhum-object.s3.ap-south-1.amazonaws.com/PythonDocuments/jharkhandtenders.gov.inpy/files/file.zip
        Output: PythonDocuments/jharkhandtenders.gov.inpy/files/
    
    Args:
        s3_url: Full S3 URL starting with https
        
    Returns:
        Folder path (without filename) or None if parsing fails
    """
    try:
        # Parse the URL
        parsed = urlparse(s3_url)
        
        # Extract the path (everything after the domain)
        path = parsed.path.lstrip('/')
        
        # Remove the filename (last part after /)
        if '/' in path:
            # Get everything except the last part (filename)
            folder_path = '/'.join(path.split('/')[:-1])
            # Add trailing slash if not present
            if folder_path and not folder_path.endswith('/'):
                folder_path += '/'
            return folder_path
        
        return None
    except Exception as e:
        print(f"    ✗ Error parsing S3 URL {s3_url}: {str(e)}")
        return None

def extract_s3_key_from_url(s3_url: str) -> Optional[str]:
    """
    Extract S3 key from full S3 URL.
    
    Example:
        Input: https://shubhum-object.s3.ap-south-1.amazonaws.com/PythonDocuments/jharkhandtenders.gov.inpy/files/file.zip
        Output: PythonDocuments/jharkhandtenders.gov.inpy/files/file.zip
    
    Args:
        s3_url: Full S3 URL
        
    Returns:
        S3 key or None if parsing fails
    """
    try:
        parsed = urlparse(s3_url)
        path = parsed.path.lstrip('/')
        return path if path else None
    except Exception as e:
        print(f"    ✗ Error extracting S3 key from URL {s3_url}: {str(e)}")
        return None

def extract_zip_and_upload_boq_files(s3_url: str, tender_id: str, 
                                      aws_access_key: str, aws_secret_key: str,
                                      bucket_name: str, region: str) -> List[Dict[str, str]]:
    """
    Extract zip file from S3, extract only Excel files (xls/xlsx), rename with tender_id prefix,
    upload to BOQ folder, and return list of uploaded file info.
    
    Args:
        s3_url: Full S3 URL of the zip file
        tender_id: Tender ID for renaming files
        aws_access_key: AWS access key
        aws_secret_key: AWS secret key
        bucket_name: S3 bucket name
        region: AWS region
        
    Returns:
        List of dictionaries with keys: 's3url', 'docname', 'doctype'
    """
    uploaded_files = []
    
    try:
        # Extract S3 key from URL
        s3_key = extract_s3_key_from_url(s3_url)
        if not s3_key:
            print(f"    ✗ Could not extract S3 key from URL: {s3_url}")
            return uploaded_files
        
        # Extract folder path dynamically
        folder_path = extract_folder_path_from_s3_url(s3_url)
        if not folder_path:
            print(f"    ✗ Could not extract folder path from URL: {s3_url}")
            return uploaded_files
        
        # Create BOQ folder path
        boq_folder_path = f"{folder_path}BOQ/"
        
        # Initialize S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=region,
            config=Config(connect_timeout=10, read_timeout=30, retries={'max_attempts': 2})
        )
        
        # Check if zip file exists
        try:
            s3_client.head_object(Bucket=bucket_name, Key=s3_key)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == '404':
                print(f"    ⚠ Zip file not found in S3: {s3_key}")
                return uploaded_files
            else:
                raise
        
        # Download zip file to memory
        print(f"    Downloading zip from S3: {s3_key}")
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        zip_content = response['Body'].read()
        
        # Extract zip contents
        with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zip_ref:
            file_list = zip_ref.namelist()
            
            # Filter out directories
            non_dir_files = [f for f in file_list if not f.endswith('/')]
            
            if not non_dir_files:
                print(f"    ⚠ No files found in zip: {s3_key}")
                return uploaded_files
            
            print(f"    Found {len(non_dir_files)} file(s) in zip")
            
            # Process each file - only Excel files (xls, xlsx)
            counter = 1
            skipped_count = 0
            for file_in_zip in non_dir_files:
                try:
                    # Get file extension
                    original_filename = os.path.basename(file_in_zip)
                    _, ext = os.path.splitext(original_filename)
                    ext_lower = ext.lower() if ext else ""
                    
                    # Only process Excel files (.xls or .xlsx)
                    if ext_lower not in ['.xls', '.xlsx']:
                        skipped_count += 1
                        print(f"      ⚠ Skipping non-Excel file: {original_filename} (extension: {ext_lower or 'none'})")
                        continue
                    
                    # Read file content from zip
                    file_content = zip_ref.read(file_in_zip)
                    
                    # Create new filename: {tender_id}_{counter}.{ext}
                    new_filename = f"{tender_id}_{counter}{ext_lower}"
                    
                    # Construct S3 key for BOQ folder
                    boq_s3_key = f"{boq_folder_path}{new_filename}"
                    
                    # Upload to S3
                    print(f"      Uploading Excel file to BOQ folder: {boq_s3_key}")
                    s3_client.put_object(
                        Bucket=bucket_name,
                        Key=boq_s3_key,
                        Body=file_content
                    )
                    
                    # Construct full S3 URL
                    boq_s3_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{boq_s3_key}"
                    
                    # Add to uploaded files list
                    uploaded_files.append({
                        's3url': boq_s3_url,
                        'docname': new_filename,
                        'doctype': 'BOQ'
                    })
                    
                    print(f"      ✓ Uploaded: {new_filename}")
                    counter += 1
                    
                except Exception as e:
                    print(f"      ✗ Error processing file {file_in_zip} from zip: {str(e)}")
                    continue
            
            if skipped_count > 0:
                print(f"    ⚠ Skipped {skipped_count} non-Excel file(s)")
        
        return uploaded_files
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        print(f"    ✗ S3 ClientError processing zip {s3_url}: {error_code}")
        return uploaded_files
    except Exception as e:
        print(f"    ✗ Error extracting zip from S3: {str(e)}")
        return uploaded_files

def process_boq_from_zip_files(documents_for_tender: list, tender_id: str,
                               aws_access_key: str, aws_secret_key: str,
                               bucket_name: str, region: str) -> Tuple[int, int]:
    """
    Process zip files from documents, extract BOQ files, and store them.
    
    Args:
        documents_for_tender: List of document records for this tender
        tender_id: Tender ID
        aws_access_key: AWS access key
        aws_secret_key: AWS secret key
        bucket_name: S3 bucket name
        region: AWS region
        
    Returns:
        Tuple of (success_count, error_count)
    """
    boq_success = 0
    boq_error = 0
    
    # Find zip files in documents
    zip_files = []
    for doc in documents_for_tender:
        s3url = doc.get('s3url', '')
        if s3url and s3url.lower().endswith('.zip'):
            zip_files.append(s3url)
    
    if not zip_files:
        return boq_success, boq_error
    
    print(f"  Step 3: Processing {len(zip_files)} zip file(s) for BOQ extraction...")
    
    for zip_index, zip_url in enumerate(zip_files, 1):
        print(f"    [{zip_index}/{len(zip_files)}] Processing zip: {zip_url}")
        
        # Extract and upload BOQ files
        uploaded_files = extract_zip_and_upload_boq_files(
            zip_url, tender_id, aws_access_key, aws_secret_key, bucket_name, region
        )
        
        if not uploaded_files:
            print(f"      ⚠ No files extracted from zip")
            continue
        
        # Store each extracted file in tender_documents API
        for file_info in uploaded_files:
            document_data = {
                'tenderid': tender_id,
                'doctype': file_info['doctype'],
                's3url': file_info['s3url'],
                'docname': file_info['docname']
            }
            
            doc_result = send_document_to_api(document_data)
            
            if doc_result.get("success"):
                boq_success += 1
                print(f"      ✓ BOQ file stored: {file_info['docname']}")
            else:
                boq_error += 1
                print(f"      ✗ Failed to store BOQ file: {file_info['docname']}")
                if "error" in doc_result:
                    print(f"        Error: {doc_result['error']}")
    
    return boq_success, boq_error

def extract_files_directory_path_from_documents(documents_for_tender: list) -> Optional[str]:
    """
    Extract the directory path up to and including '/files/' from existing documents' S3 URLs.
    This path will be used to create NIT folder at the same level as other files.
    
    Example:
        Input S3 URL: https://shubhum-object.s3.ap-south-1.amazonaws.com/PythonDocumentCorrigendum/defproc.gov.inpy/files/file.pdf
        Output: PythonDocumentCorrigendum/defproc.gov.inpy/files/
        
    Args:
        documents_for_tender: List of document records for this tender
        
    Returns:
        Directory path up to '/files/' (with trailing slash) or None if not found
    """
    for doc in documents_for_tender:
        s3url = doc.get('s3url', '')
        if not s3url:
            continue
        
        try:
            # Extract S3 key from URL
            s3_key = extract_s3_key_from_url(s3url)
            if not s3_key:
                continue
            
            # Find '/files/' in the S3 key
            if '/files/' in s3_key:
                # Extract everything up to and including '/files/'
                files_dir_path = s3_key.split('/files/')[0] + '/files/'
                return files_dir_path
        except Exception as e:
            continue
    
    return None

def upload_nit_pdf_to_s3(pdf_file_path: str, tender_id: str, files_directory_path: str,
                         aws_access_key: str, aws_secret_key: str,
                         bucket_name: str, region: str) -> Optional[Dict[str, str]]:
    """
    Upload NIT PDF file to S3 bucket under {files_directory_path}NIT/ folder.
    The NIT folder will be created at the same level as other files.
    
    Example:
        files_directory_path: PythonDocumentCorrigendum/defproc.gov.inpy/files/
        Result: PythonDocumentCorrigendum/defproc.gov.inpy/files/NIT/{tender_id}.pdf
    
    Args:
        pdf_file_path: Local path to the PDF file (e.g., "content_pdf/{tender_id}.pdf")
        tender_id: Tender ID for filename
        files_directory_path: Directory path up to '/files/' (e.g., "PythonDocumentCorrigendum/defproc.gov.inpy/files/")
        aws_access_key: AWS access key
        aws_secret_key: AWS secret key
        bucket_name: S3 bucket name
        region: AWS region
        
    Returns:
        Dictionary with keys: 's3url', 'docname', 'doctype' if successful, None otherwise
    """
    try:
        # Check if PDF file exists
        if not os.path.exists(pdf_file_path):
            print(f"    ⚠ NIT PDF file not found: {pdf_file_path}")
            return None
        
        if not files_directory_path:
            print(f"    ✗ Files directory path not found, cannot determine S3 path")
            return None
        
        # Create S3 key: {files_directory_path}NIT/{tender_id}.pdf
        # files_directory_path already ends with '/files/', so we just append 'NIT/'
        s3_key = f"{files_directory_path}NIT/{tender_id}.pdf"
        
        # Initialize S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=region,
            config=Config(connect_timeout=10, read_timeout=30, retries={'max_attempts': 2})
        )
        
        # Read PDF file
        with open(pdf_file_path, 'rb') as pdf_file:
            pdf_content = pdf_file.read()
        
        # Upload to S3
        print(f"    Uploading NIT PDF to S3: {s3_key}")
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=pdf_content,
            ContentType='application/pdf'
        )
        
        # Construct full S3 URL
        s3_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}"
        
        print(f"    ✓ NIT PDF uploaded successfully: {s3_url}")
        
        return {
            's3url': s3_url,
            'docname': 'NIT',
            'doctype': 'NIT'
        }
        
    except FileNotFoundError:
        print(f"    ✗ NIT PDF file not found: {pdf_file_path}")
        return None
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        print(f"    ✗ S3 ClientError uploading NIT PDF: {error_code}")
        return None
    except Exception as e:
        print(f"    ✗ Error uploading NIT PDF to S3: {str(e)}")
        return None

def process_nit_documents(tender_id: str, documents_for_tender: list,
                          aws_access_key: str, aws_secret_key: str,
                          bucket_name: str, region: str) -> Tuple[int, int]:
    """
    Process NIT PDF files from content_pdf folder, upload to S3, and store in tender_documents table.
    The NIT folder will be created at the same directory level as other files.
    
    Args:
        tender_id: Tender ID
        documents_for_tender: List of document records for this tender (to extract files directory path)
        aws_access_key: AWS access key
        aws_secret_key: AWS secret key
        bucket_name: S3 bucket name
        region: AWS region
        
    Returns:
        Tuple of (success_count, error_count)
    """
    nit_success = 0
    nit_error = 0
    
    # Check if content_pdf folder exists
    content_pdf_folder = "content_pdf"
    if not os.path.exists(content_pdf_folder):
        return nit_success, nit_error
    
    # Check if PDF file exists for this tender
    pdf_file_path = os.path.join(content_pdf_folder, f"{tender_id}.pdf")
    if not os.path.exists(pdf_file_path):
        return nit_success, nit_error
    
    # Extract files directory path from existing documents
    files_directory_path = extract_files_directory_path_from_documents(documents_for_tender)
    if not files_directory_path:
        print(f"  Step 5: No files directory path found in documents for {tender_id}, skipping NIT upload")
        return nit_success, nit_error
    
    print(f"  Step 5: Processing NIT document for {tender_id}...")
    print(f"    Using files directory path: {files_directory_path}")
    
    # Upload PDF to S3
    file_info = upload_nit_pdf_to_s3(
        pdf_file_path, tender_id, files_directory_path,
        aws_access_key, aws_secret_key, bucket_name, region
    )
    
    if not file_info:
        print(f"    ✗ Failed to upload NIT PDF to S3")
        return nit_success, 1
    
    # Store in tender_documents API
    document_data = {
        'tenderid': tender_id,
        'doctype': file_info['doctype'],
        's3url': file_info['s3url'],
        'docname': file_info['docname']
    }
    
    doc_result = send_document_to_api(document_data)
    
    if doc_result.get("success"):
        nit_success += 1
        print(f"    ✓ NIT document stored: {file_info['docname']}")
    else:
        nit_error += 1
        print(f"    ✗ Failed to store NIT document: {file_info['docname']}")
        if "error" in doc_result:
            print(f"      Error: {doc_result['error']}")
    
    return nit_success, nit_error

def store_single_tender_with_documents(tender_data: Dict[str, Any], documents_for_tender: list, 
                                       boq_html: Optional[str], index: int, total: int) -> tuple:
    """
    Store a single tender and all its documents and BOQ data
    
    Args:
        tender_data: Dictionary containing tender data
        documents_for_tender: List of document records for this tender
        boq_html: BOQ HTML content from original JSON (None if not available)
        index: Current tender index
        total: Total number of tenders
        
    Returns:
        Tuple of (tender_success, tender_error, doc_success, doc_error, boq_file_success, boq_file_error, boq_data_success, boq_data_error, nit_success, nit_error)
    """
    tender_id = tender_data.get("TenderID", "Unknown")
    tender_number = tender_data.get("TenderNumber", "Unknown")
    
    print(f"\n[{index}/{total}] Processing Tender: {tender_id} (TenderNumber: {tender_number})")
    print("-" * 60)
    
    tender_success = 0
    tender_error = 0
    doc_success = 0
    doc_error = 0
    boq_file_success = 0
    boq_file_error = 0
    boq_data_success = 0
    boq_data_error = 0
    nit_success = 0
    nit_error = 0
    
    # Step 1: Store tender data
    print(f"  Step 1: Storing tender data for {tender_id}...")
    result = send_tender_to_api(tender_data)
    
    tender_stored_successfully = False
    if result.get("success"):
        tender_success = 1
        tender_stored_successfully = True
        print(f"  ✓ Successfully stored tender {tender_id}")
        if "response" in result and isinstance(result["response"], dict):
            if "id" in result["response"]:
                print(f"    Tender ID in DB: {result['response']['id']}")
    else:
        tender_error = 1
        tender_stored_successfully = False
        print(f"  ✗ Failed to store tender {tender_id}")
        if "error" in result:
            print(f"    Error: {result['error']}")
        if "response" in result:
            print(f"    Response: {result['response']}")
    
    # Step 2: Store documents for this tender (only if tender was stored successfully)
    if tender_stored_successfully:
        if documents_for_tender:
            print(f"  Step 2: Storing {len(documents_for_tender)} document(s) for {tender_id}...")
            for doc_index, document_data in enumerate(documents_for_tender, 1):
                doc_result = send_document_to_api(document_data)
                
                if doc_result.get("success"):
                    doc_success += 1
                    print(f"    ✓ [{doc_index}/{len(documents_for_tender)}] Document stored: {document_data.get('s3url', 'Unknown')}")
                else:
                    doc_error += 1
                    print(f"    ✗ [{doc_index}/{len(documents_for_tender)}] Failed to store document")
                    print(f"      S3URL: {document_data.get('s3url', 'Unknown')}")
                    if "error" in doc_result:
                        print(f"      Error: {doc_result['error']}")
            
            # Step 3: Process BOQ files from zip files (only if documents were stored)
            boq_file_success, boq_file_error = process_boq_from_zip_files(
                documents_for_tender, tender_id,
                AWS_ACCESS_KEY, AWS_SECRET_KEY, BUCKET_NAME, AWS_REGION
            )
        else:
            print(f"  Step 2: No documents found for {tender_id}")
        
        # Step 4: Store BOQ data from HTML (only if tender was stored successfully)
        if boq_html and boq_html.strip():
            print(f"  Step 4: Storing BOQ data from HTML for {tender_id}...")
            boq_data_success, boq_data_error = store_boq_from_html(tender_id, boq_html)
        else:
            print(f"  Step 4: No BOQ HTML data found for {tender_id}")
        
        # Step 5: Process NIT documents (only if tender was stored successfully)
        nit_success, nit_error = process_nit_documents(
            tender_id, documents_for_tender,
            AWS_ACCESS_KEY, AWS_SECRET_KEY, BUCKET_NAME, AWS_REGION
        )
    else:
        print(f"  Step 2: Skipping documents and BOQ for {tender_id} (tender storage failed)")
    
    return tender_success, tender_error, doc_success, doc_error, boq_file_success, boq_file_error, boq_data_success, boq_data_error, nit_success, nit_error

def extract_tender_id(tender_id: Optional[str]) -> Optional[str]:
    """Extract the first tender ID from string that may contain multiple IDs separated by <br>"""
    if not tender_id or tender_id == "":
        return None
    # Split by <br> and take the first one, strip whitespace
    parts = tender_id.split("<br>")
    return parts[0].strip() if parts else None

def safe_float(value: Any) -> float:
    """Safely convert value to float, return 0.0 if conversion fails."""
    if not value or (isinstance(value, str) and value.strip() == ""):
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def safe_int(value: Any) -> int:
    """Safely convert value to int, return 0 if conversion fails."""
    if not value or (isinstance(value, str) and value.strip() == ""):
        return 0
    try:
        return int(float(value))  # Handle "1.0" -> 1
    except (ValueError, TypeError):
        return 0

def store_boq_head(tenderid: str) -> Optional[int]:
    """
    Store BOQ head information and return the head ID.
    
    Args:
        tenderid: Tender ID string
        
    Returns:
        int: BOQ head ID if successful, None otherwise
    """
    payload = {
        "tenderid": tenderid,
        "boqfilepath": tenderid  # Using tenderid as placeholder since HTML is passed directly
    }
    
    try:
        response = requests.post(BOQ_HEAD_API, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        
        if "id" in result:
            return result["id"]
        else:
            print(f"    ✗ Error: Unexpected response format: {result}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"    ✗ Error storing BOQ head: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
                print(f"      Response: {error_detail}")
            except:
                print(f"      Response status: {e.response.status_code}")
                print(f"      Response text: {e.response.text}")
        return None

def store_boq_detail(boqheadid: int, boq_item: Dict, summary_data: Dict) -> bool:
    """
    Store a single BOQ detail item.
    
    Args:
        boqheadid: BOQ head ID from the head API response
        boq_item: Dictionary containing BOQ item data
        summary_data: Dictionary containing summary data (for total amounts)
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Extract total amount from summary
    total_amount_figure = 0.0
    total_amount_word = ""
    
    if "Total in Figures" in summary_data:
        total_row = summary_data["Total in Figures"]
        total_amount_figure = safe_float(total_row.get("Total Amount (incl. GST)", "0.0"))
        total_amount_word = total_row.get("Total Amount (In Words)", "")
    
    # Prepare payload
    payload = {
        "boqheadid": boqheadid,
        "boqsino": safe_int(boq_item.get("Sl. No.", "0")),
        "itemdescription": boq_item.get("Item Description", ""),
        "quantity": safe_float(boq_item.get("Quantity", "0.0")),
        "units": boq_item.get("Units", ""),
        "estimatedrate": safe_float(boq_item.get("Estimated Rate (incl. GST)", "0.0")),
        "itemamount": safe_float(boq_item.get("Total Amount (incl. GST)", "0.0")),
        "totalamountfigure": total_amount_figure,
        "totalamountword": total_amount_word
    }
    
    try:
        response = requests.post(BOQ_DETAIL_API, json=payload, timeout=30)
        response.raise_for_status()
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"      ✗ Error storing BOQ detail for item {payload['boqsino']}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
                print(f"        Response: {error_detail}")
            except:
                print(f"        Response status: {e.response.status_code}")
        return False

def store_boq_from_html(tenderid: str, html_content: str) -> Tuple[int, int]:
    """
    Store BOQ data from HTML content.
    
    Args:
        tenderid: Tender ID string
        html_content: HTML content as string
        
    Returns:
        Tuple of (success_count, error_count)
    """
    boq_success = 0
    boq_error = 0
    
    # Extract BOQ data from HTML using extract_boq_data
    boq_data = extract_boq_data(html_content)
    
    # Check for errors in extraction
    if "error" in boq_data:
        print(f"    ✗ Error extracting BOQ data: {boq_data.get('error')}")
        return boq_success, 1
    
    # Store BOQ head
    boqheadid = store_boq_head(tenderid)
    if boqheadid is None:
        print(f"    ✗ Failed to store BOQ head. Aborting detail storage.")
        return boq_success, 1
    
    boq_success += 1  # Count head as success
    print(f"    ✓ BOQ head created with ID: {boqheadid}")
    
    # Store BOQ details
    boq_items = boq_data.get("boq_items", [])
    summary_data = boq_data.get("summary", {})
    
    if not boq_items:
        print(f"    ⚠ Warning: No BOQ items found in HTML data")
        return boq_success, boq_error
    
    print(f"    Storing {len(boq_items)} BOQ detail items...")
    for item in boq_items:
        if store_boq_detail(boqheadid, item, summary_data):
            boq_success += 1
        else:
            boq_error += 1
    
    print(f"    ✓ Successfully stored {boq_success - 1}/{len(boq_items)} BOQ detail items (1 head + {boq_success - 1} details)")
    return boq_success, boq_error

def send_document_to_api(document_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send tender document data to the API
    
    Args:
        document_data: Dictionary containing document data to be sent
                      Format: {"tenderid": "...", "doctype": "...", "s3url": "...", "docname": "..."}
        
    Returns:
        Dictionary with response status and data
    """
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(TENDER_DOCUMENTS_API, headers=headers, json=document_data, timeout=30)
        
        # Try to get JSON response
        try:
            response_data = response.json()
        except:
            response_data = {"message": response.text, "status_code": response.status_code}
        
        # Check if request was successful
        if response.status_code in [200, 201]:
            return {
                "success": True,
                "status_code": response.status_code,
                "response": response_data,
                "tender_id": document_data.get("tenderid"),
                "s3url": document_data.get("s3url")
            }
        else:
            return {
                "success": False,
                "status_code": response.status_code,
                "response": response_data,
                "tender_id": document_data.get("tenderid"),
                "s3url": document_data.get("s3url"),
                "error": f"API returned status code {response.status_code}"
            }
            
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e),
            "tender_id": document_data.get("tenderid"),
            "s3url": document_data.get("s3url")
        }

def store_tenders_with_documents(mapped_tender_file: str, mapped_documents_file: str, original_json_file: str):
    """
    Read mapped tender data and documents, then store each tender with its documents and BOQ data
    
    Args:
        mapped_tender_file: Path to the mapped tender JSON file (e.g., "mapped_jharkhandtenders_gov_in.json")
        mapped_documents_file: Path to the mapped documents JSON file (e.g., "mapped_doc_jharkhandtenders_gov_in.json")
        original_json_file: Path to the original JSON file (e.g., "jharkhandtenders_gov_in.json") to get BOQ HTML data
    """
    print(f"Reading tender data from: {mapped_tender_file}")
    
    # Read mapped tender data
    try:
        tender_data_list = read_data(mapped_tender_file)
    except FileNotFoundError:
        print(f"✗ Error: File not found: {mapped_tender_file}")
        return
    except json.JSONDecodeError as e:
        print(f"✗ Error: Invalid JSON in file: {e}")
        return
    except Exception as e:
        print(f"✗ Error reading file: {e}")
        return
    
    print(f"Reading tender documents from: {mapped_documents_file}")
    
    # Read mapped documents data
    try:
        documents_list = read_data(mapped_documents_file)
    except FileNotFoundError:
        print(f"⚠ Warning: Documents file not found: {mapped_documents_file}")
        print("  Continuing without documents...")
        documents_list = []
    except json.JSONDecodeError as e:
        print(f"⚠ Warning: Invalid JSON in documents file: {e}")
        print("  Continuing without documents...")
        documents_list = []
    except Exception as e:
        print(f"⚠ Warning: Error reading documents file: {e}")
        print("  Continuing without documents...")
        documents_list = []
    
    print(f"Reading original JSON file for BOQ data from: {original_json_file}")
    
    # Read original JSON file to get BOQ HTML data
    boq_data_by_tender = {}
    try:
        original_data = read_data(original_json_file)
        for tender in original_data:
            tender_id = extract_tender_id(tender.get("TenderId"))
            if tender_id:
                boq_html = tender.get("BOQ")
                if boq_html and boq_html.strip():
                    boq_data_by_tender[tender_id] = boq_html
        print(f"  Found BOQ data for {len(boq_data_by_tender)} tenders")
    except FileNotFoundError:
        print(f"⚠ Warning: Original JSON file not found: {original_json_file}")
        print("  Continuing without BOQ data...")
    except json.JSONDecodeError as e:
        print(f"⚠ Warning: Invalid JSON in original file: {e}")
        print("  Continuing without BOQ data...")
    except Exception as e:
        print(f"⚠ Warning: Error reading original JSON file: {e}")
        print("  Continuing without BOQ data...")
    
    # Group documents by tender_id
    documents_by_tender = {}
    for document in documents_list:
        tender_id = document.get("tenderid")
        if tender_id:
            if tender_id not in documents_by_tender:
                documents_by_tender[tender_id] = []
            documents_by_tender[tender_id].append(document)
    
    total_tenders = len(tender_data_list)
    total_documents = len(documents_list)
    print(f"\nFound {total_tenders} tenders and {total_documents} documents to process")
    print(f"Documents grouped for {len(documents_by_tender)} unique tenders")
    print(f"BOQ data available for {len(boq_data_by_tender)} tenders\n")
    
    # Track statistics
    tender_success_count = 0
    tender_error_count = 0
    doc_success_count = 0
    doc_error_count = 0
    boq_file_success_count = 0
    boq_file_error_count = 0
    boq_data_success_count = 0
    boq_data_error_count = 0
    nit_success_count = 0
    nit_error_count = 0
    
    # Process each tender with its documents and BOQ data
    for index, tender_data in enumerate(tender_data_list, 1):
        tender_id = tender_data.get("TenderID", "Unknown")
        
        # Get documents for this tender
        documents_for_tender = documents_by_tender.get(tender_id, [])
        
        # Get BOQ HTML for this tender
        boq_html = boq_data_by_tender.get(tender_id)
        
        # Store tender and its documents and BOQ data
        t_success, t_error, d_success, d_error, bf_success, bf_error, bd_success, bd_error, n_success, n_error = store_single_tender_with_documents(
            tender_data, documents_for_tender, boq_html, index, total_tenders
        )
        
        tender_success_count += t_success
        tender_error_count += t_error
        doc_success_count += d_success
        doc_error_count += d_error
        boq_file_success_count += bf_success
        boq_file_error_count += bf_error
        boq_data_success_count += bd_success
        boq_data_error_count += bd_error
        nit_success_count += n_success
        nit_error_count += n_error
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Tender Data:")
    print(f"  Total tenders processed: {total_tenders}")
    print(f"  Successfully stored: {tender_success_count}")
    print(f"  Failed: {tender_error_count}")
    print()
    print(f"Tender Documents:")
    print(f"  Total documents processed: {total_documents}")
    print(f"  Successfully stored: {doc_success_count}")
    print(f"  Failed: {doc_error_count}")
    print(f"  Unique tenders with documents: {len(documents_by_tender)}")
    print()
    print(f"BOQ Files (from zip extraction):")
    print(f"  Successfully stored: {boq_file_success_count}")
    print(f"  Failed: {boq_file_error_count}")
    print()
    print(f"BOQ Data (head + details from HTML):")
    print(f"  Successfully stored: {boq_data_success_count}")
    print(f"  Failed: {boq_data_error_count}")
    print()
    print(f"NIT Documents (from content_pdf folder):")
    print(f"  Successfully stored: {nit_success_count}")
    print(f"  Failed: {nit_error_count}")
    print("=" * 60)

if __name__ == "__main__":
    # Specify the original JSON file to get BOQ HTML data
    # This should be the original input file (e.g., "jharkhandtenders_gov_in.json")
    original_json_file = "test_15.json"

    # Specify the mapped tender data file
    # Change this to your mapped tender JSON file
    mapped_tender_file = "mapped_test_15.json"
    
    # Specify the mapped documents file
    # This should be the output from map_tender_documents.py
    # Format: "mapped_doc_{original_file_name}"
    mapped_documents_file = "mapped_doc_test_15.json"
    
    
    # Store tenders with their documents and BOQ data (one tender at a time)
    print("=" * 60)
    print("STORING TENDERS WITH DOCUMENTS AND BOQ DATA")
    print("=" * 60)
    store_tenders_with_documents(mapped_tender_file, mapped_documents_file, original_json_file)