import json
from pathlib import Path

import pytest

from po_multiagente.avaliacao.instancia import carregar_instancia
from po_multiagente.experimento.roteiro import roteiro_do_gabarito
from po_multiagente.interface import Assistente, ErroAssistente
from po_multiagente.llm import LLMRoteirizado
from tests.instancias import DESCRICAO, MODELO, QUADRO, VALOR, criar_instancia


def dados(pasta: Path) -> list[Path]:
    return sorted((pasta / "dados").iterdir())


def test_fluxo_direto_chega_ao_resultado(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst")
    llm = LLMRoteirizado(
        {
            "interpretador": [QUADRO],
            "modelador": [MODELO],
            "explicador": [{"texto": "A margem máxima é {{OBJ}}."}],
        }
    )
    assistente = Assistente(llm, pasta_trabalho=tmp_path / "trabalho")
    etapa = assistente.comecar(DESCRICAO, dados(pasta))
    assert etapa.tipo == "resultado"
    resultado = assistente.resultado()
    assert resultado.status == "otimo"
    assert resultado.valor_objetivo == pytest.approx(VALOR)
    assert resultado.explicacao == "A margem máxima é 6.000."
    assert resultado.formulacao_latex is not None
    assert resultado.formulacao_latex.startswith("\\begin{aligned}")
    assert resultado.especificacao is not None
    assert resultado.chamadas_llm == 3
    assert (tmp_path / "trabalho" / "dados" / "produtos.csv").exists()


def test_solicitacao_respondida_com_arquivo_tratado(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst", semanal=True)
    assistente = Assistente(roteiro_do_gabarito(carregar_instancia(pasta)), pasta_trabalho=tmp_path)
    etapa = assistente.comecar(DESCRICAO, dados(pasta))
    assert etapa.tipo == "solicitacoes"
    assert [s.id for s in etapa.solicitacoes] == ["s_cap"]
    final = assistente.responder_em_ordem([pasta / "dados_tratados" / "capacidade.csv"])
    assert final.tipo == "resultado"
    assert assistente.resultado().valor_objetivo == pytest.approx(VALOR)


def test_resultado_suspeito_volta_ao_modelador_se_nao_faz_sentido(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst")
    zerado = json.loads(json.dumps(MODELO))
    zerado["restricoes"][0]["expressao"] = "sum(horas[p] * x[p] for p in P) <= cap - cap"
    llm = LLMRoteirizado(
        {
            "interpretador": [QUADRO],
            "modelador": [zerado, MODELO],
            "explicador": [{"texto": "Margem de {{OBJ}}."}],
        }
    )
    assistente = Assistente(llm, pasta_trabalho=tmp_path / "trabalho")
    etapa = assistente.comecar(DESCRICAO, dados(pasta))
    assert etapa.tipo == "confirmacao"
    assert etapa.perguntas
    assert assistente.confirmar(aceita=False).tipo == "resultado"
    assert assistente.resultado().valor_objetivo == pytest.approx(VALOR)


def test_erros_de_uso(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst", semanal=True)
    assistente = Assistente(roteiro_do_gabarito(carregar_instancia(pasta)), pasta_trabalho=tmp_path)
    with pytest.raises(ErroAssistente, match="ainda não começou"):
        assistente.resultado()
    with pytest.raises(ErroAssistente, match="nenhuma"):
        assistente.confirmar(aceita=True)
    with pytest.raises(ErroAssistente, match="Descreva"):
        assistente.comecar("  ", dados(pasta))
    with pytest.raises(ErroAssistente, match="arquivo"):
        assistente.comecar(DESCRICAO, [])
    assistente.comecar(DESCRICAO, dados(pasta))
    tratado = pasta / "dados_tratados" / "capacidade.csv"
    with pytest.raises(ErroAssistente, match="2 arquivo"):
        assistente.responder_em_ordem([tratado, tratado])
    with pytest.raises(ErroAssistente, match="desconhecidas: s_x"):
        assistente.tratar({"s_x": tratado})
