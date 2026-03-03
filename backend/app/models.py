from sqlalchemy import Column, String, Float, Integer, Text, ARRAY, Boolean, ForeignKey, Date
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMPTZ
from sqlalchemy.orm import relationship
from app.core.database import Base
import uuid

class Location(Base):
    __tablename__ = "locations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city = Column(Text)
    state = Column(Text)
    country = Column(Text, nullable=False, default="US")
    lat = Column(Float)
    lng = Column(Float)
    display_name = Column(Text)
    meta = Column(JSONB)


class Organization(Base):
    """Rich entity for news outlets, wire services, parent companies, investors."""
    __tablename__ = "organizations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False, unique=True)
    slug = Column(Text, unique=True)
    org_type = Column(Text)        # 'publisher', 'wire_service', 'parent_company', 'investor'
    domain = Column(Text)
    location_id = Column(UUID(as_uuid=True), ForeignKey("locations.id"))
    founding_year = Column(Integer)
    dissolved_year = Column(Integer)
    political_lean = Column(Float)
    country = Column(Text, default="US")
    parent_org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    wikipedia_url = Column(Text)
    wikidata_id = Column(Text)
    meta = Column(JSONB)
    created_at = Column(TIMESTAMPTZ)


class Person(Base):
    """Rich entity for journalists, editors, executives."""
    __tablename__ = "people"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(Text, nullable=False)
    slug = Column(Text, unique=True)
    gender = Column(Text)
    ethnicity = Column(Text)
    birth_year = Column(Integer)
    location_id = Column(UUID(as_uuid=True), ForeignKey("locations.id"))
    byline_variants = Column(ARRAY(Text))
    wikipedia_url = Column(Text)
    wikidata_id = Column(Text)
    meta = Column(JSONB)
    created_at = Column(TIMESTAMPTZ)
    affiliations = relationship("PersonOrganization", back_populates="person")


class PersonOrganization(Base):
    """Employment / affiliation history with temporal dimension."""
    __tablename__ = "person_organization"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True), ForeignKey("people.id"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    role = Column(Text, nullable=False)  # 'reporter', 'editor', 'columnist', etc.
    beat = Column(Text)
    location_id = Column(UUID(as_uuid=True), ForeignKey("locations.id"))
    valid_from = Column(Date)
    valid_to = Column(Date)    # null = current position
    confidence = Column(Float, default=1.0)
    source = Column(Text)      # 'byline', 'linkedin', 'manual', 'inferred'
    meta = Column(JSONB)
    person = relationship("Person", back_populates="affiliations")
    organization = relationship("Organization")


class ArticleProvenance(Base):
    """Story attribution chain — tracks where a story originated."""
    __tablename__ = "article_provenance"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False)
    provenance_type = Column(Text, nullable=False)  # 'original', 'wire_pickup', 'syndicated', 'press_release'
    wire_service_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    source_article_id = Column(UUID(as_uuid=True), ForeignKey("articles.id"))
    confidence = Column(Float, nullable=False)
    detection_method = Column(Text)   # 'explicit_attribution', 'embedding_similarity', 'llm_inference'
    attribution_text = Column(Text)   # raw text that signaled this: "(AP)", "According to Reuters..."
    similarity_score = Column(Float)
    detected_at = Column(TIMESTAMPTZ)
    meta = Column(JSONB)
    article = relationship("Article", foreign_keys=[article_id], back_populates="provenance")
    wire_service = relationship("Organization", foreign_keys=[wire_service_id])


class ArticleAuthor(Base):
    """Multi-author support junction table."""
    __tablename__ = "article_authors"
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.id"), primary_key=True)
    person_id = Column(UUID(as_uuid=True), ForeignKey("people.id"), primary_key=True)
    author_order = Column(Integer, default=1)
    person = relationship("Person")


class Source(Base):
    __tablename__ = "sources"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False, unique=True)
    domain = Column(Text)
    country = Column(Text, default="US")
    political_lean = Column(Float)
    ownership = Column(Text)
    founded_year = Column(Integer)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"))  # bridge to organizations
    created_at = Column(TIMESTAMPTZ)
    articles = relationship("Article", back_populates="source")

class Author(Base):
    __tablename__ = "authors"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id"))
    gender = Column(Text)
    ethnicity = Column(Text)
    person_id = Column(UUID(as_uuid=True), ForeignKey("people.id"))  # bridge to people
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
    provenance = relationship("ArticleProvenance", foreign_keys="ArticleProvenance.article_id", back_populates="article")

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


class StoryCluster(Base):
    __tablename__ = "story_clusters"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    representative_id = Column(UUID(as_uuid=True), ForeignKey("articles.id"), nullable=True)
    topic_label = Column(Text)
    article_count = Column(Integer, default=0)
    avg_lean = Column(Float)
    avg_sentiment = Column(Float)
    source_count = Column(Integer)
    date_start = Column(TIMESTAMPTZ)
    date_end = Column(TIMESTAMPTZ)
    similarity_threshold = Column(Float, default=0.78)
    created_at = Column(TIMESTAMPTZ)
    updated_at = Column(TIMESTAMPTZ)
    members = relationship("StoryClusterArticle", back_populates="cluster", cascade="all, delete-orphan")


class StoryClusterArticle(Base):
    __tablename__ = "story_cluster_articles"
    cluster_id = Column(UUID(as_uuid=True), ForeignKey("story_clusters.id", ondelete="CASCADE"), primary_key=True)
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    similarity_score = Column(Float)
    cluster = relationship("StoryCluster", back_populates="members")
