# Relatório — arquitetura de filas para o `inemacabot`

## 1. Contexto

O sistema em questão é o `inemacabot`.

Ele já possui uma função principal:

- receber mensagens dos usuários;
- interpretar essas mensagens usando inteligência artificial;
- enviar uma resposta.

O que ainda falta é um mecanismo para tratar tarefas demoradas ou pesadas sem bloquear o bot.

Exemplos:

- criar vídeos;
- produzir textos longos;
- gerar arquivos;
- fazer pesquisas profundas;
- executar automações;
- processar documentos;
- chamar agentes externos.

Para resolver isso, o `inemacabot` deve ganhar um sistema de filas.

---

## 2. Arquitetura proposta

```text
inemacabot
│
├── Bot
│   ├── recebe mensagens
│   ├── identifica o usuário
│   ├── interpreta a intenção
│   ├── responde diretamente
│   └── cria jobs
│
├── Banco
│   ├── jobs
│   ├── workers
│   └── entregas
│
├── Fila de vídeos
│   └── worker de vídeos
│       └── agente temporário
│           └── skill
│
├── Fila de textos
│   └── worker de textos
│       └── agente temporário
│           └── skill
│
├── Fila de serviços
│   └── worker de serviços
│       └── agente temporário
│           └── skill
│
└── Watcher
    └── envia o resultado ao usuário
```

---

## 3. Fluxo completo

```text
Usuário envia uma mensagem
→ inemacabot recebe
→ identifica o usuário
→ interpreta o pedido
→ decide entre resposta direta ou tarefa
→ identifica a skill
→ escolhe a fila
→ cria o job
→ responde que o pedido entrou na fila
→ worker captura o job
→ worker inicia um agente temporário
→ agente executa a skill
→ resultado é salvo
→ watcher identifica a conclusão
→ resultado é enviado ao usuário
```

---

## 4. Diferença entre os componentes

### Bot

É o canal de entrada e saída.

Ele conversa com o usuário, interpreta a mensagem, cria tarefas e entrega respostas.

Ele não deve ficar ocupado executando tarefas demoradas.

### Fila

É o local onde os pedidos aguardam processamento.

A fila define:

- ordem;
- prioridade;
- status;
- tentativas;
- posição;
- histórico.

### Job

É uma solicitação individual dentro da fila.

Exemplo:

```text
Criar um vídeo de 60 segundos sobre agentes de IA
```

Esse pedido se torna um job com:

- identificador;
- usuário;
- fila;
- skill;
- dados de entrada;
- status;
- resultado.

### Worker

É um processo permanente que consome jobs.

Ele procura o próximo pedido, bloqueia o job, chama o agente e salva o resultado.

O worker não é a skill.

### Agente temporário

É a instância que executa uma tarefa específica.

Pode ser:

- uma chamada de API;
- uma sessão Claude;
- uma sessão Codex;
- um script Python;
- um script Node;
- outro executor.

### Skill

É a instrução especializada que explica como realizar a tarefa.

Exemplos:

- `video-explicativo`;
- `roteiro`;
- `pesquisa`;
- `transcricao`;
- `book`;
- `relatorio`.

### Watcher

É o componente que verifica quais jobs terminaram e ainda não foram entregues.

Ele evita que o usuário precise ficar consultando o status manualmente.

---

## 5. Filas iniciais

### `videos`

Para atividades como:

- vídeo explicativo;
- vídeo de curso;
- reel;
- edição;
- avatar;
- trailer.

### `textos`

Para atividades como:

- roteiro;
- artigo;
- resumo;
- transcrição;
- dublagem;
- tradução;
- legenda.

### `servicos`

Para atividades como:

- pesquisa;
- análise;
- relatório;
- automação;
- book;
- processamento técnico;
- geração de documentos.

---

## 6. Paralelismo

As três filas podem trabalhar ao mesmo tempo.

```text
videos   → 1 job por vez
textos   → 1 job por vez
servicos → 1 job por vez
```

Isso permite até três tarefas simultâneas, desde que estejam em filas diferentes.

Dentro de cada fila, os jobs são processados sequencialmente.

Exemplo:

```text
Vídeo 1 → executando
Vídeo 2 → aguardando
Vídeo 3 → aguardando
```

Enquanto isso:

```text
Texto 1   → executando
Serviço 1 → executando
```

---

## 7. Resposta direta ou fila

Nem toda mensagem deve virar job.

### Resposta direta

Use quando o pedido for rápido.

Exemplos:

- perguntas simples;
- conversa;
- explicações;
- ajuda;
- dúvidas sobre o sistema.

### Fila

Use quando a atividade:

- demora;
- gera arquivo;
- usa ferramentas externas;
- depende de um agente;
- exige várias etapas;
- pode falhar e precisar de nova tentativa.

---

## 8. Banco de dados

O sistema deve utilizar preferencialmente o banco que já existe no projeto.

Na ausência de um banco adequado, SQLite é suficiente para a primeira versão.

A tabela de jobs deve guardar:

- id;
- fila;
- skill;
- payload;
- usuário;
- chat;
- prioridade;
- status;
- tentativas;
- progresso;
- resultado;
- erro;
- datas;
- lock;
- status da entrega.

A captura do próximo job precisa ser atômica para evitar execução duplicada.

---

## 9. Estados do job

```text
pending    → aguardando
running    → em execução
completed  → concluído
failed     → falhou
cancelled  → cancelado
```

Também deve existir o estado da entrega:

```text
pending    → ainda não entregue
 delivered  → entregue
 failed     → tentativa de entrega falhou
```

---

## 10. Registro de skills

As skills devem ficar em um registro central.

Exemplo:

```text
config/skills.json
```

Cada skill deve informar:

- nome;
- fila;
- descrição;
- campos obrigatórios;
- se está habilitada;
- executor usado.

O sistema não deve inventar skills.

Se uma skill não existir, o usuário deve receber uma mensagem clara informando que a função ainda não está disponível.

---

## 11. Workers separados

A recomendação é executar cada worker como um processo independente:

```text
inemacabot-video-worker
inemacabot-text-worker
inemacabot-service-worker
```

Vantagens:

- uma fila pode falhar sem derrubar as outras;
- o bot continua respondendo;
- cada worker pode ser reiniciado separadamente;
- é fácil aumentar a capacidade futuramente;
- logs e erros ficam mais organizados.

---

## 12. Watcher separado

O watcher também pode ser um processo independente.

Funções:

- localizar jobs concluídos;
- montar a mensagem de resultado;
- enviar para o canal correto;
- marcar como entregue;
- repetir a entrega quando houver falha;
- evitar duplicidade.

---

## 13. Recuperação de falhas

O sistema deve sobreviver a reinícios.

Na inicialização, o worker deve verificar jobs que ficaram como `running`.

Caso o processo não exista mais ou o lock tenha expirado:

- liberar o lock;
- incrementar a tentativa;
- recolocar como `pending`;
- ou marcar como `failed` quando atingir o limite.

Nenhum job deve ficar travado para sempre.

---

## 14. Retry

Quando um job falhar, o sistema pode tentar novamente.

Exemplo:

```text
1ª falha → aguardar 30 segundos
2ª falha → aguardar 2 minutos
3ª falha → falha definitiva
```

O número máximo de tentativas deve ser configurável.

---

## 15. Prioridades

Sugestão:

```text
0  = normal
10 = alta
20 = urgente
```

A escolha deve seguir:

```text
maior prioridade primeiro
→ em caso de empate, job mais antigo primeiro
```

A prioridade não deve ficar livre para qualquer usuário alterar.

---

## 16. Segurança

O sistema deve evitar:

- execução de comandos montados com concatenação;
- exposição de `.env`;
- gravação de chaves no job;
- mistura de arquivos de usuários diferentes;
- envio do resultado para o usuário errado;
- execução duplicada;
- acesso de um usuário aos jobs de outro.

Cada job deve possuir uma pasta isolada.

```text
data/jobs/<job-id>/
```

---

## 17. Comandos recomendados

```text
/status
/filas
/meusjobs
/job <id>
/cancelar <id>
/repetir <id>
/skills
/ajuda
```

O usuário deve consultar somente os próprios jobs.

---

## 18. Serviços recomendados

```text
inemacabot.service
inemacabot-video-worker.service
inemacabot-text-worker.service
inemacabot-service-worker.service
inemacabot-watcher.service
```

O bot deve continuar ativo mesmo quando um worker estiver fora do ar.

---

## 19. Estratégia recomendada de implementação

A implantação deve ser incremental.

### Fase 1 — diagnóstico

Analisar o sistema atual sem alterar a arquitetura.

### Fase 2 — núcleo da fila

Criar:

- modelo de job;
- tabela;
- repository;
- registro de skills;
- roteador.

### Fase 3 — primeira fila

Começar apenas com:

```text
servicos
```

Criar uma skill simples chamada:

```text
teste-fila
```

Ela deve aguardar 10 segundos, gerar um arquivo e devolver o resultado.

### Fase 4 — outras filas

Após validar o ciclo completo, adicionar:

- `videos`;
- `textos`.

### Fase 5 — operação

Adicionar:

- systemd ou Docker;
- health check;
- logs;
- retry;
- recuperação;
- cancelamento;
- testes.

---

## 20. Teste mínimo de validação

O teste inicial deve comprovar:

```text
mensagem
→ criação do job
→ persistência
→ captura pelo worker
→ execução
→ conclusão
→ watcher
→ entrega ao usuário
```

Também deve comprovar que:

- o bot permanece responsivo;
- reiniciar o worker não perde o job;
- o resultado não é entregue duas vezes;
- um usuário não acessa tarefas de outro;
- duas filas diferentes podem trabalhar simultaneamente.

---

## 21. Conclusão

O `inemacabot` deve continuar sendo o atendente e coordenador.

Ele não precisa executar tudo diretamente.

A divisão correta é:

```text
Bot entende e coordena
Fila organiza
Worker controla
Agente executa
Skill orienta
Watcher entrega
```

A melhor estratégia é começar com uma única fila chamada `servicos` e uma skill de teste. Depois que o ciclo estiver funcionando, a mesma estrutura pode ser expandida para vídeos e textos com menor risco.
