# app/main.py
import sys, asyncio, os, shutil, time, json, redis, hashlib
import aiofiles
import uuid # 🎯 고유 식별자 생성을 위해 상단에 추가되어야 합니다.
import time
import traceback # 🎯 에러 추적을 위해 상단에 꼭 추가해 주세요!

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 🎯 비동기 쿼리를 위한 최신 SQLAlchemy 2.0 모듈 임포트
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, desc, or_, text, func
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# database.py에서 비동기 세션과 엔진을 가져옵니다.
from .database import engine, get_db, AsyncSessionLocal
from . import models
from .services.parser import resume_parser
from .services.ai import ai_service
from .services.collector import job_collector
import os
import redis
import json

# Redis 호스트 설정 (환경변수 없으면 'redis' 사용)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Redis connection 
try:
    rd = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    rd.ping()  # 실제로 통신이 되는지 확인
    print(f"✅ Redis 연결 성공 ({REDIS_HOST}:{REDIS_PORT})")
except Exception as e:
    print(f"⚠️ Redis 연결 실패, 재시도 주소 설정: {e}")
    # ConnectionRefused 방지를 위해 fallback 주소도 'redis'로 강제 지정
    try:
        rd = redis.Redis(host="redis", port=6379, db=0, decode_responses=True)
        rd.ping()
        print("✅ Redis 연결 성공 (fallback: redis)")
    except Exception as ex:
        print(f"❌ Redis 최종 연결 실패: {ex}")
        rd = None

# [JOB 1] 정기 공고 수집 작업 (비동기 DB 세션 적용)
# [JOB 1] 정기 공고 수집 작업 (비동기 DB 세션 + 일괄 수집 방식)
async def scheduled_north_america_crawl():
    # SessionLocal() 대신 AsyncSessionLocal()을 비동기 컨텍스트로 엽니다.
    async with AsyncSessionLocal() as db:
        try:
            print(f"⏰ [BATCH] 정기 수집 및 AI 태깅 시작: {datetime.now()}")
            target_keywords = ["Software Engineer"]
            for kw in target_keywords:
                for city in job_collector.NA_HUBS:
                    
                    # 🎯 수정된 부분 1: async for 대신 await를 사용하여 리스트를 한 번에 받아옵니다.
                    jobs = await job_collector.scrape_linkedin(kw, city)
                    
                    # 🎯 수정된 부분 2: 받아온 리스트(jobs)를 일반 for문으로 하나씩 꺼내어 처리합니다.
                    for job in jobs:
                        try:
                            # 비동기 쿼리 문법: select() 생성 후 await db.execute() 실행
                            stmt = select(models.JobPosting).filter(
                                models.JobPosting.title == job['title'], 
                                models.JobPosting.company == job['company']
                            )
                            result = await db.execute(stmt)
                            exists = result.scalars().first() # 첫 번째 결과값 가져오기
                            
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
                                await db.commit() # 저장 시에도 await 필수
                                print(f"✅ DB 저장 완료: {job['title']} @ {job['company']}")
                            else:
                                print(f"⏭️ 스킵 (중복): {job['title']} @ {job['company']}")
                        except Exception as inner_e:
                            await db.rollback() # 롤백 시에도 await 필수
                            print(f"⚠️ 개별 공고 처리 실패: {inner_e}")
                            continue
        except Exception as e: 
            print(f"❌ [BATCH] 전체 오류: {e}")

# [JOB 2] 오래된 공고 자동 삭제
async def cleanup_old_jobs():
    async with AsyncSessionLocal() as db:
        try:
            expiry_date = datetime.now() - timedelta(days=30)
            # 🎯 비동기 삭제(Delete) 쿼리 문법
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
    # 🎯 DB 테이블 비동기 초기화 (기존 밖에서 돌던 init_db를 내부로 편입하여 안전성 확보)
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
    # 🎯 비동기 카운트(Count) 쿼리 문법
    stmt = select(func.count(models.JobPosting.id)).filter(models.JobPosting.company != "USER_UPLOAD")
    result = await db.execute(stmt)
    total = result.scalar()
    return {"total_jobs": total}


parse_semaphore = asyncio.Semaphore(10)

# 이력서 처리 엔드포인트 수정 (완전 수정본)
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
        # 1. 파일 쓰기
        async with aiofiles.open(file_path, 'wb') as buffer:
            content = await file.read()
            await buffer.write(content)
            await buffer.flush()
            
        # 2. Windows 파일 잠금 해제 대기
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

        # 3. 파싱 및 비즈니스 로직
        async with parse_semaphore: 
            try:
                # 🎯 스레드 풀(run_in_executor)을 제거하고 정석적인 await로 원상 복구합니다.
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

                # 🎯 제가 실수로 날려먹었던 바로 그 '치트키' 복구 완료!
                res = ai_service.get_embedding(text_content)
                if asyncio.iscoroutine(res):
                    resume_vector = await res
                else:
                    resume_vector = res
                
                new_resume = models.JobPosting(
                    title=f"RESUME: {file.filename}", 
                    company="USER_UPLOAD", 
                    description=str(text_content),  # 🎯 텍스트 강제 변환 복구
                    location=str(location),         # 🎯 텍스트 강제 변환 복구
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
                    "parsed_text_preview": str(text_content) # 🎯 추출된 텍스트 전체/일부를 스웨거 응답으로 반환
                }
                
            except Exception as e:
                # 에러가 나면 터미널에 상세 위치를 찍어줍니다.
                traceback.print_exc()
                print(f"❌ 파싱/저장 오류: {e}")
                raise HTTPException(status_code=500, detail="분석 실패")

    finally:
        pass
                
@app.get("/match/{resume_id}")
async def match_jobs(
    resume_id: int, 
    db: AsyncSession = Depends(get_db), # 🎯 비동기 세션 타입 명시
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

    # 1. 이력서 정보 비동기 로드
    stmt = select(models.JobPosting).filter(models.JobPosting.id == resume_id)
    result = await db.execute(stmt)
    resume = result.scalars().first()
    if not resume: raise HTTPException(status_code=404)

    # 🎯 수정 코드 (대소문자 및 공백 제거 처리):
loc_clean = str(resume.location).strip().lower() if resume.location else ""
if loc_clean in ["north america", "northamerica", "na"]:
    search_locs = job_collector.NA_HUBS
else:
    search_locs = [resume.location]
    score_query = (1 - models.JobPosting.embedding.cosine_distance(resume.embedding)).label("score")
    
    # 2. 매칭 쿼리 조립
    query = select(models.JobPosting, score_query).filter(
        models.JobPosting.company != "USER_UPLOAD",
        models.JobPosting.location.in_(search_locs)
    )

    if levels: query = query.filter(models.JobPosting.experience_level.in_(levels))
    if types: query = query.filter(models.JobPosting.employment_type.in_(types))
    if skills:
        skill_filters = [models.JobPosting.skills.ilike(f"%{s}%") for s in skills]
        query = query.filter(or_(*skill_filters))

    query = query.order_by(desc("score")).limit(100)
    
    # 3. 비동기 쿼리 실행
    result = await db.execute(query)
    candidates = result.all() # 튜플 (JobPosting, score) 리스트 반환
    
    if not candidates: return []

    jobs_only = [c[0] for c in candidates]
    scores_dict = {c[0].id: c[1] for c in candidates}
    
    # AI 리랭킹 (유지)
    order = await ai_service.rerank_jobs(resume.description, jobs_only, preferred_skills=skills)
    
    results = []
    for idx in order[:10]: #slicing to top 10
        if idx >= len(jobs_only): continue
        job = jobs_only[idx]
        
        # 🎯 비동기 분석 기록 확인
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
            await db.commit() # 🎯 분석 결과 비동기 저장

        results.append({
            "title": str(job.title), "company": str(job.company), 
            "location": str(job.location), "salary": str(job.salary), 
            "match_score": round(float(scores_dict[job.id]), 4),
            "summary_ko": analysis.summary_ko, "analysis_ko": analysis.analysis_ko,
            "summary_en": analysis.summary_en, "analysis_en": analysis.analysis_en,
            "skills": job.skills 
        })

    if rd: rd.setex(cache_key, 3600, json.dumps(results))
    return results

app.mount("/", StaticFiles(directory="static", html=True), name="static")