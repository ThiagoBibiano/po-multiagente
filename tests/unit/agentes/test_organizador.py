from typing import Any

import pytest

from po_multiagente.agentes import ErroAgente, Organizador, Registro
from po_multiagente.agentes.organizador import DadosOrganizados, numeros_sem_origem
from po_multiagente.llm import LLMRoteirizado

TEXTO = "Mesas dão 120 de margem e cadeiras 45. Temos 1.500 horas no mês; a cadeira leva 1,5 h."


def tabela(arquivo: str = "produtos.csv", *linhas: list[str]) -> dict[str, Any]:
    return {
        "arquivo": arquivo,
        "descricao": "Produtos",
        "colunas": ["Produto", "Margem (R$/un)"],
        "linhas": list(linhas) or [["Mesa", "120"], ["Cadeira", "45"]],
    }


def test_numeros_sem_origem_aceita_ponto_de_milhar() -> None:
    dados = DadosOrganizados.model_validate(
        {
            "tabelas": [
                tabela("a.csv", ["Mesa", "120"], ["Horas", "1500"]),
                tabela("b.csv", ["Cadeira", "1,5"], ["Estante", "150"]),
            ]
        }
    )
    assert numeros_sem_origem(dados, TEXTO) == ["150"]


def test_organiza_e_recusa_numero_inventado() -> None:
    inventada = {"tabelas": [tabela("produtos.csv", ["Mesa", "130"])], "faltantes": []}
    certa = {"tabelas": [tabela()], "faltantes": ["horas de montagem da mesa"]}
    llm = LLMRoteirizado({"organizador": [inventada, certa]})
    registro = Registro()
    dados = Organizador(llm).organizar(TEXTO, registro)
    assert dados.tabelas[0].linhas == (("Mesa", "120"), ("Cadeira", "45"))
    assert dados.faltantes == ("horas de montagem da mesa",)
    assert len(registro.chamadas) == 2


@pytest.mark.parametrize(
    "saida",
    [
        {"tabelas": [tabela("Produtos.CSV")]},
        {"tabelas": [tabela("p.csv", ["Mesa"])]},
        {"tabelas": [tabela("p.csv"), tabela("p.csv")]},
    ],
)
def test_desiste_depois_das_tentativas(saida: dict[str, Any]) -> None:
    llm = LLMRoteirizado({"organizador": [saida] * 2})
    with pytest.raises(ErroAgente, match="organizador"):
        Organizador(llm, max_tentativas=2).organizar(TEXTO, Registro())


def test_sem_numeros_devolve_so_os_faltantes() -> None:
    llm = LLMRoteirizado({"organizador": [{"tabelas": [], "faltantes": ["a margem de cada peça"]}]})
    dados = Organizador(llm).organizar("Quero produzir mesas e cadeiras.", Registro())
    assert dados.tabelas == ()
    assert dados.faltantes == ("a margem de cada peça",)
