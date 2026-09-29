"""Adaptador PuLP, com o CBC distribuído junto com o PuLP.

O TG fixa o CBC 2.10.3 (cap. 3, Passo 4), que é o binário embutido no PuLP
3.x e só é acessível por ``PULP_CBC_CMD``. O PuLP 3.3 marca essa classe como
depreciada em favor de um CBC instalado à parte; por isso a dependência fica
em ``pulp<4`` e o aviso é silenciado só aqui (ADR-006).
"""

import subprocess
import tempfile
import warnings
from functools import cache
from pathlib import Path

import pulp

from po_multiagente.dominio import IdentificacaoSolver, ResultadoSolver, Sentido, StatusSolucao
from po_multiagente.modelo import ModeloInstanciado, Relacao
from po_multiagente.solver.contrato import ErroSolver, ExecucaoSolver, OpcoesSolver

_SENTIDOS = {Sentido.MINIMIZAR: pulp.LpMinimize, Sentido.MAXIMIZAR: pulp.LpMaximize}
_RELACOES = {
    Relacao.MENOR_OU_IGUAL: pulp.LpConstraintLE,
    Relacao.MAIOR_OU_IGUAL: pulp.LpConstraintGE,
    Relacao.IGUAL: pulp.LpConstraintEQ,
}
_COM_SOLUCAO = frozenset({pulp.LpSolutionOptimal, pulp.LpSolutionIntegerFeasible})
_CATEGORIAS = {"continua": pulp.LpContinuous, "inteira": pulp.LpInteger, "binaria": pulp.LpInteger}


class BackendPulp:
    """Backend ``pulp``; motor ``cbc``."""

    nome = "pulp"

    def motores(self) -> tuple[str, ...]:
        """Motores suportados."""
        return ("cbc",)

    def resolver(
        self,
        modelo: ModeloInstanciado,
        *,
        motor: str = "cbc",
        opcoes: OpcoesSolver = OpcoesSolver(),  # noqa: B008 - dataclass imutável
    ) -> ExecucaoSolver:
        """Resolve o modelo com o CBC embutido no PuLP."""
        if motor not in self.motores():
            raise ErroSolver(f"O backend pulp não suporta o motor {motor!r}; use 'cbc'")
        problema = pulp.LpProblem("modelo", _SENTIDOS[modelo.objetivo.sentido])
        # Nomes sintéticos: membros de conjunto podem ter espaço e acento, que o
        # formato MPS não aceita. O mapa devolve os nomes do modelo neutro.
        variaveis = {
            v.nome: problema.add_variable(
                f"v{posicao}", v.limite_inferior, v.limite_superior, _CATEGORIAS[v.tipo.value]
            )
            for posicao, v in enumerate(modelo.variaveis)
        }
        problema.setObjective(
            pulp.LpAffineExpression(
                [(variaveis[nome], coeficiente) for nome, coeficiente in modelo.objetivo.termos],
                constant=modelo.objetivo.constante,
            )
        )
        restricoes = {}
        for posicao, restricao in enumerate(modelo.restricoes):
            expressao = pulp.LpAffineExpression(
                [(variaveis[nome], coeficiente) for nome, coeficiente in restricao.termos]
            )
            restricoes[restricao.nome] = pulp.LpConstraint(
                expressao, sense=_RELACOES[restricao.relacao], rhs=restricao.lado_direito
            )
            problema.addConstraint(restricoes[restricao.nome], f"r{posicao}")
        with tempfile.TemporaryDirectory(prefix="po-multiagente-") as pasta:
            log = Path(pasta) / "cbc.log"
            try:
                problema.solve(_comando_cbc(opcoes, log))
            except pulp.PulpSolverError as erro:
                return ExecucaoSolver(
                    resultado=ResultadoSolver(
                        status=StatusSolucao.ERRO, solver=identificacao(), tempo_segundos=0.0
                    ),
                    log=f"{_ler(log)}\n{erro}".strip(),
                )
            texto_log = _ler(log)
        status = _status(problema)
        com_solucao = status in (StatusSolucao.OTIMO, StatusSolucao.LIMITE_TEMPO) and (
            problema.sol_status in _COM_SOLUCAO
        )
        resultado = ResultadoSolver(
            status=status,
            solver=identificacao(),
            valor_objetivo=_zero_positivo(pulp.value(problema.objective)) if com_solucao else None,
            valores=(
                {nome: _zero_positivo(v.varValue) for nome, v in variaveis.items()}
                if com_solucao
                else {}
            ),
            duais=(
                {nome: _zero_positivo(r.pi) for nome, r in restricoes.items()}
                if status is StatusSolucao.OTIMO and not modelo.inteiro
                else None
            ),
            tempo_segundos=max(problema.solutionTime or 0.0, 0.0),
        )
        return ExecucaoSolver(resultado=resultado, log=texto_log)


def identificacao() -> IdentificacaoSolver:
    """Backend, motor e versão do CBC embutido."""
    return IdentificacaoSolver(backend="pulp", motor="cbc", versao=_versao_cbc())


@cache
def _versao_cbc() -> str:
    """Versão lida do cabeçalho do próprio binário, e não presumida."""
    caminho = _comando_cbc(OpcoesSolver(), None).path
    try:
        saida = subprocess.run(
            [caminho], input="quit\n", capture_output=True, text=True, timeout=10, check=False
        ).stdout
    except OSError as erro:  # pragma: no cover - binário ausente
        raise ErroSolver(f"CBC indisponível em {caminho}: {erro}") from erro
    for linha in saida.splitlines():
        if linha.strip().startswith("Version:"):
            return f"{linha.split(':', 1)[1].strip()} (PuLP {pulp.__version__})"
    return f"desconhecida (PuLP {pulp.__version__})"  # pragma: no cover


def _comando_cbc(opcoes: OpcoesSolver, log: Path | None) -> pulp.PULP_CBC_CMD:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="PULP_CBC_CMD is deprecated")
        return pulp.PULP_CBC_CMD(
            msg=False,
            timeLimit=opcoes.limite_tempo_s,
            gapRel=opcoes.gap_relativo,
            threads=opcoes.threads,
            logPath=str(log) if log else None,
        )


def _status(problema: pulp.LpProblem) -> StatusSolucao:
    status, solucao = problema.status, problema.sol_status
    if status == pulp.LpStatusInfeasible:
        return StatusSolucao.INVIAVEL
    if status == pulp.LpStatusUnbounded:
        return StatusSolucao.ILIMITADO
    if solucao == pulp.LpSolutionOptimal:
        return StatusSolucao.OTIMO
    # Solução inteira viável sem prova de otimalidade, ou nenhuma solução no prazo.
    if solucao in (pulp.LpSolutionIntegerFeasible, pulp.LpSolutionNoSolutionFound):
        return StatusSolucao.LIMITE_TEMPO
    return StatusSolucao.ERRO


def _zero_positivo(valor: float | None) -> float:
    """Converte ``None`` e ``-0.0`` em ``0.0``, para resultados comparáveis."""
    return (valor or 0.0) + 0.0


def _ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8", errors="replace") if caminho.exists() else ""
