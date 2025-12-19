# Fazenda Comunitária (MVP)

Componentes básicos:
- `server.py`: servidor TCP simples com protocolo NDJSON (hello, welcome, pos, state).
- `game.py`: cliente Pygame com menu (Conectar/Offline), click-to-move e renderização de outros jogadores.

## Como rodar

### 1) Iniciar servidor
```powershell
python server.py
```

### 2) Iniciar cliente
```powershell
python game.py
```

- Clique em **Conectar** para entrar no servidor local (localhost:12345) ou **Offline** para jogar sem conexão.
- Clique no mapa para mover seu jogador. Outros jogadores conectados aparecerão com cores diferentes.

## Controles
- Menu: ↑/↓ para selecionar, Enter/Espaço para confirmar, Esc para sair.
- Jogo (Desktop):
	- Arraste com botão ESQUERDO no joystick esquerdo (canto inferior esquerdo) para mover.
	- Arraste com botão DIREITO no joystick direito (canto inferior direito) para mirar e atirar.
- Jogo (Mobile/Touch):
	- Arraste no joystick esquerdo para movimentar.
	- Arraste no joystick direito para mirar e atirar.

## Protocolo
- `hello { name, x, y }`: enviado pelo cliente ao conectar.
- `welcome { id }`: enviado pelo servidor com id do cliente.
- `pos { x, y }`: enviado pelo cliente ao se mover.
- `state { players }`: broadcast periódico do servidor com posições e cores de todos.

## Notas de confiabilidade
- Mensagens são delimitadas por `\n` e serializadas com JSON padrão.
- Threads dedicadas para clientes e para broadcast; acesso compartilhado protegido por lock.
- Desconexões removem o jogador do estado sem causar erros.
