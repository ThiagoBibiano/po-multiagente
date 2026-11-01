"""Interface de chat (Gradio) sobre a ``Conversa``.

O usuário descreve o problema e, se tiver, anexa as planilhas numa caixa de
mensagem; sem planilhas, o Organizador monta tabelas com os números da conversa
para ele conferir (ADR-015). A plataforma responde no chat. Enquanto o fluxo
roda, um bloco "Andamento" mostra cada passo ao vivo. Pedidos de planilha
ajustada e a conferência de um resultado suspeito (ADR-011) chegam como
perguntas, com respostas rápidas quando cabem. A resposta vem primeiro; os
detalhes técnicos (R5) ficam em blocos recolhidos, e o dossiê, no arquivo para
baixar.
"""

import queue
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import gradio as gr

from po_multiagente.agentes import Organizador
from po_multiagente.interface.app import LATEX, PRIVACIDADE, carregar_exemplo
from po_multiagente.interface.assistente import Assistente
from po_multiagente.interface.conversa import BOAS_VINDAS, Conversa, Mensagem

Historico = list[dict[str, Any]]
Saida = tuple[Historico, Conversa, dict[str, Any]]

ESPERA_S = 0.3
"""Intervalo entre atualizações do andamento na tela."""


def construir_chat(
    criar_assistente: Callable[[], Assistente],
    modelo: str = "",
    organizador: Organizador | None = None,
    copias: Path | None = None,
) -> gr.Blocks:
    """Monta a interface de chat.

    Args:
        criar_assistente: Cria um assistente novo para cada problema.
        modelo: Nome do modelo, para o aviso de privacidade.
        organizador: Monta tabelas com os números da conversa quando o
            usuário não tem planilhas (ADR-015).
        copias: Pasta para uma cópia de cada arquivo oferecido (no Colab,
            visível no painel de arquivos).
    """

    def nova_conversa() -> Conversa:
        return Conversa(criar_assistente, organizador=organizador, copias=copias)

    app = gr.Blocks(title="Otimização de decisões")
    with app:
        estado = gr.State(None)
        gr.Markdown("# Otimização de decisões a partir das suas planilhas")
        chat = gr.Chatbot(
            value=_inicio,
            height=640,
            latex_delimiters=LATEX,
            show_label=False,
            feedback_options=None,
            buttons=["copy"],
        )
        caixa = gr.MultimodalTextbox(
            placeholder="Descreva o problema; se tiver planilhas (CSV ou Excel), anexe…",
            file_count="multiple",
            show_label=False,
            autofocus=True,
        )
        with gr.Row():
            exemplo = gr.Button("Usar o exemplo da marcenaria", size="sm")
            nova = gr.Button("Nova conversa", size="sm")
        gr.Markdown(PRIVACIDADE.format(modelo=modelo or "configurado"))

        def ao_enviar(
            mensagem: dict[str, Any] | None, historico: Historico, conversa: Conversa | None
        ) -> Iterator[Saida]:
            mensagem = mensagem or {}
            yield from turno(
                conversa or nova_conversa(),
                historico,
                str(mensagem.get("text") or ""),
                [Path(f) for f in mensagem.get("files") or []],
            )

        def ao_escolher(
            historico: Historico, conversa: Conversa | None, evento: gr.SelectData
        ) -> Iterator[Saida]:
            yield from turno(conversa or nova_conversa(), historico, str(evento.value))

        def ao_usar_exemplo(historico: Historico, conversa: Conversa | None) -> Iterator[Saida]:
            descricao, arquivos = carregar_exemplo()
            yield from turno(nova_conversa(), historico, descricao, [Path(a) for a in arquivos])

        saidas = [chat, estado, caixa]
        caixa.submit(ao_enviar, [caixa, chat, estado], saidas, show_progress="hidden")
        chat.option_select(ao_escolher, [chat, estado], saidas, show_progress="hidden")
        exemplo.click(ao_usar_exemplo, [chat, estado], saidas, show_progress="hidden")
        nova.click(lambda: (_inicio(), None, gr.update(value=None)), None, saidas)
    return app


def turno(
    conversa: Conversa,
    historico: Historico,
    texto: str,
    arquivos: Sequence[Path] = (),
) -> Iterator[Saida]:
    """Uma rodada do chat: a mensagem do usuário, o andamento ao vivo e a resposta.

    Gera o histórico a cada atualização; a caixa de mensagem fica bloqueada
    enquanto o fluxo roda.
    """
    historico = [*historico, *_do_usuario(texto, arquivos)]
    bloqueada = gr.update(value=None, interactive=False)
    andamento: dict[str, Any] = {
        "role": "assistant",
        "content": "",
        "metadata": {"title": "Trabalhando…", "status": "pending"},
    }
    passos: queue.Queue[str] = queue.Queue()
    resposta: list[Mensagem] = []

    def trabalhar() -> None:
        try:
            resposta.extend(conversa.responder(texto, arquivos, passos.put))
        except Exception as erro:  # a interface não pode cair; o detalhe vai ao chat.
            resposta.append(Mensagem(f"⚠️ Erro inesperado: {erro}"))

    inicio = time.perf_counter()
    linha = threading.Thread(target=trabalhar, daemon=True)
    linha.start()
    vistos: list[str] = []
    while linha.is_alive() or not passos.empty():
        novos = _esvaziar(passos)
        if novos:
            vistos += novos
            andamento["content"] = "\n".join(f"- {p}" for p in vistos)
            andamento["metadata"]["log"] = vistos[-1]
            yield [*historico, andamento], conversa, bloqueada
        linha.join(ESPERA_S)
    if vistos:
        andamento["metadata"] = {
            "title": "Andamento",
            "status": "done",
            "duration": round(time.perf_counter() - inicio, 1),
        }
        historico.append(andamento)
    for mensagem in resposta:
        historico += para_gradio(mensagem)
    yield historico, conversa, gr.update(value=None, interactive=True)


def para_gradio(mensagem: Mensagem) -> Historico:
    """Mensagem da plataforma no formato do ``gr.Chatbot``."""
    saida: Historico = []
    if mensagem.texto:
        item: dict[str, Any] = {"role": "assistant", "content": mensagem.texto}
        if mensagem.titulo:
            item["metadata"] = {"title": mensagem.titulo, "status": "done"}
        if mensagem.opcoes:
            item["options"] = [{"value": o} for o in mensagem.opcoes]
        saida.append(item)
    if mensagem.arquivo is not None:
        saida.append({"role": "assistant", "content": {"path": str(mensagem.arquivo)}})
    return saida


def _inicio() -> Historico:
    return [{"role": "assistant", "content": BOAS_VINDAS}]


def _do_usuario(texto: str, arquivos: Sequence[Path]) -> Historico:
    mensagens: Historico = [{"role": "user", "content": {"path": str(a)}} for a in arquivos]
    if texto.strip():
        mensagens.append({"role": "user", "content": texto})
    return mensagens


def _esvaziar(fila: "queue.Queue[str]") -> list[str]:
    itens = []
    while True:
        try:
            itens.append(fila.get_nowait())
        except queue.Empty:
            return itens
