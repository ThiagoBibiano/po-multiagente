"""Representação intermediária do modelo de otimização (ADR-002).

O Modelador descreve o modelo em forma algébrica indexada — conjuntos,
parâmetros e variáveis indexados e restrições "para todo" —, e não expandida:
o tamanho não cresce com os dados. A estrutura é validada aqui; as
expressões são texto numa mini-linguagem algébrica, interpretado e checado
pelo compilador em ``po_multiagente.modelo`` (F1). Os parâmetros apontam para
o quadro de especificação e nunca carregam números: os valores são ligados
pelo código a partir das fontes.
"""

from enum import StrEnum
from itertools import chain
from typing import Literal

from pydantic import Field, model_validator

from po_multiagente.dominio._base import (
    Identificador,
    IdRequisito,
    ObjetoDominio,
    TextoNaoVazio,
    exigir_declarados,
    exigir_unicos,
)
from po_multiagente.dominio.especificacao import Sentido
from po_multiagente.dominio.fontes import Origem


class TipoVariavel(StrEnum):
    """Domínio de uma variável de decisão."""

    CONTINUA = "continua"
    INTEIRA = "inteira"
    BINARIA = "binaria"


class Conjunto(ObjetoDominio):
    """Conjunto de índices; os membros são os valores distintos da coluna de origem.

    ``subconjunto_de`` declara que todo membro pertence a outro conjunto, como
    as farinhas de origem animal entre todas as farinhas: um índice que
    percorre o subconjunto pode ocupar a posição que espera o conjunto-pai.
    """

    id: Identificador
    descricao: TextoNaoVazio
    origem: Origem
    subconjunto_de: Identificador | None = None


class ParametroModelo(ObjetoDominio):
    """Uso de um parâmetro do quadro de especificação, com seus índices."""

    id: Identificador
    indices: tuple[Identificador, ...] = ()


class Variavel(ObjetoDominio):
    """Variável de decisão indexada.

    Os limites são opcionais; ``None`` significa ilimitada naquele lado. O
    padrão é não negativa, o caso comum em PL e PLIM. ``requisitos`` liga o
    domínio a um requisito de negócio, como "não dá para entregar fração de
    móvel", que o domínio atende sem restrição própria.
    """

    id: Identificador
    descricao: TextoNaoVazio
    unidade: TextoNaoVazio
    tipo: TipoVariavel
    indices: tuple[Identificador, ...] = ()
    limite_inferior: float | None = 0.0
    limite_superior: float | None = None
    requisitos: tuple[IdRequisito, ...] = ()

    @model_validator(mode="after")
    def _limites_coerentes(self) -> "Variavel":
        inferior, superior = self.limite_inferior, self.limite_superior
        if inferior is not None and superior is not None and inferior > superior:
            raise ValueError(f"Variável {self.id}: limite inferior maior que o superior")
        if self.tipo is TipoVariavel.BINARIA and (
            inferior not in (None, 0.0) or superior not in (None, 1.0)
        ):
            raise ValueError(f"Variável binária {self.id} não admite limites além de 0 e 1")
        return self


class Quantificador(ObjetoDominio):
    """Cláusula "para todo ``indice`` em ``conjunto``" de uma restrição."""

    indice: Identificador
    conjunto: Identificador


class Objetivo(ObjetoDominio):
    """Função objetivo."""

    sentido: Sentido
    expressao: TextoNaoVazio
    descricao: TextoNaoVazio
    requisitos: tuple[IdRequisito, ...] = ()


class Restricao(ObjetoDominio):
    """Família de restrições, com o requisito de negócio que a motivou.

    ``requisitos`` exige ao menos um identificador: uma restrição sem
    requisito é justamente o que o sinal S4 procura, e o esquema já impede
    que ela seja declarada sem vínculo.
    """

    id: Identificador
    descricao: TextoNaoVazio
    requisitos: tuple[IdRequisito, ...] = Field(min_length=1)
    para_todo: tuple[Quantificador, ...] = ()
    expressao: TextoNaoVazio

    @model_validator(mode="after")
    def _indices_unicos(self) -> "Restricao":
        exigir_unicos((q.indice for q in self.para_todo), f"Índices da restrição {self.id}")
        return self


class ModeloIR(ObjetoDominio):
    """Modelo de otimização completo na representação intermediária."""

    versao_esquema: Literal[1] = 1
    conjuntos: tuple[Conjunto, ...] = ()
    parametros: tuple[ParametroModelo, ...] = ()
    variaveis: tuple[Variavel, ...] = Field(min_length=1)
    objetivo: Objetivo
    restricoes: tuple[Restricao, ...] = ()

    @model_validator(mode="after")
    def _referencias_consistentes(self) -> "ModeloIR":
        exigir_unicos(
            chain(
                (c.id for c in self.conjuntos),
                (p.id for p in self.parametros),
                (v.id for v in self.variaveis),
                (r.id for r in self.restricoes),
            ),
            "Identificadores do modelo",
        )
        exigir_declarados(
            chain(
                (c.subconjunto_de for c in self.conjuntos if c.subconjunto_de),
                chain.from_iterable(p.indices for p in self.parametros),
                chain.from_iterable(v.indices for v in self.variaveis),
                (q.conjunto for r in self.restricoes for q in r.para_todo),
            ),
            (c.id for c in self.conjuntos),
            "Conjuntos",
        )
        _exigir_hierarquia_sem_ciclo(self.conjuntos)
        return self


def _exigir_hierarquia_sem_ciclo(conjuntos: tuple[Conjunto, ...]) -> None:
    pais = {c.id: c.subconjunto_de for c in conjuntos}
    for inicio, pai in pais.items():
        vistos, atual = {inicio}, pai
        while atual is not None:
            if atual in vistos:
                raise ValueError(f"Conjunto {inicio} é subconjunto de si mesmo")
            vistos.add(atual)
            atual = pais.get(atual)
