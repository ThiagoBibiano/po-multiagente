"""Interface de linha de comando ``po-multiagente``.

Subcomandos disponíveis: ``validar-instancia``. Os subcomandos ``executar``,
``experimento`` e ``avaliar`` entram nas fases que os implementam.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

from po_multiagente import __version__
from po_multiagente.avaliacao.instancia import RelatorioInstancia, validar_instancia


def construir_parser() -> argparse.ArgumentParser:
    """Monta o parser de argumentos da CLI."""
    parser = argparse.ArgumentParser(
        prog="po-multiagente",
        description=(
            "Plataforma multiagente para formular, resolver e explicar problemas de PL e PLIM."
        ),
    )
    parser.add_argument("--versao", action="version", version=f"%(prog)s {__version__}")
    subcomandos = parser.add_subparsers(dest="comando")
    validar = subcomandos.add_parser(
        "validar-instancia",
        help="confere se a referência de cada instância executa e bate com a solução",
    )
    validar.add_argument(
        "pastas", nargs="+", type=Path, help="pastas de instância, ou pastas que as contêm"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada da CLI.

    Args:
        argv: Argumentos sem o nome do programa; ``None`` usa ``sys.argv``.

    Returns:
        Código de saída do processo: 1 se alguma instância for inválida.
    """
    parser = construir_parser()
    argumentos = parser.parse_args(argv)
    if argumentos.comando == "validar-instancia":
        relatorios = [validar_instancia(p) for p in _pastas_de_instancia(argumentos.pastas)]
        for relatorio in relatorios:
            print(_formatar(relatorio))
        validas = sum(r.valida for r in relatorios)
        print(f"\n{validas}/{len(relatorios)} instância(s) válida(s)")
        return 0 if validas == len(relatorios) else 1
    parser.print_help()
    return 0


def _pastas_de_instancia(pastas: Sequence[Path]) -> list[Path]:
    """Expande cada pasta que contém instâncias (reconhecidas por ``meta.yaml``)."""
    encontradas = []
    for pasta in pastas:
        if (pasta / "meta.yaml").exists():
            encontradas.append(pasta)
        else:
            encontradas.extend(sorted(p.parent for p in pasta.glob("*/meta.yaml")))
    return encontradas


def _formatar(relatorio: RelatorioInstancia) -> str:
    marca = "OK   " if relatorio.valida else "FALHA"
    valores = ""
    if relatorio.valor_obtido is not None and relatorio.valor_esperado is not None:
        valores = f"  obtido={relatorio.valor_obtido:g} esperado={relatorio.valor_esperado:g}"
    linhas = [f"{marca} {relatorio.pasta.name}{valores}"]
    linhas += [f"      ✗ {p}" for p in relatorio.problemas]
    linhas += [f"      ! {a}" for a in relatorio.avisos]
    return "\n".join(linhas)
