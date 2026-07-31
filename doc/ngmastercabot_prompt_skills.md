# Prompt para implementação das Skills de Transcrição e Criação de Sites/Blogs no `ngmastercabot`

## Missão

Você está trabalhando no projeto `ngmastercabot`. O sistema de filas, workers, roteador e watcher já foi implementado. 

Sua missão agora é **criar e integrar duas novas skills** ao sistema:
1. **Transcrição de Vídeos / Áudios** (na fila de textos ou serviços adequada).
2. **Criação de Sites e Blogs** (na fila de serviços).

---

## Regras obrigatórias

- Siga exatamente a mesma arquitetura de skills, agentes e workers já estabelecida no projeto.
- Não quebre o funcionamento atual das filas.
- Utilize diretórios isolados (`data/jobs/<job-id>/`) para a execução das tarefas de cada job.
- Mantenha a segurança na execução de processos externos (utilize `spawn` com argumentos separados, nunca concatene strings de usuários diretamente no shell).

---

## Detalhes das Skills a Serem Criadas

### 1. Skill: `transcricao-video`
* **Fila de destino:** `textos` (ou `servicos`, conforme a convenção do projeto).
* **Campos obrigatórios no payload:** `url` ou arquivo de áudio/vídeo enviado pelo usuário.
* **Comportamento esperado do Agente/Executor:**
  - Baixar ou acessar o arquivo de mídia dentro da pasta isolada do job (`data/jobs/<job-id>/files/`).
  - Executar a ferramenta de transcrição (ex: Whisper via API ou script Python local configurado no ambiente).
  - Gerar um arquivo de texto limpo (`transcricao.txt` ou `output.json`) com o conteúdo transcrito.
  - Marcar o job como concluído para que o watcher entregue o texto/arquivo ao usuário.

### 2. Skill: `criacao-site-blog`
* **Fila de destino:** `servicos`.
* **Campos obrigatórios no payload:** `tema`, `tipo` (ex: landing page, blog post, site estático), `instrucoes_extras` (opcional).
* **Comportamento esperado do Agente/Executor:**
  - Iniciar uma sessão de agente temporário na pasta de trabalho isolada do job.
  - Gerar a estrutura de arquivos do site/blog (ex: `index.html`, arquivos de estilo CSS, ou arquivos Markdown para blogs).
  - Compactar os arquivos gerados em um arquivo `.zip` ou disponibilizar a estrutura pronta na pasta de output.
  - Marcar o job como concluído para que o watcher envie o resultado final (arquivo ou link/resumo) ao usuário no Telegram.

---

## Tarefas de Implementação

1. **Atualizar o Registro de Skills (`config/skills.json` ou arquivo equivalente):**
   - Adicionar `transcricao-video` e `criacao-site-blog` com suas respectivas descrições, filas e campos obrigatórios.

2. **Implementar os Executors / Scripts das Skills:**
   - Criar ou ajustar os scripts executores em `src/agents/` ou na pasta de skills dedicada para processar a transcrição e a geração de código/conteúdo de sites.

3. **Validar o Fluxo no Bot:**
   - Garantir que o parser de intenções consiga reconhecer pedidos relacionados a transcrição de vídeos e criação de sites/blogs, direcionando corretamente para as respectivas filas.

4. **Criar Testes Automatizados:**
   - Adicionar testes simulando a criação e execução dessas duas novas skills para garantir que o worker processa e o watcher entrega sem erros.
