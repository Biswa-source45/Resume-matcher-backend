import io
from typing import Optional
from PyPDF2 import PdfReader


def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text from PDF file content"""
    try:
        pdf_file = io.BytesIO(file_content)
        reader = PdfReader(pdf_file)
        text_parts = []
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts).strip()
    except Exception:
        return ""


def validate_pdf(file_content: bytes) -> bool:
    """Validate if the file content is a valid PDF by checking header and attempting to read pages"""
    try:
        # Quick header check for '%PDF'
        if len(file_content) < 4:
            return False
        if not (file_content[0:4] == b"%PDF"):
            return False

        # Attempt to parse with PdfReader
        pdf_file = io.BytesIO(file_content)
        reader = PdfReader(pdf_file)
        # At least one page
        return len(reader.pages) > 0
    except Exception:
        return False