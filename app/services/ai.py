# app/services/ai.py
"""
Author: Joonyoung Ki

OpenAI-backed AI service for the job-matching pipeline.

Provides text embeddings, job metadata extraction (employment type, experience level, skills),
LLM re-ranking of vector-search candidates, and bilingual (Korean/English) match analysis.
"""
import os
import json
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class AIService:
    """Thin wrapper around the OpenAI client exposing the AI operations used by the API and crawler."""

    async def get_embedding(self, text: str):
        """Return the ``text-embedding-3-small`` vector (1536 dimensions) for the given text."""
        response = await client.embeddings.create(input=text, model="text-embedding-3-small")
        return response.data[0].embedding

    # Job posting analysis and tag extraction (enrichment)
    async def extract_job_metadata(self, description: str):
        """Extract employment type, experience level and top skills from a job description.

        Uses JSON-mode output. On any failure it returns safe defaults so that a single bad
        response never blocks the crawl pipeline.
        """
        prompt = f"""
        Analyze this job description and return JSON:
        1. employment_type: (Full-time, Part-time, Internship, Contract)
        2. experience_level: (Entry, Junior, Mid, Senior)
        3. skills: List of top 5 technical skills (e.g. ["Python", "Java"])
        
        [Job]: {description[:1500]}
        """
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={ "type": "json_object" }
            )
            return json.loads(response.choices[0].message.content)
        except:
            return {"employment_type": "Full-time", "experience_level": "Junior", "skills": []}

    async def rerank_jobs(self, resume_text: str, jobs: list, preferred_skills: list = None):
        """Ask the LLM to order candidate jobs by relevance to the resume.

        Returns a list of indices into ``jobs`` (best first). If the LLM call or its parsing
        fails, the original (vector-similarity) order is returned instead.
        """
        if not jobs: return []
        job_list_str = "\n".join([f"[{i}] {j.title} at {j.company} (Skills: {j.skills})" for i, j in enumerate(jobs)])
        
        skill_instruction = f"\nNote: The user prefers these skills: {', '.join(preferred_skills)}" if preferred_skills else ""
        
        prompt = f"""
        You are a recruiting expert. Read the resume and prioritize all of the provided job postings ({len(jobs)} in total).{skill_instruction}
        You must respond with only a list that contains every index number, like [0, 1, 2, ...].
        
        [Resume]: {resume_text[:500]}
        [Job List]:
        {job_list_str}
        """
        try:
            response = await client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0)
            content = response.choices[0].message.content
            return json.loads(content)
        except:
            return list(range(len(jobs)))

    async def analyze_match(self, resume_text: str, job_description: str, lang: str = "ko"):
        """Generate a one-sentence job summary and a detailed resume-to-job analysis.

        ``lang`` selects the output language ("ko" for Korean, anything else for English).
        ``detail_analysis`` is always normalised to a single string, even if the LLM returns a
        dict or list. On failure a placeholder result is returned.
        """
        target_lang = "Korean" if lang == "ko" else "English"
        prompt = f"""
        Respond in {target_lang}. Return JSON:
        1. job_summary: One sentence summary of the job.
        2. detail_analysis: Detailed matching analysis as a SINGLE STRING (use bullet points -).
        
        [Resume]: {resume_text[:1000]}
        [Job]: {job_description[:1000]}
        """
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={ "type": "json_object" }
            )
            data = json.loads(response.choices[0].message.content)
            detail = data.get("detail_analysis", "")
            if isinstance(detail, (dict, list)):
                if isinstance(detail, dict):
                    detail = "\n".join([f"- {k}: {v}" for k, v in detail.items()])
                else:
                    detail = "\n".join([f"- {i}" for i in detail])
            data["detail_analysis"] = str(detail)
            return data
        except:
            return {"job_summary": "Error", "detail_analysis": "AI analysis failed"}

# Shared singleton used across the application.
ai_service = AIService()