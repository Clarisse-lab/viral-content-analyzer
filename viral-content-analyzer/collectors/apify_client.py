"""Helper compartilhado para chamar atores do Apify via HTTP."""

import requests
import config

APIFY_BASE = "https://api.apify.com/v2"


def run_actor(actor_id: str, input_data: dict, timeout: int = 300) -> list[dict]:
    """
    Executa um ator do Apify de forma síncrona e retorna os itens coletados.

    Usa o endpoint run-sync-get-dataset-items que bloqueia até o ator terminar
    e já retorna os dados — sem precisar fazer polling separado.
    """
    url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    resp = requests.post(
        url,
        params={"token": config.APIFY_API_TOKEN, "timeout": timeout},
        json=input_data,
        timeout=timeout + 30,
    )
    resp.raise_for_status()
    return resp.json()
