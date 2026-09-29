from datetime import date, datetime
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openpyxl import Workbook

from po_multiagente.dados import ErroDados, ler_csv, ler_xlsx, texto_celula
from po_multiagente.dominio import MotivoTratamento, TipoColuna


def escrever(pasta: Path, nome: str, texto: str, codificacao: str = "utf-8") -> Path:
    caminho = pasta / nome
    caminho.write_bytes(texto.encode(codificacao))
    return caminho


def test_csv_brasileiro_le_decimal_com_virgula_e_milhar_com_ponto(tmp_path: Path) -> None:
    caminho = escrever(
        tmp_path,
        "produtos.csv",
        "Produto;Lucro unitário (R$);Estoque\nMesa;1.234,50;10\nCadeira;80,00;1.200\n",
    )
    tabela = ler_csv(caminho)
    assert tabela.colunas == ("Produto", "Lucro unitário (R$)", "Estoque")
    assert tabela.tipos == (TipoColuna.TEXTO, TipoColuna.DECIMAL, TipoColuna.INTEIRO)
    assert tabela.valores("Lucro unitário (R$)") == (1234.5, 80.0)
    assert tabela.valores("Estoque") == (10, 1200)


def test_csv_com_virgula_usa_notacao_norte_americana(tmp_path: Path) -> None:
    caminho = escrever(tmp_path, "d.csv", 'item,custo\nA,"1,500.25"\nB,3.5\n')
    assert ler_csv(caminho).valores("custo") == (1500.25, 3.5)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("a\tb\nx\t1,5\n", 1.5),
        ("a\tb\nx\t1.5\n", 1.5),
        ("a|b\nx|2,25\n", 2.25),
    ],
)
def test_outros_separadores_inferem_a_notacao_pelos_valores(
    tmp_path: Path, texto: str, esperado: float
) -> None:
    assert ler_csv(escrever(tmp_path, "d.csv", texto)).valores("b") == (esperado,)


def test_csv_em_windows_1252_e_lido(tmp_path: Path) -> None:
    caminho = escrever(tmp_path, "d.csv", "Região;Custo\nSão Paulo;3\n", "cp1252")
    assert ler_csv(caminho).valores("Região") == ("São Paulo",)


def test_csv_com_bom_nao_contamina_o_cabecalho(tmp_path: Path) -> None:
    caminho = escrever(tmp_path, "d.csv", "﻿Produto;Custo\nA;1\n")
    assert ler_csv(caminho).colunas == ("Produto", "Custo")


def test_linhas_vazias_sao_omitidas_e_celulas_vazias_viram_none(tmp_path: Path) -> None:
    caminho = escrever(tmp_path, "d.csv", "a;b\n1;\n;;\n\n2;3\n")
    tabela = ler_csv(caminho)
    assert tabela.linhas == ((1, None), (2, 3))


def test_valor_que_exigiria_transformacao_continua_texto(tmp_path: Path) -> None:
    caminho = escrever(tmp_path, "d.csv", "item;preco;margem\nA;R$ 10,00;12%\n")
    tabela = ler_csv(caminho)
    assert tabela.tipos[1:] == (TipoColuna.TEXTO, TipoColuna.TEXTO)
    assert tabela.valores("preco") == ("R$ 10,00",)


def test_codigo_com_zero_a_esquerda_continua_texto(tmp_path: Path) -> None:
    caminho = escrever(tmp_path, "d.csv", "codigo;qtd\n007;1\n120;2\n")
    tabela = ler_csv(caminho)
    assert tabela.tipo("codigo") is TipoColuna.TEXTO
    assert tabela.valores("codigo") == ("007", "120")


def test_zero_isolado_e_numero(tmp_path: Path) -> None:
    caminho = escrever(tmp_path, "d.csv", "a;b\nx;0\ny;0,5\n")
    assert ler_csv(caminho).valores("b") == (0.0, 0.5)


def test_datas_e_booleanos_sao_reconhecidos(tmp_path: Path) -> None:
    caminho = escrever(
        tmp_path, "d.csv", "dia;iso;ativo\n25/09/2026;2026-09-25;Sim\n01/10/2026;2026-10-01;não\n"
    )
    tabela = ler_csv(caminho)
    assert tabela.tipos == (TipoColuna.DATA, TipoColuna.DATA, TipoColuna.BOOLEANO)
    assert tabela.valores("dia") == (date(2026, 9, 25), date(2026, 10, 1))
    assert tabela.valores("ativo") == (True, False)


def test_data_invalida_continua_texto(tmp_path: Path) -> None:
    caminho = escrever(tmp_path, "d.csv", "dia;x\n31/02/2026;1\n")
    assert ler_csv(caminho).tipo("dia") is TipoColuna.TEXTO


def test_coluna_totalmente_vazia_e_texto(tmp_path: Path) -> None:
    caminho = escrever(tmp_path, "d.csv", "a;b\n1;\n2;\n")
    assert ler_csv(caminho).tipo("b") is TipoColuna.TEXTO


@pytest.mark.parametrize(
    ("texto", "mensagem"),
    [
        ("", "vazia"),
        ("a;;b\n1;2;3\n", "sem nome"),
        ("a;a\n1;2\n", "nome repetido: a"),
        ("a;b\n1;2\n3;4;5\n", "linha 3"),
    ],
)
def test_csv_malformado_e_rejeitado(tmp_path: Path, texto: str, mensagem: str) -> None:
    with pytest.raises(ErroDados, match=mensagem):
        ler_csv(escrever(tmp_path, "d.csv", texto))


def test_coluna_inexistente_indica_tratamento_de_faltante(tmp_path: Path) -> None:
    tabela = ler_csv(escrever(tmp_path, "d.csv", "a;b\n1;2\n"))
    with pytest.raises(ErroDados, match="não tem a coluna 'c'") as erro:
        tabela.valores("c")
    assert erro.value.motivo is MotivoTratamento.FALTANTE


def salvar_planilha(caminho: Path, abas: dict[str, list[list[object]]]) -> Path:
    livro = Workbook()
    livro.remove(livro.active)  # type: ignore[arg-type]
    for titulo, linhas in abas.items():
        aba = livro.create_sheet(titulo)
        for linha in linhas:
            aba.append(linha)
    livro.save(caminho)
    return caminho


def test_xlsx_com_uma_aba_leva_o_nome_do_arquivo(tmp_path: Path) -> None:
    caminho = salvar_planilha(
        tmp_path / "custos.xlsx",
        {"Plan1": [["Rota", "Custo", "Ativa", "Início"], ["A-B", 10, True, datetime(2026, 1, 5)]]},
    )
    (tabela,) = ler_xlsx(caminho)
    assert tabela.nome == "custos.xlsx"
    assert tabela.tipos == (
        TipoColuna.TEXTO,
        TipoColuna.INTEIRO,
        TipoColuna.BOOLEANO,
        TipoColuna.DATA,
    )


def test_xlsx_com_varias_abas_nomeia_cada_fonte_pela_aba(tmp_path: Path) -> None:
    caminho = salvar_planilha(
        tmp_path / "dados.xlsx",
        {"Custos": [["x", "y"], [1, 2.5]], "Vazia": [], "Demanda": [["z"], ["a"]]},
    )
    nomes = [t.nome for t in ler_xlsx(caminho)]
    assert nomes == ["dados.xlsx[Custos]", "dados.xlsx[Demanda]"]


def test_xlsx_mistura_de_tipos_vira_texto(tmp_path: Path) -> None:
    caminho = salvar_planilha(tmp_path / "d.xlsx", {"P": [["cod"], [101], ["A7"], [None]]})
    (tabela,) = ler_xlsx(caminho)
    assert tabela.tipo("cod") is TipoColuna.TEXTO
    assert tabela.valores("cod") == ("101", "A7")


def test_xlsx_numero_com_e_sem_decimal_e_decimal(tmp_path: Path) -> None:
    caminho = salvar_planilha(tmp_path / "d.xlsx", {"P": [["v"], [1], [2.5]]})
    (tabela,) = ler_xlsx(caminho)
    assert tabela.tipo("v") is TipoColuna.DECIMAL


def test_xlsx_com_valor_fora_das_colunas_nomeadas_e_rejeitado(tmp_path: Path) -> None:
    caminho = salvar_planilha(tmp_path / "d.xlsx", {"P": [["a", None], [1, 2]]})
    with pytest.raises(ErroDados, match="fora das colunas"):
        ler_xlsx(caminho)


def test_xlsx_sem_dados_e_rejeitado(tmp_path: Path) -> None:
    caminho = salvar_planilha(tmp_path / "d.xlsx", {"P": []})
    with pytest.raises(ErroDados, match="vazia"):
        ler_xlsx(caminho)


@pytest.mark.parametrize(
    ("celula", "texto"),
    [
        (None, ""),
        (True, "sim"),
        (False, "não"),
        (3.0, "3"),
        (3.5, "3.5"),
        (7, "7"),
        (datetime(2026, 9, 25), "2026-09-25"),
        (datetime(2026, 9, 25, 8, 30), "2026-09-25T08:30:00"),
        (date(2026, 9, 25), "2026-09-25"),
        ("P1", "P1"),
    ],
)
def test_texto_celula(celula: object, texto: str) -> None:
    assert texto_celula(celula) == texto  # type: ignore[arg-type]


@given(centavos=st.integers(min_value=-(10**12), max_value=10**12))
def test_numero_em_notacao_brasileira_faz_ida_e_volta(
    tmp_path_factory: pytest.TempPathFactory, centavos: int
) -> None:
    reais, resto = divmod(abs(centavos), 100)
    sinal = "-" if centavos < 0 else ""
    texto = f"{sinal}{reais:,}".replace(",", ".") + f",{resto:02d}"
    caminho = escrever(tmp_path_factory.mktemp("csv"), "d.csv", f"a;v\nx;{texto}\n")
    (valor,) = ler_csv(caminho).valores("v")
    assert valor == pytest.approx(centavos / 100)
