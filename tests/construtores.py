"""Construtores compactos de modelos para os testes."""

from collections.abc import Mapping, Sequence

from po_multiagente.dominio import (
    Conjunto,
    ModeloIR,
    Objetivo,
    Origem,
    ParametroModelo,
    Quantificador,
    Restricao,
    Sentido,
    TipoVariavel,
    Variavel,
)
from po_multiagente.modelo import ModeloCompilado, ModeloInstanciado, compilar, instanciar

Chave = tuple[str, ...]


def conjunto(id_: str) -> Conjunto:
    return Conjunto(id=id_, descricao=id_, origem=Origem(arquivo="dados.csv", coluna=id_))


def variavel(
    id_: str,
    *indices: str,
    tipo: TipoVariavel = TipoVariavel.CONTINUA,
    unidade: str = "un",
    inferior: float | None = 0.0,
    superior: float | None = None,
) -> Variavel:
    return Variavel(
        id=id_,
        descricao=id_,
        unidade=unidade,
        tipo=tipo,
        indices=indices,
        limite_inferior=inferior,
        limite_superior=superior,
    )


def restricao(
    id_: str, expressao: str, *para_todo: tuple[str, str], requisitos: tuple[str, ...] = ("REQ1",)
) -> Restricao:
    return Restricao(
        id=id_,
        descricao=id_,
        requisitos=requisitos,
        para_todo=tuple(Quantificador(indice=i, conjunto=c) for i, c in para_todo),
        expressao=expressao,
    )


def modelo(
    objetivo: str,
    *restricoes: Restricao,
    sentido: Sentido = Sentido.MAXIMIZAR,
    conjuntos: tuple[str, ...] = (),
    parametros: dict[str, tuple[str, ...]] | None = None,
    variaveis: tuple[Variavel, ...] = (),
    requisitos_objetivo: tuple[str, ...] = (),
) -> ModeloIR:
    return ModeloIR(
        conjuntos=tuple(conjunto(c) for c in conjuntos),
        parametros=tuple(ParametroModelo(id=p, indices=i) for p, i in (parametros or {}).items()),
        variaveis=variaveis or (variavel("x"),),
        objetivo=Objetivo(
            sentido=sentido,
            expressao=objetivo,
            descricao="objetivo",
            requisitos=requisitos_objetivo,
        ),
        restricoes=restricoes,
    )


def instanciado(
    ir: ModeloIR,
    conjuntos: Mapping[str, Sequence[str]] | None = None,
    parametros: Mapping[str, Mapping[Chave, float]] | None = None,
) -> ModeloInstanciado:
    compilado: ModeloCompilado = compilar(ir)
    return instanciar(compilado, conjuntos or {}, parametros or {})
