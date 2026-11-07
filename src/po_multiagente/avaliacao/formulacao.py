"""Acurácia da formulação por componente (cap. 3, Passo 7, critério 1).

Os dois modelos são comparados depois de instanciados com os dados, porque só
assim os elementos ficam independentes dos nomes que o modelo de linguagem
escolheu: uma variável é identificada pelos membros que a indexam
(``x[Mesa]``), e não pelo identificador ``x``.

1. **Famílias.** Cada família de variáveis produzida é associada à família de
   referência com mais membros em comum, admitindo outra ordem dos índices.
   Empates (duas famílias sobre o mesmo domínio, ou escalares) são desfeitos
   pelo número de linhas que passam a coincidir.
2. **Normalização.** Restrição de uma só variável vira limite do domínio;
   ``>=`` vira ``<=`` com o sinal trocado; cada linha é dividida pelo maior
   coeficiente em módulo e, na igualdade, também pelo sinal do primeiro
   termo; maximizar f vira minimizar −f.
3. **Componentes.** Variáveis (pelos membros), domínios (tipo e limites das
   variáveis em comum), restrições (pelo suporte e pelo sentido),
   coeficientes (das restrições pareadas) e função objetivo.
4. **Equivalência.** Uma linha sem par, ou com coeficientes diferentes,
   conta como certa quando o outro modelo a implica: maximiza-se o lado
   esquerdo sujeito às restrições do outro modelo, com o solver. Assim, uma
   restrição agregada que equivale a um conjunto de desagregadas é aceita, e
   uma restrição redundante não é penalizada. Um modelo inviável não implica
   nada.

A formulação é correta quando precisão e revocação valem 1 em todos os
componentes. Mesmo assim, o critério é um limite inferior da correção: uma
variável auxiliar, por exemplo, conta como excedente.
"""

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from itertools import permutations, product

from po_multiagente.dominio import ResultadoSolver, Sentido, StatusSolucao, TipoVariavel
from po_multiagente.modelo import (
    ModeloInstanciado,
    ObjetivoInstanciado,
    Relacao,
    RestricaoInstanciada,
    VariavelInstanciada,
)

Chave = tuple[str, tuple[str, ...]]
"""Família de referência (ou produzida, com prefixo ``+``) e membros da variável."""

Resolver = Callable[[ModeloInstanciado], ResultadoSolver]

COMPONENTES = ("variaveis", "dominios", "restricoes", "coeficientes", "objetivo")
TOLERANCIA = 1e-6
MAX_ATRIBUICOES = 2000
MAX_IMPLICACOES = 400
DESPREZIVEL = 1e-12
EXEMPLOS = 3


@dataclass(frozen=True)
class Componente:
    """Acertos de um componente, contados de cada lado.

    A precisão usa o lado produzido e a revocação, o de referência; os dois
    lados podem diferir quando uma linha de um modelo equivale a várias do
    outro.
    """

    certos_produzidos: int
    produzidos: int
    certos_referencia: int
    referencia: int

    @property
    def precisao(self) -> float:
        """Fração dos elementos produzidos que estão certos."""
        if not self.produzidos:
            return 1.0 if not self.referencia else 0.0
        return self.certos_produzidos / self.produzidos

    @property
    def revocacao(self) -> float:
        """Fração dos elementos de referência que foram produzidos."""
        return self.certos_referencia / self.referencia if self.referencia else 1.0

    @property
    def perfeito(self) -> bool:
        """Precisão e revocação iguais a 1."""
        return (
            self.certos_produzidos == self.produzidos and self.certos_referencia == self.referencia
        )


@dataclass(frozen=True)
class ComparacaoFormulacao:
    """Resultado do critério 1 para uma execução."""

    componentes: dict[str, Componente]
    familias: dict[str, str]
    divergencias: tuple[str, ...]

    @property
    def correta(self) -> bool:
        """Precisão e revocação iguais a 1 em todos os componentes."""
        return all(c.perfeito for c in self.componentes.values())


@dataclass
class _Dominio:
    inteira: bool
    inferior: float
    superior: float


@dataclass(frozen=True)
class _Linha:
    nome: str
    termos: tuple[tuple[Chave, float], ...]
    relacao: Relacao
    lado_direito: float

    @property
    def suporte(self) -> tuple[Relacao, frozenset[Chave]]:
        return self.relacao, frozenset(k for k, _ in self.termos)


@dataclass
class _Normalizado:
    dominios: dict[Chave, _Dominio]
    linhas: list[_Linha]
    objetivo: dict[Chave, float]
    constante: float
    nomes: dict[Chave, str] = field(default_factory=dict)


def comparar_formulacoes(
    produzido: ModeloInstanciado, referencia: ModeloInstanciado, resolver: Resolver | None = None
) -> ComparacaoFormulacao:
    """Compara o modelo produzido com o de referência, componente a componente.

    Args:
        produzido: Modelo do artefato, instanciado com os dados.
        referencia: Formulação de referência, instanciada com os mesmos dados.
        resolver: Solver para as implicações (passo 4); sem ele, só conta o
            que coincide depois da normalização.
    """
    ref = _normalizar(referencia, lambda v: (v.variavel_id, v.indices))
    familias, chave_de = _associar_familias(produzido, referencia, ref)
    prod = _normalizar(produzido, chave_de)
    implicacao = _Implicacao(prod, ref, resolver)
    divergencias: list[str] = []

    comuns = prod.dominios.keys() & ref.dominios.keys()
    variaveis = Componente(len(comuns), len(prod.dominios), len(comuns), len(ref.dominios))
    divergencias += _resumo_variaveis("sem correspondente", prod, prod.dominios.keys() - comuns)
    divergencias += _resumo_variaveis("não produzida", ref, ref.dominios.keys() - comuns)

    certos = 0
    for chave in sorted(comuns):
        if _dominio_equivalente(chave, prod.dominios[chave], ref.dominios[chave], implicacao):
            certos += 1
        else:
            divergencias.append(f"domínio de {ref.nomes[chave]} difere")
    dominios = Componente(certos, len(comuns), certos, len(comuns))

    restricoes, coeficientes = _comparar_linhas(prod, ref, implicacao, divergencias)

    igual = _objetivos_iguais(prod, ref)
    objetivo = Componente(int(igual), 1, int(igual), 1)
    if not igual:
        divergencias.append("função objetivo difere")
    if implicacao.esgotada:
        divergencias.append(f"limite de {MAX_IMPLICACOES} conferências de implicação atingido")
    return ComparacaoFormulacao(
        componentes={
            "variaveis": variaveis,
            "dominios": dominios,
            "restricoes": restricoes,
            "coeficientes": coeficientes,
            "objetivo": objetivo,
        },
        familias=familias,
        divergencias=tuple(divergencias),
    )


# ------------------------------------------------------------- famílias


def _membros(modelo: ModeloInstanciado) -> dict[str, set[tuple[str, ...]]]:
    familias: dict[str, set[tuple[str, ...]]] = {}
    for variavel in modelo.variaveis:
        familias.setdefault(variavel.variavel_id, set()).add(variavel.indices)
    return familias


def _aridade(membros: set[tuple[str, ...]]) -> int:
    return len(next(iter(membros))) if membros else 0


def _associar_familias(
    produzido: ModeloInstanciado, referencia: ModeloInstanciado, ref: _Normalizado
) -> tuple[dict[str, str], Callable[[VariavelInstanciada], Chave]]:
    """Escolhe a família de referência (e a ordem dos índices) de cada família produzida."""
    membros_p, membros_r = _membros(produzido), _membros(referencia)
    candidatos: dict[str, list[tuple[str, tuple[int, ...], int]]] = {}
    for p, mp in membros_p.items():
        opcoes = []
        for r, mr in membros_r.items():
            if _aridade(mp) != _aridade(mr):
                continue
            melhor = max(
                (
                    (len({tuple(t[i] for i in ordem) for t in mp} & mr), ordem)
                    for ordem in permutations(range(_aridade(mp)))
                ),
                key=lambda x: x[0],
            )
            if melhor[0]:
                opcoes.append((r, melhor[1], melhor[0]))
        candidatos[p] = sorted(opcoes, key=lambda o: -o[2])
    nomes = sorted(candidatos)
    listas = [[None, *candidatos[p]] for p in nomes]
    if math.prod(len(lista) for lista in listas) > MAX_ATRIBUICOES:
        listas = [[None, *candidatos[p][:2]] for p in nomes]
    atribuicoes = []
    for escolha in product(*listas):
        usadas = [o[0] for o in escolha if o is not None]
        if len(usadas) == len(set(usadas)):
            atribuicoes.append(dict(zip(nomes, escolha, strict=True)))
    if not atribuicoes:
        atribuicoes = [dict.fromkeys(nomes)]
    maior = max(sum(o[2] for o in a.values() if o) for a in atribuicoes)
    empatadas = [a for a in atribuicoes if sum(o[2] for o in a.values() if o) == maior]

    def chave_de_atribuicao(
        atribuicao: dict[str, tuple[str, tuple[int, ...], int] | None],
    ) -> Callable[[VariavelInstanciada], Chave]:
        def chave_de(v: VariavelInstanciada) -> Chave:
            opcao = atribuicao.get(v.variavel_id)
            if opcao is not None:
                indices = tuple(v.indices[i] for i in opcao[1])
                if indices in membros_r[opcao[0]]:
                    return opcao[0], indices
            return f"+{v.variavel_id}", v.indices

        return chave_de

    escolhida = empatadas[0]
    if len(empatadas) > 1:
        escolhida = max(
            empatadas[:MAX_ATRIBUICOES],
            key=lambda a: _linhas_coincidentes(_normalizar(produzido, chave_de_atribuicao(a)), ref),
        )
    familias = {p: o[0] for p, o in escolhida.items() if o is not None}
    return familias, chave_de_atribuicao(escolhida)


def _linhas_coincidentes(prod: _Normalizado, ref: _Normalizado) -> int:
    restantes = list(ref.linhas)
    total = int(_objetivos_iguais(prod, ref))
    for linha in prod.linhas:
        for i, outra in enumerate(restantes):
            if _linhas_iguais(linha, outra):
                total += 1
                del restantes[i]
                break
    return total


# ---------------------------------------------------------- normalização


def _normalizar(
    modelo: ModeloInstanciado, chave_de: Callable[[VariavelInstanciada], Chave]
) -> _Normalizado:
    chaves = {v.nome: chave_de(v) for v in modelo.variaveis}
    dominios: dict[Chave, _Dominio] = {}
    nomes: dict[Chave, str] = {}
    for v in modelo.variaveis:
        inferior = -math.inf if v.limite_inferior is None else v.limite_inferior
        superior = math.inf if v.limite_superior is None else v.limite_superior
        if v.tipo is TipoVariavel.BINARIA:
            inferior, superior = max(inferior, 0.0), min(superior, 1.0)
        dominios[chaves[v.nome]] = _Dominio(v.tipo is not TipoVariavel.CONTINUA, inferior, superior)
        nomes[chaves[v.nome]] = v.nome
    linhas = []
    for restricao in modelo.restricoes:
        termos = _somar(restricao.termos, chaves)
        if len(termos) == 1:
            _apertar(dominios, restricao, *next(iter(termos.items())))
        else:
            linhas.append(_linha(restricao, termos))
    for dominio in dominios.values():
        if dominio.inteira:
            if math.isfinite(dominio.inferior):
                dominio.inferior = math.ceil(dominio.inferior - TOLERANCIA)
            if math.isfinite(dominio.superior):
                dominio.superior = math.floor(dominio.superior + TOLERANCIA)
    objetivo, constante = _objetivo(modelo.objetivo, chaves)
    return _Normalizado(dominios, linhas, objetivo, constante, nomes)


def _somar(termos: Iterable[tuple[str, float]], chaves: dict[str, Chave]) -> dict[Chave, float]:
    soma: dict[Chave, float] = {}
    for nome, coeficiente in termos:
        chave = chaves[nome]
        soma[chave] = soma.get(chave, 0.0) + coeficiente
    return {k: c for k, c in soma.items() if abs(c) > DESPREZIVEL}


def _apertar(
    dominios: dict[Chave, _Dominio], restricao: RestricaoInstanciada, chave: Chave, a: float
) -> None:
    """Restrição ``a·x (relação) b`` vira limite do domínio de ``x``."""
    dominio = dominios[chave]
    limite = restricao.lado_direito / a
    relacao = restricao.relacao
    if a < 0 and relacao is not Relacao.IGUAL:
        relacao = (
            Relacao.MAIOR_OU_IGUAL if relacao is Relacao.MENOR_OU_IGUAL else Relacao.MENOR_OU_IGUAL
        )
    if relacao in (Relacao.MENOR_OU_IGUAL, Relacao.IGUAL):
        dominio.superior = min(dominio.superior, limite)
    if relacao in (Relacao.MAIOR_OU_IGUAL, Relacao.IGUAL):
        dominio.inferior = max(dominio.inferior, limite)


def _linha(restricao: RestricaoInstanciada, termos: dict[Chave, float]) -> _Linha:
    lado_direito = restricao.lado_direito
    relacao = restricao.relacao
    if relacao is Relacao.MAIOR_OU_IGUAL:
        termos = {k: -c for k, c in termos.items()}
        lado_direito, relacao = -lado_direito, Relacao.MENOR_OU_IGUAL
    escala = max((abs(c) for c in termos.values()), default=1.0)
    ordenados = sorted(termos.items())
    if relacao is Relacao.IGUAL and ordenados and ordenados[0][1] < 0:
        escala = -escala
    return _Linha(
        nome=restricao.nome,
        termos=tuple((k, c / escala) for k, c in ordenados),
        relacao=relacao,
        lado_direito=lado_direito / escala,
    )


def _objetivo(
    objetivo: ObjetivoInstanciado, chaves: dict[str, Chave]
) -> tuple[dict[Chave, float], float]:
    sinal = -1.0 if objetivo.sentido is Sentido.MAXIMIZAR else 1.0
    termos = _somar(objetivo.termos, chaves)
    return {k: sinal * c for k, c in termos.items()}, sinal * objetivo.constante


# ------------------------------------------------------------ comparação


def _proximos(a: float, b: float) -> bool:
    if math.isinf(a) or math.isinf(b):
        return a == b
    return math.isclose(a, b, rel_tol=TOLERANCIA, abs_tol=1e-9)


def _linhas_iguais(a: _Linha, b: _Linha) -> bool:
    return (
        a.suporte == b.suporte
        and _proximos(a.lado_direito, b.lado_direito)
        and all(_proximos(c, dict(b.termos)[k]) for k, c in a.termos)
    )


def _objetivos_iguais(prod: _Normalizado, ref: _Normalizado) -> bool:
    chaves = prod.objetivo.keys() | ref.objetivo.keys()
    return _proximos(prod.constante, ref.constante) and all(
        _proximos(prod.objetivo.get(k, 0.0), ref.objetivo.get(k, 0.0)) for k in chaves
    )


def _dominio_equivalente(chave: Chave, p: _Dominio, r: _Dominio, implicacao: "_Implicacao") -> bool:
    """Mesmo tipo e, em cada limite que difere, o mais apertado implicado pelo outro modelo."""
    if p.inteira != r.inteira:
        return False
    for sinal, vp, vr in ((-1.0, p.inferior, r.inferior), (1.0, p.superior, r.superior)):
        if _proximos(vp, vr):
            continue
        # Como linha "sinal·x <= sinal·limite": o limite mais apertado é o menor sinal·limite.
        produzido_mais_apertado = sinal * vp < sinal * vr
        limite = vp if produzido_mais_apertado else vr
        linha = _Linha(chave[0], ((chave, sinal),), Relacao.MENOR_OU_IGUAL, sinal * limite)
        if produzido_mais_apertado:
            if not implicacao.pela_referencia(linha):
                return False
        elif not implicacao.pelo_produzido(linha):
            return False
    return True


def _parear(
    prod: _Normalizado, ref: _Normalizado
) -> tuple[list[tuple[_Linha, _Linha]], list[tuple[_Linha, _Linha]], list[_Linha], list[_Linha]]:
    """Pares exatos, pares só pelo suporte e as linhas sem par de cada lado."""
    restantes: dict[tuple[Relacao, frozenset[Chave]], list[_Linha]] = {}
    for linha in ref.linhas:
        restantes.setdefault(linha.suporte, []).append(linha)
    exatas: list[tuple[_Linha, _Linha]] = []
    sem_par: list[_Linha] = []
    for linha in prod.linhas:
        grupo = restantes.get(linha.suporte, [])
        igual = next((i for i, r in enumerate(grupo) if _linhas_iguais(linha, r)), None)
        if igual is None:
            sem_par.append(linha)
        else:
            exatas.append((linha, grupo.pop(igual)))
    pares: list[tuple[_Linha, _Linha]] = []
    sobra_p: list[_Linha] = []
    for linha in sem_par:
        grupo = restantes.get(linha.suporte, [])
        if grupo:
            pares.append((linha, grupo.pop(0)))
        else:
            sobra_p.append(linha)
    sobra_r = [linha for grupo in restantes.values() for linha in grupo]
    return exatas, pares, sobra_p, sobra_r


def _comparar_linhas(
    prod: _Normalizado, ref: _Normalizado, implicacao: "_Implicacao", divergencias: list[str]
) -> tuple[Componente, Componente]:
    """Restrições pelo suporte; coeficientes nos pares; equivalência pelo solver."""
    exatas, pares, sobra_p, sobra_r = _parear(prod, ref)
    coef_certos = len(exatas)
    for p, r in pares:
        if implicacao.pela_referencia(p) and implicacao.pelo_produzido(r):
            coef_certos += 1
        else:
            divergencias.append(f"coeficientes de {p.nome} diferem de {r.nome}")
    certos_p = certos_r = len(exatas) + len(pares)
    for linha in sobra_p:
        if implicacao.pela_referencia(linha):
            certos_p += 1
        else:
            divergencias.append(f"restrição sem equivalente na referência: {linha.nome}")
    for linha in sobra_r:
        if implicacao.pelo_produzido(linha):
            certos_r += 1
        else:
            divergencias.append(f"restrição de referência não produzida: {linha.nome}")
    n_pares = len(exatas) + len(pares)
    return (
        Componente(certos_p, len(prod.linhas), certos_r, len(ref.linhas)),
        Componente(coef_certos, n_pares, coef_certos, n_pares),
    )


def _resumo_variaveis(rotulo: str, modelo: _Normalizado, chaves: Iterable[Chave]) -> list[str]:
    por_familia: dict[str, list[str]] = {}
    for chave in sorted(chaves):
        por_familia.setdefault(chave[0].lstrip("+"), []).append(modelo.nomes[chave])
    return [
        f"variável {rotulo}: {', '.join(nomes[:EXEMPLOS])}"
        + (f" e mais {len(nomes) - EXEMPLOS}" if len(nomes) > EXEMPLOS else "")
        for nomes in por_familia.values()
    ]


# ------------------------------------------------------------ implicação


class _Implicacao:
    """Confere, com o solver, se um modelo implica uma linha do outro."""

    def __init__(self, prod: _Normalizado, ref: _Normalizado, resolver: Resolver | None) -> None:
        self._modelos = {"prod": prod, "ref": ref}
        self._resolver = resolver
        self._viavel: dict[str, bool] = {}
        self._feitas = 0
        self.esgotada = False

    def pela_referencia(self, linha: _Linha) -> bool:
        return self._implica("ref", linha)

    def pelo_produzido(self, linha: _Linha) -> bool:
        return self._implica("prod", linha)

    def _implica(self, qual: str, linha: _Linha) -> bool:
        modelo = self._modelos[qual]
        if self._resolver is None or any(k not in modelo.dominios for k, _ in linha.termos):
            return False
        if not self._eh_viavel(qual):
            return False
        sentidos = [1.0] if linha.relacao is Relacao.MENOR_OU_IGUAL else [1.0, -1.0]
        for sinal in sentidos:
            maximo = self._maximo(modelo, {k: sinal * c for k, c in linha.termos})
            if maximo is None or maximo > sinal * linha.lado_direito + TOLERANCIA * max(
                1.0, abs(linha.lado_direito), abs(maximo)
            ):
                return False
        return True

    def _eh_viavel(self, qual: str) -> bool:
        if qual not in self._viavel:
            resultado = self._resolver_modelo(self._modelos[qual], {}) if self._resolver else None
            self._viavel[qual] = resultado is not None and resultado.status is StatusSolucao.OTIMO
        return self._viavel[qual]

    def _maximo(self, modelo: _Normalizado, termos: dict[Chave, float]) -> float | None:
        if self._feitas >= MAX_IMPLICACOES:
            self.esgotada = True
            return None
        self._feitas += 1
        resultado = self._resolver_modelo(modelo, termos)
        if resultado is None or resultado.status is not StatusSolucao.OTIMO:
            return None
        return resultado.valor_objetivo

    def _resolver_modelo(
        self, modelo: _Normalizado, objetivo: dict[Chave, float]
    ) -> ResultadoSolver | None:
        assert self._resolver is not None
        nomes = {k: f"v{i}" for i, k in enumerate(sorted(modelo.dominios))}
        variaveis = tuple(
            VariavelInstanciada(
                nome=nomes[k],
                variavel_id=k[0],
                indices=k[1],
                tipo=TipoVariavel.INTEIRA if d.inteira else TipoVariavel.CONTINUA,
                limite_inferior=None if math.isinf(d.inferior) else d.inferior,
                limite_superior=None if math.isinf(d.superior) else d.superior,
            )
            for k, d in sorted(modelo.dominios.items())
        )
        restricoes = tuple(
            RestricaoInstanciada(
                nome=f"r{i}",
                restricao_id=f"r{i}",
                indices=(),
                termos=tuple((nomes[k], c) for k, c in linha.termos),
                relacao=linha.relacao,
                lado_direito=linha.lado_direito,
            )
            for i, linha in enumerate(modelo.linhas)
        )
        alvo = ObjetivoInstanciado(
            sentido=Sentido.MAXIMIZAR,
            termos=tuple((nomes[k], c) for k, c in objetivo.items()),
            constante=0.0,
        )
        return self._resolver(ModeloInstanciado(variaveis, restricoes, alvo))
