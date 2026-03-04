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
        if not config.INSTAGRAM_ACCESS_TOKEN:
            raise ValueError("INSTAGRAM_ACCESS_TOKEN não configurada no .env")
        self.token = config.INSTAGRAM_ACCESS_TOKEN
        self.account_id = config.INSTAGRAM_BUSINESS_ACCOUNT_ID

    def collect(self, keywords: list[str], lookback_days: int = 7) -> list[dict]:
        """
        Coleta posts virais via hashtags.
        NOTA: A API do Instagram limita busca por hashtag a ~30 hashtags únicas por 7 dias.
        """
        results = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

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
