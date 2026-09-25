import re

import pytest
from pydantic import ValidationError

from po_multiagente.dominio import (
    AlertaAmbiguidade,
    Coluna,
    Especificacao,
    FonteDados,
    MotivoTratamento,
    Origem,
    Parametro,
    Requisito,
    Solicitacao,
    TipoColuna,
)


def test_especificacao_valida_faz_ida_e_volta_em_json(especificacao: Especificacao) -> None:
    assert Especificacao.model_validate_json(especificacao.model_dump_json()) == especificacao


def test_especificacao_exige_ao_menos_um_requisito(especificacao: Especificacao) -> None:
    dados = especificacao.model_dump(mode="json")
    dados["requisitos"] = []
    with pytest.raises(ValidationError):
        Especificacao.model_validate(dados)


def test_requisitos_repetidos_sao_rejeitados(especificacao: Especificacao) -> None:
    dados = especificacao.model_dump(mode="json")
    dados["requisitos"].append({"id": "REQ1", "texto": "Duplicado"})
    with pytest.raises(ValidationError, match="Requisitos com repetição: REQ1"):
        Especificacao.model_validate(dados)


def test_parametro_de_arquivo_nao_declarado_e_rejeitado(especificacao: Especificacao) -> None:
    fantasma = Parametro(
        id="custo",
        descricao="Custo",
        unidade="R$/un",
        origem=Origem(arquivo="custos.csv", coluna="Custo"),
    )
    dados = especificacao.model_dump(mode="json")
    dados["parametros"].append(fantasma.model_dump(mode="json"))
    with pytest.raises(
        ValidationError, match=re.escape("Arquivos de origem sem declaração: custos.csv")
    ):
        Especificacao.model_validate(dados)


def test_origem_por_solicitacao_exige_a_solicitacao(especificacao: Especificacao) -> None:
    dados = especificacao.model_dump(mode="json")
    dados["parametros"][0]["origem"]["solicitacao_id"] = "sol_lucro"
    with pytest.raises(ValidationError, match="Solicitações de origem sem declaração: sol_lucro"):
        Especificacao.model_validate(dados)


def test_origem_por_solicitacao_declarada_e_aceita(especificacao: Especificacao) -> None:
    solicitacao = Solicitacao(
        id="sol_lucro",
        parametro_id="lucro",
        arquivo="produtos.csv",
        coluna="Lucro unitário (R$)",
        motivo=MotivoTratamento.UNIDADE,
        forma_esperada="Lucro em reais por unidade, e não por lote",
    )
    dados = especificacao.model_dump(mode="json")
    dados["parametros"][0]["origem"]["solicitacao_id"] = "sol_lucro"
    dados["solicitacoes"] = [solicitacao.model_dump(mode="json")]
    assert Especificacao.model_validate(dados).solicitacoes == (solicitacao,)


def test_alerta_com_requisito_inexistente_e_rejeitado(especificacao: Especificacao) -> None:
    alerta = AlertaAmbiguidade(
        trecho="no máximo 200", leituras=("por mês", "por semana"), requisito_id="REQ9"
    )
    dados = especificacao.model_dump(mode="json")
    dados["alertas"] = [alerta.model_dump(mode="json")]
    with pytest.raises(ValidationError, match="Requisitos dos alertas sem declaração: REQ9"):
        Especificacao.model_validate(dados)


def test_alerta_exige_duas_leituras() -> None:
    with pytest.raises(ValidationError):
        AlertaAmbiguidade(trecho="no máximo 200", leituras=("por mês",))


def test_fonte_rejeita_colunas_repetidas() -> None:
    with pytest.raises(
        ValidationError, match=re.escape("Colunas de 'a.csv' com repetição: Produto")
    ):
        FonteDados(
            arquivo="a.csv",
            sha256="b" * 64,
            colunas=(
                Coluna(nome="Produto", tipo=TipoColuna.TEXTO),
                Coluna(nome="Produto", tipo=TipoColuna.TEXTO),
            ),
        )


def test_requisito_com_id_fora_do_padrao_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        Requisito(id="R1", texto="Atender à demanda")
