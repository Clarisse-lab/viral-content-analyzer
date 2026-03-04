"""
Agendador de execução diária.
Executa coleta + análise + relatório no horário configurado.
"""

import schedule
import time
import threading
from datetime import datetime

import config
from main import run_pipeline


def _run_job():
    print(f"\n{'='*60}")
    print(f"  EXECUÇÃO AUTOMÁTICA - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'='*60}\n")
    try:
        run_pipeline()
    except Exception as e:
        print(f"[Scheduler] Erro na execução: {e}")


def start():
    """Inicia o agendador em modo daemon."""
    schedule.every().day.at(config.DAILY_RUN_TIME).do(_run_job)

    print(f"[Scheduler] Agendado para executar diariamente às {config.DAILY_RUN_TIME}")
    print("[Scheduler] Pressione Ctrl+C para parar.\n")

    # Executa imediatamente na primeira vez
    print("[Scheduler] Executando análise inicial...")
    _run_job()

    while True:
        schedule.run_pending()
        time.sleep(60)
