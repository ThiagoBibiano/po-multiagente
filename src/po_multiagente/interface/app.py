"""Interface Gradio (ADR-001): assistente em etapas sobre o ``Assistente``.

Camada fina: mostra a etapa atual e repassa as respostas do usuário. Etapas:
descrever o problema, ajustar dados (solicitações de tratamento), conferir um
resultado suspeito (ADR-011) e ver a resposta. O texto fala com o usuário
final; os artefatos técnicos (R5) ficam numa seção recolhida. O andamento de
cada agente aparece ao vivo.
"""

import os
import shutil
import tempfile
import time
from collections.abc import Callable, Sequence
from importlib.resources import files
from pathlib import Path
from typing import Any

import gradio as gr
from pydantic import BaseModel

from po_multiagente.config import ConfiguracaoExecucao, carregar_perfil
from po_multiagente.interface import apresentacao
from po_multiagente.interface.assistente import Assistente, ErroAssistente, Etapa, Resultado
from po_multiagente.llm import AdaptadorOpenAI, ErroLLM

EXEMPLO = Path(str(files("po_multiagente.interface").joinpath("exemplos", "marcenaria")))
"""Piloto do TG1 (marcenaria), para o botão "carregar exemplo"."""

_APRESENTACAO = """\
# Otimização de decisões a partir das suas planilhas

Descubra quanto produzir, comprar, transportar ou misturar para ter o melhor
resultado, seja o maior lucro ou o menor custo, dentro dos limites do seu negócio.

### Como funciona

1. **Você descreve** o problema com suas palavras e envia as planilhas com os números.
2. **A plataforma trabalha:** interpreta o pedido, monta um modelo matemático, resolve,
   confere o resultado e escreve a resposta. Leva de 1 a 3 minutos, e o andamento
   aparece na tela.
3. **Você recebe a resposta** em linguagem de negócio. Se algum dado precisar de
   ajuste, a plataforma pede antes de seguir.
"""
_DICAS = """\
**Na descrição**, diga:

- o que você quer decidir (por exemplo, quanto produzir de cada produto);
- o que quer maximizar ou minimizar (por exemplo, a margem total);
- quais limites existem (por exemplo, a madeira e as horas de montagem do mês).

Não precisa escrever os números: eles vêm das planilhas.

**Nas planilhas** (CSV ou Excel), use uma tabela por arquivo ou aba, com uma linha
de cabeçalho. O nome de cada coluna deve dizer o que o número é e, se possível, a
unidade, como `Margem (R$/un)` ou `Horas de montagem no mês`.

Não sabe por onde começar? Clique em **Carregar exemplo**.
"""
_PRIVACIDADE = (
    "*Privacidade: o texto e as planilhas são enviados ao modelo de linguagem "
    "({modelo}). No nível gratuito, o provedor pode usá-los para melhorar os produtos; "
    "evite dados pessoais ou sigilosos.*"
)
_EXEMPLO_DESCRICAO = (
    "Ex.: Fabricamos mesas e cadeiras e queremos saber quanto produzir de cada uma para "
    "ter a maior margem, sem passar da madeira e das horas de montagem disponíveis no mês."
)
_MOTIVOS = {
    "granularidade": (
        "está em outro período ou nível de detalhe (por exemplo, semanal em vez de mensal)"
    ),
    "unidade": "está em outra unidade de medida",
    "identificador": "usa códigos que precisam ser trocados pelos nomes",
    "juncao": "precisa ser combinado com outra tabela",
    "faltante": "não foi encontrado nas planilhas",
}
_LATEX: list[dict[str, str | bool]] = [{"left": "$$", "right": "$$", "display": True}]

Telas = tuple[Any, ...]
Progresso = Callable[..., Any]


def construir_app(criar_assistente: Callable[[], Assistente], modelo: str = "") -> gr.Blocks:
    """Monta a interface.

    Args:
        criar_assistente: Cria um assistente novo a cada execução.
        modelo: Nome do modelo, para o aviso de privacidade.
    """
    app = gr.Blocks(title="Otimização de decisões")
    with app:
        assistente = gr.State(None)
        gr.Markdown(_APRESENTACAO)

        with gr.Column():
            gr.Markdown("## 1. Descreva o problema")
            with gr.Accordion("Como escrever a descrição e preparar as planilhas", open=False):
                gr.Markdown(_DICAS)
            descricao = gr.Textbox(label="Descrição", lines=5, placeholder=_EXEMPLO_DESCRICAO)
            arquivos = gr.File(
                label="Planilhas com os dados (CSV ou Excel)",
                file_count="multiple",
                file_types=[".csv", ".xlsx"],
                type="filepath",
            )
            with gr.Row():
                exemplo = gr.Button("Carregar exemplo")
                executar = gr.Button("Resolver", variant="primary")
            andamento = gr.Markdown()

        with gr.Column(visible=False) as passo_tratar:
            gr.Markdown("## 2. Ajuste nos dados")
            solicitacoes = gr.Markdown()
            tratados = gr.File(
                label="Planilhas ajustadas, na ordem da lista",
                file_count="multiple",
                file_types=[".csv", ".xlsx"],
                type="filepath",
            )
            tratar = gr.Button("Enviar e continuar", variant="primary")

        with gr.Column(visible=False) as passo_confirmar:
            gr.Markdown("## 2. Confira o resultado")
            perguntas = gr.Markdown()
            faz_sentido = gr.Radio(
                ["Sim, faz sentido", "Não faz sentido"], value="Sim, faz sentido", label="Resposta"
            )
            observacao = gr.Textbox(
                label="Se não faz sentido, diga o que está faltando ou errado (opcional)", lines=2
            )
            confirmar = gr.Button("Responder e continuar", variant="primary")

        resposta = _secao_resposta()

        gr.Markdown(_PRIVACIDADE.format(modelo=modelo or "configurado"))

        telas = [
            assistente,
            andamento,
            passo_tratar,
            solicitacoes,
            passo_confirmar,
            perguntas,
            *resposta,
        ]

        def ao_executar(
            texto: str,
            enviados: list[str] | None,
            progresso: Progresso = gr.Progress(),  # noqa: B008 — o Gradio injeta o progresso assim
        ) -> Telas:
            novo = criar_assistente()
            return _rodar(novo, progresso, lambda: novo.comecar(texto, _caminhos(enviados)))

        def ao_tratar(
            atual: Assistente | None,
            enviados: list[str] | None,
            progresso: Progresso = gr.Progress(),  # noqa: B008
        ) -> Telas:
            atual = _exigir(atual)
            return _rodar(atual, progresso, lambda: atual.responder_em_ordem(_caminhos(enviados)))

        def ao_confirmar(
            atual: Assistente | None,
            resposta: str,
            nota: str,
            progresso: Progresso = gr.Progress(),  # noqa: B008
        ) -> Telas:
            atual = _exigir(atual)
            aceita = resposta.startswith("Sim")
            return _rodar(atual, progresso, lambda: atual.confirmar(aceita, nota))

        exemplo.click(carregar_exemplo, outputs=[descricao, arquivos])
        executar.click(ao_executar, inputs=[descricao, arquivos], outputs=telas)
        tratar.click(ao_tratar, inputs=[assistente, tratados], outputs=telas)
        confirmar.click(ao_confirmar, inputs=[assistente, faz_sentido, observacao], outputs=telas)
    return app


def _secao_resposta() -> list[Any]:
    """Resposta ao usuário e, recolhidos, os artefatos técnicos (R5), na ordem de ``_telas``."""
    with gr.Column(visible=False) as passo_resultado:
        gr.Markdown("## Resposta")
        destaque = gr.Markdown()
        explicacao = gr.Markdown()
        plano = gr.Markdown()
        selo = gr.Markdown()
        arquivo = gr.File(label="Baixar resultados (ZIP)", interactive=False)
        with gr.Accordion("Detalhes técnicos: decisões, modelo e conferências", open=False):
            with gr.Tab("Decisões"):
                decisoes = gr.Markdown()
            with gr.Tab("Modelo matemático"):
                modelo = gr.Markdown(latex_delimiters=_LATEX)
            with gr.Tab("Conferências"):
                conferencias = gr.Markdown()
            with gr.Tab("Entendimento do pedido"):
                entendimento = gr.Markdown()
            with gr.Tab("Execução"):
                consumo = gr.Markdown()
                with gr.Accordion("Dados brutos (JSON)", open=False):
                    bruto = gr.JSON(show_label=False)
    return [
        passo_resultado,
        destaque,
        explicacao,
        plano,
        selo,
        arquivo,
        decisoes,
        modelo,
        conferencias,
        entendimento,
        consumo,
        bruto,
    ]


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
    """Descrição e arquivos do piloto da marcenaria.

    Os arquivos saem como cópias numa pasta temporária: o Gradio só aceita
    devolver arquivos da pasta de trabalho ou da temporária, e o pacote
    instalado fica fora das duas (no Colab, em ``dist-packages``).
    """
    descricao = (EXEMPLO / "descricao.md").read_text(encoding="utf-8")
    pasta = Path(tempfile.mkdtemp(prefix="po-exemplo-"))
    copias = []
    for arquivo in sorted((EXEMPLO / "dados").iterdir()):
        copias.append(str(shutil.copy(arquivo, pasta / arquivo.name)))
    return descricao, copias


def formatar_solicitacoes(etapa: Etapa) -> str:
    """Lista numerada do que o usuário precisa tratar, só sobre os dados."""
    linhas = [
        "Para continuar, a plataforma precisa que você ajuste alguns dados. Corrija cada "
        "item e envie as planilhas ajustadas na **mesma ordem** da lista:",
        "",
    ]
    for numero, solicitacao in enumerate(etapa.solicitacoes, start=1):
        coluna = f", coluna `{solicitacao.coluna}`" if solicitacao.coluna else ""
        motivo = _MOTIVOS.get(solicitacao.motivo.value, solicitacao.motivo.value)
        linhas.append(
            f"{numero}. Planilha `{solicitacao.arquivo}`{coluna}: o dado {motivo}. "
            f"Como deve ficar: {solicitacao.forma_esperada}"
        )
    return "\n".join(linhas)


def formatar_explicacao(resultado: Resultado) -> str:
    """A explicação ao gestor ou, sem ela, o motivo de o fluxo ter parado."""
    if resultado.explicacao:
        return resultado.explicacao
    motivo = resultado.falha or f"status do solver: {resultado.status or 'sem resultado'}"
    return (
        "**Não foi possível chegar a uma resposta.** Confira se a descrição diz o que "
        "decidir, o que otimizar e quais limites existem, e se as planilhas trazem os "
        f"números com cabeçalho. Detalhe técnico: {motivo}"
    )


def formatar_andamento(etapa: Etapa, segundos: float) -> str:
    """Linha de estado depois de cada execução."""
    tempo = f"{segundos:.0f} s"
    if etapa.tipo == "solicitacoes":
        return f"⏸ Parte concluída em {tempo}. **Falta você ajustar alguns dados, logo abaixo.**"
    if etapa.tipo == "confirmacao":
        return f"⏸ Parte concluída em {tempo}. **Falta você conferir um ponto, logo abaixo.**"
    return f"✅ Concluído em {tempo}. A resposta está logo abaixo."


def _rodar(assistente: Assistente, progresso: Progresso, passo: Callable[[], Etapa]) -> Telas:
    """Executa um passo mostrando o andamento de cada agente e o tempo total."""
    inicio = time.perf_counter()
    assistente.ao_avancar = lambda texto: progresso(None, desc=texto)
    try:
        etapa = _proteger(passo)
    finally:
        assistente.ao_avancar = None
    return _telas(assistente, etapa, time.perf_counter() - inicio)


def _telas(assistente: Assistente, etapa: Etapa, segundos: float = 0.0) -> Telas:
    """Visibilidade e conteúdo de cada etapa, na ordem de ``telas``."""
    em_tratamento = etapa.tipo == "solicitacoes"
    em_confirmacao = etapa.tipo == "confirmacao"
    no_fim = etapa.tipo == "resultado"
    return (
        assistente,
        formatar_andamento(etapa, segundos),
        gr.update(visible=em_tratamento),
        formatar_solicitacoes(etapa) if em_tratamento else "",
        gr.update(visible=em_confirmacao),
        "\n\n".join(etapa.perguntas),
        gr.update(visible=no_fim),
        *(_resposta(assistente.resultado(), segundos) if no_fim else _SEM_RESPOSTA),
    )


_SEM_RESPOSTA: Telas = ("", "", "", "", None, "", "", "", "", "", None)


def _resposta(resultado: Resultado, segundos: float) -> Telas:
    """Conteúdo da seção de resposta, na ordem de ``_secao_resposta`` (sem a coluna)."""
    bruto = {
        "solucao": resultado.solucao,
        "especificacao": _json(resultado.especificacao),
        "modelo": _json(resultado.modelo),
        "conferencias": [p.model_dump(mode="json") for p in resultado.pareceres],
    }
    pasta = Path(tempfile.mkdtemp(prefix="po-resultado-"))
    return (
        apresentacao.destaque(resultado),
        formatar_explicacao(resultado),
        apresentacao.plano_recomendado(resultado),
        apresentacao.selo_conferencia(resultado),
        str(apresentacao.empacotar(resultado, pasta)),
        apresentacao.decisoes(resultado),
        apresentacao.modelo_legivel(resultado),
        apresentacao.conferencias(resultado.pareceres),
        apresentacao.entendimento(resultado.especificacao),
        apresentacao.consumo(resultado, segundos),
        bruto,
    )


def _json(objeto: BaseModel | None) -> dict[str, Any] | None:
    return objeto.model_dump(mode="json") if objeto is not None else None


def _proteger(passo: Callable[[], Etapa]) -> Etapa:
    """Mostra erros de uso e de comunicação como aviso na tela, sem derrubar a interface."""
    try:
        return passo()
    except (ErroAssistente, ErroLLM) as erro:
        raise gr.Error(str(erro)) from erro


def _exigir(assistente: Assistente | None) -> Assistente:
    if assistente is None:
        raise gr.Error("Comece pela etapa 1: descreva o problema e clique em Resolver.")
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
