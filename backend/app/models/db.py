import uuid
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, ARRAY, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Source(Base):
    __tablename__ = "sources"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    domain = Column(String)
    country = Column(String, default="US")
    political_lean = Column(String)
    source_type = Column(String, default="online")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    articles = relationship("Article", back_populates="source")

class Author(Base):
    __tablename__ = "authors"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    source_id = Column(Integer, ForeignKey("sources.id"))
    gender = Column(String)
    race = Column(String)
    bio = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Article(Base):
    __tablename__ = "articles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(Integer, ForeignKey("sources.id"))
    author_id = Column(Integer, ForeignKey("authors.id"))
    title = Column(Text, nullable=False)
    url = Column(Text, unique=True)
    published_at = Column(DateTime(timezone=True))
    content = Column(Text)
    word_count = Column(Integer)
    section = Column(String)
    tags = Column(ARRAY(String))
    raw_storage_path = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    source = relationship("Source", back_populates="articles")
    analyses = relationship("Analysis", back_populates="article")

class Analysis(Base):
    __tablename__ = "analyses"
    id = Column(Integer, primary_key=True)
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.id", ondelete="CASCADE"))
    analysis_type = Column(String, nullable=False)
    model_used = Column(String)
    result = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    article = relationship("Article", back_populates="analyses")
