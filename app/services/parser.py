# app/services/parser.py
import fitz
import asyncio

class ResumeParser:
    async def extract_text(self, file_path: str) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_pdf, file_path)

    def _parse_pdf(self, file_path: str) -> str:
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
        if not text: return ""
        return " ".join(text.split())

resume_parser = ResumeParser()