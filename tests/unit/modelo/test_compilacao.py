import pytest
from pydantic import ValidationError

from po_multiagente.dominio import ModeloIR, Restricao, TipoVariavel
from po_multiagente.modelo import ErroCompilacao, compilar
from tests.construtores import conjunto, modelo, restricao, variavel


def producao(objetivo: str, *restricoes: Restricao) -> ModeloIR:
    return modelo(
        objetivo,
        *restricoes,
        conjuntos=("PRODUTOS", "MESES"),
        parametros={"lucro": ("PRODUTOS",), "cap": ()},
        variaveis=(variavel("x", "PRODUTOS"), variavel("y", tipo=TipoVariavel.BINARIA)),
    )


def erros(ir: ModeloIR) -> list[str]:
    with pytest.raises(ErroCompilacao) as erro:
        compilar(ir)
    return [str(e) for e in erro.value.erros]


def test_modelo_valido_compila(modelo: ModeloIR) -> None:
    compilado = compilar(modelo)
    assert compilado.ir is modelo
    assert [r.restricao.id for r in compilado.restricoes] == ["capacidade"]


@pytest.mark.parametrize(
    ("expressao", "mensagem"),
    [
        (
            "sum(x[p] * x[p] for p in PRODUTOS) <= cap",
            "o produto 'x[p] * x[p]' multiplica variáveis de decisão",
        ),
        ("cap / y + x['A'] <= 1", "a divisão 'cap / y' tem variável de decisão no denominador"),
        ("x['A'] / 0 <= 1", "a divisão 'x[\"A\"] / 0' é por zero"),
        ("x[m] <= 1", "o índice 'm' não está ligado"),
        ("x['A'] + lucro <= cap", "lucro tem 1 índice(s) (PRODUTOS), mas foi usado com 0"),
        ("x['A'] <= PRODUTOS", "o conjunto 'PRODUTOS' não pode ser usado como valor"),
        ("x['A'] <= demanda", "'demanda' não está declarado"),
        ("sum(x[m] for m in MESES) <= 1", "o índice 'm' percorre MESES, mas a posição 1 de x"),
        (
            "sum(x[p] for p in PRODUTOS for m in MESES) <= 1",
            "o índice 'm' do somatório não é usado",
        ),
        ("sum(x[p] for p in LOJAS) <= 1", "o conjunto 'LOJAS' não está declarado"),
        ("sum(sum(x[p] for p in PRODUTOS) for p in PRODUTOS) <= 1", "o índice 'p' já está em uso"),
        ("sum(x[cap] for cap in PRODUTOS) <= 1", "o índice 'cap' coincide com um nome"),
        ("cap <= 3", "não contém variável de decisão"),
        ("x['A'] < 3", "desigualdade estrita"),
    ],
)
def test_erros_de_restricao_sao_localizados(expressao: str, mensagem: str) -> None:
    encontrados = erros(producao("y", restricao("r", expressao)))
    assert all(e.startswith("r: ") for e in encontrados)
    assert any(mensagem in e for e in encontrados)


def test_indice_do_para_todo_nao_usado() -> None:
    ir = producao("y", restricao("r", "y <= 1", ("p", "PRODUTOS")))
    assert erros(ir) == ["r: o índice 'p' do para_todo não é usado na expressão"]


def test_indice_do_para_todo_que_coincide_com_nome() -> None:
    ir = producao("y", restricao("r", "x[cap] <= 1", ("cap", "PRODUTOS")))
    assert "coincide com um nome" in erros(ir)[0]


def test_indice_usado_como_valor() -> None:
    ir = producao("y", restricao("r", "x[p] <= p", ("p", "PRODUTOS")))
    assert erros(ir) == ["r: o índice 'p' não pode ser usado como valor numérico"]


def test_objetivo_sem_variavel_e_com_sintaxe_invalida() -> None:
    assert erros(producao("cap")) == ["objetivo: a função objetivo não contém variável de decisão"]
    assert "Erro de sintaxe" in erros(producao("y +"))[0]


def test_todos_os_erros_sao_reunidos() -> None:
    ir = producao("y * y", restricao("a", "x[q] <= 1"), restricao("b", "cap <= 1"))
    assert [e.split(":")[0] for e in erros(ir)] == ["objetivo", "a", "b"]


def test_nome_reservado_e_rejeitado() -> None:
    ir = modelo(
        "sum(x[p] for p in PRODUTOS)",
        variaveis=(variavel("x", "PRODUTOS"), variavel("in")),
        conjuntos=("PRODUTOS",),
    )
    assert erros(ir)[0] == "in: 'in' é palavra reservada da linguagem; escolha outro nome"


def test_membro_fixo_nao_e_checado_na_compilacao() -> None:
    compilar(producao("x['Mesa']"))


def test_subconjunto_ocupa_posicao_do_pai() -> None:
    ir = modelo(
        "sum(x[p] for p in PRODUTOS)",
        restricao("so_alguns", "sum(x[e] for e in ESPECIAIS) <= 1"),
        conjuntos=(
            conjunto("PRODUTOS"),
            conjunto("ESPECIAIS").model_copy(update={"subconjunto_de": "PRODUTOS"}),
        ),
        variaveis=(variavel("x", "PRODUTOS"),),
    )
    compilar(ir)
    sem_declaracao = ir.model_copy(
        update={"conjuntos": (conjunto("PRODUTOS"), conjunto("ESPECIAIS"))}
    )
    assert "percorre ESPECIAIS, mas a posição 1 de x espera PRODUTOS" in erros(sem_declaracao)[0]


def test_subconjunto_ciclico_e_rejeitado() -> None:
    with pytest.raises(ValidationError, match="subconjunto de si mesmo"):
        modelo(
            "x",
            conjuntos=(
                conjunto("A").model_copy(update={"subconjunto_de": "B"}),
                conjunto("B").model_copy(update={"subconjunto_de": "A"}),
            ),
        )
