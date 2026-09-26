"""Contrato de acesso a modelos de linguagem (ADR-003)."""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Uso:
    """Tokens de uma chamada; ``entrada_em_cache`` e ``raciocinio`` são subtotais."""

    entrada: int = 0
    entrada_em_cache: int = 0
    saida: int = 0
    raciocinio: int = 0

    def __add__(self, outro: "Uso") -> "Uso":
        """Soma de usos, para totalizar uma execução."""
        return Uso(
            self.entrada + outro.entrada,
            self.entrada_em_cache + outro.entrada_em_cache,
            self.saida + outro.saida,
            self.raciocinio + outro.raciocinio,
        )


@dataclass(frozen=True)
class Pedido:
    """Uma chamada ao modelo: instruções do agente, entrada e esquema da saída."""

    agente: str
    instrucoes: str
    entrada: str
    nome_esquema: str
    esquema: dict[str, Any]


@dataclass(frozen=True)
class RespostaLLM:
    """Resposta textual (JSON) com o uso e os parâmetros efetivamente aplicados."""

    texto: str
    modelo: str
    uso: Uso = field(default_factory=Uso)
    parametros: dict[str, Any] = field(default_factory=dict)
    duracao_s: float = 0.0
    gravada: bool = False


class ErroLLM(Exception):
    """Falha de comunicação, recusa ou resposta incompleta do modelo."""


@runtime_checkable
class LLMPort(Protocol):
    """Gera uma resposta estruturada para um pedido."""

    @property
    def modelo(self) -> str:
        """Identificador do modelo, registrado em toda execução."""
        ...

    def gerar(self, pedido: Pedido) -> RespostaLLM:
        """Chama o modelo.

        Raises:
            ErroLLM: Se não houver resposta utilizável.
        """
        ...
