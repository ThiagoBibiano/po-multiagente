from pathlib import Path

import pytest
from openpyxl import Workbook

from po_multiagente.dados import ErroDados, Fontes, arquivo_da_fonte, sha256_arquivo
from po_multiagente.dominio import TipoColuna


@pytest.fixture
def pasta(tmp_path: Path) -> Path:
    (tmp_path / "produtos.csv").write_text("Produto;Lucro\nA;10\nB;20\n", encoding="utf-8")
    livro = Workbook()
    livro.active.title = "Horas"  # type: ignore[union-attr]
    livro.active.append(["Produto", "Horas"])  # type: ignore[union-attr]
    livro.active.append(["A", 2])  # type: ignore[union-attr]
    livro.create_sheet("Limites").append(["Recurso"])
    livro["Limites"].append(["Máquina"])
    livro.save(tmp_path / "fabrica.xlsx")
    (tmp_path / "leia-me.txt").write_text("ignorado", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    return tmp_path


def test_arquivos_listam_so_fontes_aceitas(pasta: Path) -> None:
    assert Fontes(pasta).arquivos == ("fabrica.xlsx", "produtos.csv")


def test_inventario_tem_uma_fonte_por_aba(pasta: Path) -> None:
    inventario = Fontes(pasta).inventario()
    assert [f.arquivo for f in inventario] == [
        "fabrica.xlsx[Horas]",
        "fabrica.xlsx[Limites]",
        "produtos.csv",
    ]
    assert inventario[0].sha256 == inventario[1].sha256 == sha256_arquivo(pasta / "fabrica.xlsx")
    assert inventario[2].colunas[1].tipo is TipoColuna.INTEIRO


def test_tabela_por_nome_de_aba(pasta: Path) -> None:
    assert Fontes(pasta).tabela("fabrica.xlsx[Horas]").valores("Horas") == (2,)


@pytest.mark.parametrize("nome", ["inexistente.csv", "../fora.csv", "leia-me.txt"])
def test_arquivo_fora_da_colecao_e_rejeitado(pasta: Path, nome: str) -> None:
    with pytest.raises(ErroDados, match="Não há arquivo"):
        Fontes(pasta).tabela(nome)


def test_aba_inexistente_e_rejeitada(pasta: Path) -> None:
    with pytest.raises(ErroDados, match="Não há fonte"):
        Fontes(pasta).tabela("fabrica.xlsx[Outra]")


def test_diretorio_inexistente_e_rejeitado(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        Fontes(tmp_path / "nada")


def test_integridade_aponta_arquivo_alterado_ou_removido(pasta: Path) -> None:
    fontes = Fontes(pasta)
    inventario = fontes.inventario()
    assert fontes.conferir_integridade(inventario) == ()
    (pasta / "produtos.csv").write_text("Produto;Lucro\nA;11\n", encoding="utf-8")
    (pasta / "fabrica.xlsx").unlink()
    assert fontes.conferir_integridade(inventario) == (
        "fabrica.xlsx[Horas]",
        "fabrica.xlsx[Limites]",
        "produtos.csv",
    )


def test_leitura_nao_altera_os_arquivos(pasta: Path) -> None:
    antes = {c.name: c.read_bytes() for c in pasta.iterdir() if c.is_file()}
    fontes = Fontes(pasta)
    fontes.inventario()
    fontes.tabela("produtos.csv")
    assert {c.name: c.read_bytes() for c in pasta.iterdir() if c.is_file()} == antes


@pytest.mark.parametrize(
    ("nome", "arquivo"),
    [
        ("dados.xlsx[Custos]", "dados.xlsx"),
        ("dados.XLSX[a[1]]", "dados.XLSX"),
        ("rotas[2026].csv", "rotas[2026].csv"),
        ("produtos.csv", "produtos.csv"),
    ],
)
def test_arquivo_da_fonte(nome: str, arquivo: str) -> None:
    assert arquivo_da_fonte(nome) == arquivo
