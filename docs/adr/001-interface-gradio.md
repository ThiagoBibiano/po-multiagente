# ADR-001: Interface em Gradio

- **Estado:** aceita
- **Data:** 2026-09-25

## Contexto

O usuário final roda a plataforma no Google Colab e precisa subir arquivos,
responder às solicitações de tratamento e inspecionar os artefatos
intermediários (R5). O TG1 descartou o Streamlit por não exibir os objetos do
modelo e deixou a interface "a definir no TG2".

## Decisão

Usar **Gradio** (`gr.Blocks`), exibido dentro do próprio Colab. A interface é
uma camada fina: usa apenas a API pública do pacote e não contém regra de
negócio.

## Consequências

- Gradio exibe nativamente JSON, código, tabelas, LaTeX e upload de arquivos,
  o que atende a R5.
- A dependência é pesada; entra como extra opcional
  (`po-multiagente[interface]`), para que o experimento rode sem ela.
- O TG2 precisa justificar a escolha com o mesmo critério usado para
  descartar o Streamlit.
