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
        self.use_apify = bool(config.APIFY_API_TOKEN)
        self.token = config.LINKEDIN_ACCESS_TOKEN
        self.org_id = config.LINKEDIN_ORGANIZATION_ID
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def collect(self, keywords: list[str], lookback_days: int = 7) -> list[dict]:
        """
        Coleta posts virais do LinkedIn.
        Usa Apify (busca pública por keyword) se APIFY_API_TOKEN configurado,
        senão usa LinkedIn Marketing API (apenas posts da sua organização).
        """
        results = []

        if self.use_apify:
            try:
                posts = self._collect_apify(keywords, lookback_days)
                for post in posts:
                    if post and post["likes"] >= config.LINKEDIN_MIN_REACTIONS:
                        results.append(post)
            except Exception as e:
                print(f"[LinkedIn/Apify] Erro ao coletar posts: {e}")
        elif self.token and self.org_id:
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
        else:
            print("[LinkedIn] AVISO: Sem credenciais. Configure LINKEDIN_ACCESS_TOKEN ou APIFY_API_TOKEN.")
            return []

        return sorted(results, key=lambda x: x["likes"], reverse=True)

    # ─── Apify Scraper ────────────────────────────────────────────────────────

    def _collect_apify(self, keywords: list[str], lookback_days: int) -> list[dict]:
        """Coleta posts públicos via Apify curious_coder/linkedin-post-search-scraper."""
        from collectors.apify_client import run_actor
        import urllib.parse

        # Mapeia lookback_days para o filtro de data do LinkedIn
        if lookback_days <= 1:
            date_filter = "past-24h"
        elif lookback_days <= 7:
            date_filter = "past-week"
        else:
            date_filter = "past-month"

        # Monta URLs de busca do LinkedIn para cada keyword
        search_urls = []
        for keyword in keywords:
            encoded = urllib.parse.quote(keyword)
            url = (
                f"https://www.linkedin.com/search/results/content/"
                f"?datePosted=%22{date_filter}%22&keywords={encoded}&origin=FACETED_SEARCH"
            )
            search_urls.append(url)

        results = []
        try:
            items = run_actor("curious_coder/linkedin-post-search-scraper", {
                "urls": search_urls,
                "deepScrape": False,
                "rawData": False,
                "minDelay": 2,
                "maxDelay": 4,
                "proxy": {
                    "useApifyProxy": True,
                    "apifyProxyCountry": "US",
                },
            })
            for item in items:
                # Descobre qual keyword originou o post
                post_url = item.get("url", "") or item.get("postUrl", "")
                matched_kw = keywords[0]
                for kw in keywords:
                    if urllib.parse.quote(kw) in post_url or kw.lower() in (item.get("text", "") or "").lower():
                        matched_kw = kw
                        break
                parsed = self._parse_apify_post(item, matched_kw)
                if parsed:
                    results.append(parsed)
        except Exception as e:
            print(f"[LinkedIn/Apify] Erro ao coletar posts: {e}")
        return results

    def _parse_apify_post(self, item: dict, keyword: str) -> dict | None:
        try:
            published_str = item.get("publishedAt", "") or item.get("postedDate", "")
            try:
                published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00")) if published_str else datetime.now(timezone.utc)
            except Exception:
                published_at = datetime.now(timezone.utc)

            likes = int(item.get("likesCount", 0) or item.get("reactions", 0) or 0)
            comments = int(item.get("commentsCount", 0) or item.get("comments", 0) or 0)
            shares = int(item.get("sharesCount", 0) or item.get("shares", 0) or 0)
            post_url = item.get("url", "") or item.get("postUrl", "")
            text = item.get("text", "") or item.get("content", "") or item.get("commentary", "")
            author = item.get("authorName", "") or (item.get("author", {}) or {}).get("name", "")
            post_id = item.get("id", "") or post_url.split("/")[-1] or str(hash(post_url))

            return {
                "platform": self.PLATFORM,
                "platform_id": str(post_id),
                "url": post_url,
                "title": "",
                "description": text[:2000],
                "channel": author,
                "keyword": keyword,
                "published_at": published_at,
                "views": int(item.get("impressionsCount", 0) or 0),
                "likes": likes,
                "comments": comments,
                "shares": shares,
                "saves": None,
                "duration_seconds": None,
                "thumbnail_url": None,
                "tags": self._extract_hashtags(text),
                "category_id": item.get("type"),
                "engagement_rate": round((likes + comments + shares) / max(likes * 10, 1) * 100, 2),
                "raw_data": item,
            }
        except Exception as e:
            print(f"[LinkedIn/Apify] Erro ao parsear post: {e}")
            return None

    # ─── LinkedIn Marketing API (Oficial) ─────────────────────────────────────

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
