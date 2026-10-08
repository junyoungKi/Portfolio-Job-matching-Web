# app/models.py
"""
Author: Joonyoung Ki

SQLAlchemy ORM models for the job-matching service.

Defines ``JobPosting`` (crawled job postings and uploaded resumes, with pgvector embeddings and an
HNSW index for fast similarity search) and ``MatchAnalysis`` (cached Korean/English LLM analyses
for a resume/job pair).
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from datetime import datetime
from pgvector.sqlalchemy import Vector
from .database import Base
from sqlalchemy.sql import func

class JobPosting(Base):
    """A crawled job posting, or an uploaded resume (stored with ``company == "USER_UPLOAD"``).

    Both kinds share one table so that resumes and jobs live in the same embedding space and can be
    compared with a single cosine-distance query.
    """
    __tablename__ = "job_postings"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    company = Column(String)
    description = Column(Text)
    location = Column(String, index=True)
    salary = Column(String)
    search_keyword = Column(String)
    embedding = Column(Vector(1536)) 
    
    # Filtering columns
    employment_type = Column(String, index=True)
    experience_level = Column(String, index=True)
    skills = Column(Text)

    # Collection timestamp, added for data management (used to expire old postings)
    created_at = Column(DateTime, server_default=func.now())

    # This is the key code that actually creates the HNSW index.
    # At this stage there are not many crawled postings, so it is not a problem yet. However, a
    # production service would crawl tens of thousands of postings or more, and the B-Tree-only
    # indexing could make searches too slow. To prepare for that, an HNSW index (based on graph
    # traversal) is added. O(log N)
    __table_args__ = (
        Index(
            "ix_job_postings_embedding_hnsw", # index name
            "embedding",                      # target column
            postgresql_using="hnsw",          # explicitly use the HNSW algorithm
            postgresql_with={
                "m": 16,                      # maximum number of connections per graph node
                "ef_construction": 64         # search range while building the index
            },
            postgresql_ops={"embedding": "vector_cosine_ops"}, # cosine similarity as the metric
        ),
    )

    

class MatchAnalysis(Base):
    """Cached LLM match analysis between one resume and one job, in both Korean and English.

    Storing both languages lets the UI switch language without calling the LLM again.
    """
    __tablename__ = "match_analyses"
    id = Column(Integer, primary_key=True, index=True)
    resume_id = Column(Integer, index=True)
    job_id = Column(Integer, index=True)
    summary_ko = Column(Text)
    analysis_ko = Column(Text)
    summary_en = Column(Text)
    analysis_en = Column(Text)