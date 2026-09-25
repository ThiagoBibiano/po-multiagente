"""Requisitos de negócio e alertas de ambiguidade produzidos pelo Interpretador."""

from pydantic import Field

from po_multiagente.dominio._base import IdRequisito, ObjetoDominio, TextoNaoVazio


class Requisito(ObjetoDominio):
    """Requisito extraído da descrição, em vocabulário de negócio.

    Cada restrição do modelo aponta para ao menos um requisito, e cada
    requisito deve ser coberto por ao menos uma restrição ou pelo objetivo
    (sinal S4).
    """

    id: IdRequisito
    texto: TextoNaoVazio


class AlertaAmbiguidade(ObjetoDominio):
    """Trecho da descrição que admite mais de uma leitura."""

    trecho: TextoNaoVazio
    leituras: tuple[TextoNaoVazio, ...] = Field(min_length=2)
    requisito_id: IdRequisito | None = None
