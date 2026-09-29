import pytest
from hypothesis import given
from hypothesis import strategies as st

from po_multiagente.dominio import ModeloIR
from po_multiagente.modelo import (
    ADIMENSIONAL,
    Unidade,
    compilar,
    ler_unidade,
    unidade_do_objetivo,
    verificar_unidades,
)
from tests.construtores import modelo, restricao, variavel


@pytest.mark.parametrize(
    ("notacao", "esperada"),
    [
        ("R$/un", "R$/un"),
        ("Reais / Unidade", "R$/un"),
        ("R$ / (t·km)", "R$/(km·t)"),
        ("R$/t·km", "R$/(km·t)"),
        ("R$/t*km", "R$/(km·t)"),
        ("t km", "km·t"),
        ("m²", "m^2"),
        ("m³/h", "m^3/h"),
        ("m^2·s^-1", "m^2/s"),
        ("1/h", "1/h"),
        ("(kg)/(un)", "kg/un"),
        ("adimensional", "adimensional"),
        ("", "adimensional"),
        ("%", "%"),
        ("un/mês", "un/mês"),
    ],
)
def test_notacao(notacao: str, esperada: str) -> None:
    assert str(ler_unidade(notacao)) == esperada


@pytest.mark.parametrize("notacao", ["(", "R$//un", "h^", "(kg", "kg)", "²", "*un"])
def test_notacao_invalida(notacao: str) -> None:
    with pytest.raises(ValueError, match="unidade"):
        ler_unidade(notacao)


def test_sinonimos_sao_a_mesma_unidade() -> None:
    assert ler_unidade("horas") == ler_unidade("h") == ler_unidade("HR")
    assert ler_unidade("R$/un") * ler_unidade("unidades") == ler_unidade("reais")


SIMBOLOS = st.sampled_from(["R$", "un", "h", "kg", "km"])
UNIDADES = st.dictionaries(SIMBOLOS, st.integers(-3, 3)).map(Unidade.de)


@given(UNIDADES, UNIDADES)
def test_quociente_desfaz_produto(a: Unidade, b: Unidade) -> None:
    assert (a * b) / b == a
    assert a / a == ADIMENSIONAL


@given(UNIDADES)
def test_texto_faz_ida_e_volta(unidade: Unidade) -> None:
    assert ler_unidade(str(unidade)) == unidade


UNIDADES_PILOTO = {"lucro": "R$/un", "horas": "h/un", "orcamento": "R$", "cap": "h"}


def piloto(expressao: str, objetivo: str = "sum(lucro[p] * x[p] for p in PRODUTOS)") -> ModeloIR:
    return modelo(
        objetivo,
        restricao("r", expressao),
        conjuntos=("PRODUTOS",),
        parametros={"lucro": ("PRODUTOS",), "horas": ("PRODUTOS",), "orcamento": (), "cap": ()},
        variaveis=(variavel("x", "PRODUTOS", unidade="un"),),
    )


@pytest.mark.parametrize(
    "expressao",
    [
        "sum(horas[p] * x[p] for p in PRODUTOS) <= cap",
        "sum(horas[p] * x[p] for p in PRODUTOS) <= 200",
        "sum(x[p] for p in PRODUTOS) >= 10",
        "2 * sum(horas[p] * x[p] for p in PRODUTOS) <= 0.5 * cap + 1",
        "sum(lucro[p] / horas[p] * horas[p] * x[p] for p in PRODUTOS) >= orcamento / cap * cap",
        "-x['A'] <= 0",
    ],
)
def test_unidades_que_fecham(expressao: str) -> None:
    assert verificar_unidades(compilar(piloto(expressao)), UNIDADES_PILOTO) == ()


@pytest.mark.parametrize(
    ("expressao", "trecho"),
    [
        (
            "sum(horas[p] * x[p] for p in PRODUTOS) <= orcamento",
            "'sum(horas[p] * x[p] for p in PRODUTOS)' está em h e 'orcamento' está em R$",
        ),
        ("x['A'] + cap <= 1", "os termos de 'x[\"A\"] + cap'"),
        (
            "horas['A'] * x['A'] >= lucro['A'] * x['A']",
            'está em h e \'lucro["A"] * x["A"]\' está em R$',
        ),
    ],
)
def test_unidades_que_nao_fecham_sao_localizadas(expressao: str, trecho: str) -> None:
    (erro,) = verificar_unidades(compilar(piloto(expressao)), UNIDADES_PILOTO)
    assert erro.elemento == "r"
    assert trecho in erro.mensagem


def test_objetivo_tambem_e_checado() -> None:
    ir = piloto("x['A'] <= 1", objetivo="sum(lucro[p] * x[p] for p in PRODUTOS) - cap")
    (erro,) = verificar_unidades(compilar(ir), UNIDADES_PILOTO)
    assert erro.elemento == "objetivo"


def test_unidade_ilegivel_e_localizada_na_declaracao() -> None:
    erros = verificar_unidades(
        compilar(piloto("x['A'] <= 1")), {**UNIDADES_PILOTO, "lucro": "R$(/"}
    )
    assert [e.elemento for e in erros] == ["lucro"]


def test_parametro_sem_unidade_declarada_nao_e_checado() -> None:
    ir = piloto("sum(horas[p] * x[p] for p in PRODUTOS) <= orcamento")
    assert verificar_unidades(compilar(ir), {"lucro": "R$/un"}) == ()


def test_unidade_do_objetivo() -> None:
    compilado_ = compilar(piloto("x['A'] <= 1"))
    assert str(unidade_do_objetivo(compilado_, UNIDADES_PILOTO)) == "R$"
    assert unidade_do_objetivo(compilado_, {}) == ler_unidade("un")
