"""Fluxo completo pelo grafo, com modelo roteirizado (sem rede)."""

import json
from pathlib import Path

import pytest

from po_multiagente.avaliacao.instancia import carregar_instancia
from po_multiagente.cli import main
from po_multiagente.config import ConfiguracaoExecucao
from po_multiagente.experimento.calibracao import calibrar, executar_instancia, pastas_da_particao
from po_multiagente.experimento.respondedor import RespondedorSimulado
from po_multiagente.experimento.roteiro import roteiro_do_gabarito
from po_multiagente.llm import LLMRoteirizado
from po_multiagente.orquestracao import Agentes, Interrupcao, Sessao, montar_grafo
from tests.instancias import MODELO, QUADRO, VALOR, criar_instancia

COM = ConfiguracaoExecucao()
SEM = COM.model_copy(update={"validador": False})


def test_sem_validador_o_no_nao_existe() -> None:
    llm = LLMRoteirizado({})
    com = montar_grafo(Agentes.criar(llm, COM), COM).get_graph().nodes
    sem = montar_grafo(Agentes.criar(llm, SEM), SEM).get_graph().nodes
    assert {"validar", "confirmar"} <= set(com)
    assert not {"validar", "confirmar"} & set(sem)


@pytest.mark.parametrize("configuracao", [COM, SEM])
def test_fluxo_com_solicitacao_de_tratamento(
    tmp_path: Path, configuracao: ConfiguracaoExecucao
) -> None:
    instancia = carregar_instancia(criar_instancia(tmp_path / "inst", semanal=True))
    medida, estado = executar_instancia(instancia, configuracao, roteiro_do_gabarito(instancia))
    assert medida.correta
    assert medida.valor_obtido == pytest.approx(VALOR)
    assert medida.solicitacoes_emitidas == 1
    assert medida.solicitacoes_nao_atendidas == 0
    assert estado["explicacao"].texto == "O melhor resultado para o critério é 6.000."
    assert [e["agente"] for e in estado["eventos"]][:3] == [
        "interpretador",
        "usuario",
        "interpretador",
    ]


def test_pergunta_do_s5_volta_ao_modelador(tmp_path: Path) -> None:
    # Um modelo que zera a produção coincide com a cota trivial: o S5 pergunta ao
    # usuário, que diz não fazer sentido; o Modelador corrige na volta.
    instancia = carregar_instancia(criar_instancia(tmp_path / "inst"))
    zerado = json.loads(json.dumps(MODELO))
    zerado["restricoes"][0]["expressao"] = "sum(horas[p] * x[p] for p in P) <= cap - cap"
    llm = LLMRoteirizado(
        {
            "interpretador": [QUADRO],
            "modelador": [zerado, MODELO],
            "explicador": [{"texto": "Margem de {{OBJ}}."}],
        }
    )
    sessao = Sessao(llm, COM)
    passo = sessao.iniciar(instancia.descricao, instancia.pasta / "dados")
    assert isinstance(passo, Interrupcao)
    assert passo.tipo == "confirmacao"
    assert (
        "o mesmo que se obteria deixando todas as decisões no mínimo"
        in passo.conteudo["perguntas"][0]
    )
    final = sessao.responder({"aceita": False})
    assert not isinstance(final, Interrupcao)
    assert final["resultado"].valor_objetivo == pytest.approx(VALOR)
    assert "não faz sentido" in llm.pedidos["modelador"][1].entrada


def test_pergunta_aceita_segue_para_a_explicacao(tmp_path: Path) -> None:
    instancia = carregar_instancia(criar_instancia(tmp_path / "inst"))
    zerado = json.loads(json.dumps(MODELO))
    zerado["restricoes"][0]["expressao"] = "sum(horas[p] * x[p] for p in P) <= cap - cap"
    llm = LLMRoteirizado(
        {
            "interpretador": [QUADRO],
            "modelador": [zerado],
            "explicador": [{"texto": "Nada a produzir."}],
        }
    )
    sessao = Sessao(llm, COM)
    sessao.iniciar(instancia.descricao, instancia.pasta / "dados")
    final = sessao.responder({"aceita": True})
    assert final["explicacao"].texto == "Nada a produzir."  # type: ignore[index]


def test_falha_do_modelador_encerra_sem_explicacao(tmp_path: Path) -> None:
    instancia = carregar_instancia(criar_instancia(tmp_path / "inst"))
    llm = LLMRoteirizado({"interpretador": [QUADRO], "modelador": [{"x": 1}] * 3})
    medida, estado = executar_instancia(instancia, COM, llm)
    assert not medida.ponta_a_ponta
    assert estado["falha"] is not None
    assert estado["falha"].startswith("modelador")


def test_respondedor_so_atende_o_esperado(tmp_path: Path) -> None:
    instancia = carregar_instancia(criar_instancia(tmp_path / "inst", semanal=True))
    respondedor = RespondedorSimulado(instancia, tmp_path / "tratados")
    certo = {"id": "a", "arquivo": "horas_semanais.csv", "coluna": "Horas"}
    so_arquivo = {"id": "b", "arquivo": "horas_semanais.csv", "coluna": "Semana"}
    errado = {"id": "c", "arquivo": "produtos.csv", "coluna": "Produto"}
    resposta = respondedor.responder_solicitacoes([certo, so_arquivo, errado])
    assert resposta["respondidas"] == {"a": "capacidade.csv", "b": "capacidade.csv"}
    assert respondedor.nao_atendidas == [errado]
    assert (tmp_path / "tratados" / "capacidade.csv").exists()
    assert respondedor.responder_confirmacao() == {"aceita": False}


def test_calibrar_intercala_configuracoes_e_grava_relatorios(tmp_path: Path) -> None:
    conjunto = tmp_path / "conjunto"
    criar_instancia(conjunto / "a")
    criar_instancia(conjunto / "b", semanal=True, particao="conferencia")
    assert [p.name for p in pastas_da_particao(conjunto, "ajuste")] == ["a"]
    medidas = calibrar(
        pastas_da_particao(conjunto, "todas"), tmp_path / "saida", "roteiro", [COM, SEM]
    )
    ordem = [(m.instancia, m.configuracao) for m in medidas]
    assert ordem == [(i, c) for i in "ab" for c in ("com_validador", "sem_validador")]
    assert all(m.correta for m in medidas)
    resumo = (tmp_path / "saida" / "resumo.md").read_text()
    assert "| com_validador | ajuste | 1 | 1/1 (100%) | 1/1 (100%) |" in resumo
    assert len(list((tmp_path / "saida" / "execucoes").glob("*.json"))) == 4
    manifesto = json.loads((tmp_path / "saida" / "manifesto.json").read_text())
    assert set(manifesto["instrucoes_sha256"]) == {"interpretador", "modelador", "explicador"}


def test_cli_calibrar(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    criar_instancia(tmp_path / "conjunto" / "a")
    codigo = main(
        ["calibrar", str(tmp_path / "conjunto"), "--modo", "roteiro", "--configuracao", "ambas",
         "--saida", str(tmp_path / "saida")]
    )  # fmt: skip
    assert codigo == 0
    assert "| sem_validador | ajuste | 1 |" in capsys.readouterr().out
