"""Interface de linha de comando ``po-multiagente``.

Subcomandos disponíveis: ``validar-instancia`` e ``calibrar``. Os
subcomandos ``executar``, ``experimento`` e ``avaliar`` entram nas fases que
os implementam.
"""

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from po_multiagente import __version__
from po_multiagente.avaliacao.instancia import RelatorioInstancia, validar_instancia
from po_multiagente.config import ConfiguracaoExecucao
from po_multiagente.experimento.calibracao import calibrar, pastas_da_particao, resumo


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
    calibrar = subcomandos.add_parser(
        "calibrar", help="roda o fluxo completo nas instâncias de um conjunto e mede os critérios"
    )
    calibrar.add_argument("conjunto", type=Path, help="pasta com as instâncias")
    calibrar.add_argument(
        "--particao", choices=("ajuste", "conferencia", "todas"), default="ajuste"
    )
    calibrar.add_argument("--instancia", action="append", default=[], help="só esta instância")
    calibrar.add_argument(
        "--modo",
        choices=("chamar", "gravar", "reproduzir", "roteiro"),
        default="gravar",
        help="chamar o modelo, gravar as chamadas, reproduzir gravações ou usar o gabarito",
    )
    calibrar.add_argument(
        "--configuracao", choices=("com", "sem", "ambas"), default="com", help="Validador"
    )
    calibrar.add_argument(
        "--perfil",
        default=ConfiguracaoExecucao().perfil_modelo,
        help="perfil do modelo de linguagem (config/modelos/<perfil>.yaml)",
    )
    calibrar.add_argument("--repeticoes", type=int, default=1)
    calibrar.add_argument("--saida", type=Path, default=Path("saidas/calibracao"))
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
    if argumentos.comando == "calibrar":
        return _calibrar(argumentos)
    parser.print_help()
    return 0


def _calibrar(argumentos: argparse.Namespace) -> int:
    base = ConfiguracaoExecucao(perfil_modelo=argumentos.perfil)
    configuracoes = {
        "com": [base],
        "sem": [base.model_copy(update={"validador": False})],
        "ambas": [base, base.model_copy(update={"validador": False})],
    }[argumentos.configuracao]
    pastas = pastas_da_particao(argumentos.conjunto, argumentos.particao, argumentos.instancia)
    carimbo = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    medidas = calibrar(
        pastas, argumentos.saida / carimbo, argumentos.modo, configuracoes, argumentos.repeticoes
    )
    print("\n" + resumo(medidas))
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
