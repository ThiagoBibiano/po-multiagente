"""Acesso somente leitura às fontes de dados do usuário.

Leitura de CSV/XLSX, inventário de colunas, hash SHA-256 de cada arquivo e
ligação dos valores aos conjuntos e parâmetros do modelo. Nunca transforma
dados: agregação, conversão de unidade, junção e preenchimento ficam com o
usuário, por meio das solicitações de tratamento; os erros de ligação trazem
o motivo do tratamento necessário.
"""

from po_multiagente.dados.erros import ErroDados, ErroLigacao
from po_multiagente.dados.fontes import EXTENSOES, Fontes, arquivo_da_fonte, sha256_arquivo
from po_multiagente.dados.leitura import Celula, Tabela, ler_csv, ler_xlsx, texto_celula
from po_multiagente.dados.ligacao import Chave, DadosLigados, ligar, membros, valores

__all__ = [
    "EXTENSOES",
    "Celula",
    "Chave",
    "DadosLigados",
    "ErroDados",
    "ErroLigacao",
    "Fontes",
    "Tabela",
    "arquivo_da_fonte",
    "ler_csv",
    "ler_xlsx",
    "ligar",
    "membros",
    "sha256_arquivo",
    "texto_celula",
    "valores",
]
