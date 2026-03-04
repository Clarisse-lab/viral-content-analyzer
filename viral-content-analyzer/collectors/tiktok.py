"""
TikTok Collector - TikTok Research API
Documentação: https://developers.tiktok.com/products/research-api/
Requisitos:
  - Aplicação aprovada no TikTok for Developers
  - Acesso à Research API (processo de aprovação necessário)
  - Client Key + Client Secret

ALTERNATIVA SEM API:
  Se você não tiver acesso à Research API, este coletor usa a
  API não-oficial do TikTok (scraping leve via endpoint público).
  Use apenas para uso pessoal/pesquisa.
"""

import requests
import time
from datetime import datetime, timedelta, timezone

import config


class TikTokCollector:
    PLATFORM = "tiktok"
    RESEARCH_API_URL = "https://open.tiktokapis.com/v2"
    TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

    def __init__(self):
        self.client_key = config.TIKTOK_CLIENT_KEY
        self.client_secret = config.TIKTOK_CLIENT_SECRET
        self.use_apify = bool(config.APIFY_API_TOKEN)
        self._access_token = None
        self._token_expires_at = 0

    def collect(self, keywords: list[str], lookback_days: int = 7) -> list[dict]:
        """Busca vídeos virais no TikTok."""
        results = []

        if self.use_apify:
            # Apify: scraper sem necessidade de aprovação
            for keyword in keywords:
                try:
                    videos = self._collect_apify(keyword, lookback_days)
                    for v in videos:
                        if v and v["views"] >= config.TIKTOK_MIN_VIEWS:
                            results.append(v)
                except Exception as e:
                    print(f"[TikTok/Apify] Erro '{keyword}': {e}")
        elif self.client_key and self.client_secret:
            # Research API oficial
            for keyword in keywords:
                try:
                    videos = self._search_research_api(keyword, lookback_days)
                    for v in videos:
                        parsed = self._parse_research_video(v, keyword)
                        if parsed and parsed["views"] >= config.TIKTOK_MIN_VIEWS:
                            results.append(parsed)
                except Exception as e:
                    print(f"[TikTok] Erro Research API '{keyword}': {e}")
        else:
            # Fallback: endpoint público (sem autenticação)
            print("[TikTok] AVISO: Credenciais não configuradas. Usando endpoint público (limitado).")
            for keyword in keywords:
                try:
                    videos = self._search_public(keyword)
                    for v in videos:
                        parsed = self._parse_public_video(v, keyword)
                        if parsed and parsed["views"] >= config.TIKTOK_MIN_VIEWS:
                            results.append(parsed)
                except Exception as e:
                    print(f"[TikTok] Erro público '{keyword}': {e}")

        seen = set()
        unique = []
        for r in results:
            if r["platform_id"] not in seen:
                seen.add(r["platform_id"])
                unique.append(r)

        return sorted(unique, key=lambda x: x["views"], reverse=True)

    # ─── Apify Scraper ────────────────────────────────────────────────────────

    def _collect_apify(self, keyword: str, lookback_days: int) -> list[dict]:
        """Coleta vídeos via Apify clockworks/tiktok-scraper."""
        from collectors.apify_client import run_actor
        items = run_actor("clockworks/tiktok-scraper", {
            "searchQueries": [keyword],
            "searchSection": "/search/video?q=",
            "maxItems": 30,
            "dateRange": f"last_{lookback_days}_days",
            "proxy": {"useApifyProxy": True},
        })
        return [self._parse_apify_video(item, keyword) for item in items if item]

    def _parse_apify_video(self, item: dict, keyword: str) -> dict | None:
        try:
            video_id = item.get("id", "")
            author = item.get("authorMeta", {}).get("name", "")
            create_time = item.get("createTimeISO") or item.get("createTime", "")
            if create_time:
                published_at = datetime.fromisoformat(str(create_time).replace("Z", "+00:00"))
            else:
                published_at = datetime.now(timezone.utc)
            views = int(item.get("playCount", 0))
            likes = int(item.get("diggCount", 0))
            comments = int(item.get("commentCount", 0))
            shares = int(item.get("shareCount", 0))
            tags = [h.get("name", "") for h in item.get("hashtags", [])]
            duration = item.get("videoMeta", {}).get("duration")
            return {
                "platform": self.PLATFORM,
                "platform_id": str(video_id),
                "url": f"https://www.tiktok.com/@{author}/video/{video_id}",
                "title": item.get("text", "")[:200],
                "description": item.get("text", "")[:2000],
                "channel": author,
                "keyword": keyword,
                "published_at": published_at,
                "views": views,
                "likes": likes,
                "comments": comments,
                "shares": shares,
                "saves": None,
                "duration_seconds": int(duration) if duration else None,
                "thumbnail_url": item.get("videoMeta", {}).get("coverUrl"),
                "tags": tags,
                "category_id": None,
                "engagement_rate": round((likes + comments + shares) / views * 100, 2) if views > 0 else 0.0,
                "raw_data": item,
            }
        except Exception as e:
            print(f"[TikTok/Apify] Erro ao parsear vídeo: {e}")
            return None

    # ─── Research API (Oficial) ───────────────────────────────────────────────

    def _get_access_token(self) -> str:
        """Obtém ou renova o access token via Client Credentials."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        resp = requests.post(
            self.TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 7200)
        return self._access_token

    def _search_research_api(self, keyword: str, lookback_days: int) -> list[dict]:
        """Busca vídeos via TikTok Research API."""
        token = self._get_access_token()
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        payload = {
            "query": {
                "and": [
                    {"operation": "IN", "field_name": "keyword", "field_values": [keyword]},
                    {"operation": "GTE", "field_name": "create_date",
                     "field_values": [cutoff.strftime("%Y%m%d")]},
                ]
            },
            "max_count": 20,
            "cursor": 0,
            "sort_type": "0",  # 0 = relevance, 1 = likes
            "fields": "id,video_description,create_time,region_code,share_count,view_count,like_count,comment_count,music_id,hashtag_names,username,voice_to_text,duration",
        }

        resp = requests.post(
            f"{self.RESEARCH_API_URL}/research/video/query/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("videos", [])

    def _parse_research_video(self, video: dict, keyword: str) -> dict | None:
        """Normaliza vídeo da Research API."""
        try:
            video_id = video.get("id", "")
            create_time = video.get("create_time", 0)
            published_at = datetime.fromtimestamp(create_time, tz=timezone.utc)

            return {
                "platform": self.PLATFORM,
                "platform_id": str(video_id),
                "url": f"https://www.tiktok.com/@{video.get('username', '_')}/video/{video_id}",
                "title": video.get("voice_to_text", "")[:200],
                "description": video.get("video_description", "")[:2000],
                "channel": video.get("username", ""),
                "keyword": keyword,
                "published_at": published_at,
                "views": int(video.get("view_count", 0)),
                "likes": int(video.get("like_count", 0)),
                "comments": int(video.get("comment_count", 0)),
                "shares": int(video.get("share_count", 0)),
                "saves": None,        # Não disponível na Research API
                "duration_seconds": int(video.get("duration", 0)),
                "thumbnail_url": None,
                "tags": video.get("hashtag_names", []),
                "category_id": None,
                "engagement_rate": self._calc_engagement(video),
                "raw_data": video,
            }
        except Exception as e:
            print(f"[TikTok] Erro ao parsear vídeo: {e}")
            return None

    # ─── Endpoint Público (Fallback) ──────────────────────────────────────────

    def _search_public(self, keyword: str) -> list[dict]:
        """
        Busca pública via endpoint não-oficial.
        AVISO: Pode ser bloqueado a qualquer momento pelo TikTok.
        Para uso em produção, use a Research API oficial.
        """
        resp = requests.get(
            "https://www.tiktok.com/api/search/general/full/",
            params={"keyword": keyword, "offset": 0, "count": 20},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.tiktok.com/",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        items = data.get("data", [])
        return [i.get("item", {}) for i in items if i.get("type") == 1]

    def _parse_public_video(self, video: dict, keyword: str) -> dict | None:
        """Normaliza vídeo do endpoint público."""
        try:
            video_id = video.get("id", "")
            author = video.get("author", {})
            stats = video.get("stats", {})
            music = video.get("music", {})
            create_time = video.get("createTime", 0)
            published_at = datetime.fromtimestamp(create_time, tz=timezone.utc)

            return {
                "platform": self.PLATFORM,
                "platform_id": str(video_id),
                "url": f"https://www.tiktok.com/@{author.get('uniqueId', '_')}/video/{video_id}",
                "title": video.get("desc", "")[:200],
                "description": video.get("desc", "")[:2000],
                "channel": author.get("nickname", ""),
                "keyword": keyword,
                "published_at": published_at,
                "views": int(stats.get("playCount", 0)),
                "likes": int(stats.get("diggCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "shares": int(stats.get("shareCount", 0)),
                "saves": int(stats.get("collectCount", 0)),
                "duration_seconds": video.get("video", {}).get("duration"),
                "thumbnail_url": video.get("video", {}).get("cover"),
                "tags": [c.get("hashtagName", "") for c in video.get("challenges", [])],
                "category_id": None,
                "engagement_rate": self._calc_engagement_public(stats),
                "raw_data": video,
            }
        except Exception as e:
            print(f"[TikTok] Erro ao parsear vídeo público: {e}")
            return None

    def _calc_engagement(self, video: dict) -> float:
        views = int(video.get("view_count", 0))
        if views == 0:
            return 0.0
        likes = int(video.get("like_count", 0))
        comments = int(video.get("comment_count", 0))
        shares = int(video.get("share_count", 0))
        return round((likes + comments + shares) / views * 100, 2)

    def _calc_engagement_public(self, stats: dict) -> float:
        views = int(stats.get("playCount", 0))
        if views == 0:
            return 0.0
        likes = int(stats.get("diggCount", 0))
        comments = int(stats.get("commentCount", 0))
        shares = int(stats.get("shareCount", 0))
        return round((likes + comments + shares) / views * 100, 2)
