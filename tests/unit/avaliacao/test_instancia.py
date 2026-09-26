import json
from pathlib import Path
from typing import Any

import pytest

from po_multiagente.avaliacao.instancia import validar_instancia
from po_multiagente.cli import main

INTEGRIDADE = "Produto;Lucro;Horas\nA;3;1\nB;5;2\n"
QUADRO: dict[str, Any] = {
    "decisao": "Quanto produzir",
    "criterio": "Lucro total",
    "sentido": "maximizar",
    "requisitos": [
        {"id": "REQ1", "texto": "Maior lucro"},
        {"id": "REQ2", "texto": "Horas limitadas"},
    ],
    "parametros": [
        {
            "id": "lucro",
            "descricao": "Lucro",
            "unidade": "R$/un",
            "origem": {"arquivo": "produtos.csv", "coluna": "Lucro", "chaves": ["Produto"]},
        },
        {
            "id": "horas",
            "descricao": "Horas",
            "unidade": "h/un",
            "origem": {"arquivo": "produtos.csv", "coluna": "Horas", "chaves": ["Produto"]},
        },
        {
            "id": "cap",
            "descricao": "Horas disponíveis",
            "unidade": "h",
            "origem": {"arquivo": "capacidade.csv", "coluna": "Horas"},
        },
    ],
}
MODELO: dict[str, Any] = {
    "conjuntos": [
        {
            "id": "P",
            "descricao": "Produtos",
            "origem": {"arquivo": "produtos.csv", "coluna": "Produto"},
        }
    ],
    "parametros": [
        {"id": "lucro", "indices": ["P"]},
        {"id": "horas", "indices": ["P"]},
        {"id": "cap", "indices": []},
    ],
    "variaveis": [
        {"id": "x", "descricao": "Produção", "unidade": "un", "tipo": "continua", "indices": ["P"]}
    ],
    "objetivo": {
        "sentido": "maximizar",
        "expressao": "sum(lucro[p] * x[p] for p in P)",
        "descricao": "Lucro",
        "requisitos": ["REQ1"],
    },
    "restricoes": [
        {
            "id": "tempo",
            "descricao": "Horas",
            "requisitos": ["REQ2"],
            "expressao": "sum(horas[p] * x[p] for p in P) <= cap",
        }
    ],
}


def criar(
    pasta: Path, *, valor: float = 30.0, classe: str = "pl", quadro: dict[str, Any] | None = None
) -> Path:
    (pasta / "dados").mkdir(parents=True)
    (pasta / "referencia").mkdir()
    (pasta / "dados" / "produtos.csv").write_text(INTEGRIDADE, encoding="utf-8")
    (pasta / "dados" / "capacidade.csv").write_text("Horas\n10\n", encoding="utf-8")
    (pasta / "descricao.md").write_text("Quero lucrar o máximo com as horas que tenho.", "utf-8")
    (pasta / "referencia" / "quadro.json").write_text(json.dumps(quadro or QUADRO), "utf-8")
    (pasta / "referencia" / "modelo.json").write_text(json.dumps(MODELO), "utf-8")
    (pasta / "solucao.json").write_text(json.dumps({"valor_objetivo": valor}), "utf-8")
    (pasta / "meta.yaml").write_text(f"familia: alocacao\nclasse: {classe}\n", "utf-8")
    return pasta


def test_instancia_valida(tmp_path: Path) -> None:
    # A rende 3 por hora e B, 2,5: as 10 horas vão para A, lucro 30.
    relatorio = validar_instancia(criar(tmp_path / "i1"))
    assert relatorio.valida, relatorio.problemas
    assert relatorio.valor_obtido == pytest.approx(30.0)
    assert relatorio.avisos == ()


def test_valor_divergente_classe_errada_e_parametro_sobrando(tmp_path: Path) -> None:
    quadro = {
        **QUADRO,
        "parametros": [*QUADRO["parametros"], {**QUADRO["parametros"][0], "id": "sobra"}],
    }
    relatorio = validar_instancia(criar(tmp_path / "i2", valor=40.0, classe="plim", quadro=quadro))
    assert not relatorio.valida
    texto = " | ".join(relatorio.problemas)
    assert "classe 'plim', mas a referência não tem variável inteira" in texto
    assert "parâmetro 'sobra' do quadro não é usado" in texto
    assert "difere da solução registrada (40)" in texto


def test_arquivo_faltante(tmp_path: Path) -> None:
    pasta = criar(tmp_path / "i3")
    (pasta / "solucao.json").unlink()
    relatorio = validar_instancia(pasta)
    assert not relatorio.valida
    assert "solucao.json" in relatorio.problemas[0]


def test_referencia_que_nao_compila(tmp_path: Path) -> None:
    pasta = criar(tmp_path / "i4")
    modelo = {
        **MODELO,
        "objetivo": {**MODELO["objetivo"], "expressao": "sum(x[p] * x[p] for p in P)"},
    }
    (pasta / "referencia" / "modelo.json").write_text(json.dumps(modelo), "utf-8")
    relatorio = validar_instancia(pasta)
    assert any("não linear" in p for p in relatorio.problemas)


def test_cli_valida_pasta_de_instancias(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    criar(tmp_path / "conjunto" / "a")
    criar(tmp_path / "conjunto" / "b", valor=99.0)
    assert main(["validar-instancia", str(tmp_path / "conjunto")]) == 1
    saida = capsys.readouterr().out
    assert "OK    a" in saida
    assert "FALHA b" in saida
    assert "1/2 instância(s) válida(s)" in saida
    assert main(["validar-instancia", str(tmp_path / "conjunto" / "a")]) == 0


def test_instancia_inviavel_por_construcao(tmp_path: Path) -> None:
    pasta = criar(tmp_path / "i5")
    modelo = {
        **MODELO,
        "restricoes": [
            *MODELO["restricoes"],
            {
                "id": "minimo",
                "descricao": "Mínimo impossível",
                "requisitos": ["REQ2"],
                "expressao": "sum(horas[p] * x[p] for p in P) >= cap + 1",
            },
        ],
    }
    (pasta / "referencia" / "modelo.json").write_text(json.dumps(modelo), "utf-8")
    (pasta / "solucao.json").write_text(json.dumps({"status": "inviavel"}), "utf-8")
    relatorio = validar_instancia(pasta)
    assert relatorio.valida, relatorio.problemas
    (pasta / "solucao.json").write_text(json.dumps({"valor_objetivo": 30}), "utf-8")
    assert any("status inviavel" in p for p in validar_instancia(pasta).problemas)
