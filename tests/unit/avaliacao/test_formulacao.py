from collections.abc import Mapping, Sequence

from po_multiagente.avaliacao.formulacao import COMPONENTES, comparar_formulacoes
from po_multiagente.dominio import ResultadoSolver, Sentido, TipoVariavel
from po_multiagente.modelo import (
    ModeloInstanciado,
    ObjetivoInstanciado,
    Relacao,
    RestricaoInstanciada,
    VariavelInstanciada,
)
from po_multiagente.solver import OpcoesSolver, obter_backend

LE, GE, EQ = Relacao.MENOR_OU_IGUAL, Relacao.MAIOR_OU_IGUAL, Relacao.IGUAL
CONTINUA, INTEIRA = TipoVariavel.CONTINUA, TipoVariavel.INTEIRA


def resolver(m: ModeloInstanciado) -> ResultadoSolver:
    return obter_backend("pulp").resolver(m, motor="cbc", opcoes=OpcoesSolver()).resultado


def v(
    familia: str,
    *indices: str,
    tipo: TipoVariavel = CONTINUA,
    inferior: float | None = 0.0,
    superior: float | None = None,
) -> VariavelInstanciada:
    nome = f"{familia}[{','.join(indices)}]" if indices else familia
    return VariavelInstanciada(nome, familia, indices, tipo, inferior, superior)


def r(
    nome: str, termos: Mapping[str, float], relacao: Relacao, lado: float
) -> RestricaoInstanciada:
    return RestricaoInstanciada(nome, nome, (), tuple(termos.items()), relacao, lado)


def modelo(
    sentido: Sentido,
    objetivo: Mapping[str, float],
    variaveis: Sequence[VariavelInstanciada],
    restricoes: Sequence[RestricaoInstanciada],
) -> ModeloInstanciado:
    return ModeloInstanciado(
        tuple(variaveis),
        tuple(restricoes),
        ObjetivoInstanciado(sentido, tuple(objetivo.items()), 0.0),
    )


# Transporte 2 × 2: x[origem, destino].
REFERENCIA = modelo(
    Sentido.MINIMIZAR,
    {"x[A,P]": 4.0, "x[A,Q]": 6.0, "x[B,P]": 5.0, "x[B,Q]": 3.0},
    [v("x", "A", "P"), v("x", "A", "Q"), v("x", "B", "P"), v("x", "B", "Q")],
    [
        r("oferta[A]", {"x[A,P]": 1.0, "x[A,Q]": 1.0}, LE, 30.0),
        r("oferta[B]", {"x[B,P]": 1.0, "x[B,Q]": 1.0}, LE, 40.0),
        r("demanda[P]", {"x[A,P]": 1.0, "x[B,P]": 1.0}, GE, 25.0),
        r("demanda[Q]", {"x[A,Q]": 1.0, "x[B,Q]": 1.0}, GE, 35.0),
    ],
)


def test_mesma_formulacao_com_outros_nomes_ordem_de_indices_e_escala() -> None:
    # envio[destino, origem]; ofertas escritas como ">= -oferta" e com escala 2.
    produzido = modelo(
        Sentido.MAXIMIZAR,
        {"envio[P,A]": -4.0, "envio[Q,A]": -6.0, "envio[P,B]": -5.0, "envio[Q,B]": -3.0},
        [v("envio", "P", "A"), v("envio", "Q", "A"), v("envio", "P", "B"), v("envio", "Q", "B")],
        [
            r("cap[A]", {"envio[P,A]": -2.0, "envio[Q,A]": -2.0}, GE, -60.0),
            r("cap[B]", {"envio[P,B]": 1.0, "envio[Q,B]": 1.0}, LE, 40.0),
            r("dem[Q]", {"envio[Q,A]": 1.0, "envio[Q,B]": 1.0}, GE, 35.0),
            r("dem[P]", {"envio[P,A]": 1.0, "envio[P,B]": 1.0}, GE, 25.0),
        ],
    )
    comparacao = comparar_formulacoes(produzido, REFERENCIA)
    assert comparacao.correta, comparacao.divergencias
    assert comparacao.familias == {"envio": "x"}
    assert set(comparacao.componentes) == set(COMPONENTES)


def test_restricao_faltante_reduz_a_revocacao() -> None:
    produzido = modelo(
        Sentido.MINIMIZAR,
        dict(REFERENCIA.objetivo.termos),
        REFERENCIA.variaveis,
        REFERENCIA.restricoes[:3],
    )
    comparacao = comparar_formulacoes(produzido, REFERENCIA, resolver)
    restricoes = comparacao.componentes["restricoes"]
    assert (restricoes.precisao, restricoes.revocacao) == (1.0, 0.75)
    assert not comparacao.correta
    assert "restrição de referência não produzida: demanda[Q]" in comparacao.divergencias


def test_coeficiente_errado_conta_no_componente_de_coeficientes() -> None:
    errada = r("oferta[A]", {"x[A,P]": 1.0, "x[A,Q]": 2.0}, LE, 30.0)
    produzido = modelo(
        Sentido.MINIMIZAR,
        dict(REFERENCIA.objetivo.termos),
        REFERENCIA.variaveis,
        [errada, *REFERENCIA.restricoes[1:]],
    )
    comparacao = comparar_formulacoes(produzido, REFERENCIA, resolver)
    assert comparacao.componentes["restricoes"].perfeito
    assert comparacao.componentes["coeficientes"].precisao == 0.75
    assert not comparacao.correta


def test_objetivo_e_variavel_excedente() -> None:
    produzido = modelo(
        Sentido.MINIMIZAR,
        {**dict(REFERENCIA.objetivo.termos), "x[A,P]": 1.0, "folga": 1.0},
        [*REFERENCIA.variaveis, v("folga")],
        REFERENCIA.restricoes,
    )
    comparacao = comparar_formulacoes(produzido, REFERENCIA, resolver)
    assert comparacao.componentes["variaveis"].precisao == 0.8
    assert comparacao.componentes["variaveis"].revocacao == 1.0
    assert not comparacao.componentes["objetivo"].perfeito


def test_restricao_de_uma_variavel_equivale_a_limite_do_dominio() -> None:
    referencia = modelo(
        Sentido.MAXIMIZAR, {"a": 1.0, "b": 2.0}, [v("a", superior=4.0), v("b")],
        [r("total", {"a": 1.0, "b": 1.0}, LE, 10.0)],
    )  # fmt: skip
    produzido = modelo(
        Sentido.MAXIMIZAR, {"a": 1.0, "b": 2.0}, [v("a"), v("b")],
        [r("teto", {"a": 2.0}, LE, 8.0), r("total", {"a": 1.0, "b": 1.0}, LE, 10.0)],
    )  # fmt: skip
    assert comparar_formulacoes(produzido, referencia).correta


def test_limites_diferentes_mas_implicados_pelas_restricoes() -> None:
    # a + b = 10 com a <= 4 equivale a a + b = 10 com b >= 6.
    referencia = modelo(
        Sentido.MINIMIZAR, {"a": 1.0, "b": 3.0}, [v("a", superior=4.0), v("b")],
        [r("total", {"a": 1.0, "b": 1.0}, EQ, 10.0)],
    )  # fmt: skip
    produzido = modelo(
        Sentido.MINIMIZAR, {"a": 1.0, "b": 3.0}, [v("a"), v("b", inferior=6.0)],
        [r("total", {"a": -1.0, "b": -1.0}, EQ, -10.0)],
    )  # fmt: skip
    assert comparar_formulacoes(produzido, referencia, resolver).correta
    # Sem solver, a equivalência não é conferida.
    assert not comparar_formulacoes(produzido, referencia).correta


def test_restricao_agregada_equivalente_a_desagregadas() -> None:
    # a + b <= 10 e a + b >= 10 equivalem a a + b = 10.
    referencia = modelo(
        Sentido.MAXIMIZAR, {"a": 1.0, "b": 2.0}, [v("a"), v("b")],
        [r("total", {"a": 1.0, "b": 1.0}, EQ, 10.0)],
    )  # fmt: skip
    produzido = modelo(
        Sentido.MAXIMIZAR, {"a": 1.0, "b": 2.0}, [v("a"), v("b")],
        [r("teto", {"a": 1.0, "b": 1.0}, LE, 10.0), r("piso", {"a": 1.0, "b": 1.0}, GE, 10.0)],
    )  # fmt: skip
    comparacao = comparar_formulacoes(produzido, referencia, resolver)
    assert comparacao.correta, comparacao.divergencias
    assert comparacao.componentes["restricoes"].produzidos == 2


def test_inteira_no_lugar_de_continua_erra_o_dominio() -> None:
    produzido = modelo(
        Sentido.MINIMIZAR,
        dict(REFERENCIA.objetivo.termos),
        [v("x", *x.indices, tipo=INTEIRA) for x in REFERENCIA.variaveis],
        REFERENCIA.restricoes,
    )
    comparacao = comparar_formulacoes(produzido, REFERENCIA, resolver)
    assert comparacao.componentes["dominios"].precisao == 0.0
    assert not comparacao.correta


def test_empate_entre_familias_desfeito_pelas_linhas() -> None:
    # Produção p[i] e estoque e[i] sobre o mesmo domínio; o modelo troca os nomes.
    referencia = modelo(
        Sentido.MINIMIZAR, {"p[M]": 2.0, "e[M]": 1.0}, [v("p", "M"), v("e", "M")],
        [r("balanco[M]", {"p[M]": 1.0, "e[M]": -1.0}, EQ, 5.0)],
    )  # fmt: skip
    produzido = modelo(
        Sentido.MINIMIZAR, {"a[M]": 1.0, "b[M]": 2.0}, [v("a", "M"), v("b", "M")],
        [r("saldo[M]", {"b[M]": 1.0, "a[M]": -1.0}, EQ, 5.0)],
    )  # fmt: skip
    comparacao = comparar_formulacoes(produzido, referencia)
    assert comparacao.familias == {"a": "e", "b": "p"}
    assert comparacao.correta


def test_modelo_inviavel_nao_implica_nada() -> None:
    referencia = modelo(
        Sentido.MINIMIZAR, {"a": 1.0}, [v("a"), v("b")],
        [r("x", {"a": 1.0, "b": 1.0}, LE, 1.0), r("y", {"a": 1.0, "b": 1.0}, GE, 2.0)],
    )  # fmt: skip
    produzido = modelo(
        Sentido.MINIMIZAR, {"a": 1.0}, [v("a"), v("b")],
        [r("x", {"a": 1.0, "b": 1.0}, LE, 1.0), r("z", {"a": 1.0, "b": 3.0}, GE, 7.0)],
    )  # fmt: skip
    assert not comparar_formulacoes(produzido, referencia, resolver).correta
