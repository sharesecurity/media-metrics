from sqlalchemy import Column, String, Float, Integer, Text, ARRAY, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMPTZ
from sqlalchemy.orm import relationship
from app.core.database import Base
import uuid

class Source(Base):
    __tablename__ = "sources"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False, unique=True)
    domain = Column(Text)
    country = Column(Text, default="US")
    political_lean = Column(Float)
    ownership = Column(Text)
    founded_year = Column(Integer)
    created_at = Column(TIMESTAMPTZ)
    articles = relationship("Article", back_populates="source")

class Author(Base):
    __tablename__ = "authors"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id"))
    gender = Column(Text)
    ethnicity = Column(Text)
    created_at = Column(TIMESTAMPTZ)
    articles = relationship("Article", back_populates="author")

class Article(Base):
    __tablename__ = "articles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id"))
    author_id = Column(UUID(as_uuid=True), ForeignKey("authors.id"))
    title = Column(Text, nullable=False)
    url = Column(Text, unique=True)
    published_at = Column(TIMESTAMPTZ)
    ingested_at = Column(TIMESTAMPTZ)
    word_count = Column(Integer)
    section = Column(Text)
    tags = Column(ARRAY(Text))
    minio_key = Column(Text)
    raw_text = Column(Text)
    language = Column(Text, default="en")
    gdelt_id = Column(Text)
    extra = Column(JSONB)
    source = relationship("Source", back_populates="articles")
    author = relationship("Author", back_populates="articles")
    analysis_results = relationship("AnalysisResult", back_populates="article")

class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.id"))
    analyzed_at = Column(TIMESTAMPTZ)
    model_used = Column(Text)
    analysis_type = Column(Text)
    political_lean = Column(Float)
    political_confidence = Column(Float)
    sentiment_score = Column(Float)
    sentiment_label = Column(Text)
    subjectivity = Column(Float)
    primary_topic = Column(Text)
    topics = Column(JSONB)
    reading_level = Column(Float)
    avg_sentence_length = Column(Float)
    raw_analysis = Column(JSONB)
    notes = Column(Text)
    article = relationship("Article", back_populates="analysis_results")

class BiasMethod(Base):
    __tablename__ = "bias_methods"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False, unique=True)
    description = Column(Text)
    prompt_template = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMPTZ)
    modified_at = Column(TIMESTAMPTZ)
