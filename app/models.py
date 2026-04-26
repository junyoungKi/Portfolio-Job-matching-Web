# app/models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from datetime import datetime
from pgvector.sqlalchemy import Vector
from .database import Base
from sqlalchemy.sql import func

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
    created_at = Column(DateTime, server_default=func.now())

    # 🚀 바로 이 부분이 "HNSW 인덱싱"을 실제로 생성하는 핵심 코드입니다.
    # 현재 단계에서는 크롤링된 공고가 많지 않아 큰 문제가 없지만, 차후 실제 서비스가
    # 가능하도록 하려면 수만 이상의 공고가 크롤링될 것이고 현재 B-Tree방식의 인덱싱만으로는
    # 검색 시간이 너무 오래걸릴 수 있다. 이를 대비하여 HNSW 인덱싱(그래프 탐색Graph Traversal 기반)을 추가한다. O(log N)
    __table_args__ = (
        Index(
            "ix_job_postings_embedding_hnsw", # 인덱스 이름
            "embedding",                      # 대상 컬럼
            postgresql_using="hnsw",          # HNSW 알고리즘 사용 명시
            postgresql_with={
                "m": 16,                      # 그래프의 최대 연결 수
                "ef_construction": 64         # 인덱스 생성 시 탐색 범위
            },
            postgresql_ops={"embedding": "vector_cosine_ops"}, # 코사인 유사도 기준
        ),
    )

    

class MatchAnalysis(Base):
    __tablename__ = "match_analyses"
    id = Column(Integer, primary_key=True, index=True)
    resume_id = Column(Integer, index=True)
    job_id = Column(Integer, index=True)
    summary_ko = Column(Text)
    analysis_ko = Column(Text)
    summary_en = Column(Text)
    analysis_en = Column(Text)