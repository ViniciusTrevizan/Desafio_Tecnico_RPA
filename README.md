# Desafio RPA — Sauce Demo → Fakturama

Robô que gera um comprador fake, coleta o catálogo completo do Sauce Demo (**automação web**)
e cadastra comprador e produtos no Fakturama (**automação desktop**), produzindo CSVs, prints e logs.

## Arquitetura: Producer / Consumer

```
 PRODUCER (web · Playwright)                     CONSUMER (desktop · pyautogui + OpenCV)
 ─────────────────────────────                   ──────────────────────────────────────────
 1. fakenamegenerator → Comprador                5. Abre Fakturama
 2. Sauce Demo login                ─ CSVs ─▶    6. Para cada item da fila:
 3. Raspagem do catálogo            ─ fila ─▶       contato → cadastrar_contato()
 4. comprador.csv / catalogo.csv                    produto → cadastrar_produto()
    fila.json (1 item por registro)              7. Prints das listas + resumo.json
```

A fila (`fila.json`) guarda o status de cada item (`PENDENTE`, `SUCESSO`, `FALHA_NEGOCIO`,
`FALHA_SISTEMA`). Isso permite rodar as etapas separadamente e retomar uma execução interrompida.

## Estrutura

```
desafio/
├── main.py                      # orquestrador (CLI)
├── config/settings.py           # URLs, timeouts, caminhos, imagens de referência
├── assets/imagens/              # recortes PNG usados pelo reconhecimento de imagem
├── src/
│   ├── core/
│   │   ├── logger.py            # logs separados + console colorido
│   │   ├── decorators.py        # @log_etapa (início/fim/duração) e @com_retry
│   │   ├── evidencias.py        # prints: tela(), navegador(), erro()
│   │   ├── fila.py              # fila de trabalho em JSON
│   │   ├── contexto.py          # pastas da execução
│   │   ├── excecoes.py          # BusinessException × SystemException
│   │   └── relatorio.py         # conferência CSV × cadastrados
│   ├── models/entidades.py      # Comprador, Produto (+ validação)
│   ├── producer/                # navegador, gerador_identidade, saucedemo, producer
│   ├── consumer/                # desktop (primitivas), fakturama (ações), consumer
│   └── utils/csv_handler.py
├── tests/                       # testes unitários (pytest), um arquivo por módulo
└── resultados/<data_hora>/      # saída de cada execução
    ├── csv/      comprador.csv, catalogo.csv
    ├── prints/   01_gerador_identidade_…png, …, lista_contatos, lista_produtos
    ├── logs/     execucao.log, producer.log, consumer.log, erros.log
    ├── fila.json
    └── resumo.json
```

## Logs

| Arquivo        | Conteúdo                                         |
|----------------|--------------------------------------------------|
| execucao.log   | Tudo, item a item                                |
| producer.log   | Apenas a etapa web                               |
| consumer.log   | Apenas a etapa desktop                           |
| erros.log      | WARNING ou acima, com traceback                  |

Formato: `data hora | nível | componente | arquivo:linha | função() | mensagem`

```
2026-10-07 09:12:03 | INFO     | producer | saucedemo.py:52              | coletar_catalogo()             | ▶ INÍCIO | Percorre todos os produtos da vitrine...
2026-10-07 09:12:03 | INFO     | producer | saucedemo.py:71              | coletar_catalogo()             | [1/6] Coletado: #1 'Sauce Labs Backpack' — $ 29.99
2026-10-07 09:12:41 | INFO     | consumer | fakturama.py:66              | cadastrar_produto()            |   • Preço      ← '29,99'
2026-10-07 09:12:43 | INFO     | consumer | consumer.py:66               | _processar_item()              | [1/6] produto 'Sauce Labs Backpack' (id=a1b2c3d4, tentativa 1) → ✔ SUCESSO
```

Funções com `@log_etapa` registram automaticamente INÍCIO, FIM e FALHA. A descrição vem da docstring.

## Instalação

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
sudo apt install python3-tk python3-dev xclip   # dependências do pyautogui/pyperclip no Linux
```

* Fakturama: instale em <https://www.fakturama.info> e aponte `FAKTURAMA_EXE` para o executável.
* A sessão gráfica precisa ser **X11** (no login, escolha "Ubuntu on Xorg"). No Wayland o pyautogui não funciona.
* Capture as imagens de referência conforme [assets/imagens/README.md](assets/imagens/README.md).

## Execução

```bash
python main.py                                    # completo
python main.py --etapa producer                   # só web
python main.py --etapa consumer                   # só desktop (última execução)
python main.py --etapa consumer --run-id <id> --reprocessar-falhas
```

Variáveis de ambiente: `FAKTURAMA_EXE`, `RPA_HEADLESS=true`, `RPA_LOG_LEVEL=DEBUG`, `NO_COLOR=1`.
Para abortar o robô, mova o mouse para o canto superior esquerdo da tela (failsafe do pyautogui).

## Testes

Testes unitários (pytest) escritos a partir do enunciado: cada função tem testes que verificam o que
o PDF exige dela. Navegador, tela, mouse e teclado são simulados — a suíte roda em segundos, sem
internet, sem Fakturama e sem sessão gráfica.

```bash
pip install -r requirements-dev.txt
python -m pytest                                                    # suíte completa
python -m pytest --cov=src --cov=config --cov=main --cov-report=term-missing
```

| Requisito do PDF                                        | Testes                                       |
|---------------------------------------------------------|----------------------------------------------|
| §4.1 Comprador fake (nome, sobrenome, CEP)              | test_gerador_identidade, test_entidades      |
| §4.2 Login com as credenciais da própria página         | test_saucedemo                               |
| §4.3 Catálogo completo (número, nome, descrição, preço) | test_saucedemo                               |
| §4.4 CSVs como ponte web → desktop                      | test_csv_handler, test_producer, test_fila   |
| §4.5/§4.6 Cadastro por imagem + atalhos de teclado      | test_desktop, test_fakturama, test_consumer  |
| §4.7/§5 Prints, log e pasta de resultados               | test_evidencias, test_logger, test_contexto  |
| §6 Web × desktop batem 100%, tratamento de erros        | test_relatorio, test_decorators, test_main   |
