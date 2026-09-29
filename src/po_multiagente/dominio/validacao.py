"""Verificações e parecer do agente Validador."""

from enum import StrEnum

from pydantic import Field, PositiveInt, model_validator

from po_multiagente.dominio._base import ObjetoDominio, TextoNaoVazio


class Sinal(StrEnum):
    """Sinais externos do Validador (cap. 3, Quadro de sinais)."""

    S1 = "S1"
    """Estado de retorno do solver."""
    S2 = "S2"
    """Consistência de unidades."""
    S3 = "S3"
    """Cobertura de parâmetros."""
    S4 = "S4"
    """Cobertura de requisitos."""
    S5 = "S5"
    """Limites triviais do valor objetivo."""


class Verificacao(ObjetoDominio):
    """Resultado de um sinal sobre o modelo.

    Attributes:
        elementos: Identificadores localizados (restrição, parâmetro,
            requisito...). O Validador é desenhado para localizar, pois os
            modelos de linguagem corrigem bem quando recebem a localização.
        confirmacao: Pergunta ao usuário, em linguagem de negócio, quando o
            sinal não basta para reprovar, mas o resultado é suspeito
            (ADR-011). Não reprova: a resposta do usuário decide se a
            especificação volta ao Interpretador.
    """

    sinal: Sinal
    aprovada: bool
    mensagem: TextoNaoVazio
    elementos: tuple[TextoNaoVazio, ...] = ()
    confirmacao: TextoNaoVazio | None = None

    @model_validator(mode="after")
    def _confirmacao_so_sem_reprovacao(self) -> "Verificacao":
        if self.confirmacao is not None and not self.aprovada:
            raise ValueError(
                "Uma verificação reprovada volta ao Modelador; não pergunta ao usuário"
            )
        return self


class ParecerValidador(ObjetoDominio):
    """Conjunto de verificações de uma iteração do laço de correção."""

    iteracao: PositiveInt
    verificacoes: tuple[Verificacao, ...] = Field(min_length=1)

    @property
    def aprovado(self) -> bool:
        """Indica se todas as verificações foram aprovadas."""
        return all(v.aprovada for v in self.verificacoes)

    @property
    def confirmacoes(self) -> tuple[str, ...]:
        """Perguntas ao usuário que precisam de resposta antes da explicação."""
        return tuple(v.confirmacao for v in self.verificacoes if v.confirmacao)
