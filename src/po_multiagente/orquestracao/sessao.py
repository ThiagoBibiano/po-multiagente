"""Sessão de uso: conduz o grafo e expõe as interrupções ao chamador (interface ou experimento)."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from po_multiagente.config import ConfiguracaoExecucao
from po_multiagente.llm import LLMPort
from po_multiagente.orquestracao.grafo import Agentes, Estado, montar_grafo


@dataclass(frozen=True)
class Interrupcao:
    """O grafo parou e espera uma resposta.

    Attributes:
        tipo: ``solicitacoes`` (arquivos tratados) ou ``confirmacao`` (ADR-011).
        conteudo: Solicitações ou perguntas, em JSON.
    """

    tipo: str
    conteudo: dict[str, Any]


class Sessao:
    """Uma execução do fluxo, do pedido à explicação.

    Args:
        llm: Modelo de linguagem (ou cassete, ou roteiro).
        configuracao: Configuração da execução.
        ao_iniciar_no: Chamada com o nome de cada nó do grafo quando ele começa
            (``interpretar``, ``modelar``...), para a interface mostrar o progresso.
    """

    def __init__(
        self,
        llm: LLMPort,
        configuracao: ConfiguracaoExecucao,
        ao_iniciar_no: Callable[[str], None] | None = None,
    ) -> None:
        self.configuracao = configuracao
        self._grafo = montar_grafo(Agentes.criar(llm, configuracao), configuracao)
        self._config: RunnableConfig = {"configurable": {"thread_id": uuid.uuid4().hex}}
        self._ao_iniciar_no = ao_iniciar_no

    def iniciar(self, descricao: str, pasta_dados: Path) -> Interrupcao | Estado:
        """Começa pelo pedido e pela pasta de dados."""
        entrada: Estado = {"descricao": descricao, "pasta_dados": str(pasta_dados)}
        return self._executar(entrada)

    def responder(self, resposta: dict[str, Any]) -> Interrupcao | Estado:
        """Retoma depois de uma interrupção.

        Args:
            resposta: Para ``solicitacoes``, ``{"pasta": ..., "respondidas": {id: arquivo}}``;
                para ``confirmacao``, ``{"aceita": bool, "observacao": str | None}``.
        """
        return self._executar(Command(resume=resposta))

    @property
    def estado(self) -> Estado:
        """Estado atual da sessão."""
        return cast(Estado, self._grafo.get_state(self._config).values)

    def _executar(self, entrada: Estado | Command[Any]) -> Interrupcao | Estado:
        """Roda o grafo até o fim ou até a próxima interrupção, avisando cada nó que começa."""
        for evento in self._grafo.stream(entrada, self._config, stream_mode="tasks"):
            if self._ao_iniciar_no is not None and "result" not in evento:
                self._ao_iniciar_no(str(evento["name"]))
        retrato = self._grafo.get_state(self._config)
        if retrato.interrupts:
            valor = retrato.interrupts[0].value
            return Interrupcao(tipo=valor["tipo"], conteudo=valor)
        return cast(Estado, retrato.values)
