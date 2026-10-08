# app/services/ai.py
import os
import json
from openai import AsyncOpenAI
from dotenv import load_dotenv
from sqlalchemy import select, or_
from .. import models

load_dotenv()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class AIService:
    async def find_similar_jobs(self, db, resume, locations=None, levels=None, types=None, skills=None, limit: int = 100):
        """pgvector 코사인 거리(<=>)로 이력서와 가장 유사한 공고를 반환합니다.

        반환값: [(JobPosting, score), ...] — score = 1 - cosine_distance (높을수록 유사).
        """
        if resume is None or resume.embedding is None:
            return []

        distance = models.JobPosting.embedding.cosine_distance(resume.embedding)
        score = (1 - distance).label("score")
        query = select(models.JobPosting, score).filter(
            models.JobPosting.company != "USER_UPLOAD",
            models.JobPosting.embedding.is_not(None),
        )
        if locations is not None:
            query = query.filter(models.JobPosting.location.in_(locations))
        if levels:
            query = query.filter(models.JobPosting.experience_level.in_(levels))
        if types:
            query = query.filter(models.JobPosting.employment_type.in_(types))
        if skills:
            query = query.filter(or_(*[models.JobPosting.skills.ilike(f"%{s}%") for s in skills]))

        result = await db.execute(query.order_by(distance.asc()).limit(limit))
        return result.all()

    async def get_embedding(self, text: str):
        response = await client.embeddings.create(input=text, model="text-embedding-3-small")
        return response.data[0].embedding

    # 🆕 공고 분석 및 태그 추출 (Enrichment)
    async def extract_job_metadata(self, description: str):
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
        if not jobs: return []
        job_list_str = "\n".join([f"[{i}] {j.title} at {j.company} (Skills: {j.skills})" for i, j in enumerate(jobs)])
        
        skill_instruction = f"\nNote: The user prefers these skills: {', '.join(preferred_skills)}" if preferred_skills else ""
        
        prompt = f"""
        당신은 채용 전문가입니다. 이력서를 읽고 제공된 모든 공고({len(jobs)}개)의 우선순위를 정하세요.{skill_instruction}
        반드시 [0, 1, 2, ...] 처럼 모든 인덱스 번호를 포함한 리스트만 응답하세요.
        
        [이력서]: {resume_text[:500]}
        [공고 리스트]:
        {job_list_str}
        """
        try:
            response = await client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0)
            content = response.choices[0].message.content
            return json.loads(content)
        except:
            return list(range(len(jobs)))

    async def analyze_match(self, resume_text: str, job_description: str, lang: str = "ko"):
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
            return {"job_summary": "Error", "detail_analysis": "AI 분석 실패"}

ai_service = AIService()