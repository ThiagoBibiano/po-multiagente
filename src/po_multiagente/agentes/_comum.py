"""Chamada estruturada ao modelo, registro de cada chamada e descrição das fontes."""

import json
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from po_multiagente.dados import Fontes
from po_multiagente.dominio import TipoColuna
from po_multiagente.llm import LLMPort, Pedido, Uso, esquema_estrito
from po_multiagente.prompts import Instrucao

Saida = TypeVar("Saida", bound=BaseModel)

MAX_VALORES_POR_COLUNA = 12
"""Valores distintos de uma coluna de texto mostrados ao modelo."""


@dataclass(frozen=True)
class RegistroChamada:
    """Uma chamada ao modelo, para custo, reprodutibilidade e dossiê (R5)."""

    agente: str
    modelo: str
    uso: Uso
    parametros: dict[str, Any]
    duracao_s: float
    gravada: bool
    instrucao_sha256: str
    entrada: str
    saida: str
    erro: str | None = None


@dataclass
class Registro:
    """Chamadas acumuladas numa execução."""

    chamadas: list[RegistroChamada] = field(default_factory=list)

    @property
    def uso(self) -> Uso:
        """Uso total de tokens."""
        total = Uso()
        for chamada in self.chamadas:
            total = total + chamada.uso
        return total


class ErroFormato(Exception):
    """Saída do modelo fora do esquema ou recusada pela checagem do código."""


class ErroAgente(Exception):
    """O agente esgotou as tentativas sem produzir saída válida.

    Attributes:
        agente: Nome do agente.
        mensagens: Erro de cada tentativa.
    """

    def __init__(self, agente: str, mensagens: list[str]) -> None:
        super().__init__(f"{agente}: {mensagens[-1] if mensagens else 'sem saída'}")
        self.agente = agente
        self.mensagens = tuple(mensagens)


def gerar_estruturado(
    llm: LLMPort, instrucao: Instrucao, entrada: str, saida: type[Saida], registro: Registro
) -> Saida:
    """Chama o modelo com o esquema estrito de ``saida`` e valida a resposta.

    Raises:
        ErroFormato: Se a resposta não for JSON válido no esquema.
    """
    pedido = Pedido(
        agente=instrucao.agente,
        instrucoes=instrucao.texto,
        entrada=entrada,
        nome_esquema=saida.__name__,
        esquema=esquema_estrito(saida),
    )
    resposta = llm.gerar(pedido)
    erro: str | None = None
    try:
        return saida.model_validate(json.loads(resposta.texto))
    except json.JSONDecodeError as falha:
        erro = f"A resposta não é JSON válido: {falha}"
        raise ErroFormato(erro) from falha
    except ValidationError as falha:
        erro = formatar_erros_validacao(falha)
        raise ErroFormato(erro) from falha
    finally:
        registro.chamadas.append(
            RegistroChamada(
                agente=instrucao.agente,
                modelo=resposta.modelo,
                uso=resposta.uso,
                parametros=resposta.parametros,
                duracao_s=resposta.duracao_s,
                gravada=resposta.gravada,
                instrucao_sha256=instrucao.sha256,
                entrada=entrada,
                saida=resposta.texto,
                erro=erro,
            )
        )


def bloco_json(titulo: str, dados: object) -> str:
    """Seção de entrada com título e JSON indentado."""
    return f"# {titulo}\n\n```json\n{json.dumps(dados, ensure_ascii=False, indent=1)}\n```"


def formatar_erros_validacao(erro: ValidationError) -> str:
    """Erros de validação do Pydantic em uma linha por erro, com o caminho."""
    linhas = []
    for item in erro.errors(include_url=False):
        caminho = ".".join(str(parte) for parte in item["loc"])
        linhas.append(f"- {caminho or 'raiz'}: {item['msg']}")
    return "\n".join(linhas)


def descrever_fontes(fontes: Fontes) -> str:
    """Inventário das fontes para o modelo: colunas, tipos e valores de texto.

    Colunas numéricas aparecem sem valores: o modelo não precisa de números
    para localizar um parâmetro, e não recebê-los impede que os copie.
    """
    blocos = []
    for arquivo in fontes.arquivos:
        for tabela in fontes.tabelas(arquivo):
            linhas = [f"### `{tabela.nome}` ({len(tabela.linhas)} linhas)"]
            for coluna, tipo in zip(tabela.colunas, tabela.tipos, strict=True):
                if tipo in (TipoColuna.INTEIRO, TipoColuna.DECIMAL):
                    linhas.append(f"- `{coluna}` ({tipo.value})")
                    continue
                distintos = list(
                    dict.fromkeys(str(v) for v in tabela.valores(coluna) if v is not None)
                )
                amostra = ", ".join(f"`{v}`" for v in distintos[:MAX_VALORES_POR_COLUNA])
                resto = len(distintos) - MAX_VALORES_POR_COLUNA
                sufixo = f" e mais {resto}" if resto > 0 else ""
                linhas.append(f"- `{coluna}` ({tipo.value}): {amostra}{sufixo}")
            blocos.append("\n".join(linhas))
    return "\n\n".join(blocos)
