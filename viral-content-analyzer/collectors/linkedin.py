"""
LinkedIn Collector - LinkedIn Marketing API
Documentação: https://learn.microsoft.com/en-us/linkedin/marketing/
Requisitos:
  - LinkedIn Developer App com acesso a:
    r_organization_social, rw_organization_admin, r_1st_connections_size
  - Token OAuth 2.0 com essas permissões

LIMITAÇÃO IMPORTANTE:
  A API do LinkedIn NÃO permite buscar posts de outras contas.
  O que é possível:
    1. Monitorar sua própria página/empresa
    2. Monitorar concorrentes específicos (se tiver acesso)

  Para monitoramento de conteúdo viral de terceiros no LinkedIn,
  ferramentas como Taplio, Shield Analytics ou Phantombuster
  são alternativas comerciais que possuem acesso especial.
"""

import requests
from datetime import datetime, timedelta, timezone

import config


LINKEDIN_API_URL = "https://api.linkedin.com/v2"


class LinkedInCollector:
    PLATFORM = "linkedin"

    def __init__(self):
        self.token = config.LINKEDIN_ACCESS_TOKEN
        self.org_id = config.LINKEDIN_ORGANIZATION_ID
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def collect(self, keywords: list[str], lookback_days: int = 7) -> list[dict]:
        """
        Coleta posts da sua organização no LinkedIn.
        Para monitorar outras páginas, use a LinkedIn Partner API (requer aprovação especial).
        """
        results = []

        if not self.token or not self.org_id:
            print("[LinkedIn] AVISO: Credenciais não configuradas. Pulando LinkedIn.")
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        cutoff_ms = int(cutoff.timestamp() * 1000)

        try:
            posts = self._get_org_posts(cutoff_ms)
            for post in posts:
                parsed = self._parse_post(post, keywords)
                if parsed and parsed["likes"] >= config.LINKEDIN_MIN_REACTIONS:
                    results.append(parsed)
        except Exception as e:
            print(f"[LinkedIn] Erro ao coletar posts: {e}")

        return sorted(results, key=lambda x: x["likes"], reverse=True)

    def _get_org_posts(self, cutoff_ms: int) -> list[dict]:
        """Busca posts da organização com estatísticas."""
        resp = requests.get(
            f"{LINKEDIN_API_URL}/ugcPosts",
            headers=self.headers,
            params={
                "q": "authors",
                "authors": f"List(urn:li:organization:{self.org_id})",
                "count": 50,
                "sortBy": "LAST_MODIFIED",
            },
        )
        if resp.status_code != 200:
            print(f"[LinkedIn] Erro HTTP {resp.status_code}: {resp.text[:200]}")
            return []

        posts = resp.json().get("elements", [])
        # Filtra pelos recentes
        filtered = []
        for post in posts:
            created_at = post.get("created", {}).get("time", 0)
            if created_at >= cutoff_ms:
                filtered.append(post)

        # Busca estatísticas para cada post
        enriched = []
        for post in filtered:
            post_id = post["id"]
            stats = self._get_post_stats(post_id)
            post["_stats"] = stats
            enriched.append(post)

        return enriched

    def _get_post_stats(self, post_id: str) -> dict:
        """Busca estatísticas de reações, comentários e compartilhamentos."""
        stats = {}

        # Social actions (likes/reactions)
        resp = requests.get(
            f"{LINKEDIN_API_URL}/socialActions/{post_id}",
            headers=self.headers,
        )
        if resp.status_code == 200:
            data = resp.json()
            stats["likes"] = data.get("likesSummary", {}).get("totalLikes", 0)
            stats["comments"] = data.get("commentsSummary", {}).get("totalFirstLevelComments", 0)

        # Organic statistics (impressions, shares, clicks)
        resp2 = requests.get(
            f"{LINKEDIN_API_URL}/organizationalEntityShareStatistics",
            headers=self.headers,
            params={
                "q": "organizationalEntity",
                "organizationalEntity": f"urn:li:organization:{self.org_id}",
                "ugcPosts[0]": post_id,
            },
        )
        if resp2.status_code == 200:
            elements = resp2.json().get("elements", [])
            if elements:
                s = elements[0].get("totalShareStatistics", {})
                stats["views"] = s.get("impressionCount", 0)
                stats["shares"] = s.get("shareCount", 0)
                stats["clicks"] = s.get("clickCount", 0)
                stats["engagement_rate"] = round(s.get("engagement", 0) * 100, 2)

        return stats

    def _parse_post(self, post: dict, keywords: list[str]) -> dict | None:
        """Normaliza post do LinkedIn para o formato padrão."""
        try:
            stats = post.get("_stats", {})
            created_ms = post.get("created", {}).get("time", 0)
            published_at = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)

            content = post.get("specificContent", {})
            share_content = content.get("com.linkedin.ugc.ShareContent", {})
            commentary = share_content.get("shareCommentary", {}).get("text", "")

            post_id = post["id"]
            urn_encoded = requests.utils.quote(post_id, safe="")

            # Detecta qual keyword está no texto
            matched_keyword = next(
                (kw for kw in keywords if kw.lower() in commentary.lower()), keywords[0] if keywords else ""
            )

            return {
                "platform": self.PLATFORM,
                "platform_id": post_id,
                "url": f"https://www.linkedin.com/feed/update/{urn_encoded}/",
                "title": "",          # LinkedIn não tem título em posts normais
                "description": commentary[:2000],
                "channel": f"urn:li:organization:{self.org_id}",
                "keyword": matched_keyword,
                "published_at": published_at,
                "views": stats.get("views", 0),
                "likes": stats.get("likes", 0),
                "comments": stats.get("comments", 0),
                "shares": stats.get("shares", 0),
                "saves": None,        # LinkedIn não expõe saves
                "duration_seconds": None,
                "thumbnail_url": None,
                "tags": self._extract_hashtags(commentary),
                "category_id": share_content.get("shareMediaCategory", "NONE"),
                "engagement_rate": stats.get("engagement_rate", 0.0),
                "raw_data": post,
            }
        except Exception as e:
            print(f"[LinkedIn] Erro ao parsear post {post.get('id')}: {e}")
            return None

    def _extract_hashtags(self, text: str) -> list[str]:
        return [word[1:] for word in text.split() if word.startswith("#")]
