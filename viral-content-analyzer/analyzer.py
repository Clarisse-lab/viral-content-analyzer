"""
Analisador de IA - usa Claude para entender POR QUE um conteúdo viralizou.
Analisa: copy, roteiro, formato, legenda, hook, CTA, tendências.
"""

import json
import anthropic

import config
from database import Content


ANALYSIS_PROMPT = """Você é um especialista em marketing de conteúdo digital, copywriting e estratégia de redes sociais.

Analise o seguinte conteúdo viral e explique com profundidade POR QUE ele funcionou.

═══════════════════════════════════════
DADOS DO CONTEÚDO
═══════════════════════════════════════
Plataforma: {platform}
Título/Descrição: {title}
Legenda/Copy: {description}
Canal/Criador: {channel}
Data de publicação: {published_at}
Duração: {duration}
Hashtags: {tags}

MÉTRICAS DE PERFORMANCE
─────────────────────
Views/Impressões: {views}
Likes/Reações: {likes}
Comentários: {comments}
Compartilhamentos: {shares}
Salvamentos: {saves}
Taxa de Engajamento: {engagement_rate}%

═══════════════════════════════════════

Responda EXATAMENTE no seguinte formato JSON (sem texto antes ou depois):

{{
  "summary": "Resumo executivo em 2-3 frases do por que viralizou",
  "viral_reason": "Explicação detalhada dos motivos principais do sucesso viral (mínimo 150 palavras)",
  "hook_analysis": "Análise do gancho inicial: como captura atenção nos primeiros 3 segundos/linhas",
  "copy_analysis": "Análise da copy/texto: estrutura, tom, linguagem, gatilhos emocionais usados",
  "format_analysis": "Análise do formato: adequação à plataforma, estrutura visual, duração ideal",
  "script_structure": "Estrutura do roteiro/conteúdo: problema > desenvolvimento > solução > CTA",
  "recommendations": "O que replicar em outros conteúdos (lista de 5 pontos acionáveis)",
  "warnings": "O que NÃO funciona ou riscos desta abordagem (lista de 3 pontos)",
  "scores": {{
    "hook": <nota de 0 a 10 para o gancho>,
    "copy": <nota de 0 a 10 para a copy/legenda>,
    "format": <nota de 0 a 10 para o formato>,
    "cta": <nota de 0 a 10 para o call-to-action>,
    "trending": <nota de 0 a 10 para alinhamento com tendências>
  }},
  "content_pillars": ["pilar1", "pilar2"],
  "emotions_triggered": ["emoção1", "emoção2"],
  "target_audience": "Descrição do público-alvo ideal para este conteúdo",
  "best_posting_time": "Melhor horário/dia para postar este tipo de conteúdo",
  "replication_template": "Template/estrutura que pode ser replicado para criar conteúdo similar"
}}"""


class ContentAnalyzer:
    def __init__(self):
        if not config.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY não configurada no .env")
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def analyze(self, content: Content) -> dict:
        """Analisa um conteúdo e retorna o resultado estruturado."""
        prompt = self._build_prompt(content)

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = message.content[0].text.strip()

            # Extrai JSON mesmo se vier com markdown
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()

            analysis = json.loads(raw_text)
            analysis["model"] = message.model
            analysis["input_tokens"] = message.usage.input_tokens
            analysis["output_tokens"] = message.usage.output_tokens
            return analysis

        except json.JSONDecodeError as e:
            print(f"[Analyzer] Erro ao parsear JSON da IA: {e}")
            return self._fallback_analysis(raw_text)
        except Exception as e:
            print(f"[Analyzer] Erro na análise: {e}")
            return {}

    def _build_prompt(self, content: Content) -> str:
        duration = "N/A"
        if content.duration_seconds:
            mins = content.duration_seconds // 60
            secs = content.duration_seconds % 60
            duration = f"{mins}m{secs:02d}s"

        tags_str = ", ".join(content.tags or [])[:500]
        desc = (content.description or "")[:3000]
        title = (content.title or "")[:500]

        return ANALYSIS_PROMPT.format(
            platform=content.platform.upper(),
            title=title or "(sem título)",
            description=desc or "(sem descrição/legenda)",
            channel=content.channel or "Desconhecido",
            published_at=content.published_at.strftime("%d/%m/%Y %H:%M") if content.published_at else "N/A",
            duration=duration,
            tags=tags_str or "Nenhuma",
            views=f"{content.views:,}".replace(",", "."),
            likes=f"{content.likes:,}".replace(",", "."),
            comments=f"{content.comments:,}".replace(",", "."),
            shares=f"{content.shares:,}".replace(",", ".") if content.shares else "N/D",
            saves=f"{content.saves:,}".replace(",", ".") if content.saves else "N/D",
            engagement_rate=content.engagement_rate or 0,
        )

    def _fallback_analysis(self, raw_text: str) -> dict:
        """Retorna análise simplificada se o JSON não puder ser parseado."""
        return {
            "summary": "Análise disponível em formato texto",
            "viral_reason": raw_text[:1000],
            "hook_analysis": "",
            "copy_analysis": "",
            "format_analysis": "",
            "script_structure": "",
            "recommendations": "",
            "warnings": "",
            "scores": {},
        }

    def batch_analyze(self, contents: list[Content], db=None) -> list[dict]:
        """Analisa uma lista de conteúdos e persiste os resultados."""
        results = []
        total = len(contents)

        for i, content in enumerate(contents, 1):
            print(f"  [{i}/{total}] Analisando: {content.platform} | {content.platform_id[:20]}...")
            analysis = self.analyze(content)

            if analysis and db:
                db.save_analysis(content.id, content.platform, content.platform_id, analysis)

            results.append({"content_id": content.id, "analysis": analysis})

        return results
