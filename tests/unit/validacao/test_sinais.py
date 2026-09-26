import pytest

from po_multiagente.dominio import (
    Especificacao,
    IdentificacaoSolver,
    ModeloIR,
    Origem,
    Parametro,
    ParametroModelo,
    Requisito,
    ResultadoSolver,
    Sentido,
    Sinal,
    StatusSolucao,
    TipoVariavel,
)
from po_multiagente.modelo import ModeloInstanciado, Relacao, compilar
from po_multiagente.solver import OpcoesSolver, obter_backend
from po_multiagente.validacao import (
    Intervalo,
    intervalo_do_objetivo,
    limites_propagados,
    localizar_ilimitacao,
    localizar_inviabilidade,
    sinal_s1_status,
    sinal_s2_unidades,
    sinal_s3_parametros,
    sinal_s4_requisitos,
    sinal_s5_limites,
)
from tests.construtores import WYNDOR, modelo, neutro, res, restricao, var, variavel

LE, GE, EQ = Relacao.MENOR_OU_IGUAL, Relacao.MAIOR_OU_IGUAL, Relacao.IGUAL
CBC = IdentificacaoSolver(backend="pulp", motor="cbc", versao="2.10.3")


def resolver(m: ModeloInstanciado) -> ResultadoSolver:
    return obter_backend("pulp").resolver(m, motor="cbc", opcoes=OpcoesSolver()).resultado


def resultado(
    status: StatusSolucao, valor: float | None = None, **valores: float
) -> ResultadoSolver:
    return ResultadoSolver(
        status=status, solver=CBC, valor_objetivo=valor, valores=valores, tempo_segundos=0.0
    )


# --------------------------------------------------------------------- S1


@pytest.mark.parametrize(
    ("r", "aprovada", "trecho"),
    [
        (resultado(StatusSolucao.OTIMO, 1.0, x=1.0), True, "solução ótima"),
        (resultado(StatusSolucao.LIMITE_TEMPO, 1.0, x=1.0), True, "sem prova de otimalidade"),
        (resultado(StatusSolucao.LIMITE_TEMPO), False, "não encontrou solução"),
        (resultado(StatusSolucao.INVIAVEL), False, "O modelo é inviável."),
        (resultado(StatusSolucao.ILIMITADO), False, "sem limite."),
        (resultado(StatusSolucao.ERRO), False, "falhou"),
    ],
)
def test_s1_sem_diagnostico(r: ResultadoSolver, aprovada: bool, trecho: str) -> None:
    verificacao = sinal_s1_status(r)
    assert verificacao.sinal is Sinal.S1
    assert verificacao.aprovada is aprovada
    assert trecho in verificacao.mensagem


INVIAVEL = neutro(
    Sentido.MINIMIZAR,
    {"x": 1.0, "y": 1.0},
    [var("x"), var("y")],
    [
        res("demanda", {"x": 1.0, "y": 1.0}, GE, 10.0),
        res("folga", {"y": 1.0}, LE, 100.0),
        res("teto_x", {"x": 1.0}, LE, 3.0),
        res("teto_y", {"y": 1.0}, LE, 4.0),
    ],
)


def test_s1_localiza_familias_incompativeis() -> None:
    verificacao = sinal_s1_status(resolver(INVIAVEL), INVIAVEL, resolver)
    assert not verificacao.aprovada
    assert verificacao.elementos == ("demanda", "teto_x", "teto_y")
    assert "demanda, teto_x, teto_y não podem ser atendidas" in verificacao.mensagem


def test_s1_localiza_dominio_vazio() -> None:
    m = neutro(Sentido.MINIMIZAR, {"z": 1.0}, [var("z", TipoVariavel.INTEIRA, 2.5, 2.7)], [])
    verificacao = sinal_s1_status(resolver(m), m, resolver)
    assert verificacao.elementos == ("z",)
    assert "domínio das variáveis z é vazio" in verificacao.mensagem


def test_s1_localiza_variavel_sem_limite() -> None:
    m = neutro(
        Sentido.MAXIMIZAR,
        {"x": 1.0, "y": 1.0},
        [var("x", superior=5.0), var("y")],
        [res("r", {"x": 1.0, "y": -1.0}, LE, 1.0)],
    )
    verificacao = sinal_s1_status(resolver(m), m, resolver)
    assert verificacao.elementos == ("y",)
    assert "nenhuma restrição segura y" in verificacao.mensagem


def test_s1_ilimitado_por_variavel_livre_negativa() -> None:
    m = neutro(Sentido.MINIMIZAR, {"w": 1.0}, [var("w", inferior=None)], [])
    assert localizar_ilimitacao(m, resolver) == ("w",)


def test_diagnosticos_devolvem_vazio_quando_nao_se_aplicam() -> None:
    assert localizar_ilimitacao(INVIAVEL, resolver) == ()
    assert localizar_inviabilidade(WYNDOR, resolver) == ()


# --------------------------------------------------------------------- S2


def test_s2(especificacao: Especificacao, modelo: ModeloIR) -> None:
    assert sinal_s2_unidades(compilar(modelo), especificacao).aprovada
    orcamento = Parametro(
        id="orcamento", descricao="Verba", unidade="R$", origem=especificacao.parametros[0].origem
    )
    ir = modelo.model_copy(
        update={
            "parametros": (*modelo.parametros, ParametroModelo(id="orcamento")),
            "restricoes": (
                restricao("capacidade", "sum(horas[p] * x[p] for p in PRODUTOS) <= orcamento"),
            ),
        }
    )
    quadro = especificacao.model_copy(update={"parametros": (*especificacao.parametros, orcamento)})
    verificacao = sinal_s2_unidades(compilar(ir), quadro)
    assert not verificacao.aprovada
    assert verificacao.elementos == ("capacidade",)
    assert "está em h e 'orcamento' está em R$" in verificacao.mensagem


# --------------------------------------------------------------------- S3


def test_s3_aprova_o_piloto(especificacao: Especificacao, modelo: ModeloIR) -> None:
    assert sinal_s3_parametros(modelo, especificacao).aprovada


def test_s3_localiza_origens_faltantes_e_incoerentes(especificacao: Especificacao) -> None:
    ir = modelo(
        "sum(lucro[p] * x[p] for p in PRODUTOS) + sum(y[l] for l in LOJAS)",
        conjuntos=("PRODUTOS", "LOJAS"),
        parametros={"lucro": (), "horas": ("PRODUTOS",), "frete": ("PRODUTOS",)},
        variaveis=(variavel("x", "PRODUTOS"), variavel("y", "LOJAS")),
    )
    ir = ir.model_copy(
        update={
            "conjuntos": (
                ir.conjuntos[0].model_copy(
                    update={"origem": Origem(arquivo="produtos.csv", coluna="Produto")}
                ),
                ir.conjuntos[1],
            )
        }
    )
    quadro = especificacao.model_copy(
        update={
            "parametros": (
                especificacao.parametros[0],
                especificacao.parametros[1].model_copy(
                    update={
                        "origem": Origem(
                            arquivo="produtos.csv", coluna="Horas", chaves=("Produto",)
                        )
                    }
                ),
            )
        }
    )
    verificacao = sinal_s3_parametros(ir, quadro)
    assert not verificacao.aprovada
    assert verificacao.elementos == ("lucro", "horas", "frete", "LOJAS")
    assert (
        "lucro: tem 0 índice(s) no modelo, mas a origem declara 1 chave(s)" in verificacao.mensagem
    )
    assert "horas: a coluna 'Horas' não existe em 'produtos.csv'" in verificacao.mensagem
    assert "frete: é usado sem origem declarada" in verificacao.mensagem
    assert "LOJAS: aponta para 'dados.csv', que não está entre as fontes" in verificacao.mensagem


# --------------------------------------------------------------------- S4


def test_s4_aprova_o_piloto(especificacao: Especificacao, modelo: ModeloIR) -> None:
    assert sinal_s4_requisitos(modelo, especificacao).aprovada


def test_s4_localiza_requisito_descoberto_e_citacao_invalida(
    especificacao: Especificacao, modelo: ModeloIR
) -> None:
    quadro = especificacao.model_copy(
        update={
            "requisitos": (
                *especificacao.requisitos,
                Requisito(id="REQ3", texto="Atender todos os pedidos"),
            )
        }
    )
    ir = modelo.model_copy(
        update={
            "restricoes": (restricao("capacidade", "x['A'] <= 1", requisitos=("REQ1", "REQ9")),),
            "objetivo": modelo.objetivo.model_copy(update={"requisitos": ("REQ2", "REQ8")}),
        }
    )
    verificacao = sinal_s4_requisitos(ir, quadro)
    assert verificacao.elementos == ("REQ3", "objetivo", "capacidade")
    assert "REQ3: requisito sem restrição, domínio de variável nem objetivo" in verificacao.mensagem
    assert "capacidade: cita REQ9" in verificacao.mensagem


# --------------------------------------------------------------------- S5


def test_s5_aprova_solucao_do_wyndor() -> None:
    verificacao = sinal_s5_limites(WYNDOR, resolver(WYNDOR))
    assert verificacao.aprovada
    assert "faixa admitida pelos dados [0; 42]" in verificacao.mensagem


def test_s5_nao_se_aplica_sem_solucao() -> None:
    assert sinal_s5_limites(INVIAVEL, resolver(INVIAVEL)).aprovada


def test_s5_rejeita_solucao_que_viola_o_modelo() -> None:
    falsa = resultado(StatusSolucao.OTIMO, 51.0, x=5.0, y=7.0)
    verificacao = sinal_s5_limites(WYNDOR, falsa)
    assert not verificacao.aprovada
    assert verificacao.elementos == ("planta1", "planta2", "planta3", "objetivo")
    assert "planta1 violada (5 <= 4)" in verificacao.mensagem


def test_s5_rejeita_variavel_fora_do_dominio() -> None:
    m = neutro(Sentido.MAXIMIZAR, {"n": 1.0}, [var("n", TipoVariavel.INTEIRA, 0, 3)], [])
    verificacao = sinal_s5_limites(m, resultado(StatusSolucao.OTIMO, 2.5, n=2.5))
    assert verificacao.elementos == ("n",)
    verificacao = sinal_s5_limites(m, resultado(StatusSolucao.OTIMO, 4.0, n=4.0))
    assert verificacao.elementos == ("n",)


def test_s5_pergunta_ao_usuario_quando_custo_minimo_ignora_as_restricoes() -> None:
    # Falta a restrição de demanda: o custo mínimo é zero, sem produzir nada.
    m = neutro(
        Sentido.MINIMIZAR,
        {"x": 2.0, "y": 3.0},
        [var("x"), var("y")],
        [res("capacidade", {"x": 1.0, "y": 1.0}, LE, 10.0)],
    )
    verificacao = sinal_s5_limites(m, resolver(m), criterio="Custo total")
    assert verificacao.aprovada
    assert verificacao.elementos == ("objetivo",)
    assert verificacao.confirmacao == (
        "Com as exigências informadas, o melhor resultado para «Custo total» é 0, o mesmo que "
        "se obteria sem exigência nenhuma. Isso costuma indicar que falta alguma exigência, "
        "como uma quantidade mínima a atender. Esse resultado faz sentido para a sua operação?"
    )
    desligada = sinal_s5_limites(m, resolver(m), perguntar_cota_trivial=False)
    assert desligada.confirmacao is None


def test_s5_pergunta_ao_usuario_quando_lucro_maximo_e_nao_fazer_nada() -> None:
    # Sentido invertido na capacidade: nada pode ser produzido.
    m = neutro(
        Sentido.MAXIMIZAR,
        {"x": 5.0},
        [var("x")],
        [res("capacidade", {"x": -1.0}, GE, 0.0), res("tudo", {"x": 1.0}, LE, 0.0)],
    )
    verificacao = sinal_s5_limites(m, resolver(m))
    assert verificacao.aprovada
    assert verificacao.confirmacao is not None
    assert "para o objetivo é 0" in verificacao.confirmacao
    assert "entendida ao contrário" in verificacao.confirmacao


def test_s5_nao_pergunta_quando_as_restricoes_afetam_o_resultado() -> None:
    assert sinal_s5_limites(WYNDOR, resolver(WYNDOR)).confirmacao is None


def test_propagacao_de_limites() -> None:
    m = neutro(
        Sentido.MAXIMIZAR,
        {"a": 1.0, "b": 1.0, "c": 1.0, "d": 1.0},
        [var("a"), var("b"), var("c", TipoVariavel.INTEIRA), var("d", inferior=None)],
        [
            res("r1", {"a": 2.0, "b": 1.0}, LE, 10.0),
            res("r2", {"c": 3.0}, LE, 10.0),
            res("r3", {"d": 1.0, "a": 1.0}, EQ, 1.0),
        ],
    )
    limites = limites_propagados(m)
    assert limites["a"] == Intervalo(0.0, 5.0)
    assert limites["b"] == Intervalo(0.0, 10.0)
    assert limites["c"] == Intervalo(0.0, 3.0)
    assert limites["d"] == Intervalo(-4.0, 1.0)
    assert intervalo_do_objetivo(m, limites) == Intervalo(-4.0, 19.0)


def test_propagacao_com_duas_variaveis_livres_nao_limita_nenhuma() -> None:
    m = neutro(
        Sentido.MAXIMIZAR,
        {"u": 1.0},
        [var("u", inferior=None), var("v", inferior=None), var("w")],
        [res("r", {"u": 1.0, "v": 1.0, "w": 1.0}, LE, 5.0)],
    )
    limites = limites_propagados(m)
    assert limites["u"] == limites["v"] == Intervalo(float("-inf"), float("inf"))
    assert limites["w"] == Intervalo(0.0, float("inf"))


def test_dominio_vazio_so_para_limites_impossiveis() -> None:
    m = neutro(
        Sentido.MINIMIZAR,
        {"a": 1.0, "b": 1.0},
        [var("a", inferior=None, superior=1.0), var("b", TipoVariavel.INTEIRA, 2.0, 2.0)],
        [res("r", {"a": 1.0}, GE, 2.0)],
    )
    assert localizar_inviabilidade(m, resolver) == ("r",)


def test_s4_aceita_requisito_atendido_pelo_dominio(
    especificacao: Especificacao, modelo: ModeloIR
) -> None:
    quadro = especificacao.model_copy(
        update={
            "requisitos": (
                *especificacao.requisitos,
                Requisito(id="REQ3", texto="Não dá para entregar fração de móvel"),
            )
        }
    )
    inteira = modelo.variaveis[0].model_copy(
        update={"tipo": TipoVariavel.INTEIRA, "requisitos": ("REQ3",)}
    )
    assert sinal_s4_requisitos(modelo.model_copy(update={"variaveis": (inteira,)}), quadro).aprovada
    invalida = inteira.model_copy(update={"requisitos": ("REQ7",)})
    verificacao = sinal_s4_requisitos(modelo.model_copy(update={"variaveis": (invalida,)}), quadro)
    assert verificacao.elementos == ("REQ3", "x")
