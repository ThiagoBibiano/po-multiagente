"""Modelo de linguagem roteirizado, para testes e demonstrações sem rede.

Cada agente recebe, em ordem, as respostas de um roteiro. Não substitui o
modelo no experimento: serve para exercitar o arnês (grafo, agentes,
validação, dossiê) de forma determinística.
"""

import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any

from po_multiagente.llm.porta import ErroLLM, Pedido, RespostaLLM

Resposta = dict[str, Any] | Callable[[Pedido], dict[str, Any]]


class LLMRoteirizado:
    """Devolve, para cada agente, as respostas do roteiro na ordem dada.

    Args:
        roteiro: Respostas por agente; cada uma é um dicionário (serializado
            como JSON) ou uma função do pedido.
    """

    modelo = "roteirizado"

    def __init__(self, roteiro: dict[str, Iterable[Resposta]]) -> None:
        self._filas = {agente: list(respostas) for agente, respostas in roteiro.items()}
        self.pedidos: dict[str, list[Pedido]] = defaultdict(list)

    def gerar(self, pedido: Pedido) -> RespostaLLM:
        """Próxima resposta do roteiro do agente."""
        self.pedidos[pedido.agente].append(pedido)
        fila = self._filas.get(pedido.agente)
        if not fila:
            raise ErroLLM(f"Roteiro sem resposta para o agente {pedido.agente}")
        resposta = fila.pop(0)
        conteudo = resposta(pedido) if callable(resposta) else resposta
        return RespostaLLM(texto=json.dumps(conteudo, ensure_ascii=False), modelo=self.modelo)
