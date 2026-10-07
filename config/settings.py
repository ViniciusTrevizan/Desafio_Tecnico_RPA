"""Configurações centrais do RPA (URLs, caminhos, timeouts e imagens de referência).

Valores sensíveis ao ambiente podem ser sobrescritos por variáveis de ambiente.
"""
import os
from pathlib import Path

# ── Caminhos ─────────────────────────────────────────────────────────────────
RAIZ = Path(__file__).resolve().parent.parent
PASTA_RESULTADOS = RAIZ / "resultados"
PASTA_IMAGENS = RAIZ / "assets" / "imagens"

# ── Automação web (producer) ─────────────────────────────────────────────────
URL_GERADOR_IDENTIDADE = "https://www.fakenamegenerator.com/gen-random-br-br.php"
URL_SAUCEDEMO = "https://www.saucedemo.com/"
NAVEGADOR_HEADLESS = os.getenv("RPA_HEADLESS", "false").lower() == "true"
TIMEOUT_WEB_MS = int(os.getenv("RPA_TIMEOUT_WEB_MS", "30000"))

# ── Automação desktop (consumer) ─────────────────────────────────────────────
FAKTURAMA_EXECUTAVEL = os.getenv("FAKTURAMA_EXE", "/opt/Fakturama2/Fakturama")
FAKTURAMA_JANELA = "Fakturama"     # classe (Linux) / início do título (Windows) da janela principal
ESPERA_APOS_MAXIMIZAR = 1.0
TIMEOUT_ABERTURA_APP = 90          # segundos aguardando a janela principal
TIMEOUT_IMAGEM = 15                # segundos procurando uma imagem na tela
CONFIANCA_IMAGEM = 0.85            # similaridade mínima (OpenCV)
PAUSA_ENTRE_ACOES = 0.3            # pausa padrão do pyautogui entre comandos
ESPERA_APOS_SALVAR = 1.5
OFFSET_CAMPO_X = 40                # px à direita da borda do rótulo "campo_*" onde fica a caixa de texto
SEPARADOR_DECIMAL_FAKTURAMA = ","  # Fakturama em pt-BR usa vírgula

# Imagens de referência (recortes da tela salvos em assets/imagens)
IMAGENS = {
    "app_pronto":             "fakturama_janela_principal.png",
    "btn_novo_contato":       "btn_novo_contato.png",
    "btn_novo_produto":       "btn_novo_produto.png",
    "nav_contatos":           "nav_contatos.png",
    "nav_produtos":           "nav_produtos.png",
    "campo_contato_nome":     "campo_contato_nome.png",
    "campo_contato_sobrenome": "campo_contato_sobrenome.png",
    "campo_contato_cep":      "campo_contato_cep.png",
    "campo_produto_numero":   "campo_produto_numero.png",
    "campo_produto_nome":     "campo_produto_nome.png",
    "campo_produto_descricao": "campo_produto_descricao.png",
    "campo_produto_preco":    "campo_produto_preco.png",
}

# ── Resiliência ──────────────────────────────────────────────────────────────
TENTATIVAS_POR_ITEM = 3
ESPERA_ENTRE_TENTATIVAS = 2

# ── Saída ────────────────────────────────────────────────────────────────────
CSV_DELIMITADOR = ";"
CSV_ENCODING = "utf-8-sig"         # BOM para abrir corretamente no Excel
NIVEL_LOG_CONSOLE = os.getenv("RPA_LOG_LEVEL", "INFO")
