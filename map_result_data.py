import json
import os
import requests
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote


def parse_date_dd_mmm_yyyy(date_str: Optional[str]) -> Optional[str]:
    """
    Convert date like '27-Nov-2025' to '2025-11-27'.
    Returns None if parsing fails or value is empty.
    """
    if not date_str:
        return None
    date_str = date_str.strip()
    if not date_str:
        return None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_date_dd_mm_yyyy(date_str: Optional[str]) -> Optional[str]:
    """
    Convert date like '17/12/2025' to '2025-12-17'.
    Returns None if parsing fails or value is empty.
    """
    if not date_str:
        return None
    date_str = date_str.strip()
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_timestamp(value: Optional[str]) -> Optional[str]:
    """
    Normalize timestamp string to 'YYYY-MM-DD HH:MM:SS', if possible.
    """
    if not value:
        return None
    value = value.strip()
    if not value:
        return None

    # Try common formats we see in the JSON
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%d-%b-%Y %H:%M:%S",
        "%d-%B-%Y %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


def to_decimal(value: Any) -> Optional[float]:
    """
    Safely convert a numeric string like '49500.00' to float.
    Returns None if value is empty/invalid.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        # remove commas if present
        return float(text.replace(",", ""))
    except ValueError:
        return None


def extract_rank(remarks: Optional[str]) -> Optional[str]:
    """
    Extract rank string from remarks like 'L1', 'L2'.
    Returns the full string like 'L1', 'L2', etc., or None if not found.
    """
    if not remarks:
        return None
    remarks = remarks.strip().upper()
    # Check if it starts with 'L' followed by digits (e.g., 'L1', 'L2')
    if remarks.startswith('L') and len(remarks) > 1:
        # Check if the rest is digits
        if remarks[1:].isdigit():
            return remarks  # Return "L1", "L2", etc.
    return None


def build_address(city: Optional[str], state: Optional[str], country: Optional[str]) -> Optional[str]:
    """
    Build address string from city, state, country (comma-separated).
    Returns None if all fields are empty.
    """
    parts = []
    if city:
        parts.append(city.strip())
    if state:
        parts.append(state.strip())
    if country:
        parts.append(country.strip())
    
    if not parts:
        return None
    return ", ".join(parts)


def get_tender_source(tender_id: Optional[str]) -> str:
    """
    Determine tendersource based on tender_id.
    If tenderid starts with 'GEM', return 'GEM', otherwise return 'CPPP'.
    """
    if not tender_id:
        return "CPPP"
    tender_id_str = str(tender_id).strip().upper()
    if tender_id_str.startswith("GEM"):
        return "GEM"
    return "CPPP"


def map_single_result(
    parent: Dict[str, Any], bidder: Dict[str, Any], bidder_list: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Map one element of BidderList + its parent record to a row for tender_results.

    This produces keys matching the tender_results table columns:
      id, uniqueresultid, aocstatus, aocid, contractvalue, contractdate,
      tenderid, siteid, truid, technicalbidopeningdate, technicalevaluationdate,
      financebidopeningdate, financeevaluationdate, downloaddate,
      bidnumber, biddername, rank, bidamount, technicalbidstatus,
      financialbidstatus, agencyname, tendervalue, address, submissiondate,
      workdescription, cityname, statename, countryname, createdat, createdby, updatedat,
      updatedby, isdeleted, deletedat, deletedby
    """
    # Extract tender ID - try TenderId first, then fallback to OrganisationResultID
    tender_id = parent.get("TenderId")
    if not tender_id:
        # Fallback to OrganisationResultID if TenderId is not available
        tender_id = parent.get("OrganisationResultID")
        if tender_id:
            tender_id = str(tender_id).strip()
            # For GEM, keep the complete OrganisationResultID including <br> part
    
    # Determine tendersource based on tender_id
    tender_source = get_tender_source(tender_id)

    # AOC / contract level info
    contract_value = to_decimal(parent.get("ContractValue"))
    contract_date = parse_date_dd_mm_yyyy(parent.get("ContractDate"))
    download_date = parse_date_dd_mmm_yyyy(parent.get("PublicationDate"))
    publish_date = parse_date_dd_mm_yyyy(parent.get("PublicationDate"))  # Parse PublicationDate for publishdate field
    product_details = parent.get("ProductDetails")
    company_name = parent.get("CompanyName")
    
    # New fields from parent
    tender_value = to_decimal(parent.get("TenderValue"))
    submission_date = parse_date_dd_mm_yyyy(parent.get("SubmissionDate"))
    city = parent.get("City")
    # Check both "State" and "StateName" fields - data could be in either
    state = parent.get("State") or parent.get("StateName")
    country = parent.get("Country")
    address = build_address(city, state, country)
    
    # Additional fields from parent
    # For GEM results, check "BidValidity" (capital B and V), for CPPP check "bidvalidity" (lowercase)
    if tender_source == "GEM":
        bid_validity = parent.get("BidValidity") or parent.get("bidvalidity")  # For ravalidity field
    else:
        bid_validity = parent.get("bidvalidity")  # For ravalidity field
    ownership = parent.get("ownership")  # For ownership field

    # Bidder-level info
    bid_number = bidder.get("BidNumber")
    bidder_name = bidder.get("BidderName")
    result_status = bidder.get("ResultStatus") or None
    remarks = bidder.get("Remarks")
    # For Technical bidders: try TechnicalBidStatus first, then ResultStatus, then FinancialBidStatus as fallback
    technical_bid_status = bidder.get("TechnicalBidStatus") or bidder.get("ResultStatus") or bidder.get("FinancialBidStatus")
    # For Financial bidders: try FinancialBidStatus, then ResultStatus
    financial_bid_status = bidder.get("FinancialBidStatus") or bidder.get("ResultStatus")
    
    # Get BidType to determine which fields to map
    parent_bid_type = str(parent.get("BidType") or "").strip()
    bid_type = str(bidder.get("BidType") or "").strip()
    bidder_bid_type_clean = bid_type.strip()
    
    # Map bidamount based on BidType, source, and stage:
    # For GEM:
    #   Technical Stage: bidtype=0 → bidamount from BidAmount (may be null)
    #   Financial Stage: bidtype=0 → bidamount=null, bidtype=1 → bidamount from BidAmount
    #   AOC Stage: bidtype=0 → bidamount=null, bidtype=1 → bidamount from BidAmount, bidtype=2 → bidamount from BidAmount
    # For CPPP: Keep existing logic
    # Technical (0): Use BidAmount (may be null)
    # Financial (1): For GEM use BidAmount, for CPPP use FinancialBidValue
    # AOC (2): Use BidAmount
    if bidder_bid_type_clean == "1":
        # Financial: For GEM use BidAmount, for CPPP use FinancialBidValue
        if tender_source == "GEM":
            bid_amount = to_decimal(bidder.get("BidAmount"))
        else:
            # CPPP: Use FinancialBidValue
            bid_amount = to_decimal(bidder.get("FinancialBidValue"))
    elif bidder_bid_type_clean == "0":
        # Technical bidder
        if tender_source == "GEM" and parent_bid_type in ["1", "2"]:
            # GEM Financial/AOC stage: Technical bidders should have bidamount=null
            bid_amount = None
        else:
            # GEM Technical stage or CPPP: Use BidAmount (may be null)
            bid_amount = to_decimal(bidder.get("BidAmount"))
    else:
        # AOC bidder: Use BidAmount
        bid_amount = to_decimal(bidder.get("BidAmount"))
    
    # Rank: Set based on BidType and stage
    # For GEM:
    #   Technical Stage: bidtype=0 → rank=null
    #   Financial Stage: bidtype=0 → rank=null, bidtype=1 → rank from Remarks
    #   AOC Stage: bidtype=0 → rank=null, bidtype=1 → rank from Remarks, bidtype=2 → rank calculated
    # For CPPP: Keep existing logic
    if bidder_bid_type_clean == "2":
        # AOC: Rank will be calculated in process_aoc_file and passed here
        rank: Optional[str] = bidder.get("_calculated_rank")  # Will be set by process_aoc_file for AOC
    elif bidder_bid_type_clean == "1":
        # Financial: Use Remarks for rank
        rank: Optional[str] = remarks
    else:
        # Technical: Keep rank as null
        rank: Optional[str] = None
    
    # Map BidType to aocstatus:
    # For GEM: Use parent BidType (represents the current stage of the result file)
    # For CPPP: Use bidder BidType (parent doesn't have BidType field)
    # Technical (0) → aocstatus = "Technical"
    # Financial (1) → aocstatus = "Financial"
    # AOC (2) → aocstatus = "AOC"
    aoc_status: Optional[str] = None
    if tender_source == "GEM":
        # GEM: Use parent BidType to determine stage
        if parent_bid_type == "0":
            aoc_status = "Technical"
        elif parent_bid_type == "1":
            aoc_status = "Financial"
        elif parent_bid_type == "2":
            aoc_status = "AOC"
    else:
        # CPPP: Use bidder BidType (parent doesn't have BidType field)
        if bidder_bid_type_clean == "0":
            aoc_status = "Technical"
        elif bidder_bid_type_clean == "1":
            aoc_status = "Financial"
        elif bidder_bid_type_clean == "2":
            aoc_status = "AOC"
    
    # Dynamically map status fields based on BidType and stage (GEM only):
    # For GEM Results:
    #   Technical Stage (parent bidtype=0): technicalbidstatus = 'Accepted' if Qualified, 'Rejected' if Disqualified
    #   Financial Stage (parent bidtype=1): 
    #     - bidtype=0: financialbidstatus='Rejected', technicalbidstatus=null
    #     - bidtype=1: financialbidstatus='Accepted', bidamount and rank from data
    #   AOC Stage (parent bidtype=2):
    #     - bidtype=0,1: aocbidstatus='Rejected', other status fields null
    #     - bidtype=2: aocbidstatus='Accepted', bidamount and rank from data
    # For CPPP: Keep existing logic
    technical_status: Optional[str] = None
    financial_status: Optional[str] = None
    aoc_bid_status: Optional[str] = None
    
    # Check if this is GEM (for special handling)
    is_gem = tender_source == "GEM"
    
    if is_gem:
        # GEM Results - New logic
        if parent_bid_type == "0":
            # Technical Stage (parent bidtype=0)
            if bidder_bid_type_clean == "0":
                # Technical bidder: Set technicalbidstatus based on TechnicalBidStatus
                tech_status = bidder.get("TechnicalBidStatus") or ""
                tech_status_str = str(tech_status).strip().upper()
                # Check for Disqualified/Rejected FIRST (before Qualified) because "DISQUALIFIED" contains "QUALIFIED"
                if "DISQUALIFIED" in tech_status_str or "REJECTED" in tech_status_str:
                    technical_status = "Rejected"
                elif "QUALIFIED" in tech_status_str or "ACCEPTED" in tech_status_str:
                    technical_status = "Accepted"
                else:
                    technical_status = "Rejected"
                # financialbidstatus and aocbidstatus remain null
        elif parent_bid_type == "1":
            # Financial Stage (parent bidtype=1)
            if bidder_bid_type_clean == "0":
                # Technical bidder in Financial stage (bidtype=0)
                # Set financialbidstatus to NULL (not Rejected)
                financial_status = None
                # Set technicalbidstatus to "Accepted" or "Rejected" based on FinancialBidStatus
                # For Technical bidders in Financial stage, FinancialBidStatus indicates their Technical qualification status
                # Priority: FinancialBidStatus (most relevant for this stage) > TechnicalBidStatus > ResultStatus
                financial_bid_status_value = bidder.get("FinancialBidStatus")
                if financial_bid_status_value:
                    # If FinancialBidStatus is present, use it directly
                    fin_status_str = str(financial_bid_status_value).strip().upper()
                    # Check for Disqualified/Rejected FIRST (before Qualified) because "DISQUALIFIED" contains "QUALIFIED"
                    if "DISQUALIFIED" in fin_status_str or "REJECTED" in fin_status_str:
                        technical_status = "Rejected"
                    elif "QUALIFIED" in fin_status_str or "ACCEPTED" in fin_status_str:
                        technical_status = "Accepted"
                    else:
                        # Unknown status, default to Rejected
                        technical_status = "Rejected"
                else:
                    # Fallback to TechnicalBidStatus or ResultStatus if FinancialBidStatus is not available
                    tech_status_value = bidder.get("TechnicalBidStatus") or bidder.get("ResultStatus") or ""
                    tech_status_str = str(tech_status_value).strip().upper()
                    if "QUALIFIED" in tech_status_str or "ACCEPTED" in tech_status_str:
                        technical_status = "Accepted"
                    else:
                        # If Disqualified, Rejected, or empty/unknown, set to Rejected
                        technical_status = "Rejected"
                # aocbidstatus should be NULL for Technical bidders
                aoc_bid_status = None
            elif bidder_bid_type_clean == "1":
                # Financial bidder (bidtype=1)
                # technicalbidstatus should be NULL for Financial bidders
                technical_status = None
                # Set financialbidstatus to "Accepted" or "Rejected" based on status
                fin_status_value = bidder.get("FinancialBidStatus") or bidder.get("ResultStatus") or ""
                fin_status_str = str(fin_status_value).strip().upper()
                # Check for Disqualified/Rejected FIRST (before Qualified) because "DISQUALIFIED" contains "QUALIFIED"
                if "DISQUALIFIED" in fin_status_str or "REJECTED" in fin_status_str:
                    financial_status = "Rejected"
                elif "QUALIFIED" in fin_status_str or "ACCEPTED" in fin_status_str:
                    financial_status = "Accepted"
                else:
                    # If status is empty but has BidAmount, consider as Accepted (they qualified financially)
                    # Otherwise default to Rejected
                    if bid_amount is not None and bid_amount > 0:
                        financial_status = "Accepted"
                    else:
                        financial_status = "Rejected"
                # aocbidstatus should be NULL for Financial bidders
                aoc_bid_status = None
                # bidamount and rank are already set above from BidAmount and Remarks
        elif parent_bid_type == "2":
            # AOC Stage (parent bidtype=2)
            if bidder_bid_type_clean == "0":
                # Technical bidder in AOC stage (bidtype=0)
                # Set aocbidstatus to NULL (not Rejected)
                aoc_bid_status = None
                # Set technicalbidstatus to "Accepted" or "Rejected" based on status
                tech_status_value = bidder.get("TechnicalBidStatus") or bidder.get("ResultStatus") or ""
                tech_status_str = str(tech_status_value).strip().upper()
                # Check for Disqualified/Rejected FIRST (before Qualified) because "DISQUALIFIED" contains "QUALIFIED"
                if "DISQUALIFIED" in tech_status_str or "REJECTED" in tech_status_str:
                    technical_status = "Rejected"
                elif "QUALIFIED" in tech_status_str or "ACCEPTED" in tech_status_str:
                    technical_status = "Accepted"
                else:
                    # If empty/unknown, set to Rejected
                    technical_status = "Rejected"
                # financialbidstatus should be NULL for Technical bidders
                financial_status = None
            elif bidder_bid_type_clean == "1":
                # Financial bidder in AOC stage (bidtype=1)
                # Set aocbidstatus to NULL (not Rejected)
                aoc_bid_status = None
                # For Financial bidders in AOC stage, check if there's a corresponding Technical bidder
                # to preserve technicalbidstatus value (so it doesn't get overwritten when updating)
                technical_status = None
                if bidder_list and bidder_name:
                    # Find Technical bidder (bidtype=0) with same bidder name
                    tech_bidder = next(
                        (b for b in bidder_list 
                         if str(b.get("BidType") or "").strip() == "0" 
                         and str(b.get("BidderName") or "").strip().upper() == str(bidder_name).strip().upper()),
                        None
                    )
                    if tech_bidder:
                        tech_status_value = tech_bidder.get("TechnicalBidStatus") or tech_bidder.get("ResultStatus") or ""
                        tech_status_str = str(tech_status_value).strip().upper()
                        # Check for Disqualified/Rejected FIRST (before Qualified) because "DISQUALIFIED" contains "QUALIFIED"
                        if "DISQUALIFIED" in tech_status_str or "REJECTED" in tech_status_str:
                            technical_status = "Rejected"
                        elif "QUALIFIED" in tech_status_str or "ACCEPTED" in tech_status_str:
                            technical_status = "Accepted"
                        else:
                            technical_status = "Rejected"
                # Set financialbidstatus to "Accepted" or "Rejected" based on status
                fin_status_value = bidder.get("FinancialBidStatus") or bidder.get("ResultStatus") or ""
                fin_status_str = str(fin_status_value).strip().upper()
                # Check for Disqualified/Rejected FIRST (before Qualified) because "DISQUALIFIED" contains "QUALIFIED"
                if "DISQUALIFIED" in fin_status_str or "REJECTED" in fin_status_str:
                    financial_status = "Rejected"
                elif "QUALIFIED" in fin_status_str or "ACCEPTED" in fin_status_str:
                    financial_status = "Accepted"
                else:
                    # If status is empty but has BidAmount, consider as Accepted (they qualified financially)
                    # Otherwise default to Rejected
                    if bid_amount is not None and bid_amount > 0:
                        financial_status = "Accepted"
                    else:
                        financial_status = "Rejected"
                # bidamount and rank are already set above from BidAmount and Remarks
            elif bidder_bid_type_clean == "2":
                # AOC bidder (bidtype=2)
                # Only set aocbidstatus to 'Accepted' when accepted, NULL when rejected (not "Rejected")
                aoc_status_value = bidder.get("ResultStatus") or ""
                aoc_status_str = str(aoc_status_value).strip().upper()
                rank_value = bidder.get("Remarks") or ""
                rank_str = str(rank_value).strip().upper()
                
                if "L1" in rank_str or "ACCEPTED" in aoc_status_str or "QUALIFIED" in aoc_status_str:
                    aoc_bid_status = "Accepted"
                else:
                    # For rejected AOC bidders, keep aocbidstatus as NULL (not "Rejected")
                    aoc_bid_status = None
                
                # For AOC bidders, check if same bidder qualified in Technical and Financial stages
                # If bidder_list is provided, check for corresponding Technical and Financial bidders
                technical_status = None
                financial_status = None
                
                if bidder_list and bidder_name:
                    # Find Technical bidder (bidtype=0) with same bidder name
                    tech_bidder = next(
                        (b for b in bidder_list 
                         if str(b.get("BidType") or "").strip() == "0" 
                         and str(b.get("BidderName") or "").strip().upper() == str(bidder_name).strip().upper()),
                        None
                    )
                    if tech_bidder:
                        tech_status_value = tech_bidder.get("TechnicalBidStatus") or tech_bidder.get("ResultStatus") or ""
                        tech_status_str = str(tech_status_value).strip().upper()
                        # Check for Disqualified/Rejected FIRST (before Qualified) because "DISQUALIFIED" contains "QUALIFIED"
                        if "DISQUALIFIED" in tech_status_str or "REJECTED" in tech_status_str:
                            technical_status = "Rejected"
                        elif "QUALIFIED" in tech_status_str or "ACCEPTED" in tech_status_str:
                            technical_status = "Accepted"
                        else:
                            technical_status = "Rejected"
                    
                    # Find Financial bidder (bidtype=1) with same bidder name
                    fin_bidder = next(
                        (b for b in bidder_list 
                         if str(b.get("BidType") or "").strip() == "1" 
                         and str(b.get("BidderName") or "").strip().upper() == str(bidder_name).strip().upper()),
                        None
                    )
                    if fin_bidder:
                        fin_status_value = fin_bidder.get("FinancialBidStatus") or fin_bidder.get("ResultStatus") or ""
                        fin_status_str = str(fin_status_value).strip().upper()
                        # Check for Disqualified/Rejected FIRST (before Qualified) because "DISQUALIFIED" contains "QUALIFIED"
                        if "DISQUALIFIED" in fin_status_str or "REJECTED" in fin_status_str:
                            financial_status = "Rejected"
                        elif "QUALIFIED" in fin_status_str or "ACCEPTED" in fin_status_str:
                            financial_status = "Accepted"
                        else:
                            # If status is empty but has BidAmount, consider as Accepted
                            fin_bid_amount = to_decimal(fin_bidder.get("BidAmount"))
                            if fin_bid_amount is not None and fin_bid_amount > 0:
                                financial_status = "Accepted"
                            else:
                                financial_status = "Rejected"
                
                # bidamount and rank are already set above (rank calculated in process_aoc_file)
    else:
        # CPPP Results - Keep existing logic
        if bidder_bid_type_clean == "0":
            # Technical bidder: Normal Technical logic
            parts = []
            if technical_bid_status:
                parts.append(str(technical_bid_status).strip())
            if remarks:
                parts.append(str(remarks).strip())
            technical_status = " - ".join(parts) if parts else None
        elif bidder_bid_type_clean == "1":
            # Financial bidder: Always set financialbidstatus = "Accepted"
            financial_status = "Accepted"
        elif bidder_bid_type_clean == "2":
            # AOC: Set aocbidstatus = 'Accepted'
            aoc_bid_status = "Accepted"

    created_at = parse_timestamp(bidder.get("date_c"))

    mapped: Dict[str, Any] = {
        "id": None,  # will be assigned by DB
        # you can use a simple unique combination if you want, else keep None
        "uniqueresultid": None,
        "aocstatus": aoc_status,
        "aocid": parent.get("bidplus_gem_gov_in_ID"),
        "contractvalue": contract_value,
        "contractdate": contract_date,
        "tenderid": tender_id,
        "siteid": None,
        "truid": None,
        "technicalbidopeningdate": None,  # not directly available
        "technicalevaluationdate": None,  # not directly available
        "financebidopeningdate": None,  # not directly available (note: payload uses financebidopeningdate)
        "financeevaluationdate": None,  # not directly available
        "downloaddate": download_date,
        "publishdate": publish_date,  # From PublicationDate field
        "ravalidity": bid_validity,  # From bidvalidity field
        "ownership": ownership,  # From ownership field
        "bidnumber": bid_number,
        "biddername": bidder_name,
        "rank": rank,
        "bidamount": bid_amount,
        "technicalbidstatus": technical_status,
        "financialbidstatus": financial_status,
        "aocbidstatus": aoc_bid_status,
        "agencyname": company_name,  # CompanyName -> agencyname
        "tendervalue": tender_value,  # TenderValue -> tendervalue
        "address": address,  # city+state+country -> address (comma-separated)
        "submissiondate": submission_date,  # SubmissionDate -> submissiondate (DD/MM/YYYY -> YYYY-MM-DD)
        "workdescription": product_details,  # ProductDetails -> workdescription
        "cityname": city,  # City -> cityname
        "statename": state,  # State -> statename
        "countryname": country,  # Country -> countryname
        "tendersource": tender_source,  # GEM if tenderid starts with 'GEM', else 'CPPP'
        "createdat": created_at,
        "createdby": None,
        "updatedat": None,
        "updatedby": None,
        "isdeleted": 0,
        "deletedat": None,
        "deletedby": None,
    }

    return mapped


def extract_tender_id(tender_id: Optional[str]) -> Optional[str]:
    """Extract the first tender ID from string that may contain multiple IDs separated by <br>"""
    if not tender_id or tender_id == "":
        return None
    # Split by <br> and take the first one, strip whitespace
    parts = tender_id.split("<br>")
    return parts[0].strip() if parts else None

def is_valid_s3url(value: Any) -> bool:
    """Check if the TenderFileName value is valid (not empty, null, or whitespace)"""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return False

def map_result_documents(input_file: str, output_file: str) -> List[Dict[str, Any]]:
    """
    Map result documents from data format to document payload format.
    Processes TenderFileName_1 through TenderFileName_N fields and creates document records.
    
    Args:
        input_file: Path to input JSON file (e.g., "Results_Data/tntenders_gov_in.json")
        output_file: Path to output JSON file for mapped documents
    
    Returns:
        List of mapped document records
    """
    # Read input JSON file
    with open(input_file, 'r', encoding='utf-8') as f:
        result_data = json.load(f)
    
    # List to store all document records
    document_records = []
    
    # Process each result record
    for result in result_data:
        try:
            # Extract tender ID - try TenderId first, then fallback to OrganisationResultID
            tender_id = extract_tender_id(result.get("TenderId"))
            if not tender_id:
                # Fallback to OrganisationResultID if TenderId is not available
                tender_id = result.get("OrganisationResultID")
                if tender_id:
                    tender_id = str(tender_id).strip()
                    # For GEM, keep the complete OrganisationResultID including <br> part
            
            # Skip if no valid tender ID
            if not tender_id:
                continue
            
            # Check all TenderFileName_{n} fields dynamically
            # Start from 1 and check until we find no more fields
            file_index = 1
            while True:
                field_name = f"TenderFileName_{file_index}"
                s3url = result.get(field_name)
                
                # If field doesn't exist, we've reached the end
                if field_name not in result:
                    break
                
                # Check if the value is valid (non-empty)
                if is_valid_s3url(s3url):
                    # Create document record
                    document_record = {
                        "tenderid": tender_id,
                        "doctype": "Result Documents",
                        "s3url": s3url.strip(),
                        "docname": "Result Documents"
                    }
                    document_records.append(document_record)
                
                file_index += 1
                
                # Safety limit: stop after checking up to 20 fields (in case of unexpected data)
                if file_index > 20:
                    break
                    
        except Exception as e:
            print(f"Error processing result {result.get('TenderId', 'unknown')}: {e}")
            continue
    
    # Create output directory if it doesn't exist
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"Created output directory: {output_dir}")
    
    # Write mapped documents to output file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(document_records, f, indent=2, ensure_ascii=False)
    
    print(f"Successfully mapped {len(document_records)} document records from {input_file} to {output_file}")
    return document_records

def check_tender_has_data(tender_id: str) -> bool:
    """
    Check if tender has data in the API by calling result-details endpoint.
    Returns True if tender has results, False if blank/no data.
    """
    if not tender_id:
        return False
    
    try:
        # Extract first tender ID if multiple
        tender_id_clean = tender_id.split("<br>")[0].strip() if "<br>" in tender_id else tender_id.strip()
        if not tender_id_clean:
            return False
        
        # URL encode the tender ID
        tender_id_encoded = quote(tender_id_clean, safe='')
        api_url = f"http://13.202.159.122:8000/tender-results/result-details/{tender_id_encoded}"
        
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Check if results array exists and has data
            results = data.get("results", [])
            if results and len(results) > 0:
                return True
        return False
    except Exception as e:
        print(f"Error checking tender {tender_id}: {str(e)}")
        return False


def process_aoc_file(input_file: str, output_file: str) -> List[Dict[str, Any]]:
    """
    Read bidplus_gem_gov_in_AOC.json and convert to tender_results rows.
    Filters bidders to only include those with matching BidType as parent record.
    For AOC bidders (BidType = 2), calculates rank based on BidAmount (smallest = L1, second smallest = L2, etc.)
    """
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    results: List[Dict[str, Any]] = []

    for parent in data:
        # Extract tender ID - try TenderId first, then fallback to OrganisationResultID
        tender_id = parent.get("TenderId")
        if not tender_id:
            # Fallback to OrganisationResultID if TenderId is not available
            tender_id = parent.get("OrganisationResultID")
            if tender_id:
                tender_id = str(tender_id).strip()
                # For GEM, keep the complete OrganisationResultID including <br> part
        
        # Check if tender has data in API
        has_api_data = check_tender_has_data(tender_id) if tender_id else False
        
        bidder_list = parent.get("BidderList") or []
        
        if has_api_data:
            print(f"Processing tender {tender_id} - has data in API")
            # If API has data: Process all bidders (all bid types 0, 1, 2)
            # aocstatus will be set based on parent BidType (current stage)
            # Status fields (technicalbidstatus, financialbidstatus, aocbidstatus) will be set based on bidder BidType
            parent_bid_type = str(parent.get("BidType") or "").strip()
            
            # Determine tender source (GEM or CPPP)
            tender_source = get_tender_source(tender_id)
            
            # For AOC bidders (BidType = 2), calculate rank based on BidAmount
            aoc_bidders = [b for b in bidder_list if str(b.get("BidType") or "").strip() == "2"]
            if aoc_bidders:
                # For CPPP AOC Stage Results (parent bid type = 2), all bidders are "L1"
                if tender_source == "CPPP" and parent_bid_type == "2":
                    # Set all AOC bidders to L1 for CPPP AOC stage
                    for bidder in aoc_bidders:
                        bidder["_calculated_rank"] = "L1"
                else:
                    # For GEM or other stages: Sort AOC bidders by BidAmount (ascending, None values go to end)
                    def get_bid_amount(bidder):
                        bid_amount = to_decimal(bidder.get("BidAmount"))
                        return bid_amount if bid_amount is not None else float('inf')
                    
                    sorted_aoc_bidders = sorted(aoc_bidders, key=get_bid_amount)
                    
                    # Assign ranks: L1, L2, L3, etc.
                    for index, bidder in enumerate(sorted_aoc_bidders, start=1):
                        bidder["_calculated_rank"] = f"L{index}"
            
            # Process all bidders (to update previous stage data if present)
            for bidder in bidder_list:
                mapped_row = map_single_result(parent, bidder, bidder_list)
                # Clean up temporary _calculated_rank field
                if "_calculated_rank" in bidder:
                    del bidder["_calculated_rank"]
                results.append(mapped_row)
        else:
            print(f"Processing tender {tender_id} - no data in API (processing all bid types)")
            # If API has no data: Process all bidders (all bid types 0, 1, 2)
            # aocstatus will be set based on parent BidType (current stage)
            # Status fields (technicalbidstatus, financialbidstatus, aocbidstatus) will be set based on bidder BidType
            
            # Determine tender source (GEM or CPPP)
            tender_source = get_tender_source(tender_id)
            parent_bid_type = str(parent.get("BidType") or "").strip()
            
            # For AOC bidders (BidType = 2), calculate rank based on BidAmount
            aoc_bidders = [b for b in bidder_list if str(b.get("BidType") or "").strip() == "2"]
            if aoc_bidders:
                # For CPPP AOC Stage Results (parent bid type = 2), all bidders are "L1"
                if tender_source == "CPPP" and parent_bid_type == "2":
                    # Set all AOC bidders to L1 for CPPP AOC stage
                    for bidder in aoc_bidders:
                        bidder["_calculated_rank"] = "L1"
                else:
                    # For GEM or other stages: Sort AOC bidders by BidAmount (ascending, None values go to end)
                    def get_bid_amount(bidder):
                        bid_amount = to_decimal(bidder.get("BidAmount"))
                        return bid_amount if bid_amount is not None else float('inf')
                    
                    sorted_aoc_bidders = sorted(aoc_bidders, key=get_bid_amount)
                    
                    # Assign ranks: L1, L2, L3, etc.
                    for index, bidder in enumerate(sorted_aoc_bidders, start=1):
                        bidder["_calculated_rank"] = f"L{index}"
            
            for bidder in bidder_list:
                mapped_row = map_single_result(parent, bidder, bidder_list)
                # Clean up temporary _calculated_rank field
                if "_calculated_rank" in bidder:
                    del bidder["_calculated_rank"]
                results.append(mapped_row)

    # Create output directory if it doesn't exist
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"Created output directory: {output_dir}")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Mapped {len(results)} tender result rows from {input_file} to {output_file}")
    return results


if __name__ == "__main__":
    # Default paths in current workspace
    input_path = "wbtenders_gov_in (1).json"
    output_path = f"mapped_{input_path}"
    documents_output_path = f"mapped_doc_{input_path}"
    
    # Process result data mapping
    print("Processing result data mapping...")
    process_aoc_file(input_path, output_path)
    print()
    
    # Process result documents mapping
    print("Processing result documents mapping...")
    mapped_documents = map_result_documents(input_path, documents_output_path)
    
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


