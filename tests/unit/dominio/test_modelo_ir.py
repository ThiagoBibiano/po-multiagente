import pytest
from pydantic import ValidationError

from po_multiagente.dominio import (
    ModeloIR,
    Quantificador,
    Restricao,
    TipoVariavel,
    Variavel,
)


def test_modelo_valido_faz_ida_e_volta_em_json(modelo: ModeloIR) -> None:
    assert ModeloIR.model_validate_json(modelo.model_dump_json()) == modelo


def test_esquema_json_e_gerado(modelo: ModeloIR) -> None:
    esquema = ModeloIR.model_json_schema()
    assert esquema["additionalProperties"] is False
    assert {"variaveis", "objetivo"} <= set(esquema["required"])


def test_restricao_indexada_e_aceita(modelo: ModeloIR, restricao_por_produto: Restricao) -> None:
    dados = modelo.model_dump(mode="json")
    dados["restricoes"].append(restricao_por_produto.model_dump(mode="json"))
    assert len(ModeloIR.model_validate(dados).restricoes) == 2


def test_identificador_repetido_entre_categorias_e_rejeitado(modelo: ModeloIR) -> None:
    dados = modelo.model_dump(mode="json")
    dados["restricoes"][0]["id"] = "x"
    with pytest.raises(ValidationError, match="Identificadores do modelo com repetição: x"):
        ModeloIR.model_validate(dados)


def test_conjunto_nao_declarado_e_rejeitado(modelo: ModeloIR) -> None:
    dados = modelo.model_dump(mode="json")
    dados["variaveis"][0]["indices"] = ["PRODUTOS", "MESES"]
    with pytest.raises(ValidationError, match="Conjuntos sem declaração: MESES"):
        ModeloIR.model_validate(dados)


def test_quantificador_com_conjunto_nao_declarado_e_rejeitado(
    modelo: ModeloIR, restricao_por_produto: Restricao
) -> None:
    restricao = restricao_por_produto.model_copy(
        update={"para_todo": (Quantificador(indice="m", conjunto="MESES"),)}
    )
    dados = modelo.model_dump(mode="json")
    dados["restricoes"].append(restricao.model_dump(mode="json"))
    with pytest.raises(ValidationError, match="Conjuntos sem declaração: MESES"):
        ModeloIR.model_validate(dados)


def test_restricao_sem_requisito_e_rejeitada() -> None:
    with pytest.raises(ValidationError):
        Restricao(id="r", descricao="Sem vínculo", requisitos=(), expressao="x <= 1")


def test_restricao_com_indice_repetido_e_rejeitada() -> None:
    with pytest.raises(ValidationError, match="Índices da restrição r com repetição: i"):
        Restricao(
            id="r",
            descricao="Índice duplicado",
            requisitos=("REQ1",),
            para_todo=(
                Quantificador(indice="i", conjunto="A"),
                Quantificador(indice="i", conjunto="B"),
            ),
            expressao="x[i] <= 1",
        )


def test_modelo_exige_ao_menos_uma_variavel(modelo: ModeloIR) -> None:
    dados = modelo.model_dump(mode="json")
    dados["variaveis"] = []
    with pytest.raises(ValidationError):
        ModeloIR.model_validate(dados)


@pytest.mark.parametrize(
    ("inferior", "superior"),
    [(0.0, None), (None, None), (0.0, 1.0), (None, 1.0)],
)
def test_binaria_aceita_limites_triviais(inferior: float | None, superior: float | None) -> None:
    variavel = Variavel(
        id="y",
        descricao="Abre a fábrica",
        unidade="adimensional",
        tipo=TipoVariavel.BINARIA,
        limite_inferior=inferior,
        limite_superior=superior,
    )
    assert variavel.tipo is TipoVariavel.BINARIA


def test_binaria_rejeita_limite_superior_diferente_de_um() -> None:
    with pytest.raises(ValidationError, match="binária"):
        Variavel(
            id="y",
            descricao="Abre a fábrica",
            unidade="adimensional",
            tipo=TipoVariavel.BINARIA,
            limite_superior=2.0,
        )


def test_limite_inferior_maior_que_superior_e_rejeitado() -> None:
    with pytest.raises(ValidationError, match="limite inferior maior"):
        Variavel(
            id="x",
            descricao="Produção",
            unidade="un",
            tipo=TipoVariavel.CONTINUA,
            limite_inferior=10.0,
            limite_superior=5.0,
        )


def test_limite_infinito_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        Variavel(
            id="x",
            descricao="Produção",
            unidade="un",
            tipo=TipoVariavel.CONTINUA,
            limite_superior=float("inf"),
        )
