# Organizador de Projetos

Sistema cliente-servidor para organizar projetos em fases e tarefas, com dependências, progresso em percentual e uso simultâneo por várias pessoas em computadores diferentes.

Trabalho da disciplina **Paradigmas de Programação** (Faculdade Impacta, turma CC5AN), professor Alex Torquato.

**Equipe 11:** Filipe Decio Demarco e Vinicius Rodrigues Cordeiro.

## O que tem aqui

- `modulo_servidor/`: servidor em Flask (regras, validações e gravação em arquivo JSON).
- `modulo_cliente/`: cliente com interface gráfica em PyQt6.
- `dados/`: arquivos JSON do sistema (`usuarios.json` e `projetos.json`).
- `testes/`: testes automatizados do servidor.
- [`DOCUMENTACAO.md`](DOCUMENTACAO.md): requisitos funcionais e não funcionais, diagramas de classes do cliente e do servidor, condições de aceitação e plano de testes.

Padrões de projeto usados: **Builder** (criacional), **Composite** (estrutural) e **Mediator** (comportamental).

## Requisitos

- Python 3.10 ou superior (testado com 3.14).
- Bibliotecas: Flask e PyQt6, listadas em `requirements.txt`.

Não há banco de dados, APIs de terceiros, serviços de nuvem ou serviços de IA.

## Instalação

Na pasta do projeto:

```
python -m pip install -r requirements.txt
```

## Como executar

**1. Servidor** (em uma máquina):

```
python modulo_servidor/app.py
```

O servidor mostra no terminal o endereço em que está rodando. Os dados ficam em `dados/projetos.json`.

**2. Cliente** (em cada máquina que for usar o sistema):

```
python modulo_cliente/main.py
```

Na tela de entrada, digite seu nome. O campo **Servidor** é preenchido sozinho quando o cliente encontra o servidor na rede local. Se não encontrar, digite o endereço mostrado no terminal do servidor (exemplo: `192.168.1.10:5000`).

Para testar em uma única máquina, rode o servidor e o cliente nela mesma. Para testar a colaboração, abra dois clientes.

## Quem pode entrar

Só entram os nomes cadastrados em `dados/usuarios.json`. Para liberar uma pessoa, acrescente o nome (exatamente como será digitado, com as mesmas letras maiúsculas e minúsculas) na lista `usuarios` desse arquivo. Não precisa reiniciar o servidor.

## Usando em duas máquinas

1. Conecte as duas máquinas na mesma rede.
2. Na máquina do servidor, libere o servidor no firewall do Windows (prompt de comando como administrador):

```
netsh advfirewall firewall add rule name="Organizador servidor" dir=in action=allow protocol=TCP localport=5000
netsh advfirewall firewall add rule name="Organizador descoberta" dir=in action=allow protocol=UDP localport=5001
```

3. Inicie o servidor nessa máquina e o cliente na outra.

Se a rede bloquear a descoberta automática, o campo Servidor mostra "Nenhum servidor encontrado"; nesse caso, digite o endereço que aparece em "Para outras máquinas" no terminal do servidor.

## Testes

```
python -m unittest discover testes -v
```

Executa os 25 testes do servidor (projetos, hierarquia, percentual, dependências, colaboração e acesso). Os testes não alteram `dados/projetos.json`.

## Como usar o sistema

1. Entre com seu nome.
2. **Criar Projeto**: informe nome, descrição, responsável e as pessoas envolvidas com cargo.
3. Selecione o projeto e clique em **Abrir Projeto** (ou dê dois cliques).
4. **Criar Fase**, depois selecione a fase e clique em **Criar Tarefa**. Toda tarefa fica dentro de uma fase.
5. **Avançar Status** sobe a tarefa de 10 em 10 pontos até 100%. Fases e projeto mostram a média.
6. **Dependência** liga uma tarefa à tarefa da qual ela depende; ciclos são recusados.
7. Se outra pessoa alterar o mesmo projeto antes de você salvar, o sistema avisa o conflito e você recarrega antes de tentar de novo.

## Roteiro de teste rápido (para conferir o sistema)

Use dois terminais, ambos na pasta do projeto.

1. **Testes automatizados:** `python -m unittest discover testes -v` deve terminar com `Ran 25 tests ... OK`.
2. **Servidor:** `python modulo_servidor/app.py`. O terminal mostra os endereços e a frase "Os clientes na mesma rede encontram este servidor sozinhos".
3. **Cliente:** `python modulo_cliente/main.py` em outro terminal. O campo **Servidor** aparece preenchido como "Servidor".
4. **Acesso:** digite um nome inventado e clique OK: o sistema recusa e a janela continua aberta. Depois entre com um nome de `dados/usuarios.json`.
5. **Projeto:** clique em Criar Projeto, informe só o nome e conclua. Depois tente criar um sem nome: o sistema avisa o motivo.
6. **Hierarquia:** abra o projeto, use Criar Fase, selecione a fase e use Criar Tarefa. Tentar criar uma tarefa sem fase é recusado.
7. **Progresso:** selecione uma tarefa e clique em Avançar Status várias vezes. Sobe de 10 em 10 até 100%, e a fase e o projeto mostram a média.
8. **Dependência:** crie uma dependência entre duas tarefas. Tente uma da tarefa com ela mesma ou que feche um ciclo: o sistema recusa.
9. **Colaboração:** abra um segundo cliente (outro terminal, outro nome). Uma alteração feita em um aparece no outro em poucos segundos.
10. **Conflito:** com os dois clientes no mesmo projeto, altere nos dois sem esperar a atualização. O segundo a salvar recebe o aviso "O projeto foi alterado por ... Recarregue antes de salvar.".
11. **Persistência:** feche o servidor (Ctrl+C), suba de novo e abra o cliente: os dados continuam.
12. **Sem servidor:** com o servidor desligado, o cliente mostra "sem conexão com servidor" sem travar.
