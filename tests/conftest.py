"""Fixtures compartilhadas: um problema de alocação da produção, no estilo do piloto."""

import pytest

from po_multiagente.dominio import (
    Coluna,
    Conjunto,
    Especificacao,
    FonteDados,
    ModeloIR,
    Objetivo,
    Origem,
    Parametro,
    ParametroModelo,
    Quantificador,
    Requisito,
    Restricao,
    Sentido,
    TipoColuna,
    TipoVariavel,
    Variavel,
)

HASH_PRODUTOS = "a" * 64


@pytest.fixture
def fonte_produtos() -> FonteDados:
    return FonteDados(
        arquivo="produtos.csv",
        sha256=HASH_PRODUTOS,
        colunas=(
            Coluna(nome="Produto", tipo=TipoColuna.TEXTO),
            Coluna(nome="Lucro unitário (R$)", tipo=TipoColuna.DECIMAL),
            Coluna(nome="Horas de máquina", tipo=TipoColuna.DECIMAL),
        ),
    )


@pytest.fixture
def especificacao(fonte_produtos: FonteDados) -> Especificacao:
    return Especificacao(
        decisao="Quanto produzir de cada produto no mês",
        criterio="Lucro total",
        sentido=Sentido.MAXIMIZAR,
        requisitos=(
            Requisito(id="REQ1", texto="Não ultrapassar as 200 horas de máquina do mês"),
            Requisito(id="REQ2", texto="Obter o maior lucro possível"),
        ),
        parametros=(
            Parametro(
                id="lucro",
                descricao="Lucro por unidade vendida",
                unidade="R$/un",
                origem=Origem(
                    arquivo="produtos.csv", coluna="Lucro unitário (R$)", chaves=("Produto",)
                ),
            ),
            Parametro(
                id="horas",
                descricao="Horas de máquina por unidade",
                unidade="h/un",
                origem=Origem(
                    arquivo="produtos.csv", coluna="Horas de máquina", chaves=("Produto",)
                ),
            ),
        ),
        fontes=(fonte_produtos,),
        nao_considerado=("Estoque de matéria-prima",),
    )


@pytest.fixture
def modelo() -> ModeloIR:
    return ModeloIR(
        conjuntos=(
            Conjunto(
                id="PRODUTOS",
                descricao="Produtos fabricados",
                origem=Origem(arquivo="produtos.csv", coluna="Produto"),
            ),
        ),
        parametros=(
            ParametroModelo(id="lucro", indices=("PRODUTOS",)),
            ParametroModelo(id="horas", indices=("PRODUTOS",)),
        ),
        variaveis=(
            Variavel(
                id="x",
                descricao="Quantidade produzida",
                unidade="un",
                tipo=TipoVariavel.CONTINUA,
                indices=("PRODUTOS",),
            ),
        ),
        objetivo=Objetivo(
            sentido=Sentido.MAXIMIZAR,
            expressao="sum(lucro[p] * x[p] for p in PRODUTOS)",
            descricao="Lucro total",
            requisitos=("REQ2",),
        ),
        restricoes=(
            Restricao(
                id="capacidade",
                descricao="Horas de máquina disponíveis",
                requisitos=("REQ1",),
                expressao="sum(horas[p] * x[p] for p in PRODUTOS) <= 200",
            ),
        ),
    )


@pytest.fixture
def restricao_por_produto() -> Restricao:
    return Restricao(
        id="demanda",
        descricao="Produção limitada à demanda",
        requisitos=("REQ1",),
        para_todo=(Quantificador(indice="p", conjunto="PRODUTOS"),),
        expressao="x[p] <= 50",
    )
