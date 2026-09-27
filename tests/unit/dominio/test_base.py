import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import TypeAdapter, ValidationError

from po_multiagente.dominio import Identificador, IdRequisito, Requisito
from po_multiagente.dominio._base import exigir_declarados, exigir_unicos

IDENTIFICADOR = TypeAdapter(Identificador)
ID_REQUISITO = TypeAdapter(IdRequisito)


@given(st.from_regex(r"[A-Za-z_][A-Za-z0-9_]{0,63}", fullmatch=True))
def test_identificador_aceita_nomes_simbolicos(nome: str) -> None:
    assert IDENTIFICADOR.validate_python(nome) == nome


@pytest.mark.parametrize("nome", ["", "1x", "custo total", "preço", "x-1", "a" * 65])
def test_identificador_rejeita_nomes_invalidos(nome: str) -> None:
    with pytest.raises(ValidationError):
        IDENTIFICADOR.validate_python(nome)


@pytest.mark.parametrize("valor", ["REQ1", "REQ10", "REQ123"])
def test_id_requisito_aceita_formato(valor: str) -> None:
    assert ID_REQUISITO.validate_python(valor) == valor


@pytest.mark.parametrize("valor", ["REQ0", "REQ01", "R1", "req1", "REQ"])
def test_id_requisito_rejeita_formato(valor: str) -> None:
    with pytest.raises(ValidationError):
        ID_REQUISITO.validate_python(valor)


def test_objeto_de_dominio_e_imutavel() -> None:
    requisito = Requisito(id="REQ1", texto="Atender à demanda")
    with pytest.raises(ValidationError):
        requisito.texto = "Outro texto"  # type: ignore[misc]


def test_objeto_de_dominio_rejeita_campo_extra() -> None:
    with pytest.raises(ValidationError, match="extra"):
        Requisito.model_validate({"id": "REQ1", "texto": "Atender", "prioridade": 1})


def test_texto_so_com_espacos_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        Requisito(id="REQ1", texto="   ")


def test_exigir_unicos_lista_todos_os_repetidos() -> None:
    with pytest.raises(ValueError, match="Itens com repetição: a, b"):
        exigir_unicos(["b", "a", "b", "c", "a"], "Itens")


def test_exigir_declarados_lista_todos_os_faltantes() -> None:
    with pytest.raises(ValueError, match=r"Itens sem declaração: x, y \(declarados: a, b\)$"):
        exigir_declarados(["y", "a", "x"], ["a", "b"], "Itens")
    with pytest.raises(ValueError, match=r"\(nenhum declarado\)$"):
        exigir_declarados(["x"], [], "Itens")
