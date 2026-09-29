"""Suíte de conformidade obrigatória para todo backend de solver (ADR-006).

Roda contra cada backend registrado no grupo ``po_multiagente.solvers``. O
sinal S1 depende do mapeamento de status verificado aqui.
"""

import pytest

from po_multiagente.dominio import Sentido, StatusSolucao, TipoVariavel
from po_multiagente.modelo import Relacao
from po_multiagente.solver import (
    ErroSolver,
    OpcoesSolver,
    SolverBackend,
    backends_disponiveis,
    obter_backend,
)
from tests.construtores import WYNDOR, neutro, res, var

LE, GE, EQ = Relacao.MENOR_OU_IGUAL, Relacao.MAIOR_OU_IGUAL, Relacao.IGUAL
CONTINUA, INTEIRA, BINARIA = TipoVariavel.CONTINUA, TipoVariavel.INTEIRA, TipoVariavel.BINARIA


@pytest.fixture(params=backends_disponiveis())
def backend(request: pytest.FixtureRequest) -> SolverBackend:
    return obter_backend(request.param)


def test_pl_com_otimo_conhecido_e_duais(backend: SolverBackend) -> None:
    execucao = backend.resolver(WYNDOR, motor=backend.motores()[0], opcoes=OpcoesSolver())
    r = execucao.resultado
    assert r.status is StatusSolucao.OTIMO
    assert r.valor_objetivo == pytest.approx(36.0)
    assert r.valores == pytest.approx({"x": 2.0, "y": 6.0})
    assert r.duais == pytest.approx({"planta1": 0.0, "planta2": 1.5, "planta3": 1.0})
    assert r.solver.backend == backend.nome
    assert r.solver.versao
    assert execucao.log


def test_plim_difere_da_relaxacao(backend: SolverBackend) -> None:
    # Relaxação: 21 em (3; 1,5). Inteiro: 20 em (4; 0).
    m = neutro(
        Sentido.MAXIMIZAR,
        {"x": 5.0, "y": 4.0},
        [var("x", INTEIRA), var("y", INTEIRA)],
        [res("a", {"x": 6.0, "y": 4.0}, LE, 24.0), res("b", {"x": 1.0, "y": 2.0}, LE, 6.0)],
    )
    r = backend.resolver(m, motor=backend.motores()[0], opcoes=OpcoesSolver()).resultado
    assert r.status is StatusSolucao.OTIMO
    assert r.valor_objetivo == pytest.approx(20.0)
    assert r.valores == pytest.approx({"x": 4.0, "y": 0.0})
    assert r.duais is None


def test_binarias(backend: SolverBackend) -> None:
    # Mochila: pesos 3, 4, 5; valores 4, 5, 6; capacidade 7 → itens 1 e 2.
    m = neutro(
        Sentido.MAXIMIZAR,
        {"a": 4.0, "b": 5.0, "c": 6.0},
        [var("a", BINARIA, 0, 1), var("b", BINARIA, 0, 1), var("c", BINARIA, 0, 1)],
        [res("peso", {"a": 3.0, "b": 4.0, "c": 5.0}, LE, 7.0)],
    )
    r = backend.resolver(m, motor=backend.motores()[0], opcoes=OpcoesSolver()).resultado
    assert r.valor_objetivo == pytest.approx(9.0)
    assert r.valores == pytest.approx({"a": 1.0, "b": 1.0, "c": 0.0})


@pytest.mark.parametrize("tipo", [CONTINUA, INTEIRA])
def test_inviavel(backend: SolverBackend, tipo: TipoVariavel) -> None:
    m = neutro(
        Sentido.MINIMIZAR,
        {"z": 1.0},
        [var("z", tipo)],
        [res("minimo", {"z": 1.0}, GE, 2.5), res("maximo", {"z": 1.0}, LE, 2.4)],
    )
    r = backend.resolver(m, motor=backend.motores()[0], opcoes=OpcoesSolver()).resultado
    assert r.status is StatusSolucao.INVIAVEL
    assert r.valor_objetivo is None
    assert r.valores == {}


@pytest.mark.parametrize("tipo", [CONTINUA, INTEIRA])
def test_ilimitado(backend: SolverBackend, tipo: TipoVariavel) -> None:
    m = neutro(
        Sentido.MAXIMIZAR,
        {"z": 1.0, "w": 1.0},
        [var("z", tipo), var("w")],
        [res("r", {"z": 1.0, "w": -1.0}, LE, 1.0)],
    )
    r = backend.resolver(m, motor=backend.motores()[0], opcoes=OpcoesSolver()).resultado
    assert r.status is StatusSolucao.ILIMITADO
    assert r.valores == {}


def test_igualdade_variavel_livre_limite_negativo_e_constante(backend: SolverBackend) -> None:
    m = neutro(
        Sentido.MINIMIZAR,
        {"livre": 1.0, "neg": 2.0},
        [var("livre", inferior=None), var("neg", inferior=-5.0, superior=5.0)],
        [res("soma", {"livre": 1.0, "neg": 1.0}, EQ, -2.0)],
        constante=10.0,
    )
    r = backend.resolver(m, motor=backend.motores()[0], opcoes=OpcoesSolver()).resultado
    # livre = -2 - neg; objetivo = 10 - 2 + neg → mínimo com neg = -5, livre = 3.
    assert r.status is StatusSolucao.OTIMO
    assert r.valores == pytest.approx({"livre": 3.0, "neg": -5.0})
    assert r.valor_objetivo == pytest.approx(3.0)


@pytest.mark.parametrize(
    ("relacao", "status"), [(GE, StatusSolucao.INVIAVEL), (LE, StatusSolucao.OTIMO)]
)
def test_restricao_sem_termos(
    backend: SolverBackend, relacao: Relacao, status: StatusSolucao
) -> None:
    # 0 >= 1 é violada; 0 <= 1 é trivial.
    m = neutro(Sentido.MINIMIZAR, {"w": 1.0}, [var("w")], [res("vazia", {}, relacao, 1.0)])
    r = backend.resolver(m, motor=backend.motores()[0], opcoes=OpcoesSolver()).resultado
    assert r.status is status


def test_nomes_com_espaco_e_acento_sao_preservados(backend: SolverBackend) -> None:
    m = neutro(
        Sentido.MAXIMIZAR,
        {"x[Loja São Paulo]": 1.0, "x[Loja B,Março]": 2.0},
        [var("x[Loja São Paulo]", superior=1.0), var("x[Loja B,Março]", superior=1.0)],
        [res("teto[Loja São Paulo]", {"x[Loja São Paulo]": 1.0, "x[Loja B,Março]": 1.0}, LE, 5.0)],
    )
    r = backend.resolver(m, motor=backend.motores()[0], opcoes=OpcoesSolver()).resultado
    assert set(r.valores) == {"x[Loja São Paulo]", "x[Loja B,Março]"}
    assert set(r.duais or {}) == {"teto[Loja São Paulo]"}


def test_opcoes_sao_aceitas(backend: SolverBackend) -> None:
    opcoes = OpcoesSolver(limite_tempo_s=10.0, gap_relativo=0.0, threads=1)
    r = backend.resolver(WYNDOR, motor=backend.motores()[0], opcoes=opcoes).resultado
    assert r.status is StatusSolucao.OTIMO


def test_motor_desconhecido(backend: SolverBackend) -> None:
    with pytest.raises(ErroSolver, match="motor"):
        backend.resolver(WYNDOR, motor="inexistente", opcoes=OpcoesSolver())
