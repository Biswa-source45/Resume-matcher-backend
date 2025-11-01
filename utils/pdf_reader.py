import io
from typing import Optional
from PyPDF2 import PdfReader

def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text from PDF file content"""
    try:
        pdf_file = io.BytesIO(file_content)
        
        #  PDF reader object
        pdf_reader = PdfReader(pdf_file)
        
        # Extract text from all pages
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        
        return text.strip()
    except Exception as e:
        raise ValueError(f"Error reading PDF: {str(e)}")

def validate_pdf(file_content: bytes) -> bool:
    """Validate if the file content is a valid PDF"""
    try:
        # PDF header
        if not file_content.startswith(b'%PDF'):
            return False
        
        # creates a PDF reader to validate structure
        pdf_file = io.BytesIO(file_content)
        PdfReader(pdf_file)
        return True
    except:
        return False