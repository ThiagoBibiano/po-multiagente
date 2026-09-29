"""Explicador: resultado → explicação em linguagem de negócio, com números só por marcador."""

import re

from po_multiagente.agentes._comum import (
    ErroFormato,
    Registro,
    bloco_json,
    gerar_estruturado,
)
from po_multiagente.agentes.gerador_executor import Execucao
from po_multiagente.dominio import (
    Especificacao,
    Explicacao,
    ItemFicha,
    ObjetoDominio,
    ParecerValidador,
    Sinal,
    StatusSolucao,
)
from po_multiagente.dominio._base import TextoNaoVazio
from po_multiagente.llm import ErroLLM, LLMPort
from po_multiagente.prompts import carregar_instrucao

MARCADOR = re.compile(r"\{\{(OBJ|VAR:[^{}]+)\}\}")
MAX_DECISOES = 60
"""Decisões não nulas oferecidas ao modelo como marcadores."""
ZERO = 1e-9
"""Abaixo disso (em módulo), a decisão é tratada como nula."""


class SaidaExplicador(ObjetoDominio):
    """Texto com marcadores."""

    texto: TextoNaoVazio


def formatar_numero(valor: float) -> str:
    """Número em notação brasileira: ``1.234,5``; inteiros sem casas decimais."""
    arredondado = round(valor, 2)
    if arredondado.is_integer():
        return f"{int(arredondado):,}".replace(",", ".")
    inteiro, _, decimais = f"{arredondado:,.2f}".partition(".")
    return f"{inteiro.replace(',', '.')},{decimais.rstrip('0')}"


class Explicador:
    """Agente Explicador (cap. 3, Passo 3).

    Nenhum número inventado chega ao gestor: o texto é recusado se trouxer
    algarismo fora de marcador ou marcador desconhecido; depois de
    ``max_recusas``, o código monta um texto de reserva.
    """

    agente = "explicador"

    def __init__(self, llm: LLMPort, max_recusas: int = 2) -> None:
        self._llm = llm
        self._max_recusas = max_recusas
        self._instrucao = carregar_instrucao(self.agente)

    def explicar(
        self,
        especificacao: Especificacao,
        execucao: Execucao,
        parecer: ParecerValidador | None,
        registro: Registro,
    ) -> Explicacao:
        """Escreve a explicação do resultado."""
        catalogo = self._catalogo(especificacao, execucao)
        base = self._entrada(especificacao, execucao, parecer, catalogo)
        recusas: list[str] = []
        while len(recusas) < self._max_recusas:
            entrada = base if not recusas else f"{base}\n\n# Texto recusado\n\n{recusas[-1]}"
            try:
                saida = gerar_estruturado(
                    self._llm, self._instrucao, entrada, SaidaExplicador, registro
                )
                texto, ficha = self._renderizar(saida.texto, catalogo)
            except (ErroFormato, ErroLLM) as erro:
                recusas.append(str(erro))
                continue
            return Explicacao(texto=texto, ficha=ficha, recusas=len(recusas))
        return self._reserva(especificacao, execucao, catalogo, len(recusas))

    @staticmethod
    def _catalogo(especificacao: Especificacao, execucao: Execucao) -> dict[str, ItemFicha]:
        resultado = execucao.resultado
        if resultado.valor_objetivo is None or not resultado.valores:
            return {}
        origem = (
            f"solver {resultado.solver.backend}/{resultado.solver.motor} "
            f"{resultado.solver.versao}, status {resultado.status.value}"
        )
        catalogo = {"OBJ": ItemFicha(marcador="OBJ", valor=resultado.valor_objetivo, origem=origem)}
        nao_nulos = [(n, v) for n, v in resultado.valores.items() if abs(v) > ZERO]
        for nome, valor in nao_nulos[:MAX_DECISOES]:
            catalogo[f"VAR:{nome}"] = ItemFicha(marcador=f"VAR:{nome}", valor=valor, origem=origem)
        return catalogo

    @staticmethod
    def _entrada(
        especificacao: Especificacao,
        execucao: Execucao,
        parecer: ParecerValidador | None,
        catalogo: dict[str, ItemFicha],
    ) -> str:
        quadro = especificacao.model_dump(
            mode="json",
            include={
                "decisao",
                "criterio",
                "sentido",
                "requisitos",
                "premissas",
                "nao_considerado",
            },
        )
        descricoes = {v.id: v.descricao for v in execucao.compilado.ir.variaveis}
        marcadores = [f"- `{{{{OBJ}}}}`: {especificacao.criterio}"] + [
            f"- `{{{{{m}}}}}`: {descricoes.get(m[4:].split('[')[0], '')} {m[4:]}"
            for m in catalogo
            if m != "OBJ"
        ]
        partes = [
            bloco_json("Quadro de especificação", quadro),
            f"# Situação do resultado\n\n{execucao.resultado.status.value}",
        ]
        if catalogo:
            partes.append("# Marcadores disponíveis\n\n" + "\n".join(marcadores))
        s1 = next(
            (v for v in (parecer.verificacoes if parecer else ()) if v.sinal is Sinal.S1), None
        )
        if s1 is not None and not s1.aprovada:
            partes.append(f"# Localização do problema\n\n{s1.mensagem}")
        if execucao.erros:
            partes.append(
                "# Falhas ao ligar os dados\n\n" + "\n".join(f"- {e}" for e in execucao.erros)
            )
        return "\n\n".join(partes)

    @staticmethod
    def _renderizar(
        texto: str, catalogo: dict[str, ItemFicha]
    ) -> tuple[str, tuple[ItemFicha, ...]]:
        desconhecidos = sorted({m for m in MARCADOR.findall(texto) if m not in catalogo})
        if desconhecidos:
            raise ErroFormato(f"Marcadores desconhecidos: {', '.join(desconhecidos)}")
        sem_marcadores = MARCADOR.sub("", texto)
        if re.search(r"\d", sem_marcadores):
            raise ErroFormato(
                "O texto tem algarismo fora de marcador; use só os marcadores da lista"
            )
        usados = list(dict.fromkeys(MARCADOR.findall(texto)))
        renderizado = MARCADOR.sub(lambda m: formatar_numero(catalogo[m[1]].valor), texto)
        return renderizado, tuple(catalogo[m] for m in usados)

    @staticmethod
    def _reserva(
        especificacao: Especificacao,
        execucao: Execucao,
        catalogo: dict[str, ItemFicha],
        recusas: int,
    ) -> Explicacao:
        resultado = execucao.resultado
        if (
            resultado.status not in (StatusSolucao.OTIMO, StatusSolucao.LIMITE_TEMPO)
            or not catalogo
        ):
            texto = (
                f"Não foi possível obter um plano para: {especificacao.decisao}. "
                f"Situação: {resultado.status.value}."
            )
            return Explicacao(texto=texto, recusas=recusas, deterministica=True)
        linhas = [f"{especificacao.criterio}: {formatar_numero(catalogo['OBJ'].valor)}."]
        linhas += [
            f"- {marcador[4:]}: {formatar_numero(item.valor)}"
            for marcador, item in catalogo.items()
            if marcador != "OBJ"
        ]
        return Explicacao(
            texto="\n".join(linhas),
            ficha=tuple(catalogo.values()),
            recusas=recusas,
            deterministica=True,
        )
