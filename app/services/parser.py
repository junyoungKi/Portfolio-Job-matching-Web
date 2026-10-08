# app/services/parser.py
"""
Author: Joonyoung Ki

PDF resume parsing service.

Extracts plain text from uploaded PDF resumes with PyMuPDF (``fitz``) and normalises whitespace.
"""
import fitz
import asyncio

class ResumeParser:
    """Extracts and cleans text from PDF resumes."""

    async def extract_text(self, file_path: str) -> str:
        """Parse the PDF at ``file_path`` in a worker thread so the event loop is not blocked."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_pdf, file_path)

    def _parse_pdf(self, file_path: str) -> str:
        """Synchronously read every page of the PDF; return an empty string if parsing fails."""
        text = ""
        try:
            with fitz.open(file_path) as doc:
                for page in doc:
                    text += page.get_text()
            return self.clean_text(text)
        except Exception as e:
            print(f"Parsing Error: {e}")
            return ""

    def clean_text(self, text: str) -> str:
        """Collapse all runs of whitespace (including newlines) into single spaces."""
        if not text: return ""
        return " ".join(text.split())

# Shared singleton used across the application.
resume_parser = ResumeParser()