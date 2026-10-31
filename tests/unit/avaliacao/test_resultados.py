from typing import Any

import pytest

from po_multiagente.avaliacao.resultados import (
    COM,
    SEM,
    categoria_sugerida,
    criterio_4,
    decidir,
    encadeamento_validador,
    mcnemar_exato,
    pareadas,
    proporcoes,
    relatorio,
)


def medida(
    instancia: str,
    configuracao: str,
    repeticao: int = 1,
    *,
    certa: bool = True,
    formulacao_ok: bool | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "instancia": instancia,
        "configuracao": configuracao,
        "repeticao": repeticao,
        "ponta_a_ponta": True,
        "correta": certa,
        "formulacao_correta": certa if formulacao_ok is None else formulacao_ok,
        "formulacao": {"variaveis": [1.0, 1.0]},
        "associacao_precisao": 1.0,
        "associacao_revocacao": 1.0,
        "solicitacoes_nao_atendidas": 0,
        "validador_acionado": False,
        "iteracoes_validador": 1,
        "sinais_acionados": [],
        "status": "otimo",
        "faixa": "base",
        "origem": "propria",
        "familia": "mistura",
        "classe": "pl",
        **extra,
    }


@pytest.mark.parametrize(
    ("b", "c", "esperado"),
    [(0, 0, 1.0), (1, 1, 1.0), (0, 5, 0.0625), (5, 0, 0.0625), (2, 8, 0.109375)],
)
def test_mcnemar_exato(b: int, c: int, esperado: float) -> None:
    assert mcnemar_exato(b, c) == pytest.approx(esperado)


def test_maioria_entre_as_repeticoes() -> None:
    medidas = [
        medida("i1", COM, 1, certa=True),
        medida("i1", COM, 2, certa=False),
        medida("i1", COM, 3, certa=True),
        medida("i1", SEM, 1, certa=False),
        medida("i1", SEM, 2, certa=False),
        medida("i1", SEM, 3, certa=True),
    ]
    decisoes = decidir(medidas)
    assert decisoes["i1", COM].criterios == {"1": True, "2": True, "3": True}
    assert decisoes["i1", SEM].criterios["3"] is False
    assert decisoes["i1", SEM].execucoes == 3


def test_tabela_pareada_por_criterio() -> None:
    medidas = [
        medida("i1", COM, certa=True),
        medida("i1", SEM, certa=False),
        medida("i2", COM, certa=True),
        medida("i2", SEM, certa=True),
        medida("i3", COM, certa=False),
        medida("i3", SEM, certa=False),
        medida("i4", COM, certa=True),  # sem par: fica fora da tabela
    ]
    criterio_3 = pareadas(decidir(medidas))[2]
    assert (criterio_3.a, criterio_3.b, criterio_3.c, criterio_3.d) == (1, 1, 0, 1)
    assert criterio_3.p_valor == 1.0


def test_proporcoes_por_faixa() -> None:
    medidas = [
        medida("i1", COM, faixa="base"),
        medida("i2", COM, certa=False, faixa="ampliada"),
        medida("i3", COM, faixa="ampliada"),
    ]
    contagem = proporcoes(decidir(medidas), "faixa")
    assert contagem["ampliada", COM, "3"] == (1, 2)
    assert contagem["base", COM, "3"] == (1, 1)


def test_criterio_4_conta_so_execucoes_com_validador() -> None:
    medidas = [
        medida("i1", COM, validador_acionado=True, iteracoes_validador=3, sinais_acionados=["S2"]),
        medida("i2", COM),
        medida("i1", SEM, validador_acionado=True),
    ]
    c4 = criterio_4(medidas)
    assert (c4["execucoes"], c4["acionado"], c4["iteracoes_max"]) == (2, 1, 3)
    assert c4["sinais"] == {"S2": 1}


@pytest.mark.parametrize(
    ("extra", "categoria"),
    [
        ({"certa": True}, None),
        ({"certa": False, "solicitacoes_nao_atendidas": 1}, "Solicitação de tratamento"),
        (
            {"certa": False, "associacao_precisao": None},
            "Interpretação (sem quadro de especificação)",
        ),
        ({"certa": False, "associacao_revocacao": 0.5}, "Parametrização"),
        ({"certa": False, "formulacao": {}}, "Compilação do modelo"),
        ({"certa": False}, "Formulação"),
        ({"certa": False, "formulacao_correta": True, "status": "erro"}, "Execução"),
    ],
)
def test_categoria_sugerida_pela_primeira_etapa(
    extra: dict[str, Any], categoria: str | None
) -> None:
    certa = extra.pop("certa")
    assert categoria_sugerida(medida("i1", COM, certa=certa, **extra)) == categoria


def test_encadeamento_do_validador() -> None:
    sem_certa = medida("i1", SEM)
    aprovou_erro = medida("i1", COM, certa=False)
    corrigiu_indevido = medida("i1", COM, certa=False, validador_acionado=True)
    decisoes = decidir([sem_certa, aprovou_erro])
    assert encadeamento_validador(aprovou_erro, decisoes) == "erro aprovado"
    assert encadeamento_validador(corrigiu_indevido, decisoes) == "possível correção indevida"
    assert encadeamento_validador(sem_certa, decisoes) is None


def test_relatorio_em_markdown_e_tabelas_tex() -> None:
    medidas = [medida("i1", COM), medida("i1", SEM, certa=False)]
    texto, tabelas = relatorio(medidas)
    assert "| 3. Solução correta | 1/1 (100%) | 0/1 (0%) | 0 | 1 | 0 | 0 | 1.000 |" in texto
    assert set(tabelas) == {
        "criterios",
        "recorte_faixa",
        "recorte_origem",
        "recorte_familia",
        "recorte_classe",
        "validador",
    }
    assert (
        "3. Solução correta & 1/1 (100\\%) & 0/1 (0\\%) & 1 & 0 & 1{,}000" in tabelas["criterios"]
    )
