"""Gerador-Executor: compila o modelo com os dados e resolve, sem modelo de linguagem."""

from dataclasses import dataclass

from po_multiagente.dados import ErroLigacao, Fontes, ligar
from po_multiagente.dominio import (
    Especificacao,
    IdentificacaoSolver,
    ResultadoSolver,
    StatusSolucao,
)
from po_multiagente.modelo import (
    ErroInstanciacao,
    ModeloCompilado,
    ModeloInstanciado,
    instanciar,
)
from po_multiagente.solver import OpcoesSolver, SolverBackend


@dataclass(frozen=True)
class Execucao:
    """Resultado do Gerador-Executor.

    Attributes:
        instancia: Modelo instanciado; ``None`` se os dados não ligaram.
        erros: Falhas de ligação ou instanciação, localizadas.
    """

    compilado: ModeloCompilado
    instancia: ModeloInstanciado | None
    resultado: ResultadoSolver
    log: str
    erros: tuple[str, ...] = ()


class GeradorExecutor:
    """Agente Gerador-Executor: determinístico, com o solver fixo (Passo 4).

    Args:
        backend: Backend de solver, o mesmo nas duas configurações.
        motor: Motor do backend.
        opcoes: Opções do solver.
    """

    agente = "gerador_executor"

    def __init__(self, backend: SolverBackend, motor: str, opcoes: OpcoesSolver) -> None:
        self._backend = backend
        self._motor = motor
        self._opcoes = opcoes

    def executar(
        self, compilado: ModeloCompilado, especificacao: Especificacao, fontes: Fontes
    ) -> Execucao:
        """Liga os dados, instancia e resolve."""
        try:
            dados = ligar(compilado.ir, especificacao, fontes)
            instancia = instanciar(compilado, dados.conjuntos, dados.parametros)
        except ErroLigacao as erro:
            return self._falha(compilado, [str(e) for e in erro.erros])
        except ErroInstanciacao as erro:
            return self._falha(compilado, [str(e) for e in erro.erros])
        execucao = self._backend.resolver(instancia, motor=self._motor, opcoes=self._opcoes)
        return Execucao(compilado, instancia, execucao.resultado, execucao.log)

    def resolver(self, instancia: ModeloInstanciado) -> ResultadoSolver:
        """Resolve uma variante do modelo (diagnóstico do S1), com o mesmo solver."""
        return self._backend.resolver(instancia, motor=self._motor, opcoes=self._opcoes).resultado

    def _falha(self, compilado: ModeloCompilado, erros: list[str]) -> Execucao:
        resultado = ResultadoSolver(
            status=StatusSolucao.ERRO,
            solver=IdentificacaoSolver(
                backend=self._backend.nome, motor=self._motor, versao="não executado"
            ),
            tempo_segundos=0.0,
        )
        return Execucao(compilado, None, resultado, "", tuple(erros))
