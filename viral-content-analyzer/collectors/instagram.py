"""
Instagram Collector - Meta Graph API
Documentação: https://developers.facebook.com/docs/instagram-api
Requisitos:
  - Conta Business ou Creator no Instagram
  - App no Facebook for Developers
  - Token com permissões: instagram_basic, instagram_manage_insights, pages_read_engagement
"""

import requests
from datetime import datetime, timedelta, timezone

import config


GRAPH_URL = "https://graph.facebook.com/v19.0"


class InstagramCollector:
    PLATFORM = "instagram"

    def __init__(self):
        self.use_apify = bool(config.APIFY_API_TOKEN)
        if not self.use_apify and not config.INSTAGRAM_ACCESS_TOKEN:
            raise ValueError("Configure INSTAGRAM_ACCESS_TOKEN ou APIFY_API_TOKEN no .env")
        self.token = config.INSTAGRAM_ACCESS_TOKEN
        self.account_id = config.INSTAGRAM_BUSINESS_ACCOUNT_ID

    def collect(self, keywords: list[str], lookback_days: int = 7) -> list[dict]:
        """
        Coleta posts virais via hashtags.
        Usa Apify se APIFY_API_TOKEN configurado, senão usa Meta Graph API.
        """
        results = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        if self.use_apify:
            for keyword in keywords:
                try:
                    posts = self._collect_apify(keyword, lookback_days)
                    for post in posts:
                        if not post:
                            continue
                        if post["published_at"] < cutoff:
                            continue
                        if post["likes"] >= config.INSTAGRAM_MIN_LIKES:
                            results.append(post)
                except Exception as e:
                    print(f"[Instagram/Apify] Erro na keyword '{keyword}': {e}")
        else:
            for keyword in keywords:
                hashtag = keyword.replace(" ", "").lower()
                try:
                    hashtag_id = self._get_hashtag_id(hashtag)
                    if not hashtag_id:
                        continue
                    posts = self._get_top_media(hashtag_id)
                    for post in posts:
                        parsed = self._parse_post(post, keyword)
                        if not parsed:
                            continue
                        if parsed["published_at"] < cutoff:
                            continue
                        if parsed["likes"] >= config.INSTAGRAM_MIN_LIKES:
                            results.append(parsed)
                except Exception as e:
                    print(f"[Instagram] Erro na hashtag #{hashtag}: {e}")

        seen = set()
        unique = []
        for r in results:
            if r["platform_id"] not in seen:
                seen.add(r["platform_id"])
                unique.append(r)

        return sorted(unique, key=lambda x: x["likes"], reverse=True)

    # ─── Apify Scraper ────────────────────────────────────────────────────────

    def _collect_apify(self, keyword: str, lookback_days: int) -> list[dict]:
        """Coleta posts via Apify apify/instagram-hashtag-scraper."""
        from collectors.apify_client import run_actor
        hashtag = keyword.replace(" ", "").lower()
        items = run_actor("apify/instagram-hashtag-scraper", {
            "hashtags": [hashtag],
            "resultsLimit": 30,
            "proxy": {"useApifyProxy": True},
        })
        return [self._parse_apify_post(item, keyword) for item in items if item]

    def _parse_apify_post(self, item: dict, keyword: str) -> dict | None:
        try:
            timestamp = item.get("timestamp", "")
            if timestamp:
                published_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            else:
                published_at = datetime.now(timezone.utc)
            likes = int(item.get("likesCount", 0))
            comments = int(item.get("commentsCount", 0))
            caption = item.get("caption", "") or ""
            return {
                "platform": self.PLATFORM,
                "platform_id": str(item.get("id", "")),
                "url": item.get("url", ""),
                "title": "",
                "description": caption[:2000],
                "channel": item.get("ownerUsername", ""),
                "keyword": keyword,
                "published_at": published_at,
                "views": int(item.get("videoViewCount", 0) or 0),
                "likes": likes,
                "comments": comments,
                "shares": None,
                "saves": None,
                "duration_seconds": int(item.get("videoDuration", 0)) or None,
                "thumbnail_url": item.get("displayUrl"),
                "tags": [h.lstrip("#") for h in item.get("hashtags", [])],
                "category_id": item.get("type"),
                "engagement_rate": self._calc_engagement(likes, comments, max(likes * 10, 1)),
                "raw_data": item,
            }
        except Exception as e:
            print(f"[Instagram/Apify] Erro ao parsear post: {e}")
            return None

    # ─── Meta Graph API (Oficial) ─────────────────────────────────────────────

    def _get_hashtag_id(self, hashtag: str) -> str | None:
        """Obtém o ID interno do Instagram para uma hashtag."""
        resp = requests.get(
            f"{GRAPH_URL}/ig_hashtag_search",
            params={
                "user_id": self.account_id,
                "q": hashtag,
                "access_token": self.token,
            },
        )
        data = resp.json()
        items = data.get("data", [])
        return items[0]["id"] if items else None

    def _get_top_media(self, hashtag_id: str) -> list[dict]:
        """Retorna os top media de uma hashtag."""
        resp = requests.get(
            f"{GRAPH_URL}/{hashtag_id}/top_media",
            params={
                "user_id": self.account_id,
                "fields": "id,media_type,timestamp,like_count,comments_count,caption,permalink,thumbnail_url,media_url",
                "access_token": self.token,
            },
        )
        return resp.json().get("data", [])

    def _get_insights(self, media_id: str) -> dict:
        """Obtém insights de alcance e impressões (apenas para mídia própria)."""
        try:
            resp = requests.get(
                f"{GRAPH_URL}/{media_id}/insights",
                params={
                    "metric": "impressions,reach,saved,shares",
                    "access_token": self.token,
                },
            )
            data = resp.json().get("data", [])
            return {item["name"]: item["values"][0]["value"] for item in data}
        except Exception:
            return {}

    def _parse_post(self, post: dict, keyword: str) -> dict | None:
        """Normaliza dados do post Instagram para o formato padrão."""
        try:
            published_at = datetime.fromisoformat(
                post["timestamp"].replace("Z", "+00:00")
            )
            media_type = post.get("media_type", "IMAGE")
            likes = int(post.get("like_count", 0))
            comments = int(post.get("comments_count", 0))

            # Insights de saves/shares disponíveis apenas para conteúdo próprio
            insights = self._get_insights(post["id"])

            return {
                "platform": self.PLATFORM,
                "platform_id": post["id"],
                "url": post.get("permalink", ""),
                "title": "",          # Instagram não tem título
                "description": post.get("caption", "")[:2000],
                "channel": "",        # Username não disponível via hashtag search
                "keyword": keyword,
                "published_at": published_at,
                "views": insights.get("impressions", 0),
                "likes": likes,
                "comments": comments,
                "shares": insights.get("shares"),
                "saves": insights.get("saved"),
                "duration_seconds": None,   # Apenas para Reels
                "thumbnail_url": post.get("thumbnail_url") or post.get("media_url"),
                "tags": self._extract_hashtags(post.get("caption", "")),
                "category_id": media_type,
                "engagement_rate": self._calc_engagement(likes, comments, insights.get("reach", 0)),
                "raw_data": post,
            }
        except Exception as e:
            print(f"[Instagram] Erro ao parsear post {post.get('id')}: {e}")
            return None

    def _extract_hashtags(self, caption: str) -> list[str]:
        """Extrai hashtags de uma legenda."""
        return [word[1:] for word in caption.split() if word.startswith("#")]

    def _calc_engagement(self, likes: int, comments: int, reach: int) -> float:
        if reach == 0:
            return 0.0
        return round((likes + comments) / reach * 100, 2)
