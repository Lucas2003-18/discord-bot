import json
import logging
import re
import httpx
from bot import config

log = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """Você é um agente de observabilidade de infraestrutura analisando um incidente em um container Docker.

Container: {container}

Logs recentes (últimas linhas):
{logs}

Histórico de incidentes anteriores deste container no vault:
{vault_history}

Responda APENAS com um JSON válido, sem texto adicional e sem markdown, no formato exato:
{{"causa_raiz": "...", "sugestao": "...", "confianca": "Alta|Média|Baixa", "acao_sugerida": "restart|rebuild|edit_file|nenhuma"}}
"""

_CODE_FENCE_RE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)

# Limite de caracteres de log enviados ao Gemini, mesmo após truncar para N linhas
_MAX_LOG_CHARS = 4000


async def analyze_incident(container: str, logs: str, vault_history: str = "") -> dict:
    prompt = _PROMPT_TEMPLATE.format(
        container=container,
        logs=logs[-_MAX_LOG_CHARS:] if logs else "(sem logs disponíveis)",
        vault_history=vault_history or "(nenhum incidente anterior registrado)",
    )

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{config.GEMINI_BRIDGE_URL}/ask", json={"prompt": prompt})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.error("gemini_service: falha ao chamar Gemini Bridge para %s", container, exc_info=e)
        return _fallback(container)

    return _parse_response(data.get("response", ""), container)


def _parse_response(text: str, container: str) -> dict:
    cleaned = _CODE_FENCE_RE.sub("", text.strip()).strip()
    try:
        parsed = json.loads(cleaned)
        return {
            "causa_raiz": parsed.get("causa_raiz") or "Não identificada",
            "sugestao": parsed.get("sugestao") or "—",
            "confianca": parsed.get("confianca") or "Baixa",
            "acao_sugerida": parsed.get("acao_sugerida") or "nenhuma",
        }
    except (json.JSONDecodeError, AttributeError):
        log.warning("gemini_service: resposta não-JSON do Gemini para %s: %s", container, text[:200])
        return {
            "causa_raiz": (text.strip()[:500] or "Não identificada"),
            "sugestao": "—",
            "confianca": "Baixa",
            "acao_sugerida": "nenhuma",
        }


def _fallback(container: str) -> dict:
    return {
        "causa_raiz": "Não foi possível obter diagnóstico — Gemini Bridge indisponível",
        "sugestao": f"Verificar manualmente com `/logs {container}`",
        "confianca": "Baixa",
        "acao_sugerida": "nenhuma",
    }
