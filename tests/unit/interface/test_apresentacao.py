import zipfile
from pathlib import Path

import pytest

from po_multiagente.dominio import ModeloIR
from po_multiagente.interface import Assistente, Resultado
from po_multiagente.interface import apresentacao as ap
from po_multiagente.llm import LLMRoteirizado
from tests.instancias import DESCRICAO, MODELO, QUADRO, criar_instancia


@pytest.fixture
def resultado(tmp_path: Path) -> Resultado:
    pasta = criar_instancia(tmp_path / "inst")
    llm = LLMRoteirizado(
        {
            "interpretador": [QUADRO],
            "modelador": [MODELO],
            "explicador": [{"texto": "A margem máxima é {{OBJ}}."}],
        }
    )
    assistente = Assistente(llm, pasta_trabalho=tmp_path / "trabalho")
    assistente.comecar(DESCRICAO, sorted((pasta / "dados").iterdir()))
    return assistente.resultado()


def test_destaque_e_selo(resultado: Resultado) -> None:
    destaque = ap.destaque(resultado)
    assert "Melhor solução encontrada" in destaque
    assert "**Margem total** (maior valor possível)" in destaque
    assert "6.000" in destaque
    assert "5 de 5 verificações aprovadas na primeira rodada" in ap.selo_conferencia(resultado)


def test_plano_mostra_so_decisoes_diferentes_de_zero(resultado: Resultado) -> None:
    plano = ap.plano_recomendado(resultado)
    assert plano.startswith("#### Plano recomendado")
    assert "| Produto | Peças (un) |" in plano
    linhas = [li for li in plano.splitlines() if li.startswith("| ") and "Produto" not in li]
    assert linhas
    assert all(not li.endswith("| 0 |") for li in linhas)


def test_modelo_conferencias_e_entendimento_legiveis(resultado: Resultado) -> None:
    modelo = ap.modelo_legivel(resultado)
    assert modelo.startswith("$$\n\\begin{aligned}")
    assert "| `margem` | Margem por peça | R$/un | `produtos.csv` › `Margem por peça` |" in modelo
    assert "Obter a maior margem" in modelo or "Não passar das horas" in modelo
    assert "- ✅ **Resultado do solver:**" in ap.conferencias(resultado.pareceres)
    entendimento = ap.entendimento(resultado.especificacao)
    assert "**Decisão:** Quanto produzir de cada peça" in entendimento
    assert "**Critério:** Maximizar margem total" in entendimento
    assert "| `produtos.csv` |" in entendimento
    assert "| Tempo total | 3 s |" in ap.consumo(resultado, 3.2)


def test_pacote_para_baixar(resultado: Resultado, tmp_path: Path) -> None:
    caminho = ap.empacotar(resultado, tmp_path / "saida")
    with zipfile.ZipFile(caminho) as zip_:
        nomes = set(zip_.namelist())
        assert {"solucao.csv", "explicacao.md", "formulacao.tex", "modelo.json"} <= nomes
        assert zip_.read("solucao.csv").decode().startswith("variavel;indices;valor")


def transporte(tipo: str = "continua") -> ModeloIR:
    def conjunto(id_: str, coluna: str) -> dict[str, object]:
        return {"id": id_, "descricao": id_, "origem": {"arquivo": "d.csv", "coluna": coluna}}

    return ModeloIR.model_validate(
        {
            "conjuntos": [conjunto("FABRICAS", "fabrica"), conjunto("MERCADOS", "mercado")],
            "variaveis": [
                {
                    "id": "x",
                    "descricao": "Envio",
                    "unidade": "un",
                    "tipo": tipo,
                    "indices": ["FABRICAS", "MERCADOS"],
                }
            ],
            "objetivo": {
                "sentido": "minimizar",
                "expressao": "sum(x[f, m] for f in FABRICAS for m in MERCADOS)",
                "descricao": "Frete total",
            },
        }
    )


def test_duas_dimensoes_viram_tabela_cruzada_com_totais() -> None:
    solucao = {"x[A,SP]": 500.0, "x[A,RJ]": 0.0, "x[B,SP]": 100.0, "x[B,RJ]": 900.0}
    resultado = Resultado(
        explicacao=None,
        status="otimo",
        valor_objetivo=6900.0,
        falha=None,
        solucao=solucao,
        modelo=transporte(),
    )
    tabela = ap.decisoes(resultado)
    assert "| Fabrica \\ Mercado | SP | RJ | Total |" in tabela
    assert "| **A** | 500 | 0 | **500** |" in tabela
    assert "| **Total** | **600** | **900** | **1.500** |" in tabela
    assert "(menor valor possível)" in ap.destaque(resultado)
    plano = ap.plano_recomendado(resultado)
    assert "| A | RJ |" not in plano
    assert "| B | RJ | 900 |" in plano


def test_binaria_aparece_como_sim_ou_nao_e_tabela_longa_e_cortada() -> None:
    solucao = {f"x[F{i},M]": float(i % 2) for i in range(ap.MAX_LINHAS + 5)}
    resultado = Resultado(
        explicacao=None,
        status="otimo",
        valor_objetivo=1.0,
        falha=None,
        solucao=solucao,
        modelo=transporte("binaria"),
    )
    plano = ap.plano_recomendado(resultado)
    assert "| F1 | M | sim |" in plano
    assert "| não |" not in plano
    assert "| **F0** | não | **0** |" in ap.decisoes(resultado)
    longa = ap._tabela(["a"], [[str(i)] for i in range(ap.MAX_LINHAS + 5)])
    assert "… e mais 5 linha(s)" in longa
