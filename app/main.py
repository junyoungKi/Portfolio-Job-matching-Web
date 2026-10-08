import sys, asyncio, os, shutil, time, json, redis, hashlib
import aiofiles
import uuid
import traceback

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, desc, or_, text, func
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .database import engine, get_db, AsyncSessionLocal
from . import models
from .services.parser import resume_parser
from .services.ai import ai_service
from .services.collector import job_collector
from .cache import create_redis_client

rd = create_redis_client()

async def scheduled_north_america_crawl():
    async with AsyncSessionLocal() as db:
        try:
            print(f"⏰ [BATCH] 정기 수집 및 AI 태깅 시작: {datetime.now()}")
            target_keywords = ["Software Engineer"]
            for kw in target_keywords:
                for city in job_collector.NA_HUBS:
                    jobs = await job_collector.scrape_linkedin(kw, city)
                    for job in jobs:
                        try:
                            stmt = select(models.JobPosting).filter(
                                models.JobPosting.title == job['title'], 
                                models.JobPosting.company == job['company']
                            )
                            result = await db.execute(stmt)
                            exists = result.scalars().first()
                            
                            if not exists:
                                meta = await ai_service.extract_job_metadata(job['description'])
                                job_emb = await ai_service.get_embedding(job['description'])
                                
                                new_posting = models.JobPosting(
                                    title=job['title'], company=job['company'], 
                                    description=job['description'], location=job['location'], 
                                    salary=job['salary'], search_keyword=kw, embedding=job_emb,
                                    employment_type=meta.get('employment_type', 'Full-time'),
                                    experience_level=meta.get('experience_level', 'Junior'),
                                    skills=", ".join(meta.get('skills', []))
                                )
                                db.add(new_posting)
                                await db.commit()
                                print(f"✅ DB 저장 완료: {job['title']} @ {job['company']}")
                            else:
                                print(f"⏭️ 스킵 (중복): {job['title']} @ {job['company']}")
                        except Exception as inner_e:
                            await db.rollback()
                            print(f"⚠️ 개별 공고 처리 실패: {inner_e}")
                            continue
        except Exception as e: 
            print(f"❌ [BATCH] 전체 오류: {e}")

async def cleanup_old_jobs():
    async with AsyncSessionLocal() as db:
        try:
            expiry_date = datetime.now() - timedelta(days=30)
            stmt = delete(models.JobPosting).filter(
                models.JobPosting.company != "USER_UPLOAD",
                models.JobPosting.created_at < expiry_date
            )
            result = await db.execute(stmt)
            await db.commit()
            if result.rowcount > 0:
                print(f"🧹 [CLEANUP] 오래된 공고 {result.rowcount}개 삭제 완료")
        except Exception as e:
            await db.rollback()
            print(f"❌ [CLEANUP] 오류 발생: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(models.Base.metadata.create_all)
        print("✅ 데이터베이스 테이블 로드 완료")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(scheduled_north_america_crawl, 'interval', hours=6, next_run_time=datetime.now() + timedelta(seconds=5))
    scheduler.add_job(cleanup_old_jobs, 'cron', hour=0, minute=0)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    stmt = select(func.count(models.JobPosting.id)).filter(models.JobPosting.company != "USER_UPLOAD")
    result = await db.execute(stmt)
    total = result.scalar()
    return {"total_jobs": total}

parse_semaphore = asyncio.Semaphore(10)

@app.post("/process-resume")
async def process_resume(
    file: UploadFile = File(...), 
    keyword: str = Query(...), 
    location: str = Query(...), 
    db: AsyncSession = Depends(get_db)
):
    os.makedirs("temp_uploads", exist_ok=True)
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join("temp_uploads", unique_filename)
    
    try:
        async with aiofiles.open(file_path, 'wb') as buffer:
            content = await file.read()
            await buffer.write(content)
            await buffer.flush()
            
        max_retries = 20
        retry_delay = 0.1
        file_ready = False
        
        for _ in range(max_retries):
            try:
                with open(file_path, 'rb') as f:
                    file_ready = True
                    break
            except PermissionError:
                await asyncio.sleep(retry_delay)
            except FileNotFoundError:
                await asyncio.sleep(retry_delay)
                
        if not file_ready:
            raise HTTPException(status_code=500, detail="시스템 지연으로 파일을 열 수 없습니다.")

        async with parse_semaphore: 
            try:
                text_content = await resume_parser.extract_text(file_path)
                content_hash = hashlib.md5(f"{text_content}{keyword}{location}".encode()).hexdigest()
                
                stmt = select(models.JobPosting).filter(
                    models.JobPosting.company == "USER_UPLOAD",
                    models.JobPosting.search_keyword == content_hash
                )
                result = await db.execute(stmt)
                existing = result.scalars().first()

                if existing:
                    return {
                        "status": "success", 
                        "id": existing.id,
                        "parsed_text_length": len(text_content),
                        "parsed_text_preview": str(text_content)
                    }

                res = ai_service.get_embedding(text_content)
                if asyncio.iscoroutine(res):
                    resume_vector = await res
                else:
                    resume_vector = res
                
                new_resume = models.JobPosting(
                    title=f"RESUME: {file.filename}", 
                    company="USER_UPLOAD", 
                    description=str(text_content),
                    location=str(location),
                    search_keyword=str(content_hash), 
                    embedding=resume_vector
                )
                db.add(new_resume)
                await db.commit()           
                await db.refresh(new_resume) 
                
                return {
                    "status": "success", 
                    "id": new_resume.id,
                    "parsed_text_length": len(text_content),
                    "parsed_text_preview": str(text_content)
                }
                
            except Exception as e:
                traceback.print_exc()
                print(f"❌ 파싱/저장 오류: {e}")
                raise HTTPException(status_code=500, detail="분석 실패")
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

@app.get("/match/{resume_id}")
async def match_jobs(
    resume_id: int, 
    db: AsyncSession = Depends(get_db),
    levels: Optional[List[str]] = Query(None),
    types: Optional[List[str]] = Query(None),
    skills: Optional[List[str]] = Query(None)
):
    filter_tag = f"{levels}_{types}_{skills}"
    cache_key = f"match_results:{resume_id}:{hashlib.md5(filter_tag.encode()).hexdigest()}"
    
    if rd:
        try:
            cached = rd.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            print(f"Redis 읽기 오류: {e}")

    stmt = select(models.JobPosting).filter(models.JobPosting.id == resume_id)
    result = await db.execute(stmt)
    resume = result.scalars().first()
    if not resume: 
        raise HTTPException(status_code=404, detail="Resume not found")

    loc_clean = str(resume.location).strip().lower() if resume.location else ""
    if loc_clean in ["north america", "northamerica", "na"]:
        search_locs = job_collector.NA_HUBS
    else:
        search_locs = [resume.location]
        
    score_query = (1 - models.JobPosting.embedding.cosine_distance(resume.embedding)).label("score")
    
    query = select(models.JobPosting, score_query).filter(
        models.JobPosting.company != "USER_UPLOAD",
        models.JobPosting.location.in_(search_locs)
    )

    if levels: 
        query = query.filter(models.JobPosting.experience_level.in_(levels))
    if types: 
        query = query.filter(models.JobPosting.employment_type.in_(types))
    if skills:
        skill_filters = [models.JobPosting.skills.ilike(f"%{s}%") for s in skills]
        query = query.filter(or_(*skill_filters))

    query = query.order_by(desc("score")).limit(100)
    
    result = await db.execute(query)
    candidates = result.all()
    
    if not candidates: 
        return []

    jobs_only = [c[0] for c in candidates]
    scores_dict = {c[0].id: c[1] for c in candidates}
    
    order = await ai_service.rerank_jobs(resume.description, jobs_only, preferred_skills=skills)
    
    results = []
    for idx in order[:10]:
        if idx >= len(jobs_only): 
            continue
        job = jobs_only[idx]
        
        analysis_stmt = select(models.MatchAnalysis).filter(
            models.MatchAnalysis.resume_id == resume_id, 
            models.MatchAnalysis.job_id == job.id
        )
        analysis_res = await db.execute(analysis_stmt)
        analysis = analysis_res.scalars().first()

        if not analysis:
            ko = await ai_service.analyze_match(resume.description, job.description, lang="ko")
            en = await ai_service.analyze_match(resume.description, job.description, lang="en")
            analysis = models.MatchAnalysis(
                resume_id=resume_id, job_id=job.id,
                summary_ko=ko.get("job_summary", ""), analysis_ko=ko.get("detail_analysis", ""),
                summary_en=en.get("job_summary", ""), analysis_en=en.get("detail_analysis", "")
            )
            db.add(analysis)
            await db.commit()

        results.append({
            "title": str(job.title), "company": str(job.company), 
            "location": str(job.location), "salary": str(job.salary), 
            "match_score": round(float(scores_dict[job.id]), 4),
            "summary_ko": analysis.summary_ko, "analysis_ko": analysis.analysis_ko,
            "summary_en": analysis.summary_en, "analysis_en": analysis.analysis_en,
            "skills": job.skills 
        })

    if rd:
        try:
            rd.setex(cache_key, 3600, json.dumps(results))
        except Exception as e:
            print(f"Redis 쓰기 오류: {e}")
    return results

app.mount("/", StaticFiles(directory="static", html=True), name="static")