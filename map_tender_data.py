import json
import os
from datetime import datetime
from typing import Dict, Any, Optional, List

from html_to_json import extract_boq_data
from html_to_pdf import convert_html_to_pdf
import tempfile

def convert_date_format(date_str: Optional[str]) -> Optional[str]:
    """Convert date from various formats to YYYY-MM-DD format.
    Supports:
    - YYYY-MM-DD HH:MM:SS (e.g., "2025-12-16 16:59:12")
    - DD/MM/YYYY
    - DD-MM-YYYY HH:MM AM/PM (e.g., "22-12-2025 11:30 AM")
    - DD-MMM-YYYY HH:MM AM/PM (e.g., "22-Dec-2025 03:00 PM")
    - DD-MMM-YYYY (without time)
    - DD-MM-YYYY (without time)
    """
    if not date_str or date_str == "":
        return None
    
    # Strip whitespace
    date_str = date_str.strip()
    if not date_str:
        return None
    
    # Try different date formats
    date_formats = [
        "%Y-%m-%d %H:%M:%S",  # YYYY-MM-DD HH:MM:SS format (e.g., "2025-12-16 16:59:12")
        "%Y-%m-%d",  # YYYY-MM-DD format (without time)
        "%d/%m/%Y",  # DD/MM/YYYY format
        "%d-%m-%Y %I:%M %p",  # DD-MM-YYYY HH:MM AM/PM format (e.g., "22-12-2025 11:30 AM")
        "%d-%b-%Y %I:%M %p",  # DD-MMM-YYYY HH:MM AM/PM format (e.g., "22-Dec-2025 03:00 PM")
        "%d-%b-%Y",  # DD-MMM-YYYY format (without time)
        "%d-%m-%Y",  # DD-MM-YYYY format (without time)
    ]
    
    for fmt in date_formats:
        try:
            date_obj = datetime.strptime(date_str, fmt)
            return date_obj.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    
    # If none of the formats work, return None
    return None

def extract_tender_id(tender_id: Optional[str]) -> Optional[str]:
    """Extract the first tender ID from string that may contain multiple IDs separated by <br>"""
    if not tender_id or tender_id == "":
        return None
    # Split by <br> and take the first one, strip whitespace
    parts = tender_id.split("<br>")
    return parts[0].strip() if parts else None

def convert_to_number(value: Any) -> Optional[float]:
    """Convert string number to float/int, return None if empty or invalid"""
    if value is None or value == "" or value == "null":
        return None
    try:
        # Try to convert to float first
        num = float(str(value).replace(",", ""))
        # Return as int if it's a whole number
        return int(num) if num.is_integer() else num
    except (ValueError, TypeError):
        return None

def build_address(city: Optional[str], state: Optional[str], country: Optional[str], pincode: Optional[str]) -> Optional[str]:
    """Build address string from city, state, country, and pincode"""
    parts = []
    if pincode:
        parts.append(str(pincode))
    if city:
        parts.append(city)
    if state:
        parts.append(state)
    if country:
        parts.append(country)
    return ", ".join(parts) if parts else None

def extract_quantity_from_work_description(work_desc: Optional[str]) -> Optional[int]:
    """Extract quantity from WorkDescription if it contains ##Quantity: X##"""
    if not work_desc:
        return None
    try:
        if "##Quantity:" in work_desc and "##" in work_desc:
            # Extract quantity from pattern like "##Quantity: 14##"
            parts = work_desc.split("##Quantity:")
            if len(parts) > 1:
                quantity_part = parts[1].split("##")[0].strip()
                return int(quantity_part)
    except (ValueError, IndexError):
        pass
    return None

def collect_boq_data(input_file):
    """
    Collect and process BOQ (Bill of Quantities) data from tender JSON file.
    Reads tender data, extracts BOQ HTML, saves to boq_html_data directory,
    and converts to JSON format in boq_json_data directory.
    """
    with open(input_file, "r") as f:
        data = json.load(f)

    if not os.path.exists("boq_html_data"):
        os.makedirs("boq_html_data")
    if not os.path.exists("boq_json_data"):
        os.makedirs("boq_json_data")

    processed_count = 0
    skipped_count = 0
    
    for tender in data:
        try:
            name = tender.get('TenderId')
            if not name:
                skipped_count += 1
                continue
                
            boq = tender.get('BOQ')
            if not boq or boq.strip() == "":
                skipped_count += 1
                continue
                
            boq = boq.replace("\n", "")

            with open(f"boq_html_data/{name}.html", "w", encoding='utf-8') as f:
                f.write(boq)
            
            boq_data = extract_boq_data(f"boq_html_data/{name}.html")
            with open(f"boq_json_data/{name}.json", "w", encoding='utf-8') as f:
                json.dump(boq_data, f, indent=4)
            
            processed_count += 1
        except Exception as e:
            print(f"Error processing tender {tender.get('TenderId', 'unknown')}: {e}")
            skipped_count += 1
            continue
    
    print(f"Processed {processed_count} BOQ files, skipped {skipped_count} tenders")

def convert_content_to_pdf(input_file):
    """
    Convert HTML content from tender JSON file to PDF files.
    Reads tender data, extracts Content HTML, converts to PDF,
    and saves in content_pdf folder with tenderid as filename.
    """
    with open(input_file, "r", encoding='utf-8') as f:
        data = json.load(f)

    # Create content_pdf directory if it doesn't exist
    if not os.path.exists("content_pdf"):
        os.makedirs("content_pdf")

    processed_count = 0
    skipped_count = 0
    
    for tender in data:
        try:
            tender_id = extract_tender_id(tender.get("TenderId"))
            if not tender_id:
                skipped_count += 1
                continue
            
            content = tender.get("Content")
            if not content or content.strip() == "":
                skipped_count += 1
                continue
            
            # Create temporary HTML file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_html:
                temp_html.write(content)
                temp_html_path = temp_html.name
            
            # Create PDF file path in content_pdf folder
            pdf_path = os.path.join("content_pdf", f"{tender_id}.pdf")
            
            # Convert HTML to PDF
            try:
                convert_html_to_pdf(temp_html_path, pdf_path)
                processed_count += 1
            except Exception as e:
                print(f"Error converting HTML to PDF for tender {tender_id}: {e}")
                skipped_count += 1
            finally:
                # Clean up temporary HTML file
                if os.path.exists(temp_html_path):
                    os.remove(temp_html_path)
                    
        except Exception as e:
            print(f"Error processing tender {tender.get('TenderId', 'unknown')}: {e}")
            skipped_count += 1
            continue
    
    print(f"Processed {processed_count} content PDF files, skipped {skipped_count} tenders")

def map_shubham_to_db(shubham_data: Dict[str, Any], base_id: int = 1) -> Dict[str, Any]:
    """
    Map Shubham's tender data structure to Pydantic model format (PascalCase)
    """
    # Extract tender ID (first one if multiple)
    tender_id = extract_tender_id(shubham_data.get("TenderId"))
    
    # Get TenderNumber - required field, use TenderNumber or TenderId as fallback
    tender_number = shubham_data.get("TenderNumber") or tender_id or ""
    if not tender_number:
        raise ValueError("TenderNumber is required but not found in data")
    
    # Build address from City + StateName + Country
    address = build_address(
        shubham_data.get("City"),
        shubham_data.get("StateName"),
        shubham_data.get("Country"),
        shubham_data.get("Pincode")
    )
    
    # Extract quantity - prefer Quantity field, fallback to WorkDescription
    quantity = convert_to_number(shubham_data.get("Quantity"))
    if quantity is None:
        quantity = extract_quantity_from_work_description(shubham_data.get("WorkDescription"))
    # Convert to int if it's a number (Pydantic expects Optional[int])
    if quantity is not None:
        try:
            quantity = int(float(quantity))
        except (ValueError, TypeError):
            quantity = None
    
    # Convert dates (return as string in YYYY-MM-DD format for Pydantic date type)
    submission_date = convert_date_format(shubham_data.get("SubmissionDate"))
    opening_date = convert_date_format(shubham_data.get("OpeningDate"))
    publish_date = convert_date_format(shubham_data.get("PublishDate"))
    prebid_date = convert_date_format(shubham_data.get("PreBidMeetingDate"))
    
    # Handle TenderValue - default to 0.0 if empty or None
    tender_value = shubham_data.get("TenderValue")
    if tender_value == "" or tender_value is None:
        tender_value = 0.0
    else:
        tender_value = convert_to_number(tender_value) or 0.0
    # Ensure it's a float
    tender_value = float(tender_value)
    
    # Handle EMDValue - default to 0.0 if empty or None
    emd_value = shubham_data.get("EMDValue")
    if emd_value == "" or emd_value is None:
        emd_value = 0.0
    else:
        emd_value = convert_to_number(emd_value) or 0.0
    # Ensure it's a float
    emd_value = float(emd_value)
    
    # Handle DocumentValue - default to 0.0 if empty or None
    document_value = shubham_data.get("DocumentValue")
    if document_value == "" or document_value is None:
        document_value = 0.0
    else:
        document_value = convert_to_number(document_value) or 0.0
    # Ensure it's a float
    document_value = float(document_value)
    
    # Handle StartupExemption - preserve the actual value, set to None if empty
    startup_exemption = shubham_data.get("StartupExemption")
    if startup_exemption is None or str(startup_exemption).strip() == "":
        startup_exemption = None
    else:
        # Preserve the actual value (e.g., "Yes", "No", etc.)
        startup_exemption = str(startup_exemption).strip()
    
    # Handle EMDExemption - preserve the actual value, set to None if empty
    emd_exemption = shubham_data.get("EMDExemption")
    if emd_exemption is None or str(emd_exemption).strip() == "":
        emd_exemption = None
    else:
        # Preserve the actual value (e.g., "Yes", "No", etc.)
        emd_exemption = str(emd_exemption).strip()
    
    # Handle TenderSource - check if contains "gem" (case-insensitive)
    tender_source = shubham_data.get("TenderSource")
    
        # Check if TenderSource contains "gem" (case-insensitive)
    tender_source_lower = str(tender_source).lower()
    if "gem" in tender_source_lower:
        tender_source = "GEM"
    else:
        tender_source = "CPPP"
    
    # Determine tender filename from available files
    tender_filename = None
    if shubham_data.get("TenderFileName_1"):
        tender_filename = "Tender Document"
    elif shubham_data.get("TenderFileName_2"):
        tender_filename = "Tender Document"
    elif shubham_data.get("TenderFileName_3"):
        tender_filename = "Tender Document"

    # Get CityId from CityName
    city = shubham_data.get("City")
    
    # Build mapped data structure matching Pydantic model (PascalCase)
    mapped_data = {
        "TenderNumber": tender_number,  # Required field
        "PublishDate": publish_date,
        "PurchaseFromDate": None,  # Not available in Shubham's data
        "PurchaseToDate": None,  # Not available in Shubham's data
        "SubmissionDate": submission_date,
        "SubmissionTime": None,  # Not available in Shubham's data
        "Quantity": quantity,
        "OpeningDate": opening_date,
        "OpeningTime": None,  # Not available in Shubham's data
        "TenderValue": tender_value,  # Default 0.0
        "EMDValue": emd_value,  # Default 0.0
        "DocumentValue": document_value,  # Default 0.0
        "CountryId": 101 if shubham_data.get("Country") == "India" else None,  # Default to India (101)
        "StateId": None,  # Will need to be mapped separately
        "CityId": None,  # Will need to be mapped separately
        "SiteID": None,
        "AgencyID": None,  # Will need to be mapped separately
        "CurrencyId": None,  # Will need to be mapped separately
        "TenderID": tender_id,
        "TenderType": shubham_data.get("TenderType"),
        "TenderCategory": shubham_data.get("TenderCategory"),
        "Title": shubham_data.get("WorkDescription") or shubham_data.get("WorkDescription"),
        "WorkDescription": shubham_data.get("Title"),
        "Location": None,  # Not available in Shubham's data
        "Address": address or shubham_data.get("Address"),
        "ContactPerson": None,  # Not available in Shubham's data
        "ContactEmail": None,  # Not available in Shubham's data
        "ContactPhone": None,  # Not available in Shubham's data
        "ContactFax": None,  # Not available in Shubham's data
        "Pincode": shubham_data.get("Pincode"),
        "Language": shubham_data.get("Language") or "English",
        "SearchKeyword": None,  # Not available in Shubham's data
        "TenderURL": shubham_data.get("TenderURL"),
        "AgencyName": shubham_data.get("Purchaser_Name"),
        "StateName": shubham_data.get("StateName"),
        # Map source City to CityName field expected by your DB/API
        "CityName": city,
        "TenderStatus": None,
        "TenderResultStatus": None,
        "Category": None,  # Will need classification
        "SubCategory": shubham_data.get("SubCategory"),
        "TenderHtmlDoc": None,
        "TenderPdfDoc": None,
        "TenderZipDoc": None,
        "DocumentURL": None,  # Using TenderURL as document URL
        "TenderFileName": tender_filename,
        "CreatedBy": "system",  # Default value
        "CreatedDate": None,  # Will be set by system (Field(default_factory=datetime.now))
        "UpdatedBy": None,
        "UpdatedDate": None,
        "EntryStatus": "New",  # Default value
        "IsActive": True,  # Default value
        "ClassificationStatus": None,
        "BaseType": None,  # Default base type (as per our_db.json example)
        "IsCorrigendumArrived": shubham_data.get("CorrigendumType") is not None,  # Default False
        "CorrigendumType": shubham_data.get("CorrigendumType"),
        "CorrigendumTitle": shubham_data.get("CorrigendumTitle"),  # Map from CorrigendumTitle field
        "PreBidMeetingDate": prebid_date,
        "PreBidMeetingTime": None,  # Not available in Shubham's data
        "DocumentPurchaseDate": None,
        "Country": shubham_data.get("Country"),
        "IsUploaded": False,  # Default value
        "EMDExemption": emd_exemption,
        "StartupExemption": startup_exemption,
        "DocumentType": "Tender Document",
        "TenderSource": tender_source,
        "ProductCategory": shubham_data.get("ProductCategory"),
        "PurAdd" : shubham_data.get("Pur_Add"),
        "Ownership": shubham_data.get("Ownership") or shubham_data.get("OwnerShip") or None  # Map from Ownership or OwnerShip field
    }
    
    return mapped_data

def is_valid_s3url(value: Any) -> bool:
    """Check if the TenderFileName value is valid (not empty, null, or whitespace)"""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return False

def map_tender_documents(input_file: str, output_file: str) -> List[Dict[str, Any]]:
    """
    Map tender documents from Shubham's data format to document payload format.
    Processes TenderFileName_1 through TenderFileName_N fields and creates document records.
    
    Args:
        input_file: Path to input JSON file (jharkhandtenders_gov_in.json)
        output_file: Path to output JSON file for mapped documents
    
    Returns:
        List of mapped document records
    """
    # Read input JSON file
    with open(input_file, 'r', encoding='utf-8') as f:
        tender_data = json.load(f)
    
    # Create output directory if it doesn't exist
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # List to store all document records
    document_records = []
    
    # Process each tender record
    for tender in tender_data:
        try:
            # Extract tender ID using the same logic as map_tender_data.py
            tender_id = extract_tender_id(tender.get("TenderId"))
            
            # Skip if no valid tender ID
            if not tender_id:
                continue
            
            # Check all TenderFileName_{n} fields dynamically
            # Start from 1 and check until we find no more fields
            file_index = 1
            while True:
                field_name = f"TenderFileName_{file_index}"
                s3url = tender.get(field_name)
                
                # If field doesn't exist, we've reached the end
                if field_name not in tender:
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
                
                # Safety limit: stop after checking up to 20 fields (in case of unexpected data)
                if file_index > 20:
                    break
                    
        except Exception as e:
            print(f"Error processing tender {tender.get('TenderId', 'unknown')}: {e}")
            continue
    
    # Write mapped documents to output file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(document_records, f, indent=2, ensure_ascii=False)
    
    print(f"Successfully mapped {len(document_records)} document records from {input_file} to {output_file}")
    return document_records

def Process_Tender_Data_JSON_File(input_file: str, output_file: str):
    """
    Process the json file and convert it to our database format
    """
    # Read Shubham's data
    with open(input_file, 'r', encoding='utf-8') as f:
        shubham_data = json.load(f)
    
    # Map each record
    mapped_records = []
    for record in shubham_data:
        mapped_record = map_shubham_to_db(record)
        mapped_records.append(mapped_record)
    
    # Create output directory if it doesn't exist
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # Write mapped data
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(mapped_records, f, indent=2, ensure_ascii=False)
    
    print(f"Successfully mapped {len(mapped_records)} records from {input_file} to {output_file}")
    return mapped_records

if __name__ == "__main__":
    # Process the mapping
    input_file = "test_15_cor.json"

    output_file = f"mapped_{input_file}"
    documents_output_file = f"mapped_doc_{input_file}"
    
    # Collect and process BOQ data
    print("Collecting BOQ data...")
    collect_boq_data(input_file)
    print("BOQ data collection completed.\n")
    
    # Convert HTML content to PDF
    print("Converting HTML content to PDF...")
    convert_content_to_pdf(input_file)
    print("Content PDF conversion completed.\n")
    
    # Process tender data mapping
    print("Processing tender data mapping...")
    Process_Tender_Data_JSON_File(input_file, output_file)
    print()
    
    # Process tender documents mapping
    print("Processing tender documents mapping...")
    mapped_documents = map_tender_documents(input_file, documents_output_file)
    
    # Print statistics
    if mapped_documents:
        print(f"\nTotal documents mapped: {len(mapped_documents)}")
        
        # Count documents per tender (for information)
        tender_counts = {}
        for doc in mapped_documents:
            tender_id = doc.get("tenderid")
            tender_counts[tender_id] = tender_counts.get(tender_id, 0) + 1
        
        print(f"Total unique tenders with documents: {len(tender_counts)}")
    else:
        print("No documents were mapped.")