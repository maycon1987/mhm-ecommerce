import os
import requests


def get_tiny_token():
    token = os.getenv("TINY_TOKEN")
    if not token:
        raise Exception("TINY_TOKEN não configurado")
    return token


def buscar_produtos_tiny(pagina: int = None):
    """
    Busca produtos do Tiny.
    Se pagina=None, busca todas as páginas.
    Se pagina=N, busca só aquela página.
    """
    token = get_tiny_token()
    url = "https://api.tiny.com.br/api2/produtos.pesquisa.php"

    todos_produtos = []
    pagina_inicio = pagina if pagina else 1
    pagina_fim = pagina if pagina else None

    p = pagina_inicio
    while True:
        params = {"token": token, "formato": "JSON", "pagina": p}
        response = requests.get(url, params=params, timeout=30)

        if response.status_code != 200:
            break

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
            prod = item.get("produto", {})
            if not isinstance(prod, dict):
                continue

            imagem_url = _extrair_imagem(prod)
            categoria = (prod.get("categoria") or "").strip()

            todos_produtos.append({
                "tiny_id":     prod.get("id"),
                "nome":        prod.get("nome"),
                "sku":         prod.get("codigo"),
                "preco":       prod.get("preco"),
                "preco_varejo": prod.get("preco"),
                "estoque":     prod.get("estoqueAtual"),
                "imagem_url":  imagem_url,
                "categoria":   categoria,
                "peso":        prod.get("peso_bruto") or prod.get("peso"),
                "largura":     prod.get("largura"),
                "altura":      prod.get("altura"),
                "comprimento": prod.get("comprimento"),
            })

        numero_paginas = int(retorno.get("numero_paginas", 1))

        if pagina_fim and p >= pagina_fim:
            break
        if p >= numero_paginas:
            break

        p += 1

    return todos_produtos


def buscar_numero_paginas_tiny():
    """Retorna o número total de páginas do Tiny."""
    token = get_tiny_token()
    url = "https://api.tiny.com.br/api2/produtos.pesquisa.php"
    params = {"token": token, "formato": "JSON", "pagina": 1}
    response = requests.get(url, params=params, timeout=30)
    data = response.json()
    retorno = data.get("retorno", {})
    return int(retorno.get("numero_paginas", 1))


def buscar_categoria_produto(tiny_id: str) -> str:
    """Busca a categoria de um produto específico no Tiny."""
    try:
        detalhe = obter_produto_tiny(tiny_id)
        return (detalhe.get("categoria") or "").strip()
    except Exception:
        return ""


def _extrair_imagem(produto: dict):
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
    params = {"token": token, "id": tiny_id, "formato": "JSON"}
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
