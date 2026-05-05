import os
import requests


def get_tiny_token():
    token = os.getenv("TINY_TOKEN")
    if not token:
        raise Exception("TINY_TOKEN não configurado")
    return token


def buscar_produtos_tiny():
    token = get_tiny_token()
    url = "https://api.tiny.com.br/api2/produtos.pesquisa.php"

    todos_produtos = []
    pagina = 1

    while True:
        params = {
            "token": token,
            "formato": "JSON",
            "pagina": pagina
        }

        response = requests.get(url, params=params, timeout=30)

        if response.status_code != 200:
            raise Exception(f"Erro Tiny pesquisa página {pagina}: {response.text}")

        data = response.json()
        retorno = data.get("retorno", {})

        if retorno.get("status") != "OK":
            raise Exception(f"Erro Tiny pesquisa página {pagina}: {retorno}")

        produtos = retorno.get("produtos", [])

        if not produtos:
            break

        for item in produtos:
            p = item.get("produto", {})

            todos_produtos.append({
                "tiny_id": p.get("id"),
                "nome": p.get("nome"),
                "sku": p.get("codigo"),
                "preco": p.get("preco"),
                "estoque": p.get("estoqueAtual")
            })

        numero_paginas = int(retorno.get("numero_paginas", 1))

        if pagina >= numero_paginas:
            break

        pagina += 1

    return todos_produtos


def obter_produto_tiny(tiny_id: str):
    token = get_tiny_token()
    url = "https://api.tiny.com.br/api2/produto.obter.php"

    params = {
        "token": token,
        "id": tiny_id,
        "formato": "JSON"
    }

    response = requests.get(url, params=params, timeout=30)

    if response.status_code != 200:
        raise Exception(f"Erro Tiny obter produto {tiny_id}: {response.text}")

    data = response.json()
    retorno = data.get("retorno", {})

    if retorno.get("status") != "OK":
        raise Exception(f"Erro Tiny produto {tiny_id}: {retorno}")

    produto = retorno.get("produto", {})

    # =========================
# IMAGEM (TRATAMENTO COMPLETO)
# =========================
imagem_url = None
anexos = produto.get("anexos")

if isinstance(anexos, list) and len(anexos) > 0:
    primeiro = anexos[0]

    if isinstance(primeiro, dict):
        anexo = primeiro.get("anexo")

        if isinstance(anexo, dict):
            imagem_url = anexo.get("url")

elif isinstance(anexos, dict):
    lista = anexos.get("anexo")

    if isinstance(lista, list) and len(lista) > 0:
        primeiro = lista[0]

        if isinstance(primeiro, dict):
            imagem_url = primeiro.get("url")

if not imagem_url:
    imagem_url = produto.get("imagem") or produto.get("urlImagem")
    # =========================
    # CATEGORIA (TRATAMENTO SEGURO)
    # =========================
    categoria = produto.get("categoria")

    if isinstance(categoria, dict):
        categoria_nome = categoria.get("nome")
    else:
        categoria_nome = categoria

    # =========================
    # RETURN FINAL
    # =========================
    return {
        "tiny_id": tiny_id,
        "nome": produto.get("nome"),
        "sku": produto.get("codigo"),
        "preco": produto.get("preco"),
        "estoque": produto.get("estoqueAtual"),
        "peso": produto.get("peso_bruto") or produto.get("peso_liquido"),
        "comprimento": produto.get("comprimento"),
        "largura": produto.get("largura"),
        "altura": produto.get("altura"),
        "categoria": categoria_nome,
        "ncm": produto.get("ncm"),
        "descricao": produto.get("descricao_complementar"),
        "imagem_url": imagem_url
    }
