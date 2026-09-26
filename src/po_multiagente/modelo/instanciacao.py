"""Segundo estágio do compilador: instanciação do modelo neutro.

Liga o modelo compilado aos membros dos conjuntos e aos valores dos
parâmetros e expande os somatórios e os ``para_todo`` em variáveis e
restrições individuais, com coeficientes numéricos. O resultado não depende
de nenhum solver: cada adaptador (ADR-006) traduz esse modelo neutro.

A ordem das variáveis e das restrições é determinística — declaração no
modelo e, dentro dela, ordem dos membros nos dados —, pois a ordem afeta o
caminho do solver e, portanto, a reprodutibilidade.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import product

from po_multiagente.dominio import Sentido, TipoVariavel
from po_multiagente.modelo.arvore import (
    Binaria,
    Comparacao,
    Expressao,
    IndiceLivre,
    Membro,
    Negacao,
    Numero,
    Operador,
    Referencia,
    Relacao,
    Somatorio,
    texto,
)
from po_multiagente.modelo.compilacao import ModeloCompilado
from po_multiagente.modelo.erros import OBJETIVO, ErroInstanciacao, ErroModelo

Termo = tuple[str, float]
"""Nome da variável instanciada e seu coeficiente."""


@dataclass(frozen=True)
class VariavelInstanciada:
    """Uma variável do solver, como ``x[Mesa]``."""

    nome: str
    variavel_id: str
    indices: tuple[str, ...]
    tipo: TipoVariavel
    limite_inferior: float | None
    limite_superior: float | None


@dataclass(frozen=True)
class RestricaoInstanciada:
    """Uma restrição do solver: ``soma(coeficiente · variável) relação lado_direito``.

    Attributes:
        nome: Identificador da família com os membros, como ``demanda[Mesa]``.
        restricao_id: Família de origem, que aponta para os requisitos.
        termos: Coeficientes não nulos, na ordem em que aparecem.
    """

    nome: str
    restricao_id: str
    indices: tuple[str, ...]
    termos: tuple[Termo, ...]
    relacao: Relacao
    lado_direito: float


@dataclass(frozen=True)
class ObjetivoInstanciado:
    """Função objetivo instanciada, com a parte constante à parte."""

    sentido: Sentido
    termos: tuple[Termo, ...]
    constante: float


@dataclass(frozen=True)
class ModeloInstanciado:
    """Modelo neutro, pronto para qualquer adaptador de solver."""

    variaveis: tuple[VariavelInstanciada, ...]
    restricoes: tuple[RestricaoInstanciada, ...]
    objetivo: ObjetivoInstanciado

    @property
    def inteiro(self) -> bool:
        """Indica se há variável inteira ou binária (PLIM)."""
        return any(v.tipo is not TipoVariavel.CONTINUA for v in self.variaveis)

    def sem_restricoes(self, familias: set[str]) -> "ModeloInstanciado":
        """Cópia do modelo sem as famílias de restrições indicadas."""
        return ModeloInstanciado(
            variaveis=self.variaveis,
            restricoes=tuple(r for r in self.restricoes if r.restricao_id not in familias),
            objetivo=self.objetivo,
        )


def nome_instancia(base: str, indices: Sequence[str]) -> str:
    """Nome de uma instância: ``x`` sem índices, ``x[Mesa,Março]`` com índices."""
    return f"{base}[{','.join(indices)}]" if indices else base


def instanciar(
    compilado: ModeloCompilado,
    conjuntos: Mapping[str, Sequence[str]],
    parametros: Mapping[str, Mapping[tuple[str, ...], float]],
) -> ModeloInstanciado:
    """Expande o modelo compilado com os dados ligados.

    Args:
        compilado: Modelo analisado e checado.
        conjuntos: Membros de cada conjunto, na ordem dos dados.
        parametros: Valores de cada parâmetro, pela chave de membros.

    Raises:
        ErroInstanciacao: Com todos os valores ou membros que faltam.
    """
    avaliador = _Avaliador(compilado, conjuntos, parametros)
    variaveis = avaliador.variaveis()
    restricoes = [
        instancia
        for restricao in compilado.restricoes
        for instancia in avaliador.restricao(
            restricao.restricao.id,
            [(q.indice, q.conjunto) for q in restricao.restricao.para_todo],
            restricao.comparacao,
        )
    ]
    objetivo = avaliador.objetivo()
    if avaliador.erros:
        raise ErroInstanciacao(avaliador.erros)
    return ModeloInstanciado(variaveis=variaveis, restricoes=tuple(restricoes), objetivo=objetivo)


@dataclass
class _Linear:
    """Expressão linear em construção: coeficientes por variável e constante."""

    coeficientes: dict[str, float] = field(default_factory=dict)
    constante: float = 0.0

    def mais(self, outra: "_Linear", fator: float = 1.0) -> "_Linear":
        return _Linear(dict(self.coeficientes), self.constante).acumular(outra, fator)

    def acumular(self, outra: "_Linear", fator: float = 1.0) -> "_Linear":
        """Soma ``fator · outra`` a esta expressão, sem copiar (somatórios grandes)."""
        for nome, valor in outra.coeficientes.items():
            self.coeficientes[nome] = self.coeficientes.get(nome, 0.0) + fator * valor
        self.constante += fator * outra.constante
        return self

    def vezes(self, fator: float) -> "_Linear":
        return _Linear({n: fator * v for n, v in self.coeficientes.items()}, fator * self.constante)

    @property
    def constante_pura(self) -> bool:
        return not any(self.coeficientes.values())

    def termos(self) -> tuple[Termo, ...]:
        return tuple((n, v) for n, v in self.coeficientes.items() if v != 0.0)


class _Avaliador:
    """Avalia expressões com índices fixados, acumulando erros localizados."""

    def __init__(
        self,
        compilado: ModeloCompilado,
        conjuntos: Mapping[str, Sequence[str]],
        parametros: Mapping[str, Mapping[tuple[str, ...], float]],
    ) -> None:
        self._compilado = compilado
        self._parametros = parametros
        self._assinaturas = {p.id: p.indices for p in compilado.ir.parametros} | {
            v.id: v.indices for v in compilado.ir.variaveis
        }
        self._variaveis = {v.id for v in compilado.ir.variaveis}
        self.erros: list[ErroModelo] = []
        self._elemento = OBJETIVO
        self._membros: dict[str, tuple[str, ...]] = {}
        self._conjuntos_membros: dict[str, frozenset[str]] = {}
        for conjunto in compilado.ir.conjuntos:
            if conjunto.id not in conjuntos:
                self.erros.append(ErroModelo(conjunto.id, "o conjunto não tem membros ligados"))
                self._membros[conjunto.id] = ()
            else:
                self._membros[conjunto.id] = tuple(conjuntos[conjunto.id])
            self._conjuntos_membros[conjunto.id] = frozenset(self._membros[conjunto.id])

    def variaveis(self) -> tuple[VariavelInstanciada, ...]:
        instancias = []
        for variavel in self._compilado.ir.variaveis:
            binaria = variavel.tipo is TipoVariavel.BINARIA
            for chave in product(*(self._membros[c] for c in variavel.indices)):
                instancias.append(
                    VariavelInstanciada(
                        nome=nome_instancia(variavel.id, chave),
                        variavel_id=variavel.id,
                        indices=chave,
                        tipo=variavel.tipo,
                        limite_inferior=0.0 if binaria else variavel.limite_inferior,
                        limite_superior=1.0 if binaria else variavel.limite_superior,
                    )
                )
        nomes = [v.nome for v in instancias]
        for nome in sorted({n for n in nomes if nomes.count(n) > 1}):
            self.erros.append(
                ErroModelo(
                    nome,
                    "duas instâncias de variável teriam o mesmo nome; membros "
                    "de conjunto não podem conter vírgula",
                )
            )
        return tuple(instancias)

    def objetivo(self) -> ObjetivoInstanciado:
        self._elemento = OBJETIVO
        linear = self._avaliar(self._compilado.objetivo, {})
        return ObjetivoInstanciado(
            sentido=self._compilado.ir.objetivo.sentido,
            termos=linear.termos(),
            constante=linear.constante,
        )

    def restricao(
        self,
        restricao_id: str,
        para_todo: list[tuple[str, str]],
        comparacao: Comparacao,
    ) -> list[RestricaoInstanciada]:
        self._elemento = restricao_id
        instancias = []
        indices = [indice for indice, _ in para_todo]
        for chave in product(*(self._membros[c] for _, c in para_todo)):
            ambiente = dict(zip(indices, chave, strict=True))
            diferenca = self._avaliar(comparacao.esquerda, ambiente).mais(
                self._avaliar(comparacao.direita, ambiente), fator=-1.0
            )
            instancias.append(
                RestricaoInstanciada(
                    nome=nome_instancia(restricao_id, chave),
                    restricao_id=restricao_id,
                    indices=chave,
                    termos=diferenca.termos(),
                    relacao=comparacao.relacao,
                    lado_direito=-diferenca.constante + 0.0,
                )
            )
        return instancias

    def _avaliar(self, expressao: Expressao, ambiente: dict[str, str]) -> _Linear:
        match expressao:
            case Numero(valor):
                return _Linear(constante=valor)
            case Referencia():
                return self._referencia(expressao, ambiente)
            case Somatorio(corpo, geradores):
                total = _Linear()
                nomes = [g.indice for g in geradores]
                for chave in product(*(self._membros[g.conjunto] for g in geradores)):
                    interno = ambiente | dict(zip(nomes, chave, strict=True))
                    total.acumular(self._avaliar(corpo, interno))
                return total
            case Negacao(operando):
                return self._avaliar(operando, ambiente).vezes(-1.0)
            case Binaria():
                return self._binaria(expressao, ambiente)

    def _binaria(self, binaria: Binaria, ambiente: dict[str, str]) -> _Linear:
        a = self._avaliar(binaria.esquerda, ambiente)
        b = self._avaliar(binaria.direita, ambiente)
        match binaria.operador:
            case Operador.SOMA:
                return a.mais(b)
            case Operador.SUBTRACAO:
                return a.mais(b, fator=-1.0)
            case Operador.PRODUTO:
                # A compilação garante que um dos fatores é constante.
                return b.vezes(a.constante) if a.constante_pura else a.vezes(b.constante)
            case Operador.DIVISAO:
                if b.constante == 0.0:
                    self._erro(f"{texto(binaria)!r} divide por zero com os dados informados")
                    return a
                return a.vezes(1.0 / b.constante)

    def _referencia(self, referencia: Referencia, ambiente: dict[str, str]) -> _Linear:
        conjuntos = self._assinaturas[referencia.nome]
        chave = []
        for indice, conjunto in zip(referencia.indices, conjuntos, strict=True):
            if isinstance(indice, IndiceLivre):
                chave.append(ambiente[indice.nome])
                continue
            assert isinstance(indice, Membro)
            if indice.texto not in self._conjuntos_membros[conjunto]:
                self._erro(f"{texto(referencia)!r}: {indice.texto!r} não é membro de {conjunto}")
                return _Linear()
            chave.append(indice.texto)
        membros = tuple(chave)
        if referencia.nome in self._variaveis:
            return _Linear({nome_instancia(referencia.nome, membros): 1.0})
        valores = self._parametros.get(referencia.nome)
        if valores is None:
            self._erro(f"o parâmetro {referencia.nome!r} não tem valores ligados")
            return _Linear()
        valor = valores.get(membros)
        if valor is None:
            posicoes = ", ".join(f"{c}={m}" for c, m in zip(conjuntos, membros, strict=True))
            self._erro(f"o parâmetro {referencia.nome!r} não tem valor para ({posicoes})")
            return _Linear()
        return _Linear(constante=valor)

    def _erro(self, mensagem: str) -> None:
        self.erros.append(ErroModelo(self._elemento, mensagem))
