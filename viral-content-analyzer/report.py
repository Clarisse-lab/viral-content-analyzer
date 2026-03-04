"""
Gerador de relatórios - exporta análises em Markdown e JSON.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


def format_number(n) -> str:
    if n is None:
        return "N/D"
    return f"{int(n):,}".replace(",", ".")


def format_duration(seconds) -> str:
    if not seconds:
        return "N/D"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"


def score_bar(score, max_score=10) -> str:
    if score is None:
        return "N/D"
    filled = round((score / max_score) * 10)
    return "█" * filled + "░" * (10 - filled) + f" {score:.1f}/10"


def generate_markdown_report(top_contents: list[dict], output_dir: str = "reports") -> str:
    """Gera relatório completo em Markdown."""
    Path(output_dir).mkdir(exist_ok=True)
    now = datetime.now(timezone.utc)
    filename = f"{output_dir}/report_{now.strftime('%Y%m%d_%H%M%S')}.md"

    lines = [
        f"# 📊 Relatório de Conteúdos Virais",
        f"**Gerado em:** {now.strftime('%d/%m/%Y às %H:%M')} UTC",
        f"**Total de conteúdos analisados:** {len(top_contents)}",
        "",
        "---",
        "",
    ]

    # Agrupa por plataforma
    platforms = {}
    for c in top_contents:
        p = c.get("platform", "unknown")
        platforms.setdefault(p, []).append(c)

    platform_icons = {
        "youtube": "▶️  YouTube",
        "instagram": "📸 Instagram",
        "tiktok": "🎵 TikTok",
        "linkedin": "💼 LinkedIn",
    }

    for platform, contents in platforms.items():
        icon = platform_icons.get(platform, platform.upper())
        lines.append(f"## {icon}")
        lines.append("")

        for rank, c in enumerate(contents, 1):
            lines.extend(_content_section(c, rank))

    # Sumário de insights
    lines.extend(_insights_summary(top_contents))

    report = "\n".join(lines)
    Path(filename).write_text(report, encoding="utf-8")
    print(f"[Report] Markdown salvo: {filename}")
    return filename


def _content_section(c: dict, rank: int) -> list[str]:
    """Formata a seção de um conteúdo no relatório."""
    lines = []
    title = c.get("title") or c.get("description", "")[:80] or "Sem título"
    url = c.get("url", "#")
    published = c.get("published_at", "")
    if published and isinstance(published, str):
        try:
            dt = datetime.fromisoformat(published)
            published = dt.strftime("%d/%m/%Y")
        except Exception:
            pass

    lines.append(f"### #{rank} — [{title[:80]}]({url})")
    lines.append("")

    # Métricas
    lines.append("#### 📈 Métricas")
    lines.append("| Métrica | Valor |")
    lines.append("|---------|-------|")
    lines.append(f"| 👁️ Views/Impressões | {format_number(c.get('views'))} |")
    lines.append(f"| ❤️ Likes/Reações | {format_number(c.get('likes'))} |")
    lines.append(f"| 💬 Comentários | {format_number(c.get('comments'))} |")
    lines.append(f"| 🔁 Compartilhamentos | {format_number(c.get('shares'))} |")
    lines.append(f"| 🔖 Salvamentos | {format_number(c.get('saves'))} |")
    lines.append(f"| ⏱️ Duração | {format_duration(c.get('duration_seconds'))} |")
    lines.append(f"| 📅 Publicado | {published} |")
    lines.append(f"| 📊 Engajamento | {c.get('engagement_rate') or 0:.2f}% |")
    lines.append("")

    # Canal
    if c.get("channel"):
        lines.append(f"**Criador:** {c['channel']}")
        lines.append("")

    # Análise de IA
    if c.get("summary"):
        lines.append("#### 🤖 Análise de IA")
        lines.append("")
        lines.append(f"> **Resumo:** {c['summary']}")
        lines.append("")

    if c.get("viral_reason"):
        lines.append("**Por que viralizou:**")
        lines.append(c["viral_reason"])
        lines.append("")

    # Scores
    sh = c.get("score_hook")
    sc = c.get("score_copy")
    sf = c.get("score_format")
    if any(x is not None for x in [sh, sc, sf]):
        lines.append("**Scores:**")
        lines.append(f"- 🎯 Hook: `{score_bar(sh)}`")
        lines.append(f"- ✍️ Copy: `{score_bar(sc)}`")
        lines.append(f"- 📐 Formato: `{score_bar(sf)}`")
        lines.append("")

    if c.get("recommendations"):
        lines.append("**✅ O que replicar:**")
        lines.append(c["recommendations"])
        lines.append("")

    if c.get("keyword"):
        lines.append(f"*Keyword monitorada: `{c['keyword']}`*")
        lines.append("")

    lines.append("---")
    lines.append("")
    return lines


def _insights_summary(contents: list[dict]) -> list[str]:
    """Gera seção de insights consolidados."""
    lines = [
        "## 🎯 Insights Consolidados",
        "",
        f"**Total de conteúdos:** {len(contents)}",
        "",
    ]

    # Top por plataforma
    platform_counts = {}
    for c in contents:
        p = c.get("platform", "?")
        platform_counts[p] = platform_counts.get(p, 0) + 1

    lines.append("**Distribuição por plataforma:**")
    for p, count in sorted(platform_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {p.capitalize()}: {count} conteúdos")
    lines.append("")

    # Médias de engajamento
    eng_rates = [c.get("engagement_rate") for c in contents if c.get("engagement_rate")]
    if eng_rates:
        avg_eng = sum(eng_rates) / len(eng_rates)
        lines.append(f"**Taxa de engajamento média:** {avg_eng:.2f}%")
        lines.append("")

    # Keywords mais frequentes
    keyword_counts = {}
    for c in contents:
        kw = c.get("keyword", "")
        if kw:
            keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

    if keyword_counts:
        lines.append("**Keywords com mais conteúdo viral:**")
        for kw, count in sorted(keyword_counts.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"- `{kw}`: {count} posts")
        lines.append("")

    lines.append(f"*Relatório gerado automaticamente pelo Viral Content Analyzer*")
    return lines


def generate_json_export(top_contents: list[dict], output_dir: str = "reports") -> str:
    """Exporta dados brutos em JSON para integração com outros sistemas."""
    Path(output_dir).mkdir(exist_ok=True)
    now = datetime.now(timezone.utc)
    filename = f"{output_dir}/data_{now.strftime('%Y%m%d_%H%M%S')}.json"

    export = {
        "generated_at": now.isoformat(),
        "total": len(top_contents),
        "contents": top_contents,
    }

    Path(filename).write_text(json.dumps(export, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[Report] JSON salvo: {filename}")
    return filename
