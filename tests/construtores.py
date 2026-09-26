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
from po_multiagente.modelo import (
    ModeloCompilado,
    ModeloInstanciado,
    ObjetivoInstanciado,
    Relacao,
    RestricaoInstanciada,
    VariavelInstanciada,
    compilar,
    instanciar,
)

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


# Modelo neutro (já instanciado), para testar solver e sinais sem compilar.


def var(
    nome: str,
    tipo: TipoVariavel = TipoVariavel.CONTINUA,
    inferior: float | None = 0.0,
    superior: float | None = None,
) -> VariavelInstanciada:
    return VariavelInstanciada(nome, nome.split("[", 1)[0], (), tipo, inferior, superior)


def res(
    nome: str, termos: Mapping[str, float], relacao: Relacao, lado: float
) -> RestricaoInstanciada:
    return RestricaoInstanciada(
        nome, nome.split("[", 1)[0], (), tuple(termos.items()), relacao, lado
    )


def neutro(
    sentido: Sentido,
    objetivo: Mapping[str, float],
    variaveis: Sequence[VariavelInstanciada],
    restricoes: Sequence[RestricaoInstanciada],
    constante: float = 0.0,
) -> ModeloInstanciado:
    return ModeloInstanciado(
        variaveis=tuple(variaveis),
        restricoes=tuple(restricoes),
        objetivo=ObjetivoInstanciado(sentido, tuple(objetivo.items()), constante),
    )


# Wyndor Glass (Hillier e Lieberman): ótimo único e não degenerado, x = 2, y = 6, z = 36.
WYNDOR = neutro(
    Sentido.MAXIMIZAR,
    {"x": 3.0, "y": 5.0},
    [var("x"), var("y")],
    [
        res("planta1", {"x": 1.0}, Relacao.MENOR_OU_IGUAL, 4.0),
        res("planta2", {"y": 2.0}, Relacao.MENOR_OU_IGUAL, 12.0),
        res("planta3", {"x": 3.0, "y": 2.0}, Relacao.MENOR_OU_IGUAL, 18.0),
    ],
)
