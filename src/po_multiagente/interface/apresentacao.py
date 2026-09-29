"""Apresentação do resultado ao usuário: textos e tabelas em Markdown, sem Gradio.

A interface mostra primeiro o que interessa a quem decide (o resultado, o
plano e a explicação) e, em detalhes técnicos, os artefatos de cada agente
(R5) em forma legível: decisões em tabela, modelo com legenda, conferências
como lista de verificação e o entendimento do problema em texto.
"""

import csv
import io
import json
import zipfile
from collections.abc import Iterable, Sequence
from pathlib import Path

from po_multiagente.agentes import formatar_numero
from po_multiagente.dominio import (
    Especificacao,
    ModeloIR,
    Origem,
    ParecerValidador,
    Sentido,
    Sinal,
    TipoVariavel,
    Variavel,
)
from po_multiagente.interface.assistente import Resultado

MAX_LINHAS = 60
"""Linhas de uma tabela antes de cortar (o arquivo para baixar tem todas)."""

_TOLERANCIA = 1e-9

_STATUS = {
    "otimo": "✅ **Melhor solução encontrada**",
    "inviavel": "⚠️ **Não existe plano que respeite todos os limites ao mesmo tempo**",
    "ilimitado": "⚠️ **O resultado cresce sem limite: falta alguma restrição no problema**",
    "limite_tempo": "⏱️ **O solver parou pelo limite de tempo antes de garantir o melhor plano**",
    "erro": "❌ **Não foi possível resolver o problema**",
}
_SINAIS = {
    Sinal.S1: "Resultado do solver",
    Sinal.S2: "Unidades de medida",
    Sinal.S3: "Origem dos dados",
    Sinal.S4: "Requisitos do pedido",
    Sinal.S5: "Plausibilidade do resultado",
}
_TIPOS = {
    TipoVariavel.CONTINUA: "contínua",
    TipoVariavel.INTEIRA: "inteira",
    TipoVariavel.BINARIA: "sim ou não",
}


def numero(valor: float) -> str:
    """Número em notação brasileira, com até duas casas decimais."""
    valor = float(valor)
    return formatar_numero(0.0 if abs(valor) < _TOLERANCIA else valor)


def destaque(resultado: Resultado) -> str:
    """Situação da solução e valor do objetivo, em uma ou duas linhas."""
    situacao = _STATUS.get(resultado.status or "erro", _STATUS["erro"])
    if resultado.valor_objetivo is None:
        return f"### {situacao}"
    # O critério do quadro é um substantivo ("Margem total"); a descrição do objetivo
    # às vezes vem com verbo ("Maximizar a margem"), redundante ao lado de "maior valor".
    criterio = (
        resultado.especificacao.criterio
        if resultado.especificacao
        else (resultado.modelo.objetivo.descricao if resultado.modelo else "Objetivo")
    )
    extremo = "menor valor" if resultado.sentido is Sentido.MINIMIZAR else "maior valor"
    return (
        f"### {situacao}\n\n"
        f"**{criterio}** ({extremo} possível): "
        f"<span style='font-size:1.6em;font-weight:700'>{numero(resultado.valor_objetivo)}</span>"
    )


def selo_conferencia(resultado: Resultado) -> str:
    """Resumo da última rodada do Validador, quando ele participou."""
    if not resultado.pareceres:
        return ""
    ultimo = resultado.pareceres[-1]
    aprovadas = sum(v.aprovada for v in ultimo.verificacoes)
    total = len(ultimo.verificacoes)
    rodadas = len(resultado.pareceres)
    marca = "🔎" if aprovadas == total else "⚠️"
    correcoes = (
        f", depois de {rodadas - 1} correção(ões) do modelo"
        if rodadas > 1
        else " na primeira rodada"
    )
    return (
        f"{marca} Conferido pelo Validador: {aprovadas} de {total} verificações "
        f"aprovadas{correcoes}. Veja em *Detalhes técnicos → Conferências*."
    )


def plano_recomendado(resultado: Resultado) -> str:
    """Decisões diferentes de zero, uma tabela por variável, em palavras do usuário."""
    if resultado.modelo is None or not resultado.solucao:
        return ""
    blocos = []
    for variavel in resultado.modelo.variaveis:
        linhas = [
            (membros, valor)
            for membros, valor in _valores(variavel, resultado.solucao)
            if abs(valor) > _TOLERANCIA
        ]
        if not linhas:
            continue
        rotulos = _rotulos(variavel, resultado.modelo)
        coluna_valor = f"{variavel.descricao} ({variavel.unidade})"
        cabecalho = [*rotulos, coluna_valor]
        corpo = [[*membros, _valor(variavel, valor)] for membros, valor in linhas]
        blocos.append(_tabela(cabecalho, corpo))
    if not blocos:
        return "#### Plano recomendado\n\nTodas as decisões ficaram em zero."
    return "#### Plano recomendado\n\n" + "\n\n".join(blocos)


def decisoes(resultado: Resultado) -> str:
    """Todas as decisões; com dois índices, em tabela cruzada com totais."""
    if resultado.modelo is None or not resultado.solucao:
        return "Sem solução para mostrar."
    blocos = []
    for variavel in resultado.modelo.variaveis:
        valores = _valores(variavel, resultado.solucao)
        if not valores:
            continue
        titulo = f"**{variavel.descricao}** ({variavel.unidade}), símbolo `{variavel.id}`"
        rotulos = _rotulos(variavel, resultado.modelo)
        if len(rotulos) == 2 and all(len(m) == 2 for m, _ in valores):  # noqa: PLR2004
            blocos.append(f"{titulo}\n\n{_cruzada(variavel, rotulos, valores)}")
        else:
            corpo = [[*m, _valor(variavel, v)] for m, v in valores]
            blocos.append(f"{titulo}\n\n{_tabela([*rotulos, 'Valor'], corpo)}")
    return "\n\n".join(blocos) or "Sem solução para mostrar."


def modelo_legivel(resultado: Resultado) -> str:
    """Formulação em LaTeX e a legenda de cada símbolo, com a origem dos dados."""
    if resultado.modelo is None:
        return "O modelo não chegou a ser montado."
    modelo = resultado.modelo
    especificacao = resultado.especificacao
    partes = []
    if resultado.formulacao_latex:
        partes.append(f"$$\n{resultado.formulacao_latex}\n$$")
    parametros = {p.id: p for p in especificacao.parametros} if especificacao else {}
    dados = [
        [
            f"`{p.id}`",
            parametros[p.id].descricao if p.id in parametros else "",
            parametros[p.id].unidade if p.id in parametros else "",
            _origem(parametros[p.id].origem) if p.id in parametros else "",
        ]
        for p in modelo.parametros
    ]
    if dados:
        partes.append(
            "#### Dados do problema\n\n"
            + _tabela(["Símbolo", "O que é", "Unidade", "De onde veio"], dados)
        )
    variaveis = [
        [f"`{v.id}`", v.descricao, v.unidade, _TIPOS.get(v.tipo, v.tipo.value)]
        for v in modelo.variaveis
    ]
    partes.append(
        "#### Decisões\n\n" + _tabela(["Símbolo", "O que é", "Unidade", "Tipo"], variaveis)
    )
    requisitos = {r.id: r.texto for r in especificacao.requisitos} if especificacao else {}
    restricoes = [
        [f"`{r.id}`", r.descricao, "; ".join(requisitos.get(q, q) for q in r.requisitos)]
        for r in modelo.restricoes
    ]
    if restricoes:
        partes.append(
            "#### Restrições\n\n"
            + _tabela(["Nome", "O que garante", "Requisito atendido"], restricoes)
        )
    conjuntos = [[f"`{c.id}`", c.descricao, _origem(c.origem)] for c in modelo.conjuntos]
    if conjuntos:
        partes.append(
            "#### Conjuntos\n\n" + _tabela(["Símbolo", "O que é", "De onde veio"], conjuntos)
        )
    return "\n\n".join(partes)


def conferencias(pareceres: Sequence[ParecerValidador]) -> str:
    """Cada rodada do Validador como lista de verificação."""
    if not pareceres:
        return "O Validador não participou desta execução."
    blocos = []
    for parecer in pareceres:
        situacao = "aprovada" if parecer.aprovado else "com pontos a corrigir"
        linhas = [f"#### Rodada {parecer.iteracao}: {situacao}", ""]
        for verificacao in parecer.verificacoes:
            marca = "✅" if verificacao.aprovada else "❌"
            nome = _SINAIS.get(verificacao.sinal, verificacao.sinal.value)
            onde = (
                f" *(em: {', '.join(f'`{e}`' for e in verificacao.elementos)})*"
                if verificacao.elementos
                else ""
            )
            linhas.append(f"- {marca} **{nome}:** {verificacao.mensagem}{onde}")
            if verificacao.confirmacao:
                linhas.append(f"  - ❓ Pergunta feita a você: {verificacao.confirmacao}")
        blocos.append("\n".join(linhas))
    if len(pareceres) > 1:
        blocos.append(
            "*Quando uma rodada aponta problemas, o Modelador corrige o modelo e o "
            "Validador confere de novo.*"
        )
    return "\n\n".join(blocos)


def entendimento(especificacao: Especificacao | None) -> str:
    """O que a plataforma entendeu do pedido, em texto."""
    if especificacao is None:
        return "O pedido não chegou a ser interpretado."
    objetivo = "Minimizar" if especificacao.sentido is Sentido.MINIMIZAR else "Maximizar"
    partes = [
        f"**Decisão:** {especificacao.decisao}\n\n"
        f"**Critério:** {objetivo} {_minuscula(especificacao.criterio)}",
        "#### Requisitos\n\n"
        + "\n".join(f"- **{r.id}:** {r.texto}" for r in especificacao.requisitos),
    ]
    if especificacao.parametros:
        dados = [
            [f"`{p.id}`", p.descricao, p.unidade, _origem(p.origem)]
            for p in especificacao.parametros
        ]
        partes.append(
            "#### Dados usados\n\n"
            + _tabela(["Símbolo", "O que é", "Unidade", "De onde veio"], dados)
        )
    partes += [
        _lista("Premissas adotadas", especificacao.premissas),
        _lista("Fora do modelo", especificacao.nao_considerado),
    ]
    if especificacao.alertas:
        itens = [
            f"“{a.trecho}”: pode ser lido como {' ou '.join(a.leituras)}"
            for a in especificacao.alertas
        ]
        partes.append(_lista("Pontos ambíguos no pedido", itens))
    planilhas = [
        [f"`{f.arquivo}`", ", ".join(c.nome for c in f.colunas)] for f in especificacao.fontes
    ]
    if planilhas:
        partes.append("#### Planilhas recebidas\n\n" + _tabela(["Arquivo", "Colunas"], planilhas))
    return "\n\n".join(p for p in partes if p)


def consumo(resultado: Resultado, segundos: float | None = None) -> str:
    """Tempo, chamadas ao modelo e custo."""
    linhas = [
        ["Situação do solver", resultado.status or "sem resultado"],
        ["Rodadas do Validador", str(len(resultado.pareceres))],
        ["Chamadas ao modelo de linguagem", str(resultado.chamadas_llm)],
        [
            "Tokens (entrada / saída)",
            f"{numero(resultado.tokens_entrada)} / {numero(resultado.tokens_saida)}",
        ],
        ["Custo estimado", f"{resultado.moeda} {resultado.custo:.4f}"],
    ]
    if segundos is not None:
        linhas.insert(0, ["Tempo total", f"{segundos:.0f} s"])
    return _tabela(["Item", "Valor"], linhas)


def empacotar(resultado: Resultado, destino: Path) -> Path:
    """Arquivo ZIP com a solução, a formulação e os artefatos de cada agente.

    Returns:
        Caminho do ZIP criado em ``destino``.
    """
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / "resultado.zip"
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as zip_:
        zip_.writestr("solucao.csv", _csv_solucao(resultado))
        if resultado.explicacao:
            zip_.writestr("explicacao.md", resultado.explicacao + "\n")
        if resultado.formulacao_latex:
            zip_.writestr("formulacao.tex", resultado.formulacao_latex + "\n")
        artefatos = {
            "especificacao.json": resultado.especificacao,
            "modelo.json": resultado.modelo,
        }
        for nome, objeto in artefatos.items():
            if objeto is not None:
                zip_.writestr(nome, objeto.model_dump_json(indent=2))
        pareceres = [p.model_dump(mode="json") for p in resultado.pareceres]
        zip_.writestr("conferencias.json", json.dumps(pareceres, ensure_ascii=False, indent=2))
    return caminho


def _valores(variavel: Variavel, solucao: dict[str, float]) -> list[tuple[list[str], float]]:
    """Valores da variável, com os membros de cada índice, na ordem do solver."""
    encontrados: list[tuple[list[str], float]] = []
    for nome, valor in solucao.items():
        if nome == variavel.id and not variavel.indices:
            encontrados.append(([], valor))
        elif nome.startswith(f"{variavel.id}[") and nome.endswith("]"):
            membros = nome[len(variavel.id) + 1 : -1].split(",")
            if len(membros) != len(variavel.indices):
                membros = [nome[len(variavel.id) + 1 : -1]]
            encontrados.append((membros, valor))
    return encontrados


def _rotulos(variavel: Variavel, modelo: ModeloIR) -> list[str]:
    """Cabeçalho de cada índice: o nome da coluna de origem do conjunto."""
    conjuntos = {c.id: c for c in modelo.conjuntos}
    rotulos = []
    for indice in variavel.indices:
        conjunto = conjuntos.get(indice)
        nome = conjunto.origem.coluna if conjunto else indice
        rotulos.append(nome[:1].upper() + nome[1:])
    return rotulos


def _cruzada(variavel: Variavel, rotulos: list[str], valores: list[tuple[list[str], float]]) -> str:
    linhas = list(dict.fromkeys(m[0] for m, _ in valores))
    colunas = list(dict.fromkeys(m[1] for m, _ in valores))
    tabela = {(m[0], m[1]): v for m, v in valores}
    corpo = []
    for linha in linhas:
        celulas = [_valor(variavel, tabela.get((linha, c), 0.0)) for c in colunas]
        total = sum(tabela.get((linha, c), 0.0) for c in colunas)
        corpo.append([f"**{linha}**", *celulas, f"**{numero(total)}**"])
    totais = [numero(sum(tabela.get((li, c), 0.0) for li in linhas)) for c in colunas]
    geral = numero(sum(tabela.values()))
    corpo.append(["**Total**", *[f"**{t}**" for t in totais], f"**{geral}**"])
    return _tabela([f"{rotulos[0]} \\ {rotulos[1]}", *colunas, "Total"], corpo)


def _valor(variavel: Variavel, valor: float) -> str:
    if variavel.tipo is TipoVariavel.BINARIA:
        return "sim" if valor > 0.5 else "não"  # noqa: PLR2004
    return numero(valor)


def _origem(origem: Origem) -> str:
    texto = f"`{origem.arquivo}` › `{origem.coluna}`"
    if origem.filtros:
        texto += " (só " + ", ".join(f"{f.coluna} = {f.valor}" for f in origem.filtros) + ")"
    if origem.solicitacao_id:
        texto += " — ajustado por você"
    return texto


def _tabela(cabecalho: Sequence[str], linhas: Sequence[Sequence[str]]) -> str:
    """Tabela Markdown; acima de ``MAX_LINHAS``, corta e avisa."""
    cortadas = len(linhas) - MAX_LINHAS
    visiveis = linhas[:MAX_LINHAS]
    texto = "\n".join(
        [
            "| " + " | ".join(_celula(c) for c in cabecalho) + " |",
            "|" + "---|" * len(cabecalho),
            *("| " + " | ".join(_celula(c) for c in linha) + " |" for linha in visiveis),
        ]
    )
    if cortadas > 0:
        texto += f"\n\n*… e mais {cortadas} linha(s); todas estão no arquivo para baixar.*"
    return texto


def _celula(texto: str) -> str:
    return str(texto).replace("|", "\\|").replace("\n", " ")


def _lista(titulo: str, itens: Iterable[str]) -> str:
    itens = list(itens)
    return f"#### {titulo}\n\n" + "\n".join(f"- {i}" for i in itens) if itens else ""


def _minuscula(texto: str) -> str:
    return texto[:1].lower() + texto[1:]


def _csv_solucao(resultado: Resultado) -> str:
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow(["variavel", "indices", "valor"])
    for nome, valor in resultado.solucao.items():
        base, _, resto = nome.partition("[")
        escritor.writerow([base, resto.rstrip("]"), valor])
    return saida.getvalue()
