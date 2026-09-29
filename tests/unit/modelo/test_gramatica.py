import pytest
from hypothesis import given
from hypothesis import strategies as st

from po_multiagente.modelo import ErroSintaxe, analisar_comparacao, analisar_expressao, texto
from po_multiagente.modelo.arvore import (
    Binaria,
    Comparacao,
    Expressao,
    Gerador,
    IndiceLivre,
    Membro,
    Negacao,
    Numero,
    Operador,
    Referencia,
    Relacao,
    Somatorio,
)


def test_somatorio_com_dois_geradores() -> None:
    arvore = analisar_expressao("sum(c[i, j] * x[i, j] for i in ORIGENS for j in DESTINOS)")
    assert arvore == Somatorio(
        Binaria(
            Operador.PRODUTO,
            Referencia("c", (IndiceLivre("i"), IndiceLivre("j"))),
            Referencia("x", (IndiceLivre("i"), IndiceLivre("j"))),
        ),
        (Gerador("i", "ORIGENS"), Gerador("j", "DESTINOS")),
    )


def test_precedencia_e_associatividade() -> None:
    assert analisar_expressao("a - b - c") == Binaria(
        Operador.SUBTRACAO,
        Binaria(Operador.SUBTRACAO, Referencia("a"), Referencia("b")),
        Referencia("c"),
    )
    assert analisar_expressao("a + b * c") == Binaria(
        Operador.SOMA, Referencia("a"), Binaria(Operador.PRODUTO, Referencia("b"), Referencia("c"))
    )


@pytest.mark.parametrize(("fonte", "membro"), [('x["Loja A"]', "Loja A"), ("x['P-01']", "P-01")])
def test_membro_entre_aspas(fonte: str, membro: str) -> None:
    assert analisar_expressao(fonte) == Referencia("x", (Membro(membro),))


@pytest.mark.parametrize(
    ("fonte", "valor"), [("200", 200.0), ("0.5", 0.5), (".5", 0.5), ("1e3", 1000.0), ("2.", 2.0)]
)
def test_numeros(fonte: str, valor: float) -> None:
    assert analisar_expressao(fonte) == Numero(valor)


def test_nome_que_comeca_com_palavra_reservada_e_nome() -> None:
    assert analisar_expressao("summary + index") == Binaria(
        Operador.SOMA, Referencia("summary"), Referencia("index")
    )


@pytest.mark.parametrize(("fonte", "relacao"), [("x <= 1", "<="), ("x>=1", ">="), ("x == 1", "==")])
def test_relacoes(fonte: str, relacao: str) -> None:
    assert analisar_comparacao(fonte).relacao is Relacao(relacao)


@pytest.mark.parametrize(
    ("fonte", "mensagem", "coluna"),
    [
        ("x < 3", "desigualdade estrita", 3),
        ("x > 3", "desigualdade estrita", 3),
        ("x = 3", "use ==", 3),
        ("x @ 3", "'@' não pertence", 3),
        ("x <=", "terminou antes do esperado", 5),
        ("sum(x[p] for p PRODUTOS) <= 1", "encontrado 'PRODUTOS'; esperado in", 16),
        ("x <= 1 <= 2", "encontrado '<='", 8),
        ("x + 1", "terminou antes do esperado; esperado .*<=, >= ou ==", 6),
    ],
)
def test_erros_de_sintaxe_sao_localizados(fonte: str, mensagem: str, coluna: int) -> None:
    with pytest.raises(ErroSintaxe, match=mensagem) as erro:
        analisar_comparacao(fonte)
    assert erro.value.coluna == coluna


def test_objetivo_nao_aceita_relacao() -> None:
    with pytest.raises(ErroSintaxe, match="encontrado '<='"):
        analisar_expressao("x <= 1")


NOMES = st.sampled_from(["x", "y", "custo", "lucro_unit", "cap"])
INDICES = st.one_of(
    st.sampled_from(["i", "j", "p"]).map(IndiceLivre),
    st.sampled_from(["Loja A", "P1", "007"]).map(Membro),
)
ATOMOS = st.one_of(
    st.floats(min_value=0, max_value=1e9, allow_nan=False).map(Numero),
    st.builds(Referencia, NOMES, st.lists(INDICES, max_size=2).map(tuple)),
)


def _compostos(filhos: st.SearchStrategy[Expressao]) -> st.SearchStrategy[Expressao]:
    return st.one_of(
        st.builds(Binaria, st.sampled_from(list(Operador)), filhos, filhos),
        st.builds(Negacao, filhos),
        st.builds(
            Somatorio,
            filhos,
            st.lists(
                st.builds(Gerador, st.sampled_from(["i", "j"]), st.sampled_from(["I", "J"])),
                min_size=1,
                max_size=2,
            ).map(tuple),
        ),
    )


EXPRESSOES = st.recursive(ATOMOS, _compostos, max_leaves=12)


@given(EXPRESSOES)
def test_texto_e_analise_fazem_ida_e_volta(expressao: Expressao) -> None:
    assert analisar_expressao(texto(expressao)) == expressao


@given(EXPRESSOES, st.sampled_from(list(Relacao)), EXPRESSOES)
def test_comparacao_faz_ida_e_volta(a: Expressao, relacao: Relacao, b: Expressao) -> None:
    comparacao = Comparacao(a, relacao, b)
    assert analisar_comparacao(texto(comparacao)) == comparacao
