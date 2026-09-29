"""Núcleo determinístico de ponta a ponta, sem modelo de linguagem.

Instância sintética de alocação da produção (construção própria, só para
teste): fontes CSV em notação brasileira → inventário → quadro de
especificação → modelo → compilação → ligação → instanciação → CBC → S1–S5.
O quadro e o modelo, que na plataforma vêm do Interpretador e do Modelador,
são escritos à mão aqui. O ótimo, 6000, foi obtido por enumeração.
"""

import shutil
from pathlib import Path

import pytest

from po_multiagente.dados import Fontes, ligar
from po_multiagente.dominio import (
    Especificacao,
    ModeloIR,
    Origem,
    Parametro,
    Requisito,
    ResultadoSolver,
    Sentido,
    StatusSolucao,
    TipoVariavel,
)
from po_multiagente.modelo import ModeloInstanciado, compilar, instanciar, para_latex
from po_multiagente.solver import OpcoesSolver, obter_backend
from po_multiagente.validacao import (
    sinal_s1_status,
    sinal_s2_unidades,
    sinal_s3_parametros,
    sinal_s4_requisitos,
    sinal_s5_limites,
)
from tests.construtores import conjunto, modelo, restricao, variavel

FIXTURES = Path(__file__).parent.parent / "fixtures" / "producao"


@pytest.fixture
def fontes(tmp_path: Path) -> Fontes:
    shutil.copytree(FIXTURES, tmp_path, dirs_exist_ok=True)
    return Fontes(tmp_path)


def parametro(id_: str, unidade: str, arquivo: str, coluna: str, *chaves: str) -> Parametro:
    return Parametro(
        id=id_,
        descricao=coluna,
        unidade=unidade,
        origem=Origem(arquivo=arquivo, coluna=coluna, chaves=chaves),
    )


@pytest.fixture
def quadro(fontes: Fontes) -> Especificacao:
    return Especificacao(
        decisao="Quantas peças de cada produto fabricar no mês",
        criterio="Margem total",
        sentido=Sentido.MAXIMIZAR,
        requisitos=(
            Requisito(id="REQ1", texto="Obter a maior margem possível"),
            Requisito(id="REQ2", texto="Não passar das horas de marcenaria do mês"),
            Requisito(id="REQ3", texto="Não passar das horas de acabamento do mês"),
            Requisito(id="REQ4", texto="Não produzir além dos pedidos firmes"),
        ),
        parametros=(
            parametro("margem", "R$/un", "produtos.csv", "Margem por peça", "Produto"),
            parametro("h_marc", "h/un", "produtos.csv", "Horas de marcenaria", "Produto"),
            parametro("h_acab", "h/un", "produtos.csv", "Horas de acabamento", "Produto"),
            parametro("pedidos", "un", "produtos.csv", "Pedidos firmes", "Produto"),
            parametro("cap_marc", "h", "capacidade.csv", "Horas de marcenaria no mês"),
            parametro("cap_acab", "h", "capacidade.csv", "Horas de acabamento no mês"),
        ),
        fontes=fontes.inventario(),
    )


def formular(*restricoes_extras: str, pedidos: bool = True) -> ModeloIR:
    return modelo(
        "sum(margem[p] * x[p] for p in PRODUTOS)",
        restricao(
            "marcenaria",
            "sum(h_marc[p] * x[p] for p in PRODUTOS) <= cap_marc",
            requisitos=("REQ2",),
        ),
        restricao(
            "acabamento",
            "sum(h_acab[p] * x[p] for p in PRODUTOS) <= cap_acab",
            requisitos=("REQ3",),
        ),
        *(
            [
                restricao(
                    "teto_pedidos", "x[p] <= pedidos[p]", ("p", "PRODUTOS"), requisitos=("REQ4",)
                )
            ]
            if pedidos
            else []
        ),
        *(restricao(f"extra{n}", e) for n, e in enumerate(restricoes_extras)),
        conjuntos=(conjunto("PRODUTOS", "produtos.csv", "Produto"),),
        parametros={
            nome: ("PRODUTOS",) if nome in {"margem", "h_marc", "h_acab", "pedidos"} else ()
            for nome in ("margem", "h_marc", "h_acab", "pedidos", "cap_marc", "cap_acab")
        },
        variaveis=(variavel("x", "PRODUTOS", tipo=TipoVariavel.INTEIRA),),
        requisitos_objetivo=("REQ1",),
    )


def executar(ir: ModeloIR, quadro: Especificacao, fontes: Fontes) -> dict[str, bool]:
    compilado = compilar(ir)
    dados = ligar(ir, quadro, fontes)
    instancia = instanciar(compilado, dados.conjuntos, dados.parametros)
    backend = obter_backend("pulp")

    def resolver(m: ModeloInstanciado) -> ResultadoSolver:
        return backend.resolver(m, motor="cbc", opcoes=OpcoesSolver()).resultado

    resultado = resolver(instancia)
    verificacoes = [
        sinal_s1_status(resultado, instancia, resolver),
        sinal_s2_unidades(compilado, quadro),
        sinal_s3_parametros(ir, quadro),
        sinal_s4_requisitos(ir, quadro),
        sinal_s5_limites(instancia, resultado),
    ]
    return {v.sinal.value: v.aprovada for v in verificacoes}


TODOS_APROVADOS = {"S1": True, "S2": True, "S3": True, "S4": True, "S5": True}


def test_modelo_correto_resolve_e_passa_nos_cinco_sinais(
    quadro: Especificacao, fontes: Fontes
) -> None:
    ir = formular()
    compilado = compilar(ir)
    dados = ligar(ir, quadro, fontes)
    assert dados.conjuntos["PRODUTOS"] == ("Mesa", "Cadeira", "Estante")
    assert dados.parametros["h_marc"][("Cadeira",)] == 1.5
    instancia = instanciar(compilado, dados.conjuntos, dados.parametros)
    execucao = obter_backend("pulp").resolver(instancia, motor="cbc", opcoes=OpcoesSolver())
    assert execucao.resultado.status is StatusSolucao.OTIMO
    assert execucao.resultado.valor_objetivo == pytest.approx(6000.0)
    assert execucao.resultado.solver.versao.startswith("2.10.3")
    assert r"\text{(marcenaria)}" in para_latex(compilado)
    assert executar(ir, quadro, fontes) == TODOS_APROVADOS
    assert fontes.conferir_integridade(quadro.fontes) == ()


def test_restricao_incompativel_e_localizada_pelo_s1(quadro: Especificacao, fontes: Fontes) -> None:
    ir = formular("sum(x[p] for p in PRODUTOS) >= 1000")
    assert executar(ir, quadro, fontes) == {**TODOS_APROVADOS, "S1": False}


def test_unidade_trocada_e_localizada_pelo_s2(quadro: Especificacao, fontes: Fontes) -> None:
    ir = formular("sum(h_marc[p] * x[p] for p in PRODUTOS) <= cap_marc + pedidos['Mesa']")
    assert executar(ir, quadro, fontes)["S2"] is False


def test_requisito_esquecido_e_localizado_pelo_s4(quadro: Especificacao, fontes: Fontes) -> None:
    resultado = executar(formular(pedidos=False), quadro, fontes)
    assert resultado == {**TODOS_APROVADOS, "S4": False}
