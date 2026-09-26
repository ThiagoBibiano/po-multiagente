from pathlib import Path

import pytest

from po_multiagente.dados import (
    ErroDados,
    ErroLigacao,
    Fontes,
    Tabela,
    ler_csv,
    ligar,
    membros,
    valores,
)
from po_multiagente.dominio import (
    Coluna,
    Especificacao,
    FonteDados,
    ModeloIR,
    MotivoTratamento,
    Origem,
    Parametro,
    Requisito,
    Sentido,
    TipoColuna,
)


def tabela(tmp_path: Path, texto: str) -> Tabela:
    caminho = tmp_path / "d.csv"
    caminho.write_text(texto, encoding="utf-8")
    return ler_csv(caminho)


def test_membros_distintos_na_ordem_de_aparicao(tmp_path: Path) -> None:
    t = tabela(tmp_path, "loja;produto\nL1;B\nL1;A\nL2;B\n")
    assert membros(t, "produto") == ("B", "A")


def test_membro_vazio_e_faltante(tmp_path: Path) -> None:
    t = tabela(tmp_path, "loja;produto\nL1;B\nL2;\n")
    with pytest.raises(ErroDados, match="linha 3") as erro:
        membros(t, "produto")
    assert erro.value.motivo is MotivoTratamento.FALTANTE


def test_membros_numericos_viram_texto(tmp_path: Path) -> None:
    t = tabela(tmp_path, "mes;v\n1;2\n2;3\n")
    assert membros(t, "mes") == ("1", "2")


def test_valores_indexados_por_duas_chaves(tmp_path: Path) -> None:
    t = tabela(tmp_path, "origem;destino;custo\nF1;C1;2,5\nF1;C2;3\nF2;C1;4\n")
    assert valores(t, "custo", ("origem", "destino")) == {
        ("F1", "C1"): 2.5,
        ("F1", "C2"): 3.0,
        ("F2", "C1"): 4.0,
    }


def test_chave_repetida_pede_tratamento_de_granularidade(tmp_path: Path) -> None:
    t = tabela(tmp_path, "produto;dia;vendas\nA;seg;3\nA;ter;4\n")
    with pytest.raises(ErroDados, match=r"chave \(A\)") as erro:
        valores(t, "vendas", ("produto",))
    assert erro.value.motivo is MotivoTratamento.GRANULARIDADE


def test_coluna_nao_numerica_pede_tratamento_de_unidade(tmp_path: Path) -> None:
    t = tabela(tmp_path, "produto;preco\nA;R$ 3,00\n")
    with pytest.raises(ErroDados, match="não é numérica") as erro:
        valores(t, "preco", ("produto",))
    assert erro.value.motivo is MotivoTratamento.UNIDADE


@pytest.mark.parametrize(
    ("texto", "linha"),
    [("produto;v\nA;\nB;2\n", "linha 2"), ("produto;v\nA;1\n;2\n", "linha 3")],
)
def test_valor_ou_chave_vazia_e_faltante(tmp_path: Path, texto: str, linha: str) -> None:
    with pytest.raises(ErroDados, match=linha) as erro:
        valores(tabela(tmp_path, texto), "v", ("produto",))
    assert erro.value.motivo is MotivoTratamento.FALTANTE


def test_parametro_escalar(tmp_path: Path) -> None:
    t = tabela(tmp_path, "recurso;disponivel\nmaquina;200\n")
    assert valores(t, "disponivel", ()) == {(): 200.0}


def test_escalar_com_mais_de_um_valor_pede_tratamento_de_granularidade(tmp_path: Path) -> None:
    t = tabela(tmp_path, "r;v\nm;1\nn;2\n")
    with pytest.raises(ErroDados, match="2 valores") as erro:
        valores(t, "v", ())
    assert erro.value.motivo is MotivoTratamento.GRANULARIDADE


def test_ligar_le_conjuntos_e_parametros(
    tmp_path: Path, modelo: ModeloIR, especificacao: Especificacao
) -> None:
    (tmp_path / "produtos.csv").write_text(
        "Produto;Lucro unitário (R$);Horas de máquina\nA;10;2\nB;15,5;3\n", encoding="utf-8"
    )
    dados = ligar(modelo, especificacao, Fontes(tmp_path))
    assert dados.conjuntos == {"PRODUTOS": ("A", "B")}
    assert dados.parametros["lucro"] == {("A",): 10.0, ("B",): 15.5}
    assert dados.parametros["horas"] == {("A",): 2.0, ("B",): 3.0}


def test_ligar_reune_todas_as_falhas(
    tmp_path: Path, modelo: ModeloIR, especificacao: Especificacao
) -> None:
    (tmp_path / "produtos.csv").write_text(
        "Produto;Lucro unitário (R$);Horas de máquina\nA;R$ 10;2\nA;15;3\n", encoding="utf-8"
    )
    with pytest.raises(ErroLigacao) as erro:
        ligar(modelo, especificacao, Fontes(tmp_path))
    motivos = [e.motivo for e in erro.value.erros]
    assert motivos == [MotivoTratamento.UNIDADE, MotivoTratamento.GRANULARIDADE]


def test_ligar_aponta_parametro_sem_origem_e_chaves_incoerentes(
    tmp_path: Path, modelo: ModeloIR, especificacao: Especificacao
) -> None:
    (tmp_path / "produtos.csv").write_text(
        "Produto;Lucro unitário (R$);Horas de máquina\nA;10;2\n", encoding="utf-8"
    )
    sem_horas = especificacao.model_copy(
        update={
            "parametros": (
                especificacao.parametros[0].model_copy(
                    update={"origem": Origem(arquivo="produtos.csv", coluna="Lucro unitário (R$)")}
                ),
            )
        }
    )
    with pytest.raises(ErroLigacao) as erro:
        ligar(modelo, sem_horas, Fontes(tmp_path))
    mensagens = [str(e) for e in erro.value.erros]
    assert mensagens == [
        "O parâmetro 'lucro' tem 1 índice(s), mas a origem declara 0 chave(s)",
        "O parâmetro 'horas' não tem origem no quadro de especificação",
    ]


def test_ligar_aponta_fonte_inexistente(tmp_path: Path, modelo: ModeloIR) -> None:
    fonte = FonteDados(
        arquivo="outra.csv", sha256="b" * 64, colunas=(Coluna(nome="x", tipo=TipoColuna.TEXTO),)
    )
    especificacao = Especificacao(
        decisao="d",
        criterio="c",
        sentido=Sentido.MAXIMIZAR,
        requisitos=(Requisito(id="REQ1", texto="r"),),
        parametros=(
            Parametro(
                id="lucro",
                descricao="l",
                unidade="R$/un",
                origem=Origem(arquivo="outra.csv", coluna="x", chaves=("y",)),
            ),
        ),
        fontes=(fonte,),
    )
    with pytest.raises(ErroLigacao) as erro:
        ligar(modelo, especificacao, Fontes(tmp_path))
    assert [str(e) for e in erro.value.erros] == [
        "Não há arquivo de dados chamado 'produtos.csv'",
        "Não há arquivo de dados chamado 'outra.csv'",
        "O parâmetro 'horas' não tem origem no quadro de especificação",
    ]
