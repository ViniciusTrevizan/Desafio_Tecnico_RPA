# Imagens de referência (Fakturama)

Recortes PNG da tela usados pelo reconhecimento de imagem do consumer.
Capture-os **na mesma resolução/tema** em que o robô vai rodar
(ex.: `gnome-screenshot -a` ou Flameshot) e salve com os nomes abaixo
(definidos em `config/settings.py → IMAGENS`):

| Arquivo                         | O que recortar                                          |
|---------------------------------|---------------------------------------------------------|
| fakturama_janela_principal.png  | Trecho fixo da janela principal (ex.: logo/barra)       |
| btn_novo_contato.png            | Botão "Novo contato" da barra de ferramentas            |
| btn_novo_produto.png            | Botão "Novo produto" da barra de ferramentas            |
| nav_contatos.png                | Item "Contatos" do menu de navegação lateral            |
| nav_produtos.png                | Item "Produtos" do menu de navegação lateral            |
| campo_contato_nome.png          | Rótulo "Nome" no editor de contato                      |
| campo_contato_sobrenome.png     | Rótulo "Sobrenome" no editor de contato                 |
| campo_contato_cep.png           | Rótulo "CEP" no editor de contato                       |
| campo_produto_numero.png        | Rótulo "Número do item" no editor de produto            |
| campo_produto_nome.png          | Rótulo "Nome" no editor de produto                      |
| campo_produto_descricao.png     | Rótulo "Descrição" + canto da caixa multilinha (o título de seção "Description" no topo do editor tem o mesmo texto) |
| campo_produto_preco.png         | Rótulo "Preço" no editor de produto                     |

Recorte **apenas o rótulo** dos campos: para imagens `campo_*` o robô clica
`OFFSET_CAMPO_X` pixels à direita da **borda direita** do rótulo (não no rótulo)
para cair dentro da caixa de texto. Ajuste esse valor se necessário.
