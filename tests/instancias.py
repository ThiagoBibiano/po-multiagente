"""Instâncias com gabarito montadas nos testes (construção própria, públicas)."""

import json
from pathlib import Path
from typing import Any

PRODUTOS = (
    "Produto;Margem por peça;Horas de marcenaria\nMesa;120;4\nCadeira;45;1,5\nEstante;150;5\n"
)
DESCRICAO = (
    "Fabricamos mesas, cadeiras e estantes. A marcenaria tem horas limitadas no mês e cada peça "
    "consome um tanto delas. Quero o plano de produção com a maior margem.\n"
)


def _param(
    id_: str, unidade: str, arquivo: str, coluna: str, chaves: list[str], **extra: Any
) -> dict[str, Any]:
    return {
        "id": id_,
        "descricao": coluna,
        "unidade": unidade,
        "origem": {"arquivo": arquivo, "coluna": coluna, "chaves": chaves, "filtros": [], **extra},
    }


QUADRO: dict[str, Any] = {
    "decisao": "Quanto produzir de cada peça",
    "criterio": "Margem total",
    "sentido": "maximizar",
    "requisitos": [
        {"id": "REQ1", "texto": "Obter a maior margem"},
        {"id": "REQ2", "texto": "Não passar das horas de marcenaria"},
    ],
    "parametros": [
        _param("margem", "R$/un", "produtos.csv", "Margem por peça", ["Produto"]),
        _param("horas", "h/un", "produtos.csv", "Horas de marcenaria", ["Produto"]),
        _param("cap", "h", "capacidade.csv", "Horas no mês", []),
    ],
    "solicitacoes": [],
    "premissas": [],
    "nao_considerado": [],
    "alertas": [],
}
MODELO: dict[str, Any] = {
    "conjuntos": [
        {
            "id": "P",
            "descricao": "Peças",
            "origem": {"arquivo": "produtos.csv", "coluna": "Produto"},
        }
    ],
    "parametros": [
        {"id": "margem", "indices": ["P"]},
        {"id": "horas", "indices": ["P"]},
        {"id": "cap", "indices": []},
    ],
    "variaveis": [
        {"id": "x", "descricao": "Peças", "unidade": "un", "tipo": "continua", "indices": ["P"]}
    ],
    "objetivo": {
        "sentido": "maximizar",
        "expressao": "sum(margem[p] * x[p] for p in P)",
        "descricao": "Margem",
        "requisitos": ["REQ1"],
    },
    "restricoes": [
        {
            "id": "marcenaria",
            "descricao": "Horas",
            "requisitos": ["REQ2"],
            "expressao": "sum(horas[p] * x[p] for p in P) <= cap",
        }
    ],
}
# As três peças rendem 30 por hora de marcenaria: com 200 horas, a margem máxima é 6000
# (o ótimo tem várias soluções; o valor é único).
VALOR = 6000.0


def criar_instancia(pasta: Path, *, semanal: bool = False, particao: str = "ajuste") -> Path:
    """Instância de alocação; com ``semanal``, a capacidade exige tratamento de granularidade."""
    (pasta / "dados").mkdir(parents=True)
    (pasta / "referencia").mkdir()
    (pasta / "descricao.md").write_text(DESCRICAO, "utf-8")
    (pasta / "dados" / "produtos.csv").write_text(PRODUTOS, "utf-8")
    quadro = json.loads(json.dumps(QUADRO))
    if semanal:
        (pasta / "dados" / "horas_semanais.csv").write_text(
            "Semana;Horas\n1;50\n2;50\n3;50\n4;50\n", "utf-8"
        )
        (pasta / "dados_tratados").mkdir()
        (pasta / "dados_tratados" / "capacidade.csv").write_text("Horas no mês\n200\n", "utf-8")
        (pasta / "solicitacoes_esperadas.yaml").write_text(
            "- parametro: cap\n  arquivo: horas_semanais.csv\n  coluna: Horas\n"
            "  motivo: granularidade\n  resposta: capacidade.csv\n",
            "utf-8",
        )
        quadro["parametros"][2]["origem"]["solicitacao_id"] = "s_cap"
        quadro["solicitacoes"] = [
            {
                "id": "s_cap",
                "parametro_id": "cap",
                "arquivo": "horas_semanais.csv",
                "coluna": "Horas",
                "motivo": "granularidade",
                "forma_esperada": "Horas do mês",
            }
        ]
    else:
        (pasta / "dados" / "capacidade.csv").write_text("Horas no mês\n200\n", "utf-8")
    (pasta / "referencia" / "quadro.json").write_text(json.dumps(quadro), "utf-8")
    (pasta / "referencia" / "modelo.json").write_text(json.dumps(MODELO), "utf-8")
    (pasta / "solucao.json").write_text(json.dumps({"valor_objetivo": VALOR}), "utf-8")
    (pasta / "meta.yaml").write_text(
        f"familia: alocacao\nclasse: pl\nparticao: {particao}\n"
        "resultado_trivial_aceitavel: false\n",
        "utf-8",
    )
    return pasta
