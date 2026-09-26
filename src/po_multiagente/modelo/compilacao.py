"""Primeiro estágio do compilador: análise sintática e checagem do modelo.

Um modelo compilado tem todas as expressões analisadas e garante que:

- todo nome usado está declarado e é parâmetro ou variável;
- cada referência tem o número de índices declarado, e cada índice percorre
  o conjunto que a posição espera;
- todo índice de ``para_todo`` e de somatório é usado;
- o modelo é linear: não há produto de variáveis nem divisão por variável;
- objetivo e restrições contêm ao menos uma variável.

A checagem não olha dados nem unidades; unidades são o sinal S2 do Validador.
"""

from collections.abc import Iterator
from dataclasses import dataclass

from po_multiagente.dominio import ModeloIR, Restricao
from po_multiagente.modelo.arvore import (
    Binaria,
    Comparacao,
    Expressao,
    IndiceLivre,
    Negacao,
    Numero,
    Operador,
    Referencia,
    Somatorio,
    texto,
)
from po_multiagente.modelo.erros import OBJETIVO, ErroCompilacao, ErroModelo
from po_multiagente.modelo.gramatica import (
    PALAVRAS_RESERVADAS,
    ErroSintaxe,
    analisar_comparacao,
    analisar_expressao,
)


@dataclass(frozen=True)
class RestricaoCompilada:
    """Família de restrições com a expressão já analisada."""

    restricao: Restricao
    comparacao: Comparacao


@dataclass(frozen=True)
class ModeloCompilado:
    """Modelo checado, pronto para instanciar com dados."""

    ir: ModeloIR
    objetivo: Expressao
    restricoes: tuple[RestricaoCompilada, ...]


def compilar(ir: ModeloIR) -> ModeloCompilado:
    """Analisa e checa todas as expressões do modelo.

    Raises:
        ErroCompilacao: Com todos os erros encontrados, cada um localizado
            no elemento em que está.
    """
    checador = _Checador(ir)
    erros = list(checador.nomes_reservados())
    objetivo = checador.objetivo()
    restricoes = [checador.restricao(r) for r in ir.restricoes]
    erros.extend(checador.erros)
    if erros or objetivo is None or any(r is None for r in restricoes):
        raise ErroCompilacao(erros)
    return ModeloCompilado(
        ir=ir,
        objetivo=objetivo,
        restricoes=tuple(r for r in restricoes if r is not None),
    )


def indices_usados(expressao: Expressao) -> set[str]:
    """Nomes de índices livres usados na expressão (não ligados por ela)."""
    match expressao:
        case Numero():
            return set()
        case Referencia(_, indices):
            return {i.nome for i in indices if isinstance(i, IndiceLivre)}
        case Somatorio(corpo, geradores):
            return indices_usados(corpo) - {g.indice for g in geradores}
        case Negacao(operando):
            return indices_usados(operando)
        case Binaria(_, esquerda, direita):
            return indices_usados(esquerda) | indices_usados(direita)


class _Checador:
    """Percorre as expressões acumulando erros localizados."""

    def __init__(self, ir: ModeloIR) -> None:
        self._ir = ir
        self._conjuntos = {c.id for c in ir.conjuntos}
        self._variaveis = {v.id for v in ir.variaveis}
        self._assinaturas = {p.id: p.indices for p in ir.parametros} | {
            v.id: v.indices for v in ir.variaveis
        }
        self._nomes = self._conjuntos | set(self._assinaturas) | {r.id for r in ir.restricoes}
        self.erros: list[ErroModelo] = []
        self._elemento = OBJETIVO

    def nomes_reservados(self) -> Iterator[ErroModelo]:
        for nome in sorted(self._nomes & PALAVRAS_RESERVADAS):
            yield ErroModelo(nome, f"{nome!r} é palavra reservada da linguagem; escolha outro nome")

    def objetivo(self) -> Expressao | None:
        self._elemento = OBJETIVO
        try:
            expressao = analisar_expressao(self._ir.objetivo.expressao)
        except ErroSintaxe as erro:
            self._erro(str(erro))
            return None
        if self._grau(expressao, {}) == 0:
            self._erro("a função objetivo não contém variável de decisão")
        return expressao

    def restricao(self, restricao: Restricao) -> RestricaoCompilada | None:
        self._elemento = restricao.id
        ambiente = {}
        for quantificador in restricao.para_todo:
            if quantificador.indice in self._nomes | PALAVRAS_RESERVADAS:
                self._erro(
                    f"o índice {quantificador.indice!r} coincide com um nome do modelo ou da "
                    "linguagem"
                )
            ambiente[quantificador.indice] = quantificador.conjunto
        try:
            comparacao = analisar_comparacao(restricao.expressao)
        except ErroSintaxe as erro:
            self._erro(str(erro))
            return None
        graus = [self._grau(lado, ambiente) for lado in (comparacao.esquerda, comparacao.direita)]
        if max(graus) == 0:
            self._erro(f"a restrição {texto(comparacao)!r} não contém variável de decisão")
        usados = indices_usados(comparacao.esquerda) | indices_usados(comparacao.direita)
        for indice in ambiente.keys() - usados:
            self._erro(f"o índice {indice!r} do para_todo não é usado na expressão")
        return RestricaoCompilada(restricao=restricao, comparacao=comparacao)

    def _grau(self, expressao: Expressao, ambiente: dict[str, str]) -> int:
        """Grau da expressão nas variáveis de decisão: 0 (constante) ou 1 (linear).

        Um termo não linear gera erro e conta como grau 1, para não repetir o
        erro nos termos que o contêm.
        """
        match expressao:
            case Numero():
                return 0
            case Referencia():
                return self._grau_referencia(expressao, ambiente)
            case Somatorio():
                return self._grau_somatorio(expressao, ambiente)
            case Negacao(operando):
                return self._grau(operando, ambiente)
            case Binaria(operador, esquerda, direita):
                grau_esquerda = self._grau(esquerda, ambiente)
                grau_direita = self._grau(direita, ambiente)
                if operador is Operador.PRODUTO and grau_esquerda + grau_direita > 1:
                    self._erro(
                        f"o produto {texto(expressao)!r} multiplica variáveis de decisão e torna "
                        "o modelo não linear"
                    )
                elif operador is Operador.DIVISAO and grau_direita > 0:
                    self._erro(
                        f"a divisão {texto(expressao)!r} tem variável de decisão no "
                        "denominador e torna o modelo não linear"
                    )
                elif operador is Operador.DIVISAO and direita == Numero(0.0):
                    self._erro(f"a divisão {texto(expressao)!r} é por zero")
                return max(grau_esquerda, grau_direita)

    def _grau_somatorio(self, somatorio: Somatorio, ambiente: dict[str, str]) -> int:
        interno = dict(ambiente)
        for gerador in somatorio.geradores:
            if gerador.conjunto not in self._conjuntos:
                self._erro(f"o conjunto {gerador.conjunto!r} não está declarado")
            if gerador.indice in interno:
                self._erro(f"o índice {gerador.indice!r} já está em uso")
            elif gerador.indice in self._nomes | PALAVRAS_RESERVADAS:
                self._erro(
                    f"o índice {gerador.indice!r} coincide com um nome do modelo ou da linguagem"
                )
            interno[gerador.indice] = gerador.conjunto
        grau = self._grau(somatorio.corpo, interno)
        usados = indices_usados(somatorio.corpo)
        for gerador in somatorio.geradores:
            if gerador.indice not in usados:
                self._erro(
                    f"o índice {gerador.indice!r} do somatório não é usado em "
                    f"{texto(somatorio.corpo)!r}"
                )
        return grau

    def _grau_referencia(self, referencia: Referencia, ambiente: dict[str, str]) -> int:
        nome = referencia.nome
        if nome in ambiente:
            self._erro(f"o índice {nome!r} não pode ser usado como valor numérico")
            return 0
        if nome in self._conjuntos:
            self._erro(
                f"o conjunto {nome!r} não pode ser usado como valor; percorra-o com "
                f"sum(... for i in {nome})"
            )
            return 0
        if nome not in self._assinaturas:
            self._erro(f"{nome!r} não está declarado como parâmetro nem como variável do modelo")
            return 0
        esperados = self._assinaturas[nome]
        if len(referencia.indices) != len(esperados):
            self._erro(
                f"{texto(referencia)!r}: {nome} tem {len(esperados)} índice(s)"
                + (f" ({', '.join(esperados)})" if esperados else "")
                + f", mas foi usado com {len(referencia.indices)}"
            )
        else:
            for posicao, (indice, conjunto) in enumerate(
                zip(referencia.indices, esperados, strict=True), start=1
            ):
                if not isinstance(indice, IndiceLivre):
                    continue
                if indice.nome not in ambiente:
                    self._erro(
                        f"{texto(referencia)!r}: o índice {indice.nome!r} não está ligado por "
                        "para_todo nem por somatório"
                    )
                elif ambiente[indice.nome] != conjunto:
                    self._erro(
                        f"{texto(referencia)!r}: o índice {indice.nome!r} percorre "
                        f"{ambiente[indice.nome]}, mas a posição {posicao} de {nome} espera "
                        f"{conjunto}"
                    )
        return 1 if nome in self._variaveis else 0

    def _erro(self, mensagem: str) -> None:
        self.erros.append(ErroModelo(self._elemento, mensagem))
