import json
import requests
from urllib.parse import quote

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
    POST_API = "http://13.202.159.122:8000/tender-results/"  # EC2 API
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
    BASE_API = "http://13.202.159.122:8000/tender-results/update-result"  # EC2 API
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

def send_result_document_to_api(document_data):
    """
    Send result document data to the API
    
    Args:
        document_data: Dictionary with keys: tenderid, doctype, s3url, docname
    
    Returns:
        Dictionary with response status and data
    """
    RESULT_DOCUMENTS_API = "http://13.202.159.122:8000/result-documents/"
    
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
    
    for tender_id in successfully_processed_tenders:
        documents_for_tender = documents_by_tender.get(tender_id, [])
        
        if documents_for_tender:
            tenders_with_docs += 1
            print(f"\nStoring {len(documents_for_tender)} document(s) for tender: {tender_id}")
            
            for doc_index, document_data in enumerate(documents_for_tender, 1):
                doc_result = send_result_document_to_api(document_data)
                
                if doc_result.get("success"):
                    total_docs_uploaded += 1
                    print(f"  ✓ [{doc_index}/{len(documents_for_tender)}] Document stored: {document_data.get('s3url', 'Unknown')}")
                else:
                    total_docs_failed += 1
                    print(f"  ✗ [{doc_index}/{len(documents_for_tender)}] Failed to store document")
                    print(f"    S3URL: {document_data.get('s3url', 'Unknown')}")
                    if "error" in doc_result:
                        print(f"    Error: {doc_result['error']}")
    
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
    print("=" * 60)
    print("\n✓ All records processed!")