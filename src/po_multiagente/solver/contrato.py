"""Contrato que todo adaptador de solver cumpre (ADR-006)."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from po_multiagente.dominio import ResultadoSolver
from po_multiagente.modelo import ModeloInstanciado


@dataclass(frozen=True)
class OpcoesSolver:
    """Opções comuns a todos os backends.

    Attributes:
        limite_tempo_s: Tempo máximo de resolução; ``None`` sem limite.
        gap_relativo: Tolerância de otimalidade em PLIM; ``None`` usa o
            padrão do motor.
        threads: Linhas de execução. O padrão, 1, torna o caminho do solver
            reproduzível.
    """

    limite_tempo_s: float | None = None
    gap_relativo: float | None = None
    threads: int = 1


@dataclass(frozen=True)
class ExecucaoSolver:
    """Resultado canônico e o registro textual do solver, que vai para o dossiê."""

    resultado: ResultadoSolver
    log: str


class ErroSolver(Exception):
    """Backend ou motor indisponível, ou configuração inválida."""


@runtime_checkable
class SolverBackend(Protocol):
    """Traduz o modelo neutro para um solver e devolve o resultado canônico.

    Um adaptador novo implementa este protocolo, é registrado no grupo de
    entry points ``po_multiagente.solvers`` e passa pela suíte de
    conformidade (``tests/conformidade_solver``).
    """

    nome: str
    """Nome do backend no registro, como ``pulp``."""

    def motores(self) -> tuple[str, ...]:
        """Motores que este backend sabe usar, como ``("cbc",)``."""
        ...

    def resolver(
        self, modelo: ModeloInstanciado, *, motor: str, opcoes: OpcoesSolver
    ) -> ExecucaoSolver:
        """Resolve o modelo.

        Inviabilidade, ilimitação e limite de tempo são resultados, não
        exceções: voltam como ``StatusSolucao``. Uma falha do próprio solver
        volta como ``StatusSolucao.ERRO``.

        Raises:
            ErroSolver: Se o motor não for suportado ou estiver indisponível.
        """
        ...
