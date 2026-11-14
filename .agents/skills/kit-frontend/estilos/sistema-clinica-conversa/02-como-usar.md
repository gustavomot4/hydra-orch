## Como usar

1. Copie este arquivo para a raiz do projeto com o nome `PRD-FRONTEND.md`.
2. Preencha a tabela abaixo no próprio arquivo, trocando a coluna "Valor".
3. Peça ao agente: "Siga `PRD-FRONTEND.md`. Antes de entregar, rode o checklist de aceite e diga o resultado de cada item."

| O que | Valor | Onde aparece |
| --- | --- | --- |
| Nome do produto, em duas palavras | Vila Serena | Barra superior e tela Entrar: a primeira palavra em `--foreground`, a segunda em `--primary`. Título da aba: `<Tela> — <Nome>`. |
| Sigla, duas letras | VS | Só o ícone da aba: a sigla em `--primary`, `--weight-extrabold`, direto sobre o fundo da aba, sem quadrado nem círculo atrás. Na interface a marca é o nome em duas palavras (linha acima), nunca iniciais dentro de uma forma colorida. |
| Cor de marca | manter `#0D6E66` | Se trocar, troque juntos `--primary`, `--primary-hover`, `--primary-soft`, `--primary-soft-hover` e `--on-primary-muted` (o `--ring` acompanha) e refaça as linhas dessas cores na tabela de contraste da seção 9. `--primary-foreground` sobre a nova `--primary` precisa dar pelo menos 4,5:1. |
| Nomes das situações | Agendado, Confirmado, Em atendimento, Concluído, Cancelado, Faltou | Seção 4.3. Mantenha seis, na mesma ordem e com a mesma forma. |
| Perfis | Responsável e Recepção | Seção 5.2. A Recepção não vê o Painel nem as áreas financeiras. |
