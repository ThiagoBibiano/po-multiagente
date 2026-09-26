import pytest

from po_multiagente.dominio import ModeloIR, Sentido, TipoVariavel
from po_multiagente.modelo import ErroInstanciacao, Relacao, compilar, instanciar
from tests.construtores import instanciado, modelo, restricao, variavel

MEMBROS = {"PRODUTOS": ("Mesa", "Cadeira")}
VALORES: dict[str, dict[tuple[str, ...], float]] = {
    "lucro": {("Mesa",): 10.0, ("Cadeira",): 15.0},
    "horas": {("Mesa",): 2.0, ("Cadeira",): 3.0},
}


def test_modelo_do_piloto_e_expandido(modelo: ModeloIR) -> None:
    instancia = instanciar(compilar(modelo), MEMBROS, VALORES)
    assert [v.nome for v in instancia.variaveis] == ["x[Mesa]", "x[Cadeira]"]
    (capacidade,) = instancia.restricoes
    assert capacidade.termos == (("x[Mesa]", 2.0), ("x[Cadeira]", 3.0))
    assert capacidade.relacao is Relacao.MENOR_OU_IGUAL
    assert capacidade.lado_direito == 200.0
    assert instancia.objetivo.termos == (("x[Mesa]", 10.0), ("x[Cadeira]", 15.0))
    assert instancia.objetivo.sentido is Sentido.MAXIMIZAR
    assert not instancia.inteiro


def test_para_todo_gera_uma_restricao_por_membro() -> None:
    ir = modelo(
        "sum(x[p] for p in PRODUTOS)",
        restricao("teto", "x[p] <= 2 * horas[p]", ("p", "PRODUTOS")),
        conjuntos=("PRODUTOS",),
        parametros={"horas": ("PRODUTOS",)},
        variaveis=(variavel("x", "PRODUTOS"),),
    )
    teto = instanciado(ir, MEMBROS, VALORES).restricoes
    assert [(r.nome, r.indices, r.termos, r.lado_direito) for r in teto] == [
        ("teto[Mesa]", ("Mesa",), (("x[Mesa]", 1.0),), 4.0),
        ("teto[Cadeira]", ("Cadeira",), (("x[Cadeira]", 1.0),), 6.0),
    ]


def test_termos_sao_agrupados_e_constantes_vao_para_o_lado_direito() -> None:
    ir = modelo(
        "x - 5",
        restricao("r", "3 * x + 2 - (x - 1) / 2 >= x + 10"),
        sentido=Sentido.MINIMIZAR,
    )
    instancia = instanciado(ir)
    (r,) = instancia.restricoes
    # 3x - x/2 - x = 1,5x;  2 + 1/2 - 10 → lado direito 7,5
    assert r.termos == (("x", 1.5),)
    assert r.lado_direito == 7.5
    assert instancia.objetivo.constante == -5.0


def test_coeficiente_nulo_e_descartado() -> None:
    (r,) = instanciado(modelo("x", restricao("r", "x - x + 0 * x <= 1"))).restricoes
    assert r.termos == ()


def test_transporte_com_dois_indices() -> None:
    ir = modelo(
        "sum(c[i, j] * x[i, j] for i in O for j in D)",
        restricao("oferta", "sum(x[i, j] for j in D) <= s[i]", ("i", "O")),
        sentido=Sentido.MINIMIZAR,
        conjuntos=("O", "D"),
        parametros={"c": ("O", "D"), "s": ("O",)},
        variaveis=(variavel("x", "O", "D"),),
    )
    instancia = instanciado(
        ir,
        {"O": ("F1", "F2"), "D": ("C1",)},
        {
            "c": {("F1", "C1"): 4.0, ("F2", "C1"): 5.0},
            "s": {("F1",): 10.0, ("F2",): 20.0},
        },
    )
    assert [v.nome for v in instancia.variaveis] == ["x[F1,C1]", "x[F2,C1]"]
    assert [r.lado_direito for r in instancia.restricoes] == [10.0, 20.0]


def test_membro_fixo_e_binaria() -> None:
    ir = modelo(
        "sum(y[p] for p in PRODUTOS)",
        restricao("so_mesa", "y['Mesa'] <= 0"),
        conjuntos=("PRODUTOS",),
        variaveis=(variavel("y", "PRODUTOS", tipo=TipoVariavel.BINARIA, inferior=None),),
    )
    instancia = instanciado(ir, MEMBROS)
    assert instancia.inteiro
    assert {(v.limite_inferior, v.limite_superior) for v in instancia.variaveis} == {(0.0, 1.0)}
    assert instancia.restricoes[0].termos == (("y[Mesa]", 1.0),)


def test_sem_restricoes_remove_familias() -> None:
    ir = modelo("x", restricao("a", "x <= 1"), restricao("b", "x <= 2"))
    assert [r.nome for r in instanciado(ir).sem_restricoes({"a"}).restricoes] == ["b"]


def test_falhas_de_dados_sao_reunidas_e_localizadas() -> None:
    ir = modelo(
        "sum(lucro[p] * x[p] for p in PRODUTOS)",
        restricao("capacidade", "sum(horas[p] * x[p] for p in PRODUTOS) <= 10"),
        restricao("fixo", "x['Sofá'] <= 1"),
        restricao("div", "x['Mesa'] / zero <= 1"),
        conjuntos=("PRODUTOS",),
        parametros={"lucro": ("PRODUTOS",), "horas": ("PRODUTOS",), "zero": ()},
        variaveis=(variavel("x", "PRODUTOS"),),
    )
    with pytest.raises(ErroInstanciacao) as erro:
        instanciado(ir, MEMBROS, {"lucro": {("Mesa",): 1.0}, "zero": {(): 0.0}})
    assert [str(e) for e in erro.value.erros] == [
        "capacidade: o parâmetro 'horas' não tem valores ligados",
        "fixo: 'x[\"Sofá\"]': 'Sofá' não é membro de PRODUTOS",
        "div: 'x[\"Mesa\"] / zero' divide por zero com os dados informados",
        "objetivo: o parâmetro 'lucro' não tem valor para (PRODUTOS=Cadeira)",
    ]


def test_conjunto_sem_membros_ligados() -> None:
    ir = modelo("sum(x[p] for p in P)", conjuntos=("P",), variaveis=(variavel("x", "P"),))
    with pytest.raises(ErroInstanciacao, match="P: o conjunto não tem membros ligados"):
        instanciado(ir, {})


def test_membros_com_virgula_geram_nomes_ambiguos() -> None:
    ir = modelo(
        "sum(x[a, b] for a in A for b in B)",
        conjuntos=("A", "B"),
        variaveis=(variavel("x", "A", "B"),),
    )
    with pytest.raises(ErroInstanciacao, match="mesmo nome"):
        instanciado(ir, {"A": ("1", "1,2"), "B": ("2,3", "3")})
