"""Resultado canônico de uma execução do solver, independente do backend."""

from enum import StrEnum

from pydantic import Field, NonNegativeFloat, model_validator

from po_multiagente.dominio._base import ObjetoDominio, TextoNaoVazio


class StatusSolucao(StrEnum):
    """Estado de retorno do solver, padronizado entre backends (sinal S1)."""

    OTIMO = "otimo"
    INVIAVEL = "inviavel"
    ILIMITADO = "ilimitado"
    LIMITE_TEMPO = "limite_tempo"
    ERRO = "erro"


class IdentificacaoSolver(ObjetoDominio):
    """Backend, motor e versão usados, registrados em toda execução."""

    backend: TextoNaoVazio
    motor: TextoNaoVazio
    versao: TextoNaoVazio


class ResultadoSolver(ObjetoDominio):
    """Resultado de uma execução do solver.

    A solução vem sempre do solver, nunca do modelo de linguagem (ajuste
    decorrente do piloto, cap. 3).

    Attributes:
        valores: Valor de cada variável instanciada; vazio sem solução.
        duais: Preços-sombra por restrição instanciada, quando o backend os
            fornece (PL).
        tempo_segundos: Tempo de resolução informado pelo backend.
    """

    status: StatusSolucao
    solver: IdentificacaoSolver
    valor_objetivo: float | None = None
    valores: dict[str, float] = Field(default_factory=dict)
    duais: dict[str, float] | None = None
    tempo_segundos: NonNegativeFloat

    @model_validator(mode="after")
    def _coerente_com_status(self) -> "ResultadoSolver":
        if self.status is StatusSolucao.OTIMO and self.valor_objetivo is None:
            raise ValueError("Status ótimo exige valor objetivo")
        sem_solucao = (StatusSolucao.INVIAVEL, StatusSolucao.ILIMITADO, StatusSolucao.ERRO)
        if self.status in sem_solucao and (self.valor_objetivo is not None or self.valores):
            raise ValueError(f"Status {self.status.value} não admite solução")
        return self
