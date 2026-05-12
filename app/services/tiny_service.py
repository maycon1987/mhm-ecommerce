import os
import requests
import time


def get_tiny_token():
    token = os.getenv("TINY_TOKEN")
    if not token:
        raise Exception("TINY_TOKEN não configurado")
    return token


def buscar_produtos_tiny():
    """
    Busca todos os produtos do Tiny com todos os campos necessários.
    Para produtos sem categoria na pesquisa, busca o detalhe individual.
    """
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
            break

        produtos = retorno.get("produtos", [])

        if not produtos:
            break

        for item in produtos:
            if not isinstance(item, dict):
                continue

            p = item.get("produto", {})

            if not isinstance(p, dict):
                continue

            imagem_url = _extrair_imagem(p)
            categoria = (p.get("categoria") or "").strip()

            # Se não veio categoria na pesquisa, busca o detalhe individual
            if not categoria and p.get("id"):
                try:
                    time.sleep(0.1)  # Evita rate limit
                    detalhe = obter_produto_tiny(str(p.get("id")))
                    categoria = (detalhe.get("categoria") or "").strip()
                    if not imagem_url:
                        imagem_url = detalhe.get("imagem_url")
                except Exception:
                    pass

            todos_produtos.append({
                "tiny_id":     p.get("id"),
                "nome":        p.get("nome"),
                "sku":         p.get("codigo"),
                "preco":       p.get("preco"),
                "preco_varejo": p.get("preco"),
                "estoque":     p.get("estoqueAtual"),
                "imagem_url":  imagem_url,
                "categoria":   categoria,
                "peso":        p.get("peso_bruto") or p.get("peso"),
                "largura":     p.get("largura"),
                "altura":      p.get("altura"),
                "comprimento": p.get("comprimento"),
            })

        numero_paginas = int(retorno.get("numero_paginas", 1))

        if pagina >= numero_paginas:
            break

        pagina += 1

    return todos_produtos


def _extrair_imagem(produto: dict):
    """Extrai URL da imagem principal de um produto do Tiny."""
    anexos = produto.get("anexos") or []

    if isinstance(anexos, list) and len(anexos) > 0:
        primeiro = anexos[0]
        if isinstance(primeiro, dict):
            anexo = primeiro.get("anexo")
            if isinstance(anexo, str):
                return anexo
            elif isinstance(anexo, dict):
                return anexo.get("url")

    elif isinstance(anexos, dict):
        anexo = anexos.get("anexo")
        if isinstance(anexo, str):
            return anexo
        elif isinstance(anexo, list) and len(anexo) > 0:
            primeiro = anexo[0]
            if isinstance(primeiro, str):
                return primeiro
            elif isinstance(primeiro, dict):
                return primeiro.get("url")
        elif isinstance(anexo, dict):
            return anexo.get("url")

    return produto.get("imagem") or produto.get("urlImagem")


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
    imagem_url = _extrair_imagem(produto)

    return {
        "tiny_id":     tiny_id,
        "nome":        produto.get("nome"),
        "sku":         produto.get("codigo"),
        "preco":       produto.get("preco"),
        "preco_varejo": produto.get("preco"),
        "estoque":     produto.get("estoqueAtual"),
        "peso":        produto.get("peso_bruto") or produto.get("peso_liquido") or produto.get("peso"),
        "comprimento": produto.get("comprimento"),
        "largura":     produto.get("largura"),
        "altura":      produto.get("altura"),
        "categoria":   produto.get("categoria"),
        "ncm":         produto.get("ncm"),
        "descricao":   produto.get("descricao_complementar"),
        "imagem_url":  imagem_url,
    }
