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
from po_multiagente.dados.leitura import Celula, Tabela, texto_celula
from po_multiagente.dominio import Especificacao, ModeloIR, MotivoTratamento, TipoColuna

Chave = tuple[str, ...]
"""Membros dos conjuntos que indexam um valor, na ordem dos índices."""

_NUMERICOS = (TipoColuna.INTEIRO, TipoColuna.DECIMAL)


@dataclass(frozen=True)
class DadosLigados:
    """Membros de cada conjunto e valores de cada parâmetro de um modelo."""

    conjuntos: Mapping[str, tuple[str, ...]]
    parametros: Mapping[str, Mapping[Chave, float]]


def membros(tabela: Tabela, coluna: str) -> tuple[str, ...]:
    """Valores distintos da coluna, na ordem em que aparecem.

    Raises:
        ErroDados: Se a coluna não existir ou tiver célula vazia.
    """
    vistos: dict[str, None] = {}
    for linha, valor in enumerate(tabela.valores(coluna), start=2):
        if valor is None:
            raise _faltante(tabela, coluna, linha)
        vistos.setdefault(texto_celula(valor), None)
    return tuple(vistos)


def valores(tabela: Tabela, coluna: str, chaves: Sequence[str]) -> dict[Chave, float]:
    """Valores numéricos da coluna, indexados pelas colunas-chave.

    Sem chaves, o parâmetro é escalar e a coluna deve ter exatamente um
    valor preenchido.

    Raises:
        ErroDados: Se uma coluna não existir, se a coluna de valores não for
            numérica, se houver célula vazia ou chave repetida.
    """
    if tabela.tipo(coluna) not in _NUMERICOS:
        exemplo = next((v for v in tabela.valores(coluna) if v is not None), None)
        raise ErroDados(
            f"A coluna {coluna!r} de {tabela.nome!r} não é numérica (ex.: {exemplo!r})",
            arquivo=tabela.nome,
            coluna=coluna,
            motivo=MotivoTratamento.UNIDADE,
        )
    numeros = tabela.valores(coluna)
    if not chaves:
        return {(): _escalar(tabela, coluna, numeros)}
    colunas_chave = [tabela.valores(c) for c in chaves]
    resultado: dict[Chave, float] = {}
    for posicao, numero in enumerate(numeros):
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
            conjuntos[conjunto.id] = membros(tabela, conjunto.origem.coluna)
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
            parametros[parametro.id] = valores(tabela, origem.coluna, origem.chaves)
        except ErroDados as erro:
            erros.append(erro)
    if erros:
        raise ErroLigacao(tuple(erros))
    return DadosLigados(conjuntos=conjuntos, parametros=parametros)


def _escalar(tabela: Tabela, coluna: str, numeros: Sequence[Celula]) -> float:
    # A coluna é numérica, logo tem ao menos um valor preenchido.
    preenchidos = [n for n in numeros if n is not None]
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


def _numero(celula: Celula) -> float:
    # Garantido pelo tipo da coluna (inteiro ou decimal), checado antes.
    assert isinstance(celula, int | float)
    assert not isinstance(celula, bool)
    return float(celula)
