from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from po_multiagente.dominio import (
    IdentificacaoSolver,
    ParecerValidador,
    RespostaSolicitacao,
    ResultadoSolver,
    Sinal,
    StatusSolucao,
    Verificacao,
)

CBC = IdentificacaoSolver(backend="pulp", motor="cbc", versao="2.10.3")


def test_resultado_otimo_valido() -> None:
    resultado = ResultadoSolver(
        status=StatusSolucao.OTIMO,
        solver=CBC,
        valor_objetivo=1250.0,
        valores={"x[soja]": 10.0},
        tempo_segundos=0.02,
    )
    assert ResultadoSolver.model_validate_json(resultado.model_dump_json()) == resultado


def test_otimo_sem_valor_objetivo_e_rejeitado() -> None:
    with pytest.raises(ValidationError, match="exige valor objetivo"):
        ResultadoSolver(status=StatusSolucao.OTIMO, solver=CBC, tempo_segundos=0.0)


@pytest.mark.parametrize(
    "status", [StatusSolucao.INVIAVEL, StatusSolucao.ILIMITADO, StatusSolucao.ERRO]
)
def test_status_sem_solucao_rejeita_valores(status: StatusSolucao) -> None:
    with pytest.raises(ValidationError, match="não admite solução"):
        ResultadoSolver(status=status, solver=CBC, valores={"x": 1.0}, tempo_segundos=0.0)


def test_limite_de_tempo_admite_solucao_incumbente() -> None:
    resultado = ResultadoSolver(
        status=StatusSolucao.LIMITE_TEMPO,
        solver=CBC,
        valor_objetivo=900.0,
        tempo_segundos=60.0,
    )
    assert resultado.valor_objetivo == 900.0


def test_tempo_negativo_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        ResultadoSolver(status=StatusSolucao.ERRO, solver=CBC, tempo_segundos=-1.0)


def test_parecer_aprovado_so_se_todas_as_verificacoes_passam() -> None:
    aprovada = Verificacao(sinal=Sinal.S1, aprovada=True, mensagem="Solução ótima")
    reprovada = Verificacao(
        sinal=Sinal.S4,
        aprovada=False,
        mensagem="Requisito sem restrição",
        elementos=("REQ3",),
    )
    assert ParecerValidador(iteracao=1, verificacoes=(aprovada,)).aprovado
    assert not ParecerValidador(iteracao=2, verificacoes=(aprovada, reprovada)).aprovado


def test_parecer_faz_ida_e_volta_em_json() -> None:
    parecer = ParecerValidador(
        iteracao=1,
        verificacoes=(Verificacao(sinal=Sinal.S2, aprovada=True, mensagem="Unidades fecham"),),
    )
    assert ParecerValidador.model_validate_json(parecer.model_dump_json()) == parecer


def test_resposta_exige_data_com_fuso() -> None:
    with pytest.raises(ValidationError):
        RespostaSolicitacao(
            solicitacao_id="s1",
            arquivo_tratado="t.csv",
            sha256="c" * 64,
            respondida_em=datetime(2026, 9, 25, 12, 0),
        )
    resposta = RespostaSolicitacao(
        solicitacao_id="s1",
        arquivo_tratado="t.csv",
        sha256="c" * 64,
        respondida_em=datetime(2026, 9, 25, 12, 0, tzinfo=UTC),
    )
    assert resposta.respondida_em.tzinfo is UTC
