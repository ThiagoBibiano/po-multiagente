from po_multiagente.dominio import ModeloIR, Sentido, TipoVariavel
from po_multiagente.modelo import analisar_comparacao, analisar_expressao, compilar, para_latex
from po_multiagente.modelo.latex import expressao_latex
from tests.construtores import modelo, restricao, variavel


def test_formulacao_do_piloto(modelo: ModeloIR) -> None:
    assert para_latex(compilar(modelo)) == (
        "\\begin{aligned}\n"
        r"\max \quad & \sum_{p \in \mathrm{PRODUTOS}} \mathit{lucro}_{p}\, x_{p} && \\"
        "\n"
        r"\text{sujeito a} \quad & \sum_{p \in \mathrm{PRODUTOS}} \mathit{horas}_{p}\, x_{p}"
        r" \le 200 && \text{(capacidade)} \\"
        "\n"
        r"& x_{i} \ge 0 && \forall\, i \in \mathrm{PRODUTOS} \\"
        "\n"
        "\\end{aligned}"
    )


def test_para_todo_e_dominios() -> None:
    ir = modelo(
        "sum(y[i, j] for i in A for j in B) + z + w",
        restricao("liga", "y[i, j] <= z", ("i", "A"), ("j", "B")),
        sentido=Sentido.MINIMIZAR,
        conjuntos=("A", "B"),
        variaveis=(
            variavel("y", "A", "B", tipo=TipoVariavel.BINARIA),
            variavel("z", tipo=TipoVariavel.INTEIRA, superior=10.0),
            variavel("w", inferior=None, superior=None),
        ),
    )
    latex = para_latex(compilar(ir))
    assert r"\min \quad" in latex
    assert r"\forall\, i \in \mathrm{A}, j \in \mathrm{B} \quad \text{(liga)}" in latex
    assert r"y_{i,j} \in \{0, 1\} && \forall\, i \in \mathrm{A}, j \in \mathrm{B}" in latex
    assert r"0 \le z \le 10,\ z \in \mathbb{Z}" in latex
    assert r"w \in \mathbb{R}" in latex


def test_limite_so_superior() -> None:
    ir = modelo("x", variaveis=(variavel("x", inferior=None, superior=2.5),))
    assert r"x \le 2{,}5" in para_latex(compilar(ir))


def test_expressoes() -> None:
    assert expressao_latex(analisar_expressao("a - (b + c)")) == r"a - \left( b + c \right)"
    assert expressao_latex(analisar_expressao("-(a + b) * 2")) == (r"-\left( a + b \right) \cdot 2")
    assert expressao_latex(analisar_expressao("x['Loja_A'] / 4")) == r"\frac{x_{\text{Loja\_A}}}{4}"
    assert expressao_latex(analisar_expressao("2 * sum(c[k] for k in K)")) == (
        r"2\, \sum_{k \in \mathrm{K}} c_{k}"
    )
    assert expressao_latex(analisar_expressao("-sum(c[k] + 1 for k in K)")) == (
        r"-\sum_{k \in \mathrm{K}} \left( c_{k} + 1 \right)"
    )
    assert expressao_latex(analisar_comparacao("x == 1.5")) == r"x = 1{,}5"
    assert expressao_latex(analisar_comparacao("x >= 0")) == r"x \ge 0"


def test_caracteres_especiais_sao_escapados() -> None:
    assert expressao_latex(analisar_expressao("x['50% & R$ #1 ~^\\\\']")) == (
        r"x_{\text{50\% \& R\$ \#1 \textasciitilde{}\textasciicircum{}"
        r"\textbackslash{}\textbackslash{}}}"
    )
