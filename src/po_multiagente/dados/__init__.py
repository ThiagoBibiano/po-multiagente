"""Acesso somente leitura às fontes de dados do usuário.

Leitura de CSV/XLSX, inventário de colunas, hash SHA-256 de cada arquivo e
ligação dos valores aos parâmetros. Nunca transforma dados: agregação,
conversão de unidade, junção e preenchimento ficam com o usuário, por meio
das solicitações de tratamento. Implementado na F1.
"""
