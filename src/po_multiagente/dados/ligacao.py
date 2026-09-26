"""Ligação dos valores das fontes aos conjuntos e parâmetros do modelo.

O modelo de linguagem só aponta de onde vem cada valor (arquivo, coluna e
chaves); os números são lidos aqui, pelo código. A ligação não corrige o
dado: chave repetida, valor faltante ou coluna não numérica viram erro com o
motivo do tratamento que o usuário precisa fazer.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from po_multiagente.dados.erros import ErroDados, ErroLigacao
from po_multiagente.dados.fontes import Fontes
from po_multiagente.dados.leitura import Celula, Tabela, celula_igual, texto_celula
from po_multiagente.dominio import Especificacao, Filtro, ModeloIR, MotivoTratamento

Chave = tuple[str, ...]
"""Membros dos conjuntos que indexam um valor, na ordem dos índices."""


@dataclass(frozen=True)
class DadosLigados:
    """Membros de cada conjunto e valores de cada parâmetro de um modelo."""

    conjuntos: Mapping[str, tuple[str, ...]]
    parametros: Mapping[str, Mapping[Chave, float]]


def membros(tabela: Tabela, coluna: str, filtros: Sequence[Filtro] = ()) -> tuple[str, ...]:
    """Valores distintos da coluna, na ordem em que aparecem.

    Raises:
        ErroDados: Se a coluna não existir ou tiver célula vazia.
    """
    vistos: dict[str, None] = {}
    selecionadas = _linhas_filtradas(tabela, filtros)
    for linha, valor in enumerate(tabela.valores(coluna), start=2):
        if linha - 2 not in selecionadas:
            continue
        if valor is None:
            raise _faltante(tabela, coluna, linha)
        vistos.setdefault(texto_celula(valor), None)
    return tuple(vistos)


def valores(
    tabela: Tabela, coluna: str, chaves: Sequence[str], filtros: Sequence[Filtro] = ()
) -> dict[Chave, float]:
    """Valores numéricos da coluna, indexados pelas colunas-chave.

    Sem chaves, o parâmetro é escalar e a coluna, nas linhas selecionadas
    pelos filtros, deve ter exatamente um valor preenchido. A coluna só
    precisa ser numérica nas linhas selecionadas: numa tabela "longa", as
    demais linhas podem ter texto.

    Raises:
        ErroDados: Se uma coluna não existir, se a coluna de valores não for
            numérica, se houver célula vazia ou chave repetida.
    """
    selecionadas = _linhas_filtradas(tabela, filtros)
    numeros = tuple(v if i in selecionadas else None for i, v in enumerate(tabela.valores(coluna)))
    if not all(_eh_numero(v) for v in numeros if v is not None):
        exemplo = next((v for v in numeros if v is not None and not _eh_numero(v)), None)
        raise ErroDados(
            f"A coluna {coluna!r} de {tabela.nome!r} não é numérica (ex.: {exemplo!r})",
            arquivo=tabela.nome,
            coluna=coluna,
            motivo=MotivoTratamento.UNIDADE,
        )
    if not chaves:
        return {(): _escalar(tabela, coluna, numeros)}
    colunas_chave = [tabela.valores(c) for c in chaves]
    resultado: dict[Chave, float] = {}
    for posicao, numero in enumerate(numeros):
        if posicao not in selecionadas:
            continue
        linha = posicao + 2
        celulas = [valores_chave[posicao] for valores_chave in colunas_chave]
        for nome, celula in zip(chaves, celulas, strict=True):
            if celula is None:
                raise _faltante(tabela, nome, linha)
        if numero is None:
            raise _faltante(tabela, coluna, linha)
        chave = tuple(texto_celula(c) for c in celulas)
        if chave in resultado:
            raise ErroDados(
                f"A chave ({', '.join(chave)}) aparece em mais de uma linha de "
                f"{tabela.nome!r}; {coluna!r} precisa de um valor por chave",
                arquivo=tabela.nome,
                coluna=coluna,
                motivo=MotivoTratamento.GRANULARIDADE,
            )
        resultado[chave] = _numero(numero)
    return resultado


def ligar(modelo: ModeloIR, especificacao: Especificacao, fontes: Fontes) -> DadosLigados:
    """Lê os membros dos conjuntos e os valores dos parâmetros do modelo.

    A origem de cada conjunto está no próprio modelo; a de cada parâmetro,
    no quadro de especificação. Os índices do parâmetro correspondem, em
    ordem, às chaves da origem.

    Raises:
        ErroLigacao: Com todas as falhas encontradas, e não só a primeira.
    """
    erros: list[ErroDados] = []
    conjuntos: dict[str, tuple[str, ...]] = {}
    for conjunto in modelo.conjuntos:
        try:
            tabela = fontes.tabela(conjunto.origem.arquivo)
            conjuntos[conjunto.id] = membros(
                tabela, conjunto.origem.coluna, conjunto.origem.filtros
            )
        except ErroDados as erro:
            erros.append(erro)
    origens = {p.id: p.origem for p in especificacao.parametros}
    parametros: dict[str, dict[Chave, float]] = {}
    for parametro in modelo.parametros:
        origem = origens.get(parametro.id)
        if origem is None:
            erros.append(
                ErroDados(
                    f"O parâmetro {parametro.id!r} não tem origem no quadro de especificação",
                    arquivo=None,
                )
            )
            continue
        if len(origem.chaves) != len(parametro.indices):
            erros.append(
                ErroDados(
                    f"O parâmetro {parametro.id!r} tem {len(parametro.indices)} índice(s), "
                    f"mas a origem declara {len(origem.chaves)} chave(s)",
                    arquivo=origem.arquivo,
                    coluna=origem.coluna,
                )
            )
            continue
        try:
            tabela = fontes.tabela(origem.arquivo)
            parametros[parametro.id] = valores(tabela, origem.coluna, origem.chaves, origem.filtros)
        except ErroDados as erro:
            erros.append(erro)
    if erros:
        raise ErroLigacao(tuple(erros))
    return DadosLigados(conjuntos=conjuntos, parametros=parametros)


def _escalar(tabela: Tabela, coluna: str, numeros: Sequence[Celula]) -> float:
    preenchidos = [n for n in numeros if n is not None]
    if not preenchidos:
        raise ErroDados(
            f"A coluna {coluna!r} de {tabela.nome!r} não tem valor nas linhas selecionadas",
            arquivo=tabela.nome,
            coluna=coluna,
            motivo=MotivoTratamento.FALTANTE,
        )
    if len(preenchidos) > 1:
        raise ErroDados(
            f"A coluna {coluna!r} de {tabela.nome!r} tem {len(preenchidos)} valores, mas o "
            "parâmetro é um valor único",
            arquivo=tabela.nome,
            coluna=coluna,
            motivo=MotivoTratamento.GRANULARIDADE,
        )
    return _numero(preenchidos[0])


def _faltante(tabela: Tabela, coluna: str, linha: int) -> ErroDados:
    return ErroDados(
        f"A coluna {coluna!r} de {tabela.nome!r} tem valor faltante na linha {linha}",
        arquivo=tabela.nome,
        coluna=coluna,
        motivo=MotivoTratamento.FALTANTE,
    )


def _linhas_filtradas(tabela: Tabela, filtros: Sequence[Filtro]) -> frozenset[int]:
    """Posições (a partir de 0) das linhas que passam em todos os filtros.

    Raises:
        ErroDados: Se um filtro não selecionar nenhuma linha.
    """
    selecionadas = frozenset(range(len(tabela.linhas)))
    for filtro in filtros:
        celulas = tabela.valores(filtro.coluna)
        selecionadas = frozenset(i for i in selecionadas if celula_igual(celulas[i], filtro.valor))
        if not selecionadas:
            raise ErroDados(
                f"Nenhuma linha de {tabela.nome!r} tem {filtro.coluna!r} igual a {filtro.valor!r}",
                arquivo=tabela.nome,
                coluna=filtro.coluna,
                motivo=MotivoTratamento.IDENTIFICADOR,
            )
    return selecionadas


def _eh_numero(celula: Celula) -> bool:
    return isinstance(celula, int | float) and not isinstance(celula, bool)


def _numero(celula: Celula) -> float:
    # Garantido pelo tipo da coluna (inteiro ou decimal), checado antes.
    assert isinstance(celula, int | float)
    assert not isinstance(celula, bool)
    return float(celula)
