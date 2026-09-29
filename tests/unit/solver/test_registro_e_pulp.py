from types import SimpleNamespace

import pulp
import pytest

from po_multiagente.dominio import StatusSolucao
from po_multiagente.solver import ErroSolver, backends_disponiveis, obter_backend, registro
from po_multiagente.solver.adaptador_pulp import BackendPulp, _status
from tests.construtores import WYNDOR


def test_pulp_esta_registrado() -> None:
    assert "pulp" in backends_disponiveis()
    assert isinstance(obter_backend("pulp"), BackendPulp)


def test_backend_desconhecido() -> None:
    with pytest.raises(ErroSolver, match="'gurobi' não registrado; disponíveis: pulp"):
        obter_backend("gurobi")


def test_backend_que_nao_cumpre_o_contrato(monkeypatch: pytest.MonkeyPatch) -> None:
    ponto = SimpleNamespace(name="falso", load=lambda: object)
    monkeypatch.setattr(registro, "entry_points", lambda **_: [ponto])
    with pytest.raises(ErroSolver, match="não cumpre o contrato"):
        obter_backend("falso")


@pytest.mark.parametrize(
    ("status", "solucao", "esperado"),
    [
        (pulp.LpStatusOptimal, pulp.LpSolutionOptimal, StatusSolucao.OTIMO),
        (pulp.LpStatusOptimal, pulp.LpSolutionIntegerFeasible, StatusSolucao.LIMITE_TEMPO),
        (pulp.LpStatusNotSolved, pulp.LpSolutionNoSolutionFound, StatusSolucao.LIMITE_TEMPO),
        (pulp.LpStatusInfeasible, pulp.LpSolutionNoSolutionFound, StatusSolucao.INVIAVEL),
        (pulp.LpStatusInfeasible, pulp.LpSolutionInfeasible, StatusSolucao.INVIAVEL),
        (pulp.LpStatusUnbounded, pulp.LpSolutionUnbounded, StatusSolucao.ILIMITADO),
        (pulp.LpStatusUndefined, pulp.LpSolutionInfeasible, StatusSolucao.ERRO),
    ],
)
def test_mapeamento_de_status(status: int, solucao: int, esperado: StatusSolucao) -> None:
    assert _status(SimpleNamespace(status=status, sol_status=solucao)) is esperado


def test_falha_do_solver_vira_status_erro(monkeypatch: pytest.MonkeyPatch) -> None:
    def falhar(*_: object, **__: object) -> None:
        raise pulp.PulpSolverError("binário quebrado")

    monkeypatch.setattr(pulp.LpProblem, "solve", falhar)
    execucao = BackendPulp().resolver(WYNDOR)
    assert execucao.resultado.status is StatusSolucao.ERRO
    assert "binário quebrado" in execucao.log
