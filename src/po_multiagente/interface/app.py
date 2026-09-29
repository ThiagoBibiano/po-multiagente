"""Interface Gradio (ADR-001): assistente em etapas sobre o ``Assistente``.

Camada fina: mostra a etapa atual e repassa as respostas do usuário. Etapas:
descrever o problema, esclarecer (solicitações de tratamento), confirmar um
resultado suspeito (ADR-011) e ver o resultado, com a explicação primeiro e
os artefatos técnicos em abas (R5).
"""

import os
from collections.abc import Callable, Sequence
from importlib.resources import files
from pathlib import Path
from typing import Any

import gradio as gr

from po_multiagente.config import ConfiguracaoExecucao, carregar_perfil
from po_multiagente.interface.assistente import Assistente, ErroAssistente, Etapa, Resultado
from po_multiagente.llm import AdaptadorOpenAI, ErroLLM

EXEMPLO = Path(str(files("po_multiagente.interface").joinpath("exemplos", "marcenaria")))
"""Piloto do TG1 (marcenaria), para o botão "carregar exemplo"."""

_AVISO = (
    "Os textos e os dados enviados vão para o provedor do modelo de linguagem "
    "(**{modelo}**). No nível gratuito, o provedor pode usá-los para melhorar os "
    "produtos; não envie dados pessoais nem sigilosos."
)
_MOTIVOS = {
    "granularidade": "está em outra granularidade",
    "unidade": "está em outra unidade",
    "identificador": "usa códigos que precisam ser traduzidos",
    "juncao": "precisa ser combinado com outra tabela",
    "faltante": "não existe nas fontes",
}
_LATEX: list[dict[str, str | bool]] = [{"left": "$$", "right": "$$", "display": True}]

Telas = tuple[Any, ...]


def construir_app(criar_assistente: Callable[[], Assistente], modelo: str = "") -> gr.Blocks:
    """Monta a interface.

    Args:
        criar_assistente: Cria um assistente novo a cada execução.
        modelo: Nome do modelo, para o aviso de privacidade.
    """
    app = gr.Blocks(title="Plataforma multiagente de PO")
    with app:
        assistente = gr.State(None)
        gr.Markdown(
            "# Plataforma multiagente de Pesquisa Operacional\n\n"
            "Descreva o problema em português e envie as planilhas: a plataforma "
            "formula o modelo, resolve com o solver e explica o resultado.\n\n"
            + _AVISO.format(modelo=modelo or "configurado")
        )

        with gr.Column():
            gr.Markdown("## 1. Descrever")
            descricao = gr.Textbox(label="Problema", lines=6, placeholder="O que decidir e por quê")
            arquivos = gr.File(
                label="Fontes de dados (CSV ou XLSX)",
                file_count="multiple",
                file_types=[".csv", ".xlsx"],
                type="filepath",
            )
            with gr.Row():
                exemplo = gr.Button("Carregar exemplo")
                executar = gr.Button("Formular e resolver", variant="primary")

        with gr.Column(visible=False) as passo_tratar:
            gr.Markdown("## 2. Esclarecer os dados")
            solicitacoes = gr.Markdown()
            tratados = gr.File(
                label="Arquivos tratados, na ordem da lista",
                file_count="multiple",
                file_types=[".csv", ".xlsx"],
                type="filepath",
            )
            tratar = gr.Button("Enviar arquivos tratados", variant="primary")

        with gr.Column(visible=False) as passo_confirmar:
            gr.Markdown("## 2. Conferir o resultado")
            perguntas = gr.Markdown()
            faz_sentido = gr.Radio(
                ["Sim, faz sentido", "Não faz sentido"], value="Sim, faz sentido", label="Resposta"
            )
            observacao = gr.Textbox(label="O que está faltando ou errado (opcional)", lines=2)
            confirmar = gr.Button("Responder", variant="primary")

        with gr.Column(visible=False) as passo_resultado:
            gr.Markdown("## 3. Resultado")
            explicacao = gr.Markdown()
            with gr.Tab("Solução"):
                solucao = gr.JSON(label="Valor de cada variável")
            with gr.Tab("Formulação"):
                formulacao = gr.Markdown(latex_delimiters=_LATEX)
            with gr.Tab("Especificação"):
                especificacao = gr.JSON(label="Quadro de especificação")
            with gr.Tab("Modelo"):
                modelo_ir = gr.JSON(label="Representação intermediária")
            with gr.Tab("Validação"):
                pareceres = gr.JSON(label="Pareceres do Validador")
            with gr.Tab("Execução"):
                execucao = gr.Markdown()

        telas = [
            assistente,
            passo_tratar,
            solicitacoes,
            passo_confirmar,
            perguntas,
            passo_resultado,
            explicacao,
            solucao,
            formulacao,
            especificacao,
            modelo_ir,
            pareceres,
            execucao,
        ]

        def ao_executar(texto: str, enviados: list[str] | None) -> Telas:
            novo = criar_assistente()
            return _telas(novo, _proteger(lambda: novo.comecar(texto, _caminhos(enviados))))

        def ao_tratar(atual: Assistente | None, enviados: list[str] | None) -> Telas:
            atual = _exigir(atual)
            return _telas(atual, _proteger(lambda: atual.responder_em_ordem(_caminhos(enviados))))

        def ao_confirmar(atual: Assistente | None, resposta: str, nota: str) -> Telas:
            atual = _exigir(atual)
            aceita = resposta.startswith("Sim")
            return _telas(atual, _proteger(lambda: atual.confirmar(aceita, nota)))

        exemplo.click(carregar_exemplo, outputs=[descricao, arquivos])
        executar.click(ao_executar, inputs=[descricao, arquivos], outputs=telas)
        tratar.click(ao_tratar, inputs=[assistente, tratados], outputs=telas)
        confirmar.click(ao_confirmar, inputs=[assistente, faz_sentido, observacao], outputs=telas)
    return app


def iniciar(perfil: str | None = None, *, compartilhar: bool = False) -> None:
    """Abre a interface (no Colab, dentro do próprio notebook).

    A chave do modelo vem da variável de ambiente do perfil (por exemplo,
    ``GEMINI_API_KEY``) ou, no Colab, dos Secrets com o mesmo nome.

    Args:
        perfil: Perfil do modelo; o padrão é o do experimento.
        compartilhar: Gera um link público temporário do Gradio.
    """
    configuracao = ConfiguracaoExecucao(perfil_modelo=perfil) if perfil else ConfiguracaoExecucao()
    perfil_modelo = carregar_perfil(configuracao.perfil_modelo)
    _ler_segredo_do_colab(perfil_modelo.variavel_chave)
    llm = AdaptadorOpenAI(perfil_modelo)
    app = construir_app(lambda: Assistente(llm, configuracao), modelo=perfil_modelo.modelo)
    app.launch(share=compartilhar, show_error=True)


def carregar_exemplo() -> tuple[str, list[str]]:
    """Descrição e arquivos do piloto da marcenaria."""
    descricao = (EXEMPLO / "descricao.md").read_text(encoding="utf-8")
    return descricao, [str(p) for p in sorted((EXEMPLO / "dados").iterdir())]


def formatar_solicitacoes(etapa: Etapa) -> str:
    """Lista numerada do que o usuário precisa tratar, só sobre os dados."""
    linhas = [
        "A plataforma não conseguiu ler alguns dados diretamente. Trate cada item "
        "e envie os arquivos na **mesma ordem** da lista:",
        "",
    ]
    for numero, solicitacao in enumerate(etapa.solicitacoes, start=1):
        coluna = f", coluna `{solicitacao.coluna}`" if solicitacao.coluna else ""
        motivo = _MOTIVOS.get(solicitacao.motivo.value, solicitacao.motivo.value)
        linhas.append(
            f"{numero}. `{solicitacao.arquivo}`{coluna}: o dado {motivo}. "
            f"Forma esperada: {solicitacao.forma_esperada}"
        )
    return "\n".join(linhas)


def formatar_explicacao(resultado: Resultado) -> str:
    """A explicação ao gestor ou, sem ela, o motivo de o fluxo ter parado."""
    if resultado.explicacao:
        return resultado.explicacao
    motivo = resultado.falha or f"status do solver: {resultado.status or 'sem resultado'}"
    return f"**O fluxo terminou sem solução.** {motivo}"


def formatar_execucao(resultado: Resultado) -> str:
    """Status, valor e consumo da execução."""
    valor = "—" if resultado.valor_objetivo is None else f"{resultado.valor_objetivo:g}"
    return (
        f"- Status do solver: {resultado.status or 'sem resultado'}\n"
        f"- Valor do objetivo: {valor}\n"
        f"- Iterações do Validador: {len(resultado.pareceres)}\n"
        f"- Chamadas ao modelo: {resultado.chamadas_llm} "
        f"({resultado.tokens_entrada} tokens de entrada, {resultado.tokens_saida} de saída)\n"
        f"- Custo estimado: {resultado.moeda} {resultado.custo:.4f}"
    )


def _telas(assistente: Assistente, etapa: Etapa) -> Telas:
    """Visibilidade e conteúdo de cada etapa, na ordem de ``telas``."""
    em_tratamento = etapa.tipo == "solicitacoes"
    em_confirmacao = etapa.tipo == "confirmacao"
    no_fim = etapa.tipo == "resultado"
    resultado = assistente.resultado() if no_fim else None
    return (
        assistente,
        gr.update(visible=em_tratamento),
        formatar_solicitacoes(etapa) if em_tratamento else "",
        gr.update(visible=em_confirmacao),
        "\n\n".join(etapa.perguntas),
        gr.update(visible=no_fim),
        formatar_explicacao(resultado) if resultado else "",
        resultado.solucao if resultado else None,
        f"$$\n{resultado.formulacao_latex}\n$$" if resultado and resultado.formulacao_latex else "",
        resultado.especificacao if resultado else None,
        resultado.modelo if resultado else None,
        resultado.pareceres if resultado else None,
        formatar_execucao(resultado) if resultado else "",
    )


def _proteger(passo: Callable[[], Etapa]) -> Etapa:
    """Mostra erros de uso e de comunicação como aviso na tela, sem derrubar a interface."""
    try:
        return passo()
    except (ErroAssistente, ErroLLM) as erro:
        raise gr.Error(str(erro)) from erro


def _exigir(assistente: Assistente | None) -> Assistente:
    if assistente is None:
        raise gr.Error("Comece pela etapa 1: descreva o problema e execute.")
    return assistente


def _caminhos(enviados: Sequence[str] | None) -> list[Path]:
    return [Path(p) for p in enviados or []]


def _ler_segredo_do_colab(nome: str) -> None:
    """No Colab, copia o segredo ``nome`` para o ambiente, se ainda não estiver lá."""
    if os.environ.get(nome):
        return
    try:
        from google.colab import userdata  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError:
        return
    try:
        valor = userdata.get(nome)
    except Exception:  # segredo ausente ou sem permissão: o adaptador avisa depois.
        return
    if valor:
        os.environ[nome] = str(valor)
