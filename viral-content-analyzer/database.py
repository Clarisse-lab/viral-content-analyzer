"""
Camada de persistência - SQLite via SQLAlchemy.
Armazena conteúdos coletados e análises de IA.
"""

import json
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, String, Integer, Float,
    DateTime, Text, JSON, UniqueConstraint, Index,
)
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


class Content(Base):
    """Conteúdo viral coletado das plataformas."""
    __tablename__ = "contents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(20), nullable=False)        # youtube, instagram, tiktok, linkedin
    platform_id = Column(String(100), nullable=False)    # ID original na plataforma
    url = Column(String(500))
    title = Column(Text)
    description = Column(Text)
    channel = Column(String(200))
    keyword = Column(String(200))
    published_at = Column(DateTime(timezone=True))
    collected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Métricas
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer)
    saves = Column(Integer)
    duration_seconds = Column(Integer)
    engagement_rate = Column(Float)

    # Metadata
    thumbnail_url = Column(String(500))
    tags = Column(JSON)           # Lista de tags/hashtags
    category_id = Column(String(100))
    raw_data = Column(JSON)       # Resposta completa da API

    __table_args__ = (
        UniqueConstraint("platform", "platform_id", name="uq_platform_content"),
        Index("ix_platform_published", "platform", "published_at"),
        Index("ix_keyword", "keyword"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "platform": self.platform,
            "platform_id": self.platform_id,
            "url": self.url,
            "title": self.title,
            "description": self.description,
            "channel": self.channel,
            "keyword": self.keyword,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
            "views": self.views,
            "likes": self.likes,
            "comments": self.comments,
            "shares": self.shares,
            "saves": self.saves,
            "duration_seconds": self.duration_seconds,
            "engagement_rate": self.engagement_rate,
            "thumbnail_url": self.thumbnail_url,
            "tags": self.tags or [],
            "category_id": self.category_id,
        }


class Analysis(Base):
    """Análise de IA gerada para cada conteúdo viral."""
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_id = Column(Integer, nullable=False)
    platform = Column(String(20))
    platform_id = Column(String(100))
    analyzed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Scores de 0-10
    score_hook = Column(Float)          # Força do gancho inicial
    score_copy = Column(Float)          # Qualidade da copy/texto
    score_format = Column(Float)        # Formato adequado à plataforma
    score_cta = Column(Float)           # Call-to-action
    score_trending = Column(Float)      # Alinhamento com tendências

    # Análises textuais
    viral_reason = Column(Text)         # Por que viralizou
    hook_analysis = Column(Text)        # Análise do gancho
    copy_analysis = Column(Text)        # Análise da copy/legenda
    format_analysis = Column(Text)      # Análise do formato
    script_structure = Column(Text)     # Estrutura do roteiro
    recommendations = Column(Text)      # O que replicar
    warnings = Column(Text)             # O que evitar
    summary = Column(Text)              # Resumo executivo

    raw_analysis = Column(JSON)         # Resposta completa da IA

    __table_args__ = (
        Index("ix_analysis_content", "content_id"),
        Index("ix_analysis_platform", "platform", "platform_id"),
    )


class Database:
    def __init__(self, db_path: str = "viral_content.db"):
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return Session(self.engine)

    def upsert_content(self, data: dict) -> tuple[Content, bool]:
        """Insere ou atualiza um conteúdo. Retorna (content, is_new)."""
        with self.session() as session:
            existing = session.query(Content).filter_by(
                platform=data["platform"],
                platform_id=data["platform_id"],
            ).first()

            if existing:
                # Atualiza métricas
                existing.views = data.get("views", existing.views)
                existing.likes = data.get("likes", existing.likes)
                existing.comments = data.get("comments", existing.comments)
                existing.shares = data.get("shares", existing.shares)
                existing.saves = data.get("saves", existing.saves)
                existing.engagement_rate = data.get("engagement_rate", existing.engagement_rate)
                session.commit()
                session.refresh(existing)
                return existing, False
            else:
                content = Content(
                    platform=data["platform"],
                    platform_id=data["platform_id"],
                    url=data.get("url"),
                    title=data.get("title"),
                    description=data.get("description"),
                    channel=data.get("channel"),
                    keyword=data.get("keyword"),
                    published_at=data.get("published_at"),
                    views=data.get("views", 0),
                    likes=data.get("likes", 0),
                    comments=data.get("comments", 0),
                    shares=data.get("shares"),
                    saves=data.get("saves"),
                    duration_seconds=data.get("duration_seconds"),
                    engagement_rate=data.get("engagement_rate"),
                    thumbnail_url=data.get("thumbnail_url"),
                    tags=data.get("tags", []),
                    category_id=data.get("category_id"),
                    raw_data=data.get("raw_data"),
                )
                session.add(content)
                session.commit()
                session.refresh(content)
                return content, True

    def save_analysis(self, content_id: int, platform: str, platform_id: str, analysis: dict):
        """Persiste a análise de IA de um conteúdo."""
        with self.session() as session:
            # Remove análise anterior se existir
            session.query(Analysis).filter_by(content_id=content_id).delete()

            obj = Analysis(
                content_id=content_id,
                platform=platform,
                platform_id=platform_id,
                score_hook=analysis.get("scores", {}).get("hook"),
                score_copy=analysis.get("scores", {}).get("copy"),
                score_format=analysis.get("scores", {}).get("format"),
                score_cta=analysis.get("scores", {}).get("cta"),
                score_trending=analysis.get("scores", {}).get("trending"),
                viral_reason=analysis.get("viral_reason"),
                hook_analysis=analysis.get("hook_analysis"),
                copy_analysis=analysis.get("copy_analysis"),
                format_analysis=analysis.get("format_analysis"),
                script_structure=analysis.get("script_structure"),
                recommendations=analysis.get("recommendations"),
                warnings=analysis.get("warnings"),
                summary=analysis.get("summary"),
                raw_analysis=analysis,
            )
            session.add(obj)
            session.commit()

    def get_unanalyzed(self, platform: str | None = None, limit: int = 50) -> list[Content]:
        """Retorna conteúdos que ainda não foram analisados."""
        with self.session() as session:
            analyzed_ids = {
                row[0] for row in session.query(Analysis.content_id).all()
            }
            query = session.query(Content)
            if platform:
                query = query.filter_by(platform=platform)
            contents = query.order_by(Content.views.desc()).limit(limit * 3).all()
            result = [c for c in contents if c.id not in analyzed_ids][:limit]
            # Detach from session
            session.expunge_all()
            return result

    def get_top_content(self, platform: str | None = None, days: int = 7, limit: int = 20) -> list[dict]:
        """Retorna top conteúdos com suas análises."""
        from sqlalchemy import text
        cutoff = datetime.now(timezone.utc).timestamp() - days * 86400

        with self.session() as session:
            query = """
                SELECT c.*, a.score_hook, a.score_copy, a.score_format,
                       a.viral_reason, a.summary, a.recommendations
                FROM contents c
                LEFT JOIN analyses a ON a.content_id = c.id
                WHERE strftime('%s', c.published_at) >= :cutoff
            """
            params = {"cutoff": str(int(cutoff))}
            if platform:
                query += " AND c.platform = :platform"
                params["platform"] = platform

            query += " ORDER BY c.views DESC LIMIT :limit"
            params["limit"] = limit

            rows = session.execute(text(query), params).mappings().all()
            return [dict(row) for row in rows]
