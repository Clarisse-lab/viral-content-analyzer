"""
YouTube Collector - YouTube Data API v3
Documentação: https://developers.google.com/youtube/v3
Quota: 10.000 unidades/dia (grátis)
"""

import isodate
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config


class YouTubeCollector:
    PLATFORM = "youtube"

    def __init__(self):
        if not config.YOUTUBE_API_KEY:
            raise ValueError("YOUTUBE_API_KEY não configurada no .env")
        self.youtube = build("youtube", "v3", developerKey=config.YOUTUBE_API_KEY)

    def collect(self, keywords: list[str], lookback_days: int = 7) -> list[dict]:
        """Busca vídeos virais no YouTube pelos keywords informados."""
        results = []
        published_after = (
            datetime.now(timezone.utc) - timedelta(days=lookback_days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        for keyword in keywords:
            try:
                video_ids = self._search_videos(keyword, published_after)
                if video_ids:
                    details = self._get_video_details(video_ids)
                    for item in details:
                        parsed = self._parse_video(item, keyword)
                        if parsed and parsed["views"] >= config.YOUTUBE_MIN_VIEWS:
                            results.append(parsed)
            except HttpError as e:
                print(f"[YouTube] Erro na busca por '{keyword}': {e}")

        # Remove duplicatas por video_id
        seen = set()
        unique = []
        for r in results:
            if r["platform_id"] not in seen:
                seen.add(r["platform_id"])
                unique.append(r)

        return sorted(unique, key=lambda x: x["views"], reverse=True)

    def _search_videos(self, keyword: str, published_after: str) -> list[str]:
        """Retorna lista de video IDs relevantes."""
        response = self.youtube.search().list(
            q=keyword,
            part="id",
            type="video",
            order="viewCount",          # Ordenar por mais visualizados
            publishedAfter=published_after,
            maxResults=25,
            relevanceLanguage="pt",     # Prioriza conteúdo em português
            regionCode="BR",
        ).execute()

        return [item["id"]["videoId"] for item in response.get("items", [])]

    def _get_video_details(self, video_ids: list[str]) -> list[dict]:
        """Busca estatísticas detalhadas dos vídeos."""
        response = self.youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(video_ids),
        ).execute()
        return response.get("items", [])

    def _parse_video(self, item: dict, keyword: str) -> dict | None:
        """Normaliza os dados do vídeo para o formato padrão do sistema."""
        try:
            snippet = item["snippet"]
            stats = item.get("statistics", {})
            details = item.get("contentDetails", {})

            duration_iso = details.get("duration", "PT0S")
            duration_seconds = int(isodate.parse_duration(duration_iso).total_seconds())

            published_at = datetime.fromisoformat(
                snippet["publishedAt"].replace("Z", "+00:00")
            )

            return {
                "platform": self.PLATFORM,
                "platform_id": item["id"],
                "url": f"https://www.youtube.com/watch?v={item['id']}",
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:2000],
                "channel": snippet.get("channelTitle", ""),
                "keyword": keyword,
                "published_at": published_at,
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "shares": None,       # YouTube API não expõe shares
                "saves": None,        # YouTube API não expõe saves
                "duration_seconds": duration_seconds,
                "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                "tags": snippet.get("tags", []),
                "category_id": snippet.get("categoryId"),
                "engagement_rate": self._calc_engagement(stats),
                "raw_data": item,
            }
        except Exception as e:
            print(f"[YouTube] Erro ao parsear vídeo {item.get('id')}: {e}")
            return None

    def _calc_engagement(self, stats: dict) -> float:
        """Calcula taxa de engajamento: (likes + comments) / views * 100"""
        views = int(stats.get("viewCount", 0))
        if views == 0:
            return 0.0
        likes = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))
        return round((likes + comments) / views * 100, 2)
