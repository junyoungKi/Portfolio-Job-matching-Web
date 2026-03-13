# app/main.py
import sys, asyncio, os, shutil, time, json, redis, hashlib
from datetime import datetime, timedelta
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, text  # 🎯 text 임포트 추가
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .database import engine, get_db, SessionLocal
from . import models
from .services.parser import resume_parser
from .services.ai import ai_service
from .services.collector import job_collector

# 🎯 Python 3.14+ 대응: WindowsProactorEventLoopPolicy 경고 코드를 삭제했습니다.

# 🎯 [데이터베이스 초기화] pgvector 확장 활성화 및 테이블 생성
def init_db():
    with engine.connect() as conn:
        # pgvector 확장이 설치되어 있지 않으면 설치합니다.
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    # 테이블 생성
    models.Base.metadata.create_all(bind=engine)

init_db()

# Redis 연결
try:
    rd = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    print("✅ Redis 연결 성공")
except:
    rd = None

# [JOB 1] 정기 공고 수집 작업
async def scheduled_north_america_crawl():
    db = SessionLocal()
    try:
        print(f"⏰ [BATCH] 정기 수집 및 AI 태깅 시작: {datetime.now()}")
        target_keywords = ["Software Engineer"]
        for kw in target_keywords:
            for city in job_collector.NA_HUBS:
                jobs = await job_collector.scrape_linkedin(kw, city)
                for job in jobs:
                    exists = db.query(models.JobPosting).filter(
                        models.JobPosting.title == job['title'], 
                        models.JobPosting.company == job['company']
                    ).first()
                    
                    if not exists:
                        meta = await ai_service.extract_job_metadata(job['description'])
                        job_emb = await ai_service.get_embedding(job['description'])
                        
                        db.add(models.JobPosting(
                            title=job['title'], 
                            company=job['company'], 
                            description=job['description'], 
                            location=job['location'], 
                            salary=job['salary'], 
                            search_keyword=kw, 
                            embedding=job_emb,
                            employment_type=meta.get('employment_type', 'Full-time'),
                            experience_level=meta.get('experience_level', 'Junior'),
                            skills=", ".join(meta.get('skills', []))
                        ))
                db.commit()
    except Exception as e: 
        print(f"❌ [BATCH] 오류: {e}")
    finally: 
        db.close()

# [JOB 2] 오래된 공고 자동 삭제 (데이터 생명주기 관리)
async def cleanup_old_jobs():
    db = SessionLocal()
    try:
        expiry_date = datetime.now() - timedelta(days=30)
        deleted_count = db.query(models.JobPosting).filter(
            models.JobPosting.company != "USER_UPLOAD",
            models.JobPosting.created_at < expiry_date
        ).delete()
        
        db.commit()
        if deleted_count > 0:
            print(f"🧹 [CLEANUP] 30일 경과된 오래된 공고 {deleted_count}개 자동 삭제 완료")
    except Exception as e:
        print(f"❌ [CLEANUP] 오류 발생: {e}")
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    
    # 1. 6시간마다 공고 수집
    scheduler.add_job(scheduled_north_america_crawl, 'interval', hours=6, 
                      next_run_time=datetime.now() + timedelta(seconds=5))
    
    # 2. 매일 자정(00:00)에 데이터 청소 실행
    scheduler.add_job(cleanup_old_jobs, 'cron', hour=0, minute=0)
    
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    total = db.query(models.JobPosting).filter(models.JobPosting.company != "USER_UPLOAD").count()
    return {"total_jobs": total}

@app.post("/process-resume")
async def process_resume(file: UploadFile = File(...), keyword: str = Query(...), location: str = Query(...), db: Session = Depends(get_db)):
    os.makedirs("temp_uploads", exist_ok=True)
    file_path = os.path.join("temp_uploads", file.filename)
    with open(file_path, "wb") as buffer: 
        shutil.copyfileobj(file.file, buffer)
    
    try:
        text_content = await resume_parser.extract_text(file_path)
        content_hash = hashlib.md5(f"{text_content}{keyword}{location}".encode()).hexdigest()
        
        existing = db.query(models.JobPosting).filter(
            models.JobPosting.company == "USER_UPLOAD",
            models.JobPosting.search_keyword == content_hash
        ).first()

        if existing:
            return {"status": "success", "id": existing.id}

        resume_vector = await ai_service.get_embedding(text_content)
        new_resume = models.JobPosting(
            title=f"RESUME: {file.filename}", 
            company="USER_UPLOAD", 
            description=text_content, 
            location=location, 
            search_keyword=content_hash, 
            embedding=resume_vector
        )
        db.add(new_resume)
        db.commit()
        db.refresh(new_resume)
        return {"status": "success", "id": new_resume.id}
    finally:
        if os.path.exists(file_path): 
            os.remove(file_path)

@app.get("/match/{resume_id}")
async def match_jobs(
    resume_id: int, 
    db: Session = Depends(get_db),
    levels: Optional[List[str]] = Query(None),
    types: Optional[List[str]] = Query(None),
    skills: Optional[List[str]] = Query(None)
):
    filter_tag = f"{levels}_{types}_{skills}"
    cache_key = f"match_results:{resume_id}:{hashlib.md5(filter_tag.encode()).hexdigest()}"
    
    if rd:
        cached = rd.get(cache_key)
        if cached: return json.loads(cached)

    resume = db.query(models.JobPosting).filter(models.JobPosting.id == resume_id).first()
    if not resume: raise HTTPException(status_code=404)

    search_locs = job_collector.NA_HUBS if resume.location == "North America" else [resume.location]
    score_query = (1 - models.JobPosting.embedding.cosine_distance(resume.embedding)).label("score")
    
    query = db.query(models.JobPosting, score_query).filter(
        models.JobPosting.company != "USER_UPLOAD",
        models.JobPosting.location.in_(search_locs)
    )

    if levels: query = query.filter(models.JobPosting.experience_level.in_(levels))
    if types: query = query.filter(models.JobPosting.employment_type.in_(types))
    if skills:
        skill_filters = [models.JobPosting.skills.ilike(f"%{s}%") for s in skills]
        query = query.filter(or_(*skill_filters))

    candidates = query.order_by(desc("score")).limit(100).all()
    if not candidates: return []

    jobs_only = [c[0] for c in candidates]
    scores_dict = {c[0].id: c[1] for c in candidates}
    
    # AI 리랭킹
    order = await ai_service.rerank_jobs(resume.description, jobs_only, preferred_skills=skills)
    
    results = []
    # 🎯 결과 출력 개수를 5개에서 10개로 상향 조정했습니다.
    for idx in order[:10]:
        if idx >= len(jobs_only): continue
        job = jobs_only[idx]
        analysis = db.query(models.MatchAnalysis).filter(
            models.MatchAnalysis.resume_id == resume_id, models.MatchAnalysis.job_id == job.id
        ).first()

        if not analysis:
            ko = await ai_service.analyze_match(resume.description, job.description, lang="ko")
            en = await ai_service.analyze_match(resume.description, job.description, lang="en")
            analysis = models.MatchAnalysis(
                resume_id=resume_id, job_id=job.id,
                summary_ko=ko.get("job_summary", ""), analysis_ko=ko.get("detail_analysis", ""),
                summary_en=en.get("job_summary", ""), analysis_en=en.get("detail_analysis", "")
            )
            db.add(analysis)
            db.commit()

        results.append({
            "title": str(job.title), 
            "company": str(job.company), 
            "location": str(job.location),
            "salary": str(job.salary), 
            "match_score": round(float(scores_dict[job.id]), 4),
            "summary_ko": analysis.summary_ko, 
            "analysis_ko": analysis.analysis_ko,
            "summary_en": analysis.summary_en, 
            "analysis_en": analysis.analysis_en,
            "skills": job.skills 
        })

    if rd: rd.setex(cache_key, 3600, json.dumps(results))
    return results

app.mount("/", StaticFiles(directory="static", html=True), name="static")