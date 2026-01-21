import json
import os
import requests
import boto3
from urllib.parse import quote, urlparse
from botocore.exceptions import ClientError
from botocore.config import Config
from typing import Optional, Dict, Tuple
from dotenv import load_dotenv

load_dotenv()

# AWS S3 Configuration
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION")

def Read_Data(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return data

def extract_tender_id(tender_id):
    """Extract the first tender ID from string that may contain multiple IDs separated by <br>"""
    if not tender_id or tender_id == "":
        return None
    # Split by <br> and take the first one, strip whitespace
    parts = str(tender_id).split("<br>")
    return parts[0].strip() if parts else None

def map_to_update_payload(item):
    """Map the mapped result data to the update API payload format"""
    # For GEM results, keep the complete tender ID (including <br> part)
    # For CPPP, extract first tender ID if multiple
    tender_id_raw = item.get("tenderid")
    if tender_id_raw and str(tender_id_raw).upper().startswith("GEM"):
        # GEM: Keep complete ID
        tender_id = str(tender_id_raw).strip() if tender_id_raw else None
    else:
        # CPPP: Extract first tender ID if multiple
        tender_id = extract_tender_id(tender_id_raw)
    aoc_status = item.get("aocstatus")
    
    # Handle rank: keep as null if not set, don't default to "0"
    rank_value = item.get("rank")
    if rank_value is None:
        rank_value = None  # Keep as null
    elif rank_value == "":
        rank_value = None
    else:
        rank_value = str(rank_value)
    
    payload = {
        "aocstatus": aoc_status,
        "aocid": item.get("aocid") or 0,
        "contractvalue": item.get("contractvalue") or 0,
        "contractdate": item.get("contractdate"),
        "tenderid": tender_id,
        "siteid": item.get("siteid") or 0,
        "truid": item.get("truid") or "",
        "technicalbidopeningdate": item.get("technicalbidopeningdate"),
        "technicalevaluationdate": item.get("technicalevaluationdate"),
        "financebidopeningdate": item.get("financebidopeningdate"),  # Fixed: use financebidopeningdate (not financialbidopeningdate)
        "financeevaluationdate": item.get("financeevaluationdate"),  # Fixed: use financeevaluationdate
        "downloaddate": item.get("downloaddate"),
        "publishdate": item.get("publishdate"),  # From PublicationDate field
        "ravalidity": item.get("ravalidity"),  # From bidvalidity field
        "ownership": item.get("ownership"),  # From ownership field
        "bidnumber": item.get("bidnumber") or 0,
        "biddername": item.get("biddername") or "",
        "rank": rank_value,
        "bidamount": item.get("bidamount"),  # Keep as null if not present, don't default to 0
        "agencyname": item.get("agencyname") or "",  # New field: CompanyName -> agencyname
        "tendervalue": item.get("tendervalue") or 0,  # New field: TenderValue -> tendervalue
        "address": item.get("address") or "",  # New field: city+state+country -> address
        "submissiondate": item.get("submissiondate"),  # New field: SubmissionDate -> submissiondate
        "workdescription": item.get("workdescription") or "",  # New field: ProductDetails -> workdescription
        "cityname": item.get("cityname") or "",  # New field: City -> cityname
        "statename": item.get("statename") or "",  # New field: State -> statename
        "countryname": item.get("countryname") or "",  # New field: Country -> countryname
        "tendersource": item.get("tendersource") or "CPPP",  # GEM if tenderid starts with 'GEM', else 'CPPP'
        "resultstatus": item.get("newresultstatus") or 0,  # Map from newresultstatus
        "updatedby": item.get("updatedby") or 0,
        "isdeleted": item.get("isdeleted") or 0,
        "deletedby": item.get("deletedby") or 0
    }
    
    # Add status fields based on aocstatus
    if aoc_status == "Technical":
        payload["technicalbidstatus"] = item.get("technicalbidstatus") or ""
    elif aoc_status == "Financial":
        # For Financial stage: include both technicalbidstatus and financialbidstatus
        # Technical bidders (bidtype=0) will have technicalbidstatus set
        # Financial bidders (bidtype=1) will have financialbidstatus set
        technical_status = item.get("technicalbidstatus")
        if technical_status is not None and str(technical_status).strip():
            payload["technicalbidstatus"] = str(technical_status).strip()
        else:
            payload["technicalbidstatus"] = ""
        
        # For Financial stage: always include financialbidstatus
        # Use the value from item, default to "Accepted" if not set (for Financial bidders)
        financial_status = item.get("financialbidstatus")
        if financial_status is not None and str(financial_status).strip():
            payload["financialbidstatus"] = str(financial_status).strip()
        else:
            # Default to "Accepted" for Financial stage if not explicitly set
            payload["financialbidstatus"] = "Accepted"
    elif aoc_status == "AOC":
        # For AOC stage: include all three status fields
        # Technical bidders (bidtype=0) will have technicalbidstatus set
        # Financial bidders (bidtype=1) will have financialbidstatus set
        # AOC bidders (bidtype=2) will have aocbidstatus set
        technical_status = item.get("technicalbidstatus")
        if technical_status is not None and str(technical_status).strip():
            payload["technicalbidstatus"] = str(technical_status).strip()
        else:
            payload["technicalbidstatus"] = ""
        
        financial_status = item.get("financialbidstatus")
        if financial_status is not None and str(financial_status).strip():
            payload["financialbidstatus"] = str(financial_status).strip()
        else:
            payload["financialbidstatus"] = ""
        
        aoc_status_value = item.get("aocbidstatus")
        if aoc_status_value is not None and str(aoc_status_value).strip():
            payload["aocbidstatus"] = str(aoc_status_value).strip()
        else:
            payload["aocbidstatus"] = ""
    
    return payload

def Send_Data_to_DB(item):
    """Send tender result data using the normal POST API (for Technical status)"""
    POST_API = "https://api.tenderapex.com/tender-results/"  # EC2 API
    # POST_API = "http://192.168.1.19:8000/tender-results/"  # Umang API
    
    # Map data to API payload format (same as update payload)
    payload = map_to_update_payload(item)
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(POST_API, headers=headers, json=payload, timeout=30)
        
        # Try to parse JSON response
        try:
            response_data = response.json() if response.text else {"message": "No content"}
        except:
            response_data = {"message": response.text[:200] if response.text else "No content", "raw_status": response.status_code}
        
        return {
            "status_code": response.status_code,
            "response": response_data,
            "tender_id": item.get("tenderid"),
            "bidder_name": item.get("biddername"),
            "success": response.status_code in [200, 201]
        }
    except requests.exceptions.RequestException as e:
        return {
            "error": str(e),
            "tender_id": item.get("tenderid"),
            "bidder_name": item.get("biddername"),
            "success": False
        }

def Update_Result_Data(item):
    """Update tender result data using the update-result API (for AOC and Financial status)"""
    BASE_API = "https://api.tenderapex.com/tender-results/update-result"  # EC2 API
    # BASE_API = "http://192.168.1.19:8000/tender-results/update-result"  # Umang API
    
    # Extract tender_id and bidder_name for query parameters
    # For GEM results, keep the complete tender ID (including <br> part)
    # For CPPP, extract first tender ID if multiple
    tender_id_raw = item.get("tenderid")
    if tender_id_raw and str(tender_id_raw).upper().startswith("GEM"):
        # GEM: Keep complete ID
        tender_id = str(tender_id_raw).strip() if tender_id_raw else None
    else:
        # CPPP: Extract first tender ID if multiple
        tender_id = extract_tender_id(tender_id_raw)
    bidder_name = item.get("biddername") or ""
    
    if not tender_id or not bidder_name:
        return {"error": "Missing tender_id or bidder_name"}
    
    # URL encode the parameters
    tender_id_encoded = quote(tender_id, safe='')
    bidder_name_encoded = quote(bidder_name, safe='')
    
    # Build URL with only tender_id and bidder_name as query parameters
    url = f"{BASE_API}?tender_id={tender_id_encoded}&bidder_name={bidder_name_encoded}"
    
    # Map data to API payload format
    payload = map_to_update_payload(item)
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.patch(url, headers=headers, json=payload, timeout=30)
        return {
            "status_code": response.status_code,
            "response": response.json() if response.text else {"message": "No content"},
            "tender_id": tender_id,
            "bidder_name": bidder_name,
            "success": response.status_code in [200, 201, 204]
        }
    except requests.exceptions.RequestException as e:
        return {
            "error": str(e),
            "tender_id": tender_id,
            "bidder_name": bidder_name,
            "success": False
        }

def sanitize_tender_id_for_filename(tender_id: str) -> str:
    """
    Sanitize tender ID to be safe for use in filenames.
    Replaces invalid filename characters with underscores.
    
    Args:
        tender_id: Original tender ID (e.g., "GEM/2025/B/7027851")
        
    Returns:
        Sanitized tender ID safe for filenames (e.g., "GEM_2025_B_7027851")
    """
    if not tender_id:
        return ""
    
    # Replace invalid filename characters with underscores
    # Common invalid characters: / \ : * ? " < > |
    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    sanitized = str(tender_id).strip()
    
    for char in invalid_chars:
        sanitized = sanitized.replace(char, '_')
    
    # Remove any leading/trailing dots or spaces (Windows doesn't allow these)
    sanitized = sanitized.strip('. ')
    
    return sanitized

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

def extract_files_directory_path_from_documents(documents_for_tender: list) -> Optional[str]:
    """
    Extract the directory path up to and including '/files/' from existing documents' S3 URLs.
    This path will be used to create NIT folder at the same level as other files.
    
    Example:
        Input S3 URL: https://shubhum-object.s3.ap-south-1.amazonaws.com/PythonDocumentResults/defproc.gov.inpy/files/file.pdf
        Output: PythonDocumentResults/defproc.gov.inpy/files/
        
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

def upload_result_nit_pdf_to_s3(pdf_file_path: str, tender_id: str, pdf_suffix: str, files_directory_path: str,
                                aws_access_key: str, aws_secret_key: str,
                                bucket_name: str, region: str) -> Optional[Dict[str, str]]:
    """
    Upload NIT PDF file to S3 bucket under {files_directory_path}NIT/ folder.
    The NIT folder will be created at the same level as other files.
    
    Example:
        files_directory_path: PythonDocumentResults/defproc.gov.inpy/files/
        Result: PythonDocumentResults/defproc.gov.inpy/files/NIT/{tender_id}_{pdf_suffix}.pdf
    
    Args:
        pdf_file_path: Local path to the PDF file (e.g., "result_content_pdf/{tender_id}_1.pdf")
        tender_id: Tender ID for filename
        pdf_suffix: Suffix for PDF filename (e.g., "1" or "2")
        files_directory_path: Directory path up to '/files/' (e.g., "PythonDocumentResults/defproc.gov.inpy/files/")
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
        
        # Create S3 key: {files_directory_path}NIT/{sanitized_tender_id}_{pdf_suffix}.pdf
        # files_directory_path already ends with '/files/', so we just append 'NIT/'
        # Sanitize tender_id for S3 key (replace invalid characters)
        sanitized_tender_id = sanitize_tender_id_for_filename(tender_id)
        s3_key = f"{files_directory_path}NIT/{sanitized_tender_id}_{pdf_suffix}.pdf"
        
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

def process_result_nit_documents(tender_id: str, documents_for_tender: list,
                                  aws_access_key: str, aws_secret_key: str,
                                  bucket_name: str, region: str) -> Tuple[int, int]:
    """
    Process NIT PDF files from result_content_pdf folder, upload to S3, and store in result_documents table.
    Handles both tenderid_1.pdf (from Content) and tenderid_2.pdf (from Content1).
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
    
    # Check if result_content_pdf folder exists
    result_content_pdf_folder = "result_content_pdf"
    if not os.path.exists(result_content_pdf_folder):
        return nit_success, nit_error
    
    # Extract files directory path from existing documents
    files_directory_path = extract_files_directory_path_from_documents(documents_for_tender)
    if not files_directory_path:
        print(f"  Processing NIT: No files directory path found in documents for {tender_id}, skipping NIT upload")
        return nit_success, nit_error
    
    print(f"  Processing NIT documents for {tender_id}...")
    print(f"    Using files directory path: {files_directory_path}")
    
    # Get sanitized tender ID for filename lookup
    # Check if any document has sanitized_tender_id stored, otherwise sanitize on the fly
    sanitized_tender_id = None
    for doc in documents_for_tender:
        if doc.get('sanitized_tender_id'):
            sanitized_tender_id = doc.get('sanitized_tender_id')
            break
    
    # If not found in documents, sanitize the tender_id
    if not sanitized_tender_id:
        sanitized_tender_id = sanitize_tender_id_for_filename(tender_id)
    
    # Process first NIT PDF (from Content field) - tenderid_1.pdf
    pdf_file_path_1 = os.path.join(result_content_pdf_folder, f"{sanitized_tender_id}_1.pdf")
    if os.path.exists(pdf_file_path_1):
        print(f"    Processing NIT document 1 (from Content)...")
        file_info = upload_result_nit_pdf_to_s3(
            pdf_file_path_1, tender_id, "1", files_directory_path,
            aws_access_key, aws_secret_key, bucket_name, region
        )
        
        if file_info:
            # Store in result_documents API
            document_data = {
                'tenderid': tender_id,
                'doctype': file_info['doctype'],
                's3url': file_info['s3url'],
                'docname': file_info['docname']
            }
            
            doc_result = send_result_document_to_api(document_data)
            
            if doc_result.get("success"):
                nit_success += 1
                print(f"    ✓ NIT document 1 stored: {file_info['docname']}")
            else:
                nit_error += 1
                print(f"    ✗ Failed to store NIT document 1: {file_info['docname']}")
                if "error" in doc_result:
                    print(f"      Error: {doc_result['error']}")
        else:
            nit_error += 1
            print(f"    ✗ Failed to upload NIT PDF 1 to S3")
    
    # Process second NIT PDF (from Content1 field) - tenderid_2.pdf
    pdf_file_path_2 = os.path.join(result_content_pdf_folder, f"{sanitized_tender_id}_2.pdf")
    if os.path.exists(pdf_file_path_2):
        print(f"    Processing NIT document 2 (from Content1)...")
        file_info = upload_result_nit_pdf_to_s3(
            pdf_file_path_2, tender_id, "2", files_directory_path,
            aws_access_key, aws_secret_key, bucket_name, region
        )
        
        if file_info:
            # Store in result_documents API
            document_data = {
                'tenderid': tender_id,
                'doctype': file_info['doctype'],
                's3url': file_info['s3url'],
                'docname': file_info['docname']
            }
            
            doc_result = send_result_document_to_api(document_data)
            
            if doc_result.get("success"):
                nit_success += 1
                print(f"    ✓ NIT document 2 stored: {file_info['docname']}")
            else:
                nit_error += 1
                print(f"    ✗ Failed to store NIT document 2: {file_info['docname']}")
                if "error" in doc_result:
                    print(f"      Error: {doc_result['error']}")
        else:
            nit_error += 1
            print(f"    ✗ Failed to upload NIT PDF 2 to S3")
    
    return nit_success, nit_error

def send_result_document_to_api(document_data):
    """
    Send result document data to the API
    
    Args:
        document_data: Dictionary with keys: tenderid, doctype, s3url, docname
    
    Returns:
        Dictionary with response status and data
    """
    RESULT_DOCUMENTS_API = "https://api.tenderapex.com/result-documents/"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(RESULT_DOCUMENTS_API, headers=headers, json=document_data, timeout=30)
        
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

if __name__ == "__main__":
    # File paths
    input_file = "Tech_Fin_AOC_Json/Technical_Json/eproc_punjab_gov_in_TEvolution.json"
    mapped_results_file = f"Tech_Fin_AOC_Json/Technical_Json/mapped_{input_file.split('/')[-1]}"
    mapped_documents_file = f"Tech_Fin_AOC_Json/Technical_Json/mapped_doc_{input_file.split('/')[-1]}"
    
    # Read mapped result data
    print(f"Reading mapped result data from: {mapped_results_file}")
    try:
        data = Read_Data(mapped_results_file)
    except FileNotFoundError:
        print(f"✗ Error: File not found: {mapped_results_file}")
        print("  Please update the file name in the script to match your actual file.")
        exit(1)
    
    # Read mapped result documents
    print(f"Reading mapped result documents from: {mapped_documents_file}")
    try:
        mapped_documents = Read_Data(mapped_documents_file)
    except FileNotFoundError:
        print(f"⚠ Warning: File not found: {mapped_documents_file}")
        print("  Continuing without documents...")
        mapped_documents = []
    
    # Group documents by tender_id
    documents_by_tender = {}
    for document in mapped_documents:
        tender_id = document.get("tenderid")
        if tender_id:
            if tender_id not in documents_by_tender:
                documents_by_tender[tender_id] = []
            documents_by_tender[tender_id].append(document)
    
    print(f"\nFound {len(data)} result records and {len(mapped_documents)} document records")
    print(f"Documents grouped for {len(documents_by_tender)} unique tenders")
    print("=" * 60)
    
    # Separate records by aocstatus
    technical_records = [item for item in data if item.get("aocstatus") == "Technical"]
    update_records = [item for item in data if item.get("aocstatus") in ["AOC", "Financial"]]
    
    print(f"\nTotal records: {len(data)}")
    print(f"Technical records (POST): {len(technical_records)}")
    print(f"Update records (PATCH - AOC/Financial): {len(update_records)}\n")
    
    # Track successfully processed tenders (to store documents only once per tender)
    successfully_processed_tenders = set()
    
    # Process Technical records with POST API
    if technical_records:
        print("Processing Technical records (POST API)...")
        for item in technical_records:
            response = Send_Data_to_DB(item)
            tender_id = extract_tender_id(response.get('tender_id'))
            
            if response.get("success"):
                if tender_id:
                    successfully_processed_tenders.add(tender_id)
                print(f"  ✓ Tender: {response.get('tender_id')}, Bidder: {response.get('bidder_name')}")
            else:
                print(f"  ✗ Tender: {response.get('tender_id')}, Bidder: {response.get('bidder_name')}")
                # Print error details
                if "error" in response:
                    print(f"    Error: {response.get('error')}")
                elif "status_code" in response:
                    status_code = response.get("status_code")
                    response_data = response.get("response", {})
                    print(f"    Status Code: {status_code}")
                    if isinstance(response_data, dict):
                        # Print error message from API response
                        error_msg = response_data.get("detail") or response_data.get("message") or response_data.get("error") or str(response_data)
                        print(f"    API Error: {error_msg}")
                    else:
                        print(f"    API Response: {response_data}")
            print()
    
    # Process AOC and Financial records with PATCH update API
    if update_records:
        print("Processing AOC/Financial records (PATCH update API)...")
        for item in update_records:
            response = Update_Result_Data(item)
            tender_id = extract_tender_id(response.get('tender_id'))
            
            # If update returns 404 (record not found), create it with POST API
            if response.get("status_code") == 404:
                print(f"  → Record not found (404), creating with POST API...")
                response = Send_Data_to_DB(item)
                tender_id = extract_tender_id(response.get('tender_id'))
                print(f"  → POST API Response: {response}")
            
            if response.get("success"):
                if tender_id:
                    successfully_processed_tenders.add(tender_id)
                print(f"  ✓ Tender: {response.get('tender_id')}, Bidder: {response.get('bidder_name')}")
            else:
                print(f"  ✗ Tender: {response.get('tender_id')}, Bidder: {response.get('bidder_name')}")
                if "error" in response:
                    print(f"    Error: {response.get('error')}")
            print()
    
    # Store result documents for successfully processed tenders
    print("=" * 60)
    print("STORING RESULT DOCUMENTS")
    print("=" * 60)
    
    total_docs_uploaded = 0
    total_docs_failed = 0
    tenders_with_docs = 0
    total_nit_success = 0
    total_nit_error = 0
    
    for tender_id in successfully_processed_tenders:
        documents_for_tender = documents_by_tender.get(tender_id, [])
        
        if documents_for_tender:
            tenders_with_docs += 1
            print(f"\nStoring {len(documents_for_tender)} document(s) for tender: {tender_id}")
            
            # Filter out NIT documents with empty s3url (they will be uploaded from local PDFs)
            documents_to_store = []
            for doc in documents_for_tender:
                # Skip NIT documents that have local_pdf_path (they need to be uploaded first)
                if doc.get('doctype') == 'NIT' and doc.get('local_pdf_path'):
                    continue
                # Skip documents with empty s3url
                if not doc.get('s3url'):
                    continue
                documents_to_store.append(doc)
            
            # Store regular documents (with S3 URLs)
            for doc_index, document_data in enumerate(documents_to_store, 1):
                doc_result = send_result_document_to_api(document_data)
                
                if doc_result.get("success"):
                    total_docs_uploaded += 1
                    print(f"  ✓ [{doc_index}/{len(documents_to_store)}] Document stored: {document_data.get('s3url', 'Unknown')}")
                else:
                    total_docs_failed += 1
                    print(f"  ✗ [{doc_index}/{len(documents_to_store)}] Failed to store document")
                    print(f"    S3URL: {document_data.get('s3url', 'Unknown')}")
                    if "error" in doc_result:
                        print(f"    Error: {doc_result['error']}")
            
            # Process NIT documents (upload from local PDFs and store)
            if AWS_ACCESS_KEY and AWS_SECRET_KEY and BUCKET_NAME and AWS_REGION:
                nit_success, nit_error = process_result_nit_documents(
                    tender_id, documents_for_tender,
                    AWS_ACCESS_KEY, AWS_SECRET_KEY, BUCKET_NAME, AWS_REGION
                )
                total_nit_success += nit_success
                total_nit_error += nit_error
            else:
                print(f"  ⚠ AWS credentials not configured, skipping NIT PDF upload")
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Result Data:")
    print(f"  Total records processed: {len(data)}")
    print(f"  Successfully processed tenders: {len(successfully_processed_tenders)}")
    print()
    print(f"Result Documents:")
    print(f"  Total documents available: {len(mapped_documents)}")
    print(f"  Tenders with documents stored: {tenders_with_docs}")
    print(f"  Successfully stored: {total_docs_uploaded}")
    print(f"  Failed: {total_docs_failed}")
    print()
    print(f"NIT Documents:")
    print(f"  Successfully uploaded and stored: {total_nit_success}")
    print(f"  Failed: {total_nit_error}")
    print("=" * 60)
    print("\n✓ All records processed!")