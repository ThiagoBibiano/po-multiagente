"""Quadro de especificação: saída do Interpretador e documento que o usuário lê."""

from enum import StrEnum

from pydantic import Field, model_validator

from po_multiagente.dominio._base import (
    Identificador,
    ObjetoDominio,
    TextoNaoVazio,
    exigir_declarados,
    exigir_unicos,
)
from po_multiagente.dominio.fontes import FonteDados, Origem
from po_multiagente.dominio.requisitos import AlertaAmbiguidade, Requisito
from po_multiagente.dominio.solicitacoes import Solicitacao


class Sentido(StrEnum):
    """Sentido da otimização."""

    MINIMIZAR = "minimizar"
    MAXIMIZAR = "maximizar"


class Parametro(ObjetoDominio):
    """Grandeza conhecida do problema, com unidade e origem declaradas.

    A unidade alimenta o sinal S2 e a origem, o sinal S3. Use
    ``"adimensional"`` quando não houver unidade.
    """

    id: Identificador
    descricao: TextoNaoVazio
    unidade: TextoNaoVazio
    origem: Origem


class Especificacao(ObjetoDominio):
    """Quadro de especificação do problema, em linguagem de negócio.

    Segue a modelagem conceitual de Robinson (2008): separa premissas de
    simplificações, e ``nao_considerado`` torna visíveis as simplificações.
    """

    decisao: TextoNaoVazio
    criterio: TextoNaoVazio
    sentido: Sentido
    requisitos: tuple[Requisito, ...] = Field(min_length=1)
    parametros: tuple[Parametro, ...]
    fontes: tuple[FonteDados, ...]
    solicitacoes: tuple[Solicitacao, ...] = ()
    premissas: tuple[TextoNaoVazio, ...] = ()
    nao_considerado: tuple[TextoNaoVazio, ...] = ()
    alertas: tuple[AlertaAmbiguidade, ...] = ()

    @model_validator(mode="after")
    def _referencias_consistentes(self) -> "Especificacao":
        exigir_unicos((r.id for r in self.requisitos), "Requisitos")
        exigir_unicos((p.id for p in self.parametros), "Parâmetros")
        exigir_unicos((f.arquivo for f in self.fontes), "Arquivos")
        exigir_unicos((s.id for s in self.solicitacoes), "Solicitações")
        exigir_declarados(
            (p.origem.arquivo for p in self.parametros),
            (f.arquivo for f in self.fontes),
            "Arquivos de origem",
        )
        exigir_declarados(
            (p.origem.solicitacao_id for p in self.parametros if p.origem.solicitacao_id),
            (s.id for s in self.solicitacoes),
            "Solicitações de origem",
        )
        exigir_declarados(
            (s.parametro_id for s in self.solicitacoes),
            (p.id for p in self.parametros),
            "Parâmetros das solicitações",
        )
        exigir_declarados(
            (a.requisito_id for a in self.alertas if a.requisito_id),
            (r.id for r in self.requisitos),
            "Requisitos dos alertas",
        )
        return self
