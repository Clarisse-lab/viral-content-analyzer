"""
Viral Content Analyzer
======================
Sistema de monitoramento e análise de conteúdos virais com IA.

Uso:
  python main.py              # Executa uma vez agora
  python main.py --schedule   # Modo daemon (executa diariamente)
  python main.py --report     # Apenas gera relatório dos dados existentes
  python main.py --platform youtube   # Apenas uma plataforma
"""

import sys
import argparse
from rich.console import Console
from rich.table import Table
from rich.progress import track

import config
from database import Database
from analyzer import ContentAnalyzer
from report import generate_markdown_report, generate_json_export

console = Console()


def get_enabled_collectors(platform_filter: str | None = None):
    """Instancia coletores das plataformas disponíveis (com credenciais)."""
    collectors = []

    platforms = {
        "youtube": (config.YOUTUBE_API_KEY, "collectors.youtube", "YouTubeCollector"),
        "instagram": (config.INSTAGRAM_ACCESS_TOKEN, "collectors.instagram", "InstagramCollector"),
        "tiktok": (True, "collectors.tiktok", "TikTokCollector"),     # TikTok tem fallback público
        "linkedin": (config.LINKEDIN_ACCESS_TOKEN, "collectors.linkedin", "LinkedInCollector"),
    }

    for name, (credential, module_path, class_name) in platforms.items():
        if platform_filter and name != platform_filter:
            continue
        if not credential:
            console.print(f"[yellow]⚠ {name.capitalize()}: sem credenciais, pulando.[/yellow]")
            continue
        try:
            import importlib
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            collectors.append(cls())
            console.print(f"[green]✓ {name.capitalize()}: coletor ativo[/green]")
        except Exception as e:
            console.print(f"[red]✗ {name.capitalize()}: erro ao inicializar - {e}[/red]")

    return collectors


def run_pipeline(platform_filter: str | None = None):
    """Pipeline completo: coleta → armazena → analisa → relatório."""
    db = Database()
    analyzer = ContentAnalyzer()

    console.rule("[bold cyan]FASE 1 — COLETA DE CONTEÚDOS[/bold cyan]")
    collectors = get_enabled_collectors(platform_filter)

    if not collectors:
        console.print("[red]Nenhum coletor disponível. Configure as credenciais no .env[/red]")
        return

    all_collected = []
    for collector in collectors:
        platform_name = collector.PLATFORM.capitalize()
        console.print(f"\n[bold]Coletando {platform_name}...[/bold]")
        try:
            items = collector.collect(config.KEYWORDS, config.LOOKBACK_DAYS)
            console.print(f"  → {len(items)} itens encontrados")

            new_count = 0
            for item in items:
                content, is_new = db.upsert_content(item)
                all_collected.append(content)
                if is_new:
                    new_count += 1

            console.print(f"  → {new_count} novos conteúdos salvos no banco")
        except Exception as e:
            console.print(f"  [red]Erro: {e}[/red]")

    console.rule("[bold cyan]FASE 2 — ANÁLISE COM IA[/bold cyan]")
    unanalyzed = db.get_unanalyzed(platform=platform_filter, limit=30)
    console.print(f"Conteúdos para analisar: {len(unanalyzed)}")

    if unanalyzed:
        if not config.ANTHROPIC_API_KEY:
            console.print("[yellow]⚠ ANTHROPIC_API_KEY não configurada. Pulando análise de IA.[/yellow]")
        else:
            for content in track(unanalyzed, description="Analisando com IA..."):
                try:
                    analysis = analyzer.analyze(content)
                    if analysis:
                        db.save_analysis(content.id, content.platform, content.platform_id, analysis)
                except Exception as e:
                    console.print(f"  [red]Erro ao analisar {content.platform_id}: {e}[/red]")
    else:
        console.print("Nenhum conteúdo novo para analisar.")

    console.rule("[bold cyan]FASE 3 — RELATÓRIO[/bold cyan]")
    top_contents = db.get_top_content(platform=platform_filter, days=config.LOOKBACK_DAYS, limit=30)

    if top_contents:
        md_file = generate_markdown_report(top_contents)
        json_file = generate_json_export(top_contents)
        console.print(f"\n[bold green]✓ Relatórios gerados:[/bold green]")
        console.print(f"  📄 {md_file}")
        console.print(f"  📦 {json_file}")
        _print_summary_table(top_contents[:10])
    else:
        console.print("[yellow]Nenhum conteúdo encontrado para o período.[/yellow]")


def _print_summary_table(contents: list[dict]):
    """Exibe tabela resumida no terminal."""
    table = Table(title="\nTop Conteúdos Virais", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Plataforma", style="cyan", width=12)
    table.add_column("Título/Copy", width=35)
    table.add_column("Views", justify="right", style="green")
    table.add_column("Likes", justify="right", style="red")
    table.add_column("Eng%", justify="right", style="yellow")
    table.add_column("Resumo IA", width=40)

    for i, c in enumerate(contents, 1):
        title = c.get("title") or c.get("description", "")
        title = (title or "")[:35].replace("\n", " ")
        summary = (c.get("summary") or "")[:40].replace("\n", " ")

        views = c.get("views") or 0
        views_str = f"{views/1_000_000:.1f}M" if views >= 1_000_000 else f"{views/1_000:.0f}K" if views >= 1_000 else str(views)

        likes = c.get("likes") or 0
        likes_str = f"{likes/1_000:.1f}K" if likes >= 1_000 else str(likes)

        eng = c.get("engagement_rate") or 0

        table.add_row(
            str(i),
            c.get("platform", "?").upper(),
            title,
            views_str,
            likes_str,
            f"{eng:.1f}%",
            summary,
        )

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Viral Content Analyzer")
    parser.add_argument("--schedule", action="store_true", help="Modo daemon com execução diária")
    parser.add_argument("--report", action="store_true", help="Gera relatório dos dados existentes sem coletar")
    parser.add_argument("--platform", choices=["youtube", "instagram", "tiktok", "linkedin"],
                        help="Limita a uma plataforma específica")
    args = parser.parse_args()

    console.print("[bold cyan]═══════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]     VIRAL CONTENT ANALYZER            [/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════[/bold cyan]\n")
    console.print(f"Keywords: {', '.join(config.KEYWORDS)}")
    console.print(f"Período: últimos {config.LOOKBACK_DAYS} dias\n")

    if args.schedule:
        from scheduler import start
        start()
    elif args.report:
        db = Database()
        top_contents = db.get_top_content(platform=args.platform, days=config.LOOKBACK_DAYS, limit=30)
        if top_contents:
            generate_markdown_report(top_contents)
            generate_json_export(top_contents)
            _print_summary_table(top_contents[:10])
        else:
            console.print("[yellow]Nenhum dado encontrado. Execute primeiro sem --report.[/yellow]")
    else:
        run_pipeline(platform_filter=args.platform)


if __name__ == "__main__":
    main()
