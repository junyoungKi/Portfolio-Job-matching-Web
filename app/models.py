# app/models.py
from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from pgvector.sqlalchemy import Vector
from .database import Base

class JobPosting(Base):
    __tablename__ = "job_postings"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    company = Column(String)
    description = Column(Text)
    location = Column(String, index=True)
    salary = Column(String)
    search_keyword = Column(String)
    embedding = Column(Vector(1536)) 
    
    # 필터링 컬럼
    employment_type = Column(String, index=True)
    experience_level = Column(String, index=True)
    skills = Column(Text)

    # 🆕 데이터 관리를 위한 수집 일시 추가
    created_at = Column(DateTime, default=datetime.now)

class MatchAnalysis(Base):
    __tablename__ = "match_analyses"
    id = Column(Integer, primary_key=True, index=True)
    resume_id = Column(Integer, index=True)
    job_id = Column(Integer, index=True)
    summary_ko = Column(Text)
    analysis_ko = Column(Text)
    summary_en = Column(Text)
    analysis_en = Column(Text)