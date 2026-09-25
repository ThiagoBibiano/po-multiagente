"""Interface de linha de comando ``po-multiagente``.

Os subcomandos ``executar``, ``experimento``, ``avaliar`` e
``validar-instancia`` entram nas fases que os implementam.
"""

import argparse
from collections.abc import Sequence

from po_multiagente import __version__


def construir_parser() -> argparse.ArgumentParser:
    """Monta o parser de argumentos da CLI."""
    parser = argparse.ArgumentParser(
        prog="po-multiagente",
        description=(
            "Plataforma multiagente para formular, resolver e explicar problemas de PL e PLIM."
        ),
    )
    parser.add_argument("--versao", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada da CLI.

    Args:
        argv: Argumentos sem o nome do programa; ``None`` usa ``sys.argv``.

    Returns:
        Código de saída do processo.
    """
    parser = construir_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
