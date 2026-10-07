"""Ponto de entrada do RPA.

Uso:
    python main.py                       # producer + consumer (execução completa)
    python main.py --etapa producer      # só a coleta web
    python main.py --etapa consumer      # só o cadastro desktop (usa a última execução)
    python main.py --etapa consumer --run-id 2026-10-07_08-40-01 --reprocessar-falhas
"""
import argparse
import sys

from config import settings
from src.core.ambiente import validar_ambiente
from src.core.contexto import Contexto
from src.core.excecoes import BusinessException, SystemException
from src.core.logger import banner, configurar_logs, get_logger
from src.core.relatorio import gerar_relatorio

log = get_logger()


def ler_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RPA Sauce Demo → Fakturama")
    parser.add_argument("--etapa", choices=["todas", "producer", "consumer"], default="todas")
    parser.add_argument("--run-id", help="Pasta de resultados a usar/retomar (resultados/<run-id>)")
    parser.add_argument("--reprocessar-falhas", action="store_true",
                        help="Recoloca na fila os itens que falharam em execução anterior")
    return parser.parse_args()


def main() -> int:
    args = ler_argumentos()
    ctx = Contexto.criar(args.run_id, usar_ultima=args.etapa == "consumer")
    configurar_logs(ctx.pasta_logs, settings.NIVEL_LOG_CONSOLE)

    banner(log, f"RPA iniciado — execução {ctx.run_id}")
    log.info(f"Etapa: {args.etapa} | Resultados: {ctx.pasta}")

    try:  # antes de tudo: não adianta coletar na web se o desktop não vai conseguir cadastrar
        validar_ambiente(precisa_desktop=args.etapa != "producer")
    except SystemException as erro:
        log.error(f"Ambiente inválido: {erro}")
        return 1

    try:
        if args.etapa in ("todas", "producer"):
            from src.producer.producer import executar_producer
            executar_producer(ctx)
        if args.etapa in ("todas", "consumer"):
            # Import tardio: pyautogui exige sessão gráfica, desnecessária para o producer
            from src.consumer.consumer import executar_consumer
            executar_consumer(ctx, args.reprocessar_falhas)
    except KeyboardInterrupt:
        log.warning("Execução interrompida pelo usuário")
        return 130
    except BusinessException as erro:
        log.error(f"Execução abortada por regra de negócio: {erro}")
        return 2
    except Exception:
        log.exception("Execução abortada por erro inesperado")
        ctx.evidencias.erro("execucao")
        return 1
    finally:
        if args.etapa != "producer":  # só há o que conferir depois do cadastro desktop
            gerar_relatorio(ctx)

    return 0


if __name__ == "__main__":
    sys.exit(main())
