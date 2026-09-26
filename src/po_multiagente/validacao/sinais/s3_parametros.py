"""S3 — cobertura de parâmetros.

Confronta o modelo com o quadro de especificação: todo parâmetro usado
precisa de origem declarada, com o número de chaves igual ao de índices e
colunas que existem na fonte; todo conjunto precisa apontar para uma
coluna existente.
"""

from po_multiagente.dominio import Especificacao, ModeloIR, Origem, Sinal, Verificacao


def sinal_s3_parametros(ir: ModeloIR, especificacao: Especificacao) -> Verificacao:
    """Verifica a origem declarada de cada parâmetro e de cada conjunto."""
    problemas: list[tuple[str, str]] = []
    origens = {p.id: p.origem for p in especificacao.parametros}
    colunas = {f.arquivo: {c.nome for c in f.colunas} for f in especificacao.fontes}
    for parametro in ir.parametros:
        origem = origens.get(parametro.id)
        if origem is None:
            problemas.append(
                (parametro.id, "é usado sem origem declarada no quadro de especificação")
            )
            continue
        if len(origem.chaves) != len(parametro.indices):
            problemas.append(
                (
                    parametro.id,
                    f"tem {len(parametro.indices)} índice(s) no modelo, mas a origem declara "
                    f"{len(origem.chaves)} chave(s)",
                )
            )
        problemas.extend((parametro.id, p) for p in _colunas_ausentes(origem, colunas))
    for conjunto in ir.conjuntos:
        problemas.extend((conjunto.id, p) for p in _colunas_ausentes(conjunto.origem, colunas))
    if not problemas:
        return Verificacao(
            sinal=Sinal.S3,
            aprovada=True,
            mensagem="Todo parâmetro e todo conjunto têm origem declarada nas fontes.",
        )
    return Verificacao(
        sinal=Sinal.S3,
        aprovada=False,
        mensagem="; ".join(f"{elemento}: {problema}" for elemento, problema in problemas),
        elementos=tuple(dict.fromkeys(elemento for elemento, _ in problemas)),
    )


def _colunas_ausentes(origem: Origem, colunas: dict[str, set[str]]) -> list[str]:
    if origem.arquivo not in colunas:
        return [f"aponta para {origem.arquivo!r}, que não está entre as fontes"]
    return [
        f"a coluna {coluna!r} não existe em {origem.arquivo!r}"
        for coluna in (origem.coluna, *origem.chaves)
        if coluna not in colunas[origem.arquivo]
    ]
