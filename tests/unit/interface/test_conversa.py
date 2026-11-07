import gc
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import gradio as gr
import pytest

from po_multiagente.agentes import Organizador
from po_multiagente.avaliacao.instancia import carregar_instancia
from po_multiagente.dominio import MotivoTratamento, Solicitacao
from po_multiagente.experimento.roteiro import roteiro_do_gabarito
from po_multiagente.interface import Assistente
from po_multiagente.interface.chat import construir_chat, para_gradio, turno
from po_multiagente.interface.conversa import (
    CORRIGIR,
    NAO,
    NOVO,
    ORGANIZANDO,
    REFAZER,
    SEGUIR_SEM,
    SIM,
    USAR,
    Conversa,
    Mensagem,
    _associar,
)
from po_multiagente.llm import LLMPort, LLMRoteirizado
from tests.instancias import DESCRICAO, MODELO, QUADRO, criar_instancia

EXPLICACAO = {"texto": "A margem máxima é {{OBJ}}."}


@pytest.fixture(autouse=True)
def _coletar_lixo() -> Iterator[None]:
    yield
    gc.collect()


def dados(pasta: Path) -> list[Path]:
    return sorted((pasta / "dados").iterdir())


def conversa(llm: LLMPort, tmp_path: Path) -> Conversa:
    return Conversa(lambda: Assistente(llm, pasta_trabalho=tmp_path / "trabalho"), tmp_path / "c")


def roteiro(**extra: list[Any]) -> LLMRoteirizado:
    return LLMRoteirizado(
        {"interpretador": [QUADRO], "modelador": [MODELO], "explicador": [EXPLICACAO], **extra}
    )


def fase(c: Conversa) -> str:
    # Função, e não ``c.fase`` direto: o mypy estreitaria o tipo e não veria a mudança.
    return c.fase


def textos(mensagens: list[Mensagem]) -> str:
    return "\n".join(m.texto for m in mensagens)


def test_pedido_em_partes_e_resposta_com_detalhes_recolhidos(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst")
    c = conversa(roteiro(), tmp_path)
    assert "anexe as planilhas" in textos(c.responder(DESCRICAO))
    passos: list[str] = []
    resposta = c.responder("", dados(pasta), passos.append)
    assert fase(c) == "resultado"
    assert passos[0].startswith("Interpretador")
    assert "A margem máxima é 6.000." in resposta[0].texto
    assert "Plano recomendado" in resposta[0].texto
    titulos = [m.titulo for m in resposta if m.titulo]
    assert titulos == [
        "Decisões",
        "Limites e preços-sombra",
        "Modelo matemático",
        "Conferências",
        "Entendimento do pedido",
        "Execução",
    ]
    arquivo = next(m.arquivo for m in resposta if m.arquivo)
    assert arquivo is not None
    assert arquivo.is_file()


def test_planilhas_primeiro_e_descricao_depois(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst")
    c = conversa(roteiro(), tmp_path)
    resposta = c.responder("", dados(pasta))
    assert "`produtos.csv`" in textos(resposta)
    assert fase(c) == "pedido"
    c.responder(DESCRICAO)
    assert fase(c) == "resultado"


def test_solicitacao_pede_anexo_e_aceita_o_arquivo_ajustado(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst", semanal=True)
    c = conversa(roteiro_do_gabarito(carregar_instancia(pasta)), tmp_path)
    pedido = c.responder(DESCRICAO, dados(pasta))
    assert fase(c) == "solicitacoes"
    assert "Planilha `" in textos(pedido)
    assert "Anexe aqui a planilha ajustada." in textos(pedido)
    so_texto = c.responder("são 200 horas no mês")
    assert fase(c) == "solicitacoes"
    assert so_texto[0].opcoes == (SEGUIR_SEM,)
    final = c.responder("", [pasta / "dados_tratados" / "capacidade.csv"])
    assert fase(c) == "resultado"
    assert "6.000" in final[0].texto


def test_resultado_suspeito_pergunta_e_aceita_observacao(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst")
    zerado = json.loads(json.dumps(MODELO))
    zerado["restricoes"][0]["expressao"] = "sum(horas[p] * x[p] for p in P) <= cap - cap"
    llm = LLMRoteirizado(
        {
            "interpretador": [QUADRO, QUADRO],
            "modelador": [zerado, MODELO],
            "explicador": [EXPLICACAO],
        }
    )
    c = conversa(llm, tmp_path)
    pergunta = c.responder(DESCRICAO, dados(pasta))
    assert fase(c) == "confirmacao"
    assert pergunta[-1].opcoes == (SIM, NAO)
    assert "Não entendi" in textos(c.responder("talvez"))
    pede_obs = c.responder(NAO)
    assert fase(c) == "observacao"
    assert "O que está faltando" in textos(pede_obs)
    c.responder("falta usar as horas de marcenaria")
    assert fase(c) == "resultado"


def test_ajuste_depois_do_resultado_refaz_com_as_mesmas_planilhas(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst")
    c = conversa(
        roteiro(
            interpretador=[QUADRO, QUADRO],
            modelador=[MODELO, MODELO],
            explicador=[EXPLICACAO, EXPLICACAO],
        ),
        tmp_path,
    )
    c.responder(DESCRICAO, dados(pasta))
    proposta = c.responder("considere só mesas e cadeiras")
    assert fase(c) == "ajuste"
    assert proposta[0].opcoes == (REFAZER, NOVO)
    refeita = c.responder(REFAZER)
    assert fase(c) == "resultado"
    assert "6.000" in refeita[0].texto
    assert "Ajuste pedido pelo usuário: considere só mesas e cadeiras" in c._descricao


def test_problema_novo_depois_do_resultado(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst")
    c = conversa(roteiro(), tmp_path)
    c.responder(DESCRICAO, dados(pasta))
    c.responder("outra coisa")
    resposta = c.responder(NOVO)
    assert fase(c) == "pedido"
    assert "problema novo" in textos(resposta)


def test_ambiguidade_aparece_com_a_leitura_adotada(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst")
    quadro = {
        **QUADRO,
        "alertas": [
            {
                "trecho": "horas limitadas no mês",
                "leituras": ["horas totais da marcenaria", "horas por marceneiro"],
                "requisito_id": "REQ2",
            }
        ],
    }
    c = conversa(roteiro(interpretador=[quadro]), tmp_path)
    resposta = c.responder(DESCRICAO, dados(pasta))
    alerta = resposta[0].texto
    assert "«horas limitadas no mês»" in alerta
    assert "- horas por marceneiro" in alerta
    assert "Considerei: **Não passar das horas de marcenaria**" in alerta
    assert "6.000" in resposta[1].texto


def test_erro_do_modelo_vira_aviso_no_chat(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst")
    c = conversa(LLMRoteirizado({}), tmp_path)
    resposta = c.responder(DESCRICAO, dados(pasta))
    assert resposta[0].texto.startswith("⚠️")


def test_associa_anexos_pelo_nome_e_depois_pela_ordem(tmp_path: Path) -> None:
    def solicitacao(id_: str, arquivo: str) -> Solicitacao:
        return Solicitacao(
            id=id_,
            parametro_id="p",
            arquivo=arquivo,
            coluna=None,
            motivo=MotivoTratamento.UNIDADE,
            forma_esperada="em horas",
        )

    pendentes = [solicitacao("s1", "a.csv"), solicitacao("s2", "b.csv")]
    b, x = tmp_path / "b.csv", tmp_path / "x.csv"
    assert _associar(pendentes, [b, x]) == {"s2": b, "s1": x}


def test_turno_mostra_andamento_e_resposta_no_formato_do_chatbot(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst")
    c = conversa(roteiro(), tmp_path)
    saidas = list(turno(c, [], DESCRICAO, dados(pasta)))
    historico, _, caixa = saidas[-1]
    assert caixa["interactive"] is True
    assert historico[0] == {"role": "user", "content": {"path": str(dados(pasta)[0])}}
    assert historico[2] == {"role": "user", "content": DESCRICAO}
    andamento = historico[3]
    assert andamento["metadata"]["title"] == "Andamento"
    assert "Interpretador" in andamento["content"]
    assert any(m.get("metadata", {}).get("title") == "Modelo matemático" for m in historico)
    assert any(isinstance(m["content"], dict) and "path" in m["content"] for m in historico[4:])


def test_para_gradio_com_opcoes_e_arquivo(tmp_path: Path) -> None:
    arquivo = tmp_path / "r.zip"
    mensagem = Mensagem("Faz sentido?", opcoes=(SIM, NAO), arquivo=arquivo)
    assert para_gradio(mensagem) == [
        {
            "role": "assistant",
            "content": "Faz sentido?",
            "options": [{"value": SIM}, {"value": NAO}],
        },
        {"role": "assistant", "content": {"path": str(arquivo)}},
    ]


@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_chat_monta_sem_abrir_servidor() -> None:
    app = construir_chat(lambda: Assistente(LLMRoteirizado({})), modelo="gemini-3.5-flash-lite")
    assert isinstance(app, gr.Blocks)


# ------------------------------------------------- sem planilhas (ADR-015)

DESCRICAO_COM_NUMEROS = (
    "Fabricamos mesas, cadeiras e estantes. Margem por peça: mesa 120, cadeira 45 e estante "
    "150. Horas de marcenaria por peça: mesa 4, cadeira 1,5 e estante 5. A marcenaria tem "
    "200 horas no mês. Quero o plano de produção com a maior margem."
)
TABELAS = {
    "tabelas": [
        {
            "arquivo": "produtos.csv",
            "descricao": "Margem e horas de cada peça",
            "colunas": ["Produto", "Margem por peça", "Horas de marcenaria"],
            "linhas": [["Mesa", "120", "4"], ["Cadeira", "45", "1,5"], ["Estante", "150", "5"]],
        },
        {
            "arquivo": "capacidade.csv",
            "descricao": "Horas disponíveis",
            "colunas": ["Horas no mês"],
            "linhas": [["200"]],
        },
    ],
    "faltantes": [],
}


def conversa_sem_planilha(llm: LLMRoteirizado, tmp_path: Path) -> Conversa:
    return Conversa(
        lambda: Assistente(llm, pasta_trabalho=tmp_path / "trabalho"),
        tmp_path / "c",
        organizador=Organizador(llm),
    )


def test_sem_planilha_monta_tabelas_para_conferir_e_resolve(tmp_path: Path) -> None:
    llm = roteiro(organizador=[TABELAS])
    c = conversa_sem_planilha(llm, tmp_path)
    passos: list[str] = []
    proposta = c.responder(DESCRICAO_COM_NUMEROS, ao_progresso=passos.append)
    assert fase(c) == "dados"
    assert passos == [ORGANIZANDO]
    assert proposta[0].opcoes == (USAR, CORRIGIR)
    assert "| Cadeira | 45 | 1,5 |" in proposta[0].texto
    csvs = [m.arquivo for m in proposta if m.arquivo]
    assert [p.name for p in csvs if p] == ["produtos.csv", "capacidade.csv"]
    resposta = c.responder(USAR)
    assert fase(c) == "resultado"
    assert "tabelas que montei" in resposta[0].texto
    assert "6.000" in resposta[1].texto


def test_sem_numeros_pede_os_dados(tmp_path: Path) -> None:
    faltantes = {"tabelas": [], "faltantes": ["a margem de cada peça"]}
    c = conversa_sem_planilha(roteiro(organizador=[faltantes]), tmp_path)
    resposta = c.responder("Quero saber quanto produzir de mesas e cadeiras.")
    assert fase(c) == "pedido"
    assert "- a margem de cada peça" in resposta[0].texto


def test_correcao_refaz_as_tabelas(tmp_path: Path) -> None:
    errada = json.loads(json.dumps(TABELAS))
    errada["tabelas"][1]["linhas"] = [["150"]]
    c = conversa_sem_planilha(roteiro(organizador=[errada, TABELAS]), tmp_path)
    assert "| 150 |" in c.responder(DESCRICAO_COM_NUMEROS)[0].texto
    assert "Escreva o que corrigir" in textos(c.responder(CORRIGIR))
    corrigida = c.responder("A capacidade é de 200 horas, e não 150.")
    assert fase(c) == "dados"
    assert "| 200 |" in corrigida[0].texto
    assert "A capacidade é de 200 horas" in c._descricao


def test_planilha_anexada_depois_substitui_as_tabelas(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst")
    c = conversa_sem_planilha(roteiro(organizador=[TABELAS]), tmp_path)
    c.responder(DESCRICAO_COM_NUMEROS)
    c.responder("", dados(pasta))
    assert fase(c) == "resultado"


def test_texto_anexado_vira_descricao_e_formato_desconhecido_avisa(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst")
    descricao = tmp_path / "pedido.txt"
    descricao.write_text(DESCRICAO, encoding="utf-8")
    pdf = tmp_path / "manual.pdf"
    pdf.write_bytes(b"%PDF")
    c = conversa(roteiro(), tmp_path)
    resposta = c.responder("", [descricao, pdf, *dados(pasta)])
    assert "Não consigo ler `manual.pdf`" in resposta[0].texto
    assert fase(c) == "resultado"


def test_texto_para_copiar_e_copia_na_pasta_visivel(tmp_path: Path) -> None:
    llm = roteiro(organizador=[TABELAS])
    c = Conversa(
        lambda: Assistente(llm, pasta_trabalho=tmp_path / "trabalho"),
        tmp_path / "c",
        organizador=Organizador(llm),
        copias=tmp_path / "content",
    )
    proposta = c.responder(DESCRICAO_COM_NUMEROS)
    bloco = next(m for m in proposta if m.titulo == "capacidade.csv: texto para copiar")
    assert bloco.texto == "```csv\nHoras no mês\n200\n```"
    assert "Também salvei uma cópia" in proposta[-1].texto
    assert sorted(p.name for p in (tmp_path / "content").rglob("*.csv")) == [
        "capacidade.csv",
        "produtos.csv",
    ]
    resposta = c.responder(USAR)
    baixar = next(m for m in resposta if m.arquivo)
    assert "Também salvei uma cópia" in baixar.texto
    assert list((tmp_path / "content").rglob("resultado.zip"))
