import json
from pathlib import Path
from typing import Any

import pytest

from po_multiagente.agentes import (
    ErroAgente,
    Explicador,
    GeradorExecutor,
    Interpretador,
    Modelador,
    Registro,
    Validador,
    descrever_fontes,
    formatar_numero,
)
from po_multiagente.avaliacao.instancia import carregar_instancia
from po_multiagente.dados import Fontes
from po_multiagente.llm import ErroSaidaForaDoEsquema, LLMRoteirizado, Pedido
from po_multiagente.modelo import compilar
from po_multiagente.solver import OpcoesSolver, obter_backend
from tests.instancias import MODELO, QUADRO, criar_instancia


@pytest.fixture
def instancia(tmp_path: Path) -> Any:
    return carregar_instancia(criar_instancia(tmp_path / "inst"))


def test_descricao_das_fontes_nao_mostra_numeros(instancia: Any) -> None:
    texto = descrever_fontes(instancia.fontes)
    assert "`Produto` (texto): `Mesa`, `Cadeira`, `Estante`" in texto
    assert "`Margem por peça` (inteiro)" in texto
    assert "120" not in texto


def test_interpretador_corrige_origem_invalida(instancia: Any) -> None:
    errado = json.loads(json.dumps(QUADRO))
    errado["parametros"][0]["origem"]["coluna"] = "Margem"
    llm = LLMRoteirizado({"interpretador": [errado, QUADRO]})
    registro = Registro()
    resultado = Interpretador(llm).especificar(instancia.descricao, instancia.fontes, registro)
    assert resultado.tentativas == 2
    assert resultado.pendentes == ()
    assert "não tem a(s) coluna(s) 'Margem'" in llm.pedidos["interpretador"][1].entrada
    assert len(registro.chamadas) == 2


def test_interpretador_cria_solicitacao_para_dado_ilegivel(tmp_path: Path) -> None:
    pasta = criar_instancia(tmp_path / "inst", semanal=True)
    instancia = carregar_instancia(pasta)
    fontes = Fontes(pasta / "dados")
    quadro = json.loads(json.dumps(QUADRO))
    quadro["parametros"][2]["origem"] = {
        "arquivo": "horas_semanais.csv", "coluna": "Horas", "chaves": [], "filtros": []
    }  # fmt: skip
    llm = LLMRoteirizado({"interpretador": [quadro]})
    resultado = Interpretador(llm).especificar(instancia.descricao, fontes, Registro())
    (pendente,) = resultado.pendentes
    assert pendente.id == "auto_cap"
    assert pendente.motivo.value == "granularidade"


def test_interpretador_esgota_tentativas(instancia: Any) -> None:
    llm = LLMRoteirizado({"interpretador": [{"decisao": "x"}] * 3})
    with pytest.raises(ErroAgente) as erro:
        Interpretador(llm).especificar(instancia.descricao, instancia.fontes, Registro())
    assert len(erro.value.mensagens) == 3


def test_modelador_corrige_erro_de_compilacao(instancia: Any) -> None:
    nao_linear = json.loads(json.dumps(MODELO))
    nao_linear["objetivo"]["expressao"] = "sum(x[p] * x[p] for p in P)"
    llm = LLMRoteirizado({"modelador": [nao_linear, MODELO]})
    resultado = Modelador(llm).formular(instancia.especificacao, instancia.fontes, Registro())
    assert resultado.tentativas_formato == 2
    assert "não linear" in llm.pedidos["modelador"][1].entrada


def test_modelador_trata_recusa_do_provedor_como_erro_de_formato(instancia: Any) -> None:
    def recusa(_: Pedido) -> dict[str, Any]:
        raise ErroSaidaForaDoEsquema("[] should be non-empty")

    llm = LLMRoteirizado({"modelador": [recusa, MODELO]})
    registro = Registro()
    resultado = Modelador(llm).formular(instancia.especificacao, instancia.fontes, registro)
    assert resultado.tentativas_formato == 2
    assert "should be non-empty" in llm.pedidos["modelador"][1].entrada
    assert "não segue o esquema" in (registro.chamadas[0].erro or "")


def executar(instancia: Any) -> Any:
    gerador = GeradorExecutor(obter_backend("pulp"), "cbc", OpcoesSolver())
    return gerador, gerador.executar(
        compilar(instancia.modelo), instancia.especificacao, instancia.fontes
    )


def test_explicador_recusa_algarismo_e_marcador_desconhecido(instancia: Any) -> None:
    _, execucao = executar(instancia)
    llm = LLMRoteirizado(
        {
            "explicador": [
                {"texto": "Lucro de 6000."},
                {"texto": "Faça {{VAR:x[Estante]}} estantes; margem {{OBJ}}."},
            ]
        }
    )
    explicacao = Explicador(llm).explicar(instancia.especificacao, execucao, None, Registro())
    assert explicacao.recusas == 1
    assert "algarismo fora de marcador" in llm.pedidos["explicador"][1].entrada
    llm = LLMRoteirizado(
        {"explicador": [{"texto": "Faça {{VAR:x[Estante]}} estantes; margem {{OBJ}}."}]}
    )
    explicacao = Explicador(llm).explicar(instancia.especificacao, execucao, None, Registro())
    assert explicacao.texto == "Faça 40 estantes; margem 6.000."
    assert [item.marcador for item in explicacao.ficha] == ["VAR:x[Estante]", "OBJ"]


def test_explicador_cai_no_texto_de_reserva(instancia: Any) -> None:
    _, execucao = executar(instancia)
    llm = LLMRoteirizado({"explicador": [{"texto": "Lucro 1."}, {"texto": "Lucro 2."}]})
    explicacao = Explicador(llm).explicar(instancia.especificacao, execucao, None, Registro())
    assert explicacao.deterministica
    assert explicacao.recusas == 2
    assert explicacao.texto.startswith("Margem total: 6.000.")


def test_validador_aprova_e_monta_retorno(instancia: Any) -> None:
    gerador, execucao = executar(instancia)
    parecer = Validador().validar(1, execucao, instancia.especificacao, gerador.resolver)
    assert parecer.aprovado
    assert Validador.retorno(parecer) == ""


@pytest.mark.parametrize(
    ("valor", "texto"),
    [
        (6000.0, "6.000"),
        (133.3333, "133,33"),
        (0.5, "0,5"),
        (1234567.891, "1.234.567,89"),
        (-2.0, "-2"),
    ],
)
def test_formatar_numero(valor: float, texto: str) -> None:
    assert formatar_numero(valor) == texto
